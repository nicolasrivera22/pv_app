from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dash import dcc
import pandas as pd

from app import create_app
from components.risk_controls import risk_controls_section
from components.scenario_controls import scenario_sidebar
from components.risk_charts import build_histogram_figure
from services import (
    ScenarioSessionState,
    add_scenario,
    build_assumption_sections,
    build_display_columns,
    create_scenario_record,
    export_deterministic_artifacts,
    export_risk_artifacts,
    extract_config_metadata,
    format_metric,
    legacy_deterministic_export_manifest,
    legacy_risk_export_manifest,
    load_config_from_excel,
    load_example_config,
    rebuild_bundle_from_ui,
    run_monte_carlo,
    run_scenario_scan,
    tr,
)
from services.ui_schema import field_help, field_label, metric_label
from services.workbench_ui import demand_profile_visibility, frame_from_rows


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
        "mc_n_simulations": 8,
    }
    return replace(bundle, config=config)


def _find_component(node, component_id: str):
    if getattr(node, "id", None) == component_id:
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    return _find_component(children, component_id)


def test_app_defaults_to_spanish() -> None:
    app = create_app()
    selector = _find_component(app.layout, "language-selector")
    assert isinstance(selector, dcc.Dropdown)
    assert selector.value == "es"


def test_first_render_placeholders_are_spanish_first() -> None:
    sidebar = scenario_sidebar()
    scenario_dropdown = _find_component(sidebar, "scenario-dropdown")
    rename_input = _find_component(sidebar, "rename-scenario-input")
    risk_controls = risk_controls_section()
    risk_scenario_dropdown = _find_component(risk_controls, "risk-scenario-dropdown")
    risk_candidate_dropdown = _find_component(risk_controls, "risk-candidate-dropdown")

    assert scenario_dropdown.placeholder == "No hay escenarios cargados"
    assert rename_input.placeholder == "Nombre del escenario"
    assert risk_scenario_dropdown.placeholder == "Selecciona un escenario completado"
    assert risk_candidate_dropdown.placeholder == "Selecciona un candidato factible"


def test_translation_helper_prefers_spanish_fallback_for_workbench_labels() -> None:
    assert tr("workbench.sidebar.title", "es") == "Escenarios"
    assert tr("workbench.run_scan", "fr") == "Ejecutar escaneo determinístico"
    assert tr("nav.compare", "fr") == "Comparar"
    assert tr("risk.placeholder.scenario", "fr") == "Selecciona un escenario completado"


def test_extract_config_metadata_preserves_workbook_order_and_groups() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))
    metadata = extract_config_metadata(bundle.config_table, bundle.config)

    assert metadata[0].group == "Demanda y Perfil"
    assert metadata[0].item == "E_month_kWh"
    assert any(meta.item == "coupling" and meta.config_key == "bat_coupling" for meta in metadata)
    assert any(meta.group == "Precios" for meta in metadata)


def test_assumption_sections_group_and_fallback_help() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))
    sections = build_assumption_sections(bundle, lang="es", show_all=False)

    groups = [section["group"] for section in sections]
    assert "Demanda y Perfil" in groups
    assert "Economía" in groups

    meta = next(meta for meta in extract_config_metadata(bundle.config_table, bundle.config) if meta.item == "E_month_kWh")
    section = next(section for section in sections if section["group"] == "Demanda y Perfil")
    field = next(field for field in section["basic"] if field["field"] == "E_month_kWh")

    assert field["label"] == field_label(meta, "es")
    assert field["help"] == field_help(meta, "es")
    assert section["help"]


def test_display_schema_formats_metrics_and_labels() -> None:
    assert format_metric("NPV_COP", 12500000, "es") == "COP 12,500,000"
    assert format_metric("self_consumption_ratio", 0.456, "es") == "45.6%"
    assert format_metric("payback_years", 7.25, "en") == "7.25 years"
    assert format_metric("selected_battery", "None", "es") == "Sin batería"
    columns, tooltips = build_display_columns(["kWp", "NPV_COP", "self_consumption_ratio"], "es")
    assert [column["name"] for column in columns] == ["kWp", "VPN [COP]", "Autoconsumo [%]"]
    assert tooltips["NPV_COP"].startswith("Valor presente")
    assert metric_label("annual_import_kwh", "es") == "Importación anual [kWh]"


