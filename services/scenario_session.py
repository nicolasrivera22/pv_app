from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import uuid4

import pandas as pd

from .config_metadata import update_config_table_values
from .cache import fingerprint_deterministic_input
from .candidate_financials import resolve_financial_best_candidate_key
from .economics_engine import (
    PREVIEW_STATE_CANDIDATE_MISSING,
    PREVIEW_STATE_READY,
    economics_preview_warning_messages,
    resolve_economics_preview,
)
from .economics_tables import (
    compute_economics_runtime_signature,
    normalize_economics_cost_items_frame,
    normalize_economics_price_items_frame,
)
from .scenario_runner import resolve_deterministic_scan
from .types import LoadedConfigBundle, RuntimePriceBridgeRecord, ScenarioRecord, ScenarioSessionState, ValidationIssue
from .validation import refresh_bundle_issues


def _scenario_id() -> str:
    return f"scenario-{uuid4().hex[:8]}"


def create_scenario_record(name: str, bundle: LoadedConfigBundle, source_name: str | None = None) -> ScenarioRecord:
    refreshed_bundle = refresh_bundle_issues(bundle)
    return ScenarioRecord(
        scenario_id=_scenario_id(),
        name=name,
        source_name=source_name or bundle.source_name,
        config_bundle=refreshed_bundle,
        scan_result=None,
        scan_fingerprint=None,
        selected_candidate_key=None,
        dirty=True,
        last_run_at=None,
        runtime_price_bridge=None,
    )


def default_scenario_name(state: ScenarioSessionState, prefix: str = "Scenario") -> str:
    existing = {scenario.name for scenario in state.scenarios}
    index = 1
    while f"{prefix} {index}" in existing:
        index += 1
    return f"{prefix} {index}"


def _replace_scenario(state: ScenarioSessionState, updated: ScenarioRecord) -> ScenarioSessionState:
    scenarios = tuple(updated if item.scenario_id == updated.scenario_id else item for item in state.scenarios)
    return replace(state, scenarios=scenarios)


def _mark_project_dirty(state: ScenarioSessionState, *, dirty: bool = True) -> ScenarioSessionState:
    return replace(state, project_dirty=dirty)


def _normalize_bridge_compare_value(value: object) -> object:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return int(number) if number.is_integer() else round(number, 10)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return ""
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        numeric_text = stripped.replace(",", "")
        try:
            number = float(numeric_text)
        except ValueError:
            return stripped
        return int(number) if number.is_integer() else round(number, 10)
    return value


@dataclass(frozen=True)
class PreparedEconomicsRuntimePriceBridge:
    applied: bool
    candidate_key: str | None
    preview_state: str
    blocker_key: str | None = None
    warning_messages: tuple[str, ...] = ()
    final_price_COP: float | None = None
    economics_signature: str | None = None
    bundle: LoadedConfigBundle | None = None
    bridge_record: RuntimePriceBridgeRecord | None = None

