from __future__ import annotations
import json
import shutil
from dataclasses import replace
from pathlib import Path

from .config_metadata import materialize_panel_config_rows
from .io_excel import TABLE_FILE_MAP, load_bundle_from_tables
from .runtime_paths import legacy_packaged_root, project_exports_root, project_inputs_root, project_root, projects_root
from .scenario_session import create_scenario_record
from .types import LoadedConfigBundle, ProjectManifest, ProjectScenarioManifest, ScenarioRecord, ScenarioSessionState

PROJECT_FORMAT_VERSION = 1


def _slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return collapsed or "proyecto"


def _manifest_path(slug: str) -> Path:
    return project_root(slug) / "project.json"


def _read_manifest(path: Path) -> ProjectManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ProjectManifest.from_payload(payload)


def _current_manifest_path(slug: str) -> Path:
    return (projects_root() / slug / "project.json").resolve()


def _legacy_manifest_path(slug: str) -> Path | None:
    legacy_root = legacy_packaged_root()
    if legacy_root is None:
        return None
    return (legacy_root / "proyectos" / slug / "project.json").resolve()


def _resolve_manifest_path_for_open(slug: str) -> Path:
    current = _current_manifest_path(slug)
    legacy = _legacy_manifest_path(slug)
    if current.exists():
        return current
    if legacy is not None and legacy.exists():
        return legacy
    return current


def _scenario_input_root(slug: str, scenario_id: str) -> Path:
    root = project_inputs_root(slug) / scenario_id
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def load_project_bundle_from_tables(path: str | Path, *, source_name: str = "project") -> LoadedConfigBundle:
    return load_bundle_from_tables(path, source_name=source_name)


def _write_table_inputs(root: Path, scenario: ScenarioRecord) -> None:
    bundle = scenario.config_bundle
    tables = {
        "Config": materialize_panel_config_rows(bundle.config_table, bundle.config, bundle.panel_catalog),
        "Demand_Profile": bundle.demand_profile_table,
        "Demand_Profile_General": bundle.demand_profile_general_table,
        "Demand_Profile_Weights": bundle.demand_profile_weights_table,
        "Month_Demand_Profile": bundle.month_profile_table,
        "SUN_HSP_PROFILE": bundle.sun_profile_table,
        "Precios_kWp_relativos": bundle.cop_kwp_table,
        "Precios_kWp_relativos_Otros": bundle.cop_kwp_table_others,
        "Inversor_Catalog": bundle.inverter_catalog,
        "Battery_Catalog": bundle.battery_catalog,
        "Panel_Catalog": bundle.panel_catalog,
        "Economics_Cost_Items": bundle.economics_cost_items_table,
        "Economics_Price_Items": bundle.economics_price_items_table,
    }
    for table_name, frame in tables.items():
        frame.to_csv(root / TABLE_FILE_MAP[table_name], index=False)


def _build_manifest(state: ScenarioSessionState, *, project_name: str, slug: str, language: str) -> ProjectManifest:
    scenarios = tuple(
        ProjectScenarioManifest(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            source_name=scenario.source_name,
            selected_candidate_key=scenario.selected_candidate_key,
            dirty=scenario.dirty,
            last_run_at=scenario.last_run_at,
            scan_fingerprint=scenario.scan_fingerprint,
        )
        for scenario in state.scenarios
    )
    return ProjectManifest(
        format_version=PROJECT_FORMAT_VERSION,
        name=project_name,
        slug=slug,
        active_scenario_id=state.active_scenario_id,
        comparison_scenario_ids=state.comparison_scenario_ids,
        design_comparison_candidate_keys=state.design_comparison_candidate_keys,
        scenarios=scenarios,
        ui_prefs={"language": language},
    )


def _write_manifest(manifest: ProjectManifest) -> None:
    _manifest_path(manifest.slug).write_text(
        json.dumps(manifest.to_payload(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_project(
    state: ScenarioSessionState,
    *,
    project_name: str | None = None,
    slug: str | None = None,
    language: str = "es",
) -> ScenarioSessionState:
    resolved_name = (project_name or state.project_name or state.project_slug or "Proyecto").strip() or "Proyecto"
    resolved_slug = _slugify(slug or state.project_slug or resolved_name)
    project_root(resolved_slug)
    project_exports_root(resolved_slug)
    for scenario in state.scenarios:
        _write_table_inputs(_scenario_input_root(resolved_slug, scenario.scenario_id), scenario)
    manifest = _build_manifest(state, project_name=resolved_name, slug=resolved_slug, language=language)
    _write_manifest(manifest)
    return replace(state, project_slug=resolved_slug, project_name=resolved_name, project_dirty=False)


def save_project_as(
    state: ScenarioSessionState,
    *,
    project_name: str,
    language: str = "es",
) -> ScenarioSessionState:
    return save_project(state, project_name=project_name, slug=_slugify(project_name), language=language)


def delete_project(slug: str) -> str:
    manifest_path = _resolve_manifest_path_for_open(slug)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Project '{slug}' not found.")
    manifest = _read_manifest(manifest_path)
    shutil.rmtree(manifest_path.parent)
    return manifest.name


def read_project_manifest(slug: str) -> ProjectManifest:
    return _read_manifest(_manifest_path(slug))


def open_project(slug: str) -> ScenarioSessionState:
    manifest_path = _resolve_manifest_path_for_open(slug)
    manifest = _read_manifest(manifest_path)
    manifest_path = _resolve_manifest_path_for_open(slug)
    manifest = _read_manifest(manifest_path)
    scenarios: list[ScenarioRecord] = []
    project_base = manifest_path.parent
    for item in manifest.scenarios:
        table_root = project_base / "inputs" / item.scenario_id
        bundle = load_project_bundle_from_tables(table_root, source_name=item.source_name)
        record = create_scenario_record(item.name, bundle, source_name=item.source_name)
        scenarios.append(
            replace(
                record,
                scenario_id=item.scenario_id,
                selected_candidate_key=item.selected_candidate_key,
                dirty=item.dirty,
                last_run_at=item.last_run_at,
                scan_fingerprint=item.scan_fingerprint,
            )
        )
    scenario_ids = {scenario.scenario_id for scenario in scenarios}
    active_scenario_id = manifest.active_scenario_id if manifest.active_scenario_id in scenario_ids else (scenarios[0].scenario_id if scenarios else None)
    comparison_ids = tuple(scenario_id for scenario_id in manifest.comparison_scenario_ids if scenario_id in scenario_ids)
    design_keys = {
        scenario_id: tuple(candidate_keys)
        for scenario_id, candidate_keys in manifest.design_comparison_candidate_keys.items()
        if scenario_id in scenario_ids
    }
    return ScenarioSessionState(
        scenarios=tuple(scenarios),
        active_scenario_id=active_scenario_id,
        comparison_scenario_ids=comparison_ids,
        design_comparison_candidate_keys=design_keys,
        project_slug=manifest.slug,
        project_name=manifest.name,
        project_dirty=False,
    )


def list_projects() -> list[ProjectManifest]:
    manifests: list[ProjectManifest] = []
    for path in sorted(projects_root().glob("*/project.json")):
        try:
            manifests.append(ProjectManifest.from_payload(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    return sorted(manifests, key=lambda item: item.name.lower())