def test_profile_visibility_and_bundle_rebuild_round_trip() -> None:
    bundle = _fast_bundle()
    visibility = demand_profile_visibility("perfil horario relativo")
    assert visibility["demand-profile-weights-panel"]["display"] == "block"
    assert visibility["demand-profile-panel"]["display"] == "none"

    edited_month = bundle.month_profile_table.copy()
    edited_month.loc[0, "Demand_month"] = 1.15
    rebuilt = rebuild_bundle_from_ui(
        bundle,
        config_updates=dict(bundle.config),
        inverter_catalog=bundle.inverter_catalog,
        battery_catalog=bundle.battery_catalog,
        demand_profile=frame_from_rows(bundle.demand_profile_table.to_dict("records"), list(bundle.demand_profile_table.columns)),
        demand_profile_weights=frame_from_rows(bundle.demand_profile_weights_table.to_dict("records"), list(bundle.demand_profile_weights_table.columns)),
        demand_profile_general=frame_from_rows(bundle.demand_profile_general_table.to_dict("records"), list(bundle.demand_profile_general_table.columns)),
        month_profile=edited_month,
        sun_profile=bundle.sun_profile_table,
        cop_kwp_table=bundle.cop_kwp_table,
        cop_kwp_table_others=bundle.cop_kwp_table_others,
    )

    assert float(rebuilt.month_profile_table.loc[0, "Demand_month"]) == 1.15
    assert float(rebuilt.demand_month_factor[0]) == 1.15


def test_artifact_exports_write_into_resultados_without_deleting_existing_files(tmp_path) -> None:
    base_dir = tmp_path / "Resultados"
    keep_file = base_dir / "keep.txt"
    base_dir.mkdir(parents=True, exist_ok=True)
    keep_file.write_text("keep", encoding="utf-8")

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()

    deterministic_paths = export_deterministic_artifacts(scenario, output_root=base_dir)
    assert keep_file.exists()
    assert deterministic_paths
    assert any(path.suffix == ".png" for path in deterministic_paths)
    assert {path.name for path in deterministic_paths}.issuperset({"chart_npv_vs_kWp.png", "resumen_valor_presente_neto.csv", "resumen_optimizacion.txt"})
    scenario_root = next(path for path in deterministic_paths if path.name == "chart_npv_vs_kWp.png").parent
    assert set(legacy_deterministic_export_manifest()).issubset({path.name for path in scenario_root.iterdir()})
    assert any(path.name == "candidatos_factibles.csv" for path in deterministic_paths)

    candidate_key = scenario.selected_candidate_key or scenario.scan_result.best_candidate_key
    risk_result = run_monte_carlo(
        scenario.config_bundle,
        selected_candidate_key=candidate_key,
        seed=0,
        n_simulations=6,
        return_samples=False,
        baseline_scan=scenario.scan_result,
    )
    risk_paths = export_risk_artifacts(scenario, risk_result, output_root=base_dir)
    assert {path.name for path in risk_paths}.issuperset(set(legacy_risk_export_manifest()))
    assert any(path.name == "histograma_payback.png" for path in risk_paths)
    assert any(path.name == "riesgo_percentiles.csv" for path in risk_paths)
    assert keep_file.exists()


def test_payback_histogram_highlight_band_is_rendered() -> None:
    frame = pd.DataFrame(
        {
            "bin_left": [1.0, 2.0, 3.0],
            "bin_right": [2.0, 3.0, 4.0],
            "count": [2, 3, 1],
            "probability": [0.2, 0.5, 0.3],
        }
    )
    figure = build_histogram_figure(
        frame,
        title="Histograma",
        x_title="Payback [años]",
        lang="es",
        highlight_range=(1.5, 3.5),
        density_frame=pd.DataFrame({"value": [1.0, 2.0, 3.0], "density": [0.1, 0.2, 0.1]}),
    )
    assert len(figure.layout.shapes or []) == 1
    assert len(figure.data) == 2