def _normalized_economics_tables(
    scenario: ScenarioRecord,
    *,
    economics_cost_items: pd.DataFrame | list[dict[str, Any]] | None = None,
    economics_price_items: pd.DataFrame | list[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cost_source = scenario.config_bundle.economics_cost_items_table if economics_cost_items is None else economics_cost_items
    price_source = scenario.config_bundle.economics_price_items_table if economics_price_items is None else economics_price_items
    return (
        normalize_economics_cost_items_frame(cost_source),
        normalize_economics_price_items_frame(price_source),
    )


def resolve_runtime_bridge_candidate_key(scenario: ScenarioRecord) -> str | None:
    if scenario.scan_result is not None:
        if scenario.selected_candidate_key in scenario.scan_result.candidate_details:
            return str(scenario.selected_candidate_key)
        if scenario.scan_result.best_candidate_key in scenario.scan_result.candidate_details:
            return str(scenario.scan_result.best_candidate_key)
        return None
    if scenario.selected_candidate_key in (None, ""):
        return None
    return str(scenario.selected_candidate_key)


BRIDGE_RUNTIME_CONFIG_FIELDS = (
    "pricing_mode",
    "price_total_COP",
    "include_hw_in_price",
    "price_others_total",
)


def _bridge_aware_scan_fingerprint(
    bundle: LoadedConfigBundle,
    record: RuntimePriceBridgeRecord | None,
) -> str:
    if record is None or record.stale or not runtime_price_bridge_matches_config(record, bundle.config):
        return fingerprint_deterministic_input(bundle)
    fingerprint_config = {
        key: value
        for key, value in bundle.config.items()
        if key not in BRIDGE_RUNTIME_CONFIG_FIELDS
    }
    return fingerprint_deterministic_input(replace(bundle, config=fingerprint_config))


def runtime_price_bridge_matches_config(record: RuntimePriceBridgeRecord | None, config: dict[str, object]) -> bool:
    if record is None:
        return False
    return all(
        (
            _normalize_bridge_compare_value(config.get("pricing_mode"))
            == _normalize_bridge_compare_value(record.applied_pricing_mode),
            _normalize_bridge_compare_value(config.get("price_total_COP"))
            == _normalize_bridge_compare_value(record.applied_price_total_COP),
            _normalize_bridge_compare_value(config.get("include_hw_in_price"))
            == _normalize_bridge_compare_value(record.applied_include_hw_in_price),
            _normalize_bridge_compare_value(config.get("price_others_total"))
            == _normalize_bridge_compare_value(record.applied_price_others_total),
        )
    )


def runtime_price_bridge_matches_scenario(record: RuntimePriceBridgeRecord | None, scenario: ScenarioRecord) -> bool:
    if not runtime_price_bridge_matches_config(record, scenario.config_bundle.config):
        return False
    current_candidate_key = resolve_runtime_bridge_candidate_key(scenario)
    current_economics_signature = compute_economics_runtime_signature(
        scenario.config_bundle.economics_cost_items_table,
        scenario.config_bundle.economics_price_items_table,
    )
    return all(
        (
            _normalize_bridge_compare_value(record.candidate_key)
            == _normalize_bridge_compare_value(current_candidate_key),
            _normalize_bridge_compare_value(record.applied_scan_fingerprint)
            == _normalize_bridge_compare_value(scenario.scan_fingerprint),
            _normalize_bridge_compare_value(record.applied_economics_signature)
            == _normalize_bridge_compare_value(current_economics_signature),
        )
    )


def invalidate_runtime_price_bridge_if_needed(
    record: RuntimePriceBridgeRecord | None,
    scenario: ScenarioRecord,
) -> RuntimePriceBridgeRecord | None:
    if record is None or record.stale:
        return record
    if runtime_price_bridge_matches_scenario(record, scenario):
        return record
    return replace(record, stale=True)


def resolve_runtime_price_bridge_state(scenario: ScenarioRecord) -> str:
    record = scenario.runtime_price_bridge
    if record is None:
        return "none"
    if record.stale or not runtime_price_bridge_matches_scenario(record, scenario):
        return "stale"
    return "active"


def build_runtime_price_bridge_record(
    *,
    candidate_key: str,
    final_price_COP: float,
    resolved_preview_state: str,
    applied_scan_fingerprint: str | None = None,
    applied_economics_signature: str | None = None,
    applied_at: str | None = None,
) -> RuntimePriceBridgeRecord:
    resolved_total = float(final_price_COP)
    return RuntimePriceBridgeRecord(
        source="economics_preview",
        candidate_key=str(candidate_key),
        final_price_COP=resolved_total,
        resolved_preview_state=str(resolved_preview_state),
        applied_at=applied_at or datetime.now().isoformat(timespec="seconds"),
        applied_pricing_mode="total",
        applied_price_total_COP=resolved_total,
        applied_include_hw_in_price=False,
        applied_price_others_total=0.0,
        applied_scan_fingerprint=applied_scan_fingerprint,
        applied_economics_signature=applied_economics_signature,
        stale=False,
    )


def prepare_economics_runtime_price_bridge(
    scenario: ScenarioRecord,
    *,
    candidate_key: str | None = None,
    economics_cost_items: pd.DataFrame | list[dict[str, Any]] | None = None,
    economics_price_items: pd.DataFrame | list[dict[str, Any]] | None = None,
    applied_at: str | None = None,
) -> PreparedEconomicsRuntimePriceBridge:
    normalized_cost_items, normalized_price_items = _normalized_economics_tables(
        scenario,
        economics_cost_items=economics_cost_items,
        economics_price_items=economics_price_items,
    )
    economics_signature = compute_economics_runtime_signature(normalized_cost_items, normalized_price_items)

    if scenario.scan_result is None:
        return PreparedEconomicsRuntimePriceBridge(
            applied=False,
            candidate_key=resolve_runtime_bridge_candidate_key(scenario),
            preview_state="no_scan",
            blocker_key="preview_state:no_scan",
            economics_signature=economics_signature,
        )

    resolved_candidate_key: str | None
    if candidate_key not in (None, ""):
        explicit_candidate_key = str(candidate_key)
        if explicit_candidate_key not in scenario.scan_result.candidate_details:
            return PreparedEconomicsRuntimePriceBridge(
                applied=False,
                candidate_key=explicit_candidate_key,
                preview_state=PREVIEW_STATE_CANDIDATE_MISSING,
                blocker_key=f"preview_state:{PREVIEW_STATE_CANDIDATE_MISSING}",
                economics_signature=economics_signature,
            )
        resolved_candidate_key = explicit_candidate_key
    else:
        resolved_candidate_key = resolve_runtime_bridge_candidate_key(scenario)

    preview = resolve_economics_preview(
        scenario,
        economics_cost_items=normalized_cost_items,
        economics_price_items=normalized_price_items,
        candidate_key=resolved_candidate_key,
        allow_best_fallback=False,
        candidate_source="selected" if resolved_candidate_key is not None else None,
    )
    warning_messages = economics_preview_warning_messages(preview)
    final_price_COP = None if preview.result is None else float(preview.result.final_price_COP)

    if preview.state != PREVIEW_STATE_READY or preview.result is None:
        return PreparedEconomicsRuntimePriceBridge(
            applied=False,
            candidate_key=preview.candidate_key or resolved_candidate_key,
            preview_state=preview.state,
            blocker_key=f"preview_state:{preview.state}",
            warning_messages=warning_messages,
            final_price_COP=final_price_COP,
            economics_signature=economics_signature,
        )
    if warning_messages:
        return PreparedEconomicsRuntimePriceBridge(
            applied=False,
            candidate_key=preview.candidate_key or resolved_candidate_key,
            preview_state=preview.state,
            blocker_key="warnings",
            warning_messages=warning_messages,
            final_price_COP=final_price_COP,
            economics_signature=economics_signature,
        )

    next_config = dict(scenario.config_bundle.config)
    next_config.update(
        {
            "pricing_mode": "total",
            "price_total_COP": final_price_COP,
            "include_hw_in_price": False,
            "price_others_total": 0.0,
        }
    )
    prepared_bundle = replace(
        scenario.config_bundle,
        config=next_config,
        config_table=update_config_table_values(scenario.config_bundle.config_table, next_config),
        economics_cost_items_table=normalized_cost_items,
        economics_price_items_table=normalized_price_items,
    )
    bridge_record = build_runtime_price_bridge_record(
        candidate_key=preview.candidate_key or resolved_candidate_key or preview.result.quantities.candidate_key,
        final_price_COP=final_price_COP,
        resolved_preview_state=preview.state,
        applied_scan_fingerprint=scenario.scan_fingerprint,
        applied_economics_signature=economics_signature,
        applied_at=applied_at,
    )
    return PreparedEconomicsRuntimePriceBridge(
        applied=True,
        candidate_key=bridge_record.candidate_key,
        preview_state=preview.state,
        warning_messages=warning_messages,
        final_price_COP=final_price_COP,
        economics_signature=economics_signature,
        bundle=prepared_bundle,
        bridge_record=bridge_record,
    )


def apply_prepared_economics_runtime_price_bridge(
    state: ScenarioSessionState,
    scenario_id: str,
    prepared: PreparedEconomicsRuntimePriceBridge,
    *,
    mark_project_dirty: bool,
) -> ScenarioSessionState:
    if not prepared.applied or prepared.bundle is None or prepared.bridge_record is None:
        return state
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")

    refreshed_bundle = refresh_bundle_issues(prepared.bundle)
    final_economics_signature = compute_economics_runtime_signature(
        refreshed_bundle.economics_cost_items_table,
        refreshed_bundle.economics_price_items_table,
    )
    final_bridge_record = replace(
        prepared.bridge_record,
        applied_economics_signature=final_economics_signature,
        stale=False,
    )
    updated = replace(
        scenario,
        config_bundle=refreshed_bundle,
        source_name=refreshed_bundle.source_name,
        runtime_price_bridge=final_bridge_record,
    )
    next_state = _replace_scenario(state, updated)
    if mark_project_dirty:
        next_state = _mark_project_dirty(next_state, dirty=True)
    return next_state


def sync_selected_candidate_runtime_price(
    state: ScenarioSessionState,
    scenario_id: str,
) -> tuple[ScenarioSessionState, PreparedEconomicsRuntimePriceBridge]:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    prepared = prepare_economics_runtime_price_bridge(scenario)
    if prepared.applied:
        return (
            apply_prepared_economics_runtime_price_bridge(
                state,
                scenario_id,
                prepared,
                mark_project_dirty=False,
            ),
            prepared,
        )

    stale_record = invalidate_runtime_price_bridge_if_needed(scenario.runtime_price_bridge, scenario)
    if stale_record is scenario.runtime_price_bridge:
        return state, prepared
    return _replace_scenario(state, replace(scenario, runtime_price_bridge=stale_record)), prepared


def select_candidate_and_sync_runtime_price(
    state: ScenarioSessionState,
    scenario_id: str,
    candidate_key: str | None,
) -> tuple[ScenarioSessionState, PreparedEconomicsRuntimePriceBridge]:
    next_state = update_selected_candidate(state, scenario_id, candidate_key)
    return sync_selected_candidate_runtime_price(next_state, scenario_id)


def _sanitize_design_comparison_keys(
    state: ScenarioSessionState,
    scenario_id: str,
    valid_candidate_keys: set[str] | None,
) -> dict[str, tuple[str, ...]]:
    selections = dict(state.design_comparison_candidate_keys)
    if scenario_id not in selections:
        return selections
    if valid_candidate_keys is None:
        return selections
    cleaned: list[str] = []
    seen: set[str] = set()
    for candidate_key in selections.get(scenario_id, ()):
        if candidate_key in valid_candidate_keys and candidate_key not in seen:
            cleaned.append(candidate_key)
            seen.add(candidate_key)
        if len(cleaned) >= 10:
            break
    selections[scenario_id] = tuple(cleaned)
    return selections


def add_scenario(state: ScenarioSessionState, scenario: ScenarioRecord, make_active: bool = True) -> ScenarioSessionState:
    active_id = scenario.scenario_id if make_active else state.active_scenario_id
    return replace(state, scenarios=(*state.scenarios, scenario), active_scenario_id=active_id, project_dirty=True)


def duplicate_scenario(state: ScenarioSessionState, scenario_id: str, new_name: str | None = None) -> ScenarioSessionState:
    source = state.get_scenario(scenario_id)
    if source is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")

    copied = ScenarioRecord(
        scenario_id=_scenario_id(),
        name=new_name or default_scenario_name(state, prefix=f"{source.name} copy"),
        source_name=source.source_name,
        config_bundle=refresh_bundle_issues(replace(source.config_bundle)),
        scan_result=None if source.scan_result is None else replace(source.scan_result),
        scan_fingerprint=source.scan_fingerprint,
        selected_candidate_key=source.selected_candidate_key,
        dirty=source.dirty,
        last_run_at=source.last_run_at,
        runtime_price_bridge=source.runtime_price_bridge,
    )
    return add_scenario(state, copied, make_active=True)


def rename_scenario(state: ScenarioSessionState, scenario_id: str, new_name: str) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    return _mark_project_dirty(_replace_scenario(state, replace(scenario, name=new_name.strip() or scenario.name)))


def delete_scenario(state: ScenarioSessionState, scenario_id: str) -> ScenarioSessionState:
    remaining = tuple(item for item in state.scenarios if item.scenario_id != scenario_id)
    comparison = tuple(item for item in state.comparison_scenario_ids if item != scenario_id)
    design_compare = dict(state.design_comparison_candidate_keys)
    design_compare.pop(scenario_id, None)
    active_id = state.active_scenario_id
    if active_id == scenario_id:
        active_id = remaining[0].scenario_id if remaining else None
    return replace(
        state,
        scenarios=remaining,
        active_scenario_id=active_id,
        comparison_scenario_ids=comparison,
        design_comparison_candidate_keys=design_compare,
        project_dirty=True,
    )


def set_active_scenario(state: ScenarioSessionState, scenario_id: str | None) -> ScenarioSessionState:
    if scenario_id is None:
        return replace(state, active_scenario_id=None, project_dirty=True)
    if state.get_scenario(scenario_id) is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    return replace(state, active_scenario_id=scenario_id, project_dirty=True)


def set_comparison_scenarios(state: ScenarioSessionState, scenario_ids: list[str] | tuple[str, ...]) -> ScenarioSessionState:
    valid_ids = {scenario.scenario_id for scenario in state.scenarios if not scenario.dirty}
    selected = tuple(item for item in scenario_ids if item in valid_ids)
    return replace(state, comparison_scenario_ids=selected, project_dirty=True)


def set_design_comparison_candidates(
    state: ScenarioSessionState,
    scenario_id: str,
    candidate_keys: list[str] | tuple[str, ...],
) -> ScenarioSessionState:
    if state.get_scenario(scenario_id) is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    selections = dict(state.design_comparison_candidate_keys)
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate_key in candidate_keys:
        key = str(candidate_key)
        if key not in seen:
            deduped.append(key)
            seen.add(key)
        if len(deduped) >= 10:
            break
    selections[scenario_id] = tuple(deduped)
    return replace(state, design_comparison_candidate_keys=selections, project_dirty=True)


def update_scenario_bundle(state: ScenarioSessionState, scenario_id: str, bundle: LoadedConfigBundle) -> ScenarioSessionState:
    scenario: ScenarioRecord | None = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    preserve_scan = False
    next_fingerprint: str | None = None
    if scenario.scan_result is not None and not scenario.dirty:
        next_fingerprint = _bridge_aware_scan_fingerprint(bundle, scenario.runtime_price_bridge)
        current_fingerprint = _bridge_aware_scan_fingerprint(scenario.config_bundle, scenario.runtime_price_bridge)
        preserve_scan = next_fingerprint == current_fingerprint
    persisted_extra_issues: list[ValidationIssue] = []
    if preserve_scan and scenario.scan_result is not None:
        if scenario.selected_candidate_key in scenario.scan_result.candidate_details:
            selected_candidate_key = scenario.selected_candidate_key
        else:
            selected_candidate_key = scenario.scan_result.best_candidate_key
        preview = resolve_economics_preview(
            replace(
                scenario,
                config_bundle=bundle,
                scan_result=scenario.scan_result,
                scan_fingerprint=scenario.scan_fingerprint,
                selected_candidate_key=selected_candidate_key,
                dirty=False,
            ),
            economics_cost_items=bundle.economics_cost_items_table,
            economics_price_items=bundle.economics_price_items_table,
        )
        persisted_extra_issues = [
            ValidationIssue("warning", "economics_cost_items", message)
            for message in economics_preview_warning_messages(preview)
        ]
    refreshed_bundle = refresh_bundle_issues(bundle, extra_issues=tuple(persisted_extra_issues))
    if preserve_scan and scenario.scan_result is not None:
        updated = replace(
            scenario,
            config_bundle=refreshed_bundle,
            source_name=refreshed_bundle.source_name,
            scan_result=scenario.scan_result,
            scan_fingerprint=scenario.scan_fingerprint,
            selected_candidate_key=selected_candidate_key,
            dirty=False,
        )
    else:
        updated = replace(
            scenario,
            config_bundle=refreshed_bundle,
            source_name=refreshed_bundle.source_name,
            scan_result=None,
            scan_fingerprint=None,
            selected_candidate_key=None,
            dirty=True,
            last_run_at=None,
        )
    updated = replace(
        updated,
        runtime_price_bridge=invalidate_runtime_price_bridge_if_needed(scenario.runtime_price_bridge, updated),
    )
    return _mark_project_dirty(_replace_scenario(state, updated))


def update_scenario_risk_config(
    state: ScenarioSessionState,
    scenario_id: str,
    config_updates: dict[str, object],
) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    if not config_updates:
        return state

    updated_config = dict(scenario.config_bundle.config)
    changed = False
    for field, value in config_updates.items():
        if updated_config.get(field) != value:
            updated_config[field] = value
            changed = True
    if not changed:
        return state

    updated_bundle = replace(
        scenario.config_bundle,
        config=updated_config,
        config_table=update_config_table_values(scenario.config_bundle.config_table, updated_config),
    )
    updated_fingerprint = (
        fingerprint_deterministic_input(updated_bundle)
        if scenario.scan_result is not None and not scenario.dirty
        else scenario.scan_fingerprint
    )
    updated = replace(
        scenario,
        config_bundle=updated_bundle,
        source_name=updated_bundle.source_name,
        scan_fingerprint=updated_fingerprint,
    )
    updated = replace(
        updated,
        runtime_price_bridge=invalidate_runtime_price_bridge_if_needed(scenario.runtime_price_bridge, updated),
    )
    return _mark_project_dirty(_replace_scenario(state, updated))


def _apply_scan_result(
    state: ScenarioSessionState,
    scenario_id: str,
    *,
    preserve_selection: bool,
    auto_bridge: bool,
) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    scan_result = resolve_deterministic_scan(scenario.config_bundle)
    provisional_updated = replace(
        scenario,
        scan_result=scan_result,
        dirty=False,
    )
    if preserve_selection and scenario.selected_candidate_key in scan_result.candidate_details:
        selected_candidate_key = scenario.selected_candidate_key
    else:
        selected_candidate_key = resolve_financial_best_candidate_key(provisional_updated) or scan_result.best_candidate_key
    preview = resolve_economics_preview(
        replace(
            scenario,
            scan_result=scan_result,
            selected_candidate_key=selected_candidate_key,
            dirty=False,
        ),
        economics_cost_items=scenario.config_bundle.economics_cost_items_table,
        economics_price_items=scenario.config_bundle.economics_price_items_table,
    )
    refreshed_bundle = refresh_bundle_issues(
        scenario.config_bundle,
        extra_issues=tuple(
            ValidationIssue("warning", "economics_cost_items", message)
            for message in economics_preview_warning_messages(preview)
        ),
    )
    updated = replace(
        scenario,
        config_bundle=refreshed_bundle,
        scan_result=scan_result,
        scan_fingerprint=fingerprint_deterministic_input(refreshed_bundle),
        selected_candidate_key=selected_candidate_key,
        dirty=False,
        last_run_at=datetime.now().isoformat(timespec="seconds"),
    )
    next_state = _replace_scenario(state, updated)
    selections = _sanitize_design_comparison_keys(next_state, scenario_id, set(scan_result.candidate_details))
    next_state = replace(next_state, design_comparison_candidate_keys=selections)
    if not auto_bridge:
        return next_state
    synced_state, _prepared = sync_selected_candidate_runtime_price(next_state, scenario_id)
    return synced_state


def run_scenario_scan(state: ScenarioSessionState, scenario_id: str) -> ScenarioSessionState:
    return _apply_scan_result(state, scenario_id, preserve_selection=False, auto_bridge=False)


def hydrate_scenario_scan(state: ScenarioSessionState, scenario_id: str) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None or scenario.dirty or scenario.scan_result is not None:
        return state
    return _apply_scan_result(state, scenario_id, preserve_selection=True, auto_bridge=False)


def update_selected_candidate(state: ScenarioSessionState, scenario_id: str, candidate_key: str | None) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    if scenario.scan_result is None:
        return state
    selected = candidate_key if candidate_key in scenario.scan_result.candidate_details else scenario.scan_result.best_candidate_key
    if selected == scenario.selected_candidate_key:
        return state
    updated = replace(scenario, selected_candidate_key=selected)
    updated = replace(
        updated,
        runtime_price_bridge=invalidate_runtime_price_bridge_if_needed(scenario.runtime_price_bridge, updated),
    )
    return _mark_project_dirty(_replace_scenario(state, updated))
