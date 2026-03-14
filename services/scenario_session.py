from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

from .scenario_runner import run_scan
from .types import LoadedConfigBundle, ScenarioRecord, ScenarioSessionState
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
        selected_candidate_key=None,
        dirty=True,
        last_run_at=None,
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
    return replace(state, scenarios=(*state.scenarios, scenario), active_scenario_id=active_id)


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
        selected_candidate_key=source.selected_candidate_key,
        dirty=source.dirty,
        last_run_at=source.last_run_at,
    )
    return add_scenario(state, copied, make_active=True)


def rename_scenario(state: ScenarioSessionState, scenario_id: str, new_name: str) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    return _replace_scenario(state, replace(scenario, name=new_name.strip() or scenario.name))


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
    )


def set_active_scenario(state: ScenarioSessionState, scenario_id: str | None) -> ScenarioSessionState:
    if scenario_id is None:
        return replace(state, active_scenario_id=None)
    if state.get_scenario(scenario_id) is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    return replace(state, active_scenario_id=scenario_id)


def set_comparison_scenarios(state: ScenarioSessionState, scenario_ids: list[str] | tuple[str, ...]) -> ScenarioSessionState:
    valid_ids = {scenario.scenario_id for scenario in state.scenarios if scenario.scan_result is not None and not scenario.dirty}
    selected = tuple(item for item in scenario_ids if item in valid_ids)
    return replace(state, comparison_scenario_ids=selected)


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
    return replace(state, design_comparison_candidate_keys=selections)


def update_scenario_bundle(state: ScenarioSessionState, scenario_id: str, bundle: LoadedConfigBundle) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    refreshed_bundle = refresh_bundle_issues(bundle)
    updated = replace(
        scenario,
        config_bundle=refreshed_bundle,
        source_name=refreshed_bundle.source_name,
        scan_result=None,
        selected_candidate_key=None,
        dirty=True,
        last_run_at=None,
    )
    return _replace_scenario(state, updated)


def run_scenario_scan(state: ScenarioSessionState, scenario_id: str) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")

    scan_result = run_scan(scenario.config_bundle)
    updated = replace(
        scenario,
        scan_result=scan_result,
        selected_candidate_key=scan_result.best_candidate_key,
        dirty=False,
        last_run_at=datetime.now().isoformat(timespec="seconds"),
    )
    next_state = _replace_scenario(state, updated)
    selections = _sanitize_design_comparison_keys(next_state, scenario_id, set(scan_result.candidate_details))
    return replace(next_state, design_comparison_candidate_keys=selections)


def update_selected_candidate(state: ScenarioSessionState, scenario_id: str, candidate_key: str | None) -> ScenarioSessionState:
    scenario = state.get_scenario(scenario_id)
    if scenario is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    if scenario.scan_result is None:
        return state
    selected = candidate_key if candidate_key in scenario.scan_result.candidate_details else scenario.scan_result.best_candidate_key
    return _replace_scenario(state, replace(scenario, selected_candidate_key=selected))
