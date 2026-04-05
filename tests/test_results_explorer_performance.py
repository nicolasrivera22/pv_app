from __future__ import annotations

import sys
import types
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pandas.testing as pdt
import pytest

if "dash_cytoscape" not in sys.modules:
    stub = types.ModuleType("dash_cytoscape")

    class Cytoscape:
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.children = kwargs.get("children")
            self.id = kwargs.get("id")

    stub.Cytoscape = Cytoscape
    sys.modules["dash_cytoscape"] = stub

import services.results_explorer_dataset as explorer_dataset
import services.workspace_results_callbacks as results_callbacks
from components.candidate_explorer import candidate_explorer_section
from services.candidate_financials import get_candidate_financial_snapshot_cache
from services import (
    ResultsExplorerDataset,
    ResultsExplorerDatasetCache,
    ScenarioSessionState,
    add_scenario,
    bootstrap_client_session,
    build_results_explorer_dataset,
    build_results_explorer_horizon_table,
    commit_client_session,
    create_scenario_record,
    get_results_explorer_dataset_cache,
    load_example_config,
    run_scenario_scan,
    update_scenario_bundle,
)


def _fast_bundle():
    bundle = load_example_config()
    return replace(
        bundle,
        config={
            **bundle.config,
            "years": 5,
            "modules_span_each_side": 4,
            "kWp_min": 12.0,
            "kWp_max": 18.0,
        },
    )


def _session_payload(state, *, lang: str = "es") -> dict:
    return commit_client_session(bootstrap_client_session(lang), state).to_payload()


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


@pytest.fixture(autouse=True)
def _clear_results_explorer_caches():
    get_results_explorer_dataset_cache().clear()
    get_candidate_financial_snapshot_cache().clear()
    yield
    get_results_explorer_dataset_cache().clear()
    get_candidate_financial_snapshot_cache().clear()


def test_results_explorer_dataset_cache_reuses_key_and_invalidates_on_economics_change(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    active = state.get_scenario()
    assert active is not None

    calls = {"count": 0}
    original = explorer_dataset.attach_candidate_financial_snapshots

    def _wrapped(scenario):
        calls["count"] += 1
        return original(scenario)

    monkeypatch.setattr(explorer_dataset, "attach_candidate_financial_snapshots", _wrapped)

    first = build_results_explorer_dataset(active)
    second = build_results_explorer_dataset(active)

    changed_prices = active.config_bundle.economics_price_items_table.copy()
    changed_prices.at[1, "value"] = float(changed_prices.at[1, "value"]) + 0.05
    changed_state = update_scenario_bundle(
        state,
        active.scenario_id,
        replace(active.config_bundle, economics_price_items_table=changed_prices),
    )
    changed_active = changed_state.get_scenario()
    assert changed_active is not None
    third = build_results_explorer_dataset(changed_active)

    assert first is second
    assert third is not first
    assert first.scan_fingerprint == third.scan_fingerprint
    assert first.economics_signature != third.economics_signature
    assert calls["count"] == 2


def test_results_explorer_dataset_cache_evicts_least_recently_used_entry() -> None:
    cache = ResultsExplorerDatasetCache(max_entries=2, max_horizon_tables_per_dataset=2)
    empty_rows = pd.DataFrame(columns=explorer_dataset.RESULTS_EXPLORER_BASE_ROW_COLUMNS)
    first = ResultsExplorerDataset("scan-1", "econ-1", {}, empty_rows, ())
    second = ResultsExplorerDataset("scan-2", "econ-2", {}, empty_rows, ())
    third = ResultsExplorerDataset("scan-3", "econ-3", {}, empty_rows, ())

    cache.put(("scan-1", "econ-1"), first)
    cache.put(("scan-2", "econ-2"), second)
    assert cache.get(("scan-1", "econ-1")) is first
    cache.put(("scan-3", "econ-3"), third)

    assert cache.get(("scan-2", "econ-2")) is None
    assert cache.get(("scan-1", "econ-1")) is first
    assert cache.get(("scan-3", "econ-3")) is third


def test_results_explorer_horizon_table_reuses_cached_frame(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    active = state.get_scenario()
    assert active is not None
    dataset = build_results_explorer_dataset(active)

    calls = {"count": 0}
    original = explorer_dataset.snapshot_npv_at_horizon

    def _wrapped(snapshot, horizon_years):
        calls["count"] += 1
        return original(snapshot, horizon_years)

    monkeypatch.setattr(explorer_dataset, "snapshot_npv_at_horizon", _wrapped)

    first = build_results_explorer_horizon_table(dataset, 5)
    second = build_results_explorer_horizon_table(dataset, 5)

    assert calls["count"] == len(dataset.base_rows.index)
    pdt.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True))


def test_results_callbacks_reuse_dataset_base_across_interactions_and_language_switch(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    payload = _session_payload(state)

    calls = {"count": 0}
    original = explorer_dataset.attach_candidate_financial_snapshots

    def _wrapped(scenario):
        calls["count"] += 1
        return original(scenario)

    monkeypatch.setattr(explorer_dataset, "attach_candidate_financial_snapshots", _wrapped)

    store = results_callbacks.sync_results_explorer_state(payload, "es", {})
    options, selected_value, disabled = results_callbacks.populate_results_explorer_controls(payload, "es", store)
    outputs = results_callbacks.populate_results(payload, "es", 5, store)
    _options_en, _selected_value_en, _disabled_en = results_callbacks.populate_results_explorer_controls(payload, "en", store)

    assert disabled is False
    assert selected_value == store["subset_key"]
    assert calls["count"] == 1

    alternative_subset = next(option["value"] for option in options if option["value"] != selected_value)
    monkeypatch.setattr(results_callbacks, "ctx", SimpleNamespace(triggered_id="results-battery-family-dropdown"))

    next_store, next_payload = results_callbacks.persist_selected_candidate(
        alternative_subset,
        outputs[13],
        None,
        5,
        store,
        outputs[11],
        payload,
        "es",
    )

    assert next_store["subset_key"] == alternative_subset
    assert next_payload is not None
    assert calls["count"] == 1


def test_results_frontend_payload_keeps_only_required_hidden_fields() -> None:
    section = candidate_explorer_section()
    table_component = _find_component(section, "active-candidate-table")
    assert list(table_component.hidden_columns) == ["candidate_key", "battery_family_key"]

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    payload = _session_payload(state)
    store = results_callbacks.sync_results_explorer_state(payload, "es", {})
    rows = results_callbacks.populate_results(payload, "es", 5, store)[11]

    assert rows
    first_row = rows[0]
    assert "candidate_key" in first_row
    assert "battery_family_key" in first_row
    assert "scan_order" not in first_row
    assert "best_battery_for_kwp" not in first_row
    assert "battery_family_label" not in first_row
    assert "battery_kwh" not in first_row
    assert "battery_name_raw" not in first_row
