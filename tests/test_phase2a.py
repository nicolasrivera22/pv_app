from __future__ import annotations

from dataclasses import replace
from io import BytesIO

import pandas.testing as pdt
from openpyxl import load_workbook

from services import (
    ScenarioSessionState,
    add_scenario,
    build_comparison_figures,
    build_comparison_table,
    create_scenario_record,
    delete_scenario,
    duplicate_scenario,
    export_comparison_workbook,
    export_scenario_workbook,
    load_example_config,
    normalize_inverter_catalog_rows,
    rename_scenario,
    run_scenario_scan,
    set_comparison_scenarios,
    update_scenario_bundle,
    update_selected_candidate,
)


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
    }
    return replace(bundle, config=config)


def _run_named_scenario(name: str, bundle=None):
    bundle = bundle or _fast_bundle()
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record(name, bundle))
    return run_scenario_scan(state, state.active_scenario_id)


def test_scenario_duplicate_rename_delete_workflow() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    active_id = state.active_scenario_id
    state = run_scenario_scan(state, active_id)

    duplicated = duplicate_scenario(state, active_id, new_name="Base copy")
    assert len(duplicated.scenarios) == 2
    assert duplicated.active_scenario_id != active_id
    assert duplicated.get_scenario().name == "Base copy"
    assert duplicated.get_scenario().scan_result is not None

    renamed = rename_scenario(duplicated, duplicated.active_scenario_id, "Variant A")
    assert renamed.get_scenario().name == "Variant A"

    reduced = delete_scenario(renamed, active_id)
    assert len(reduced.scenarios) == 1
    assert reduced.get_scenario().name == "Variant A"


def test_update_bundle_marks_scenario_dirty_and_clears_scan() -> None:
    state = _run_named_scenario("Editable")
    active = state.get_scenario()
    updated_bundle = replace(active.config_bundle, config={**active.config_bundle.config, "PR": 0.85})

    state = update_scenario_bundle(state, active.scenario_id, updated_bundle)
    active = state.get_scenario()

    assert active.dirty is True
    assert active.scan_result is None
    assert active.selected_candidate_key is None


def test_selected_candidate_resets_after_scenario_change_and_rerun() -> None:
    state = _run_named_scenario("Selection test")
    active = state.get_scenario()
    assert active.scan_result is not None
    non_best_key = next(
        key
        for key, detail in active.scan_result.candidate_details.items()
        if key != active.scan_result.best_candidate_key and float(detail["kWp"]) >= 16.0
    )

    state = update_selected_candidate(state, active.scenario_id, non_best_key)
    selected = state.get_scenario().selected_candidate_key
    assert selected == non_best_key

    narrowed_bundle = replace(
        active.config_bundle,
        config={**active.config_bundle.config, "kWp_max": 13.8},
    )
    state = update_scenario_bundle(state, active.scenario_id, narrowed_bundle)
    state = run_scenario_scan(state, active.scenario_id)
    rerun = state.get_scenario()

    assert rerun.selected_candidate_key == rerun.scan_result.best_candidate_key
    assert non_best_key not in rerun.scan_result.candidate_details


def test_catalog_row_validation_reports_duplicate_names_and_nonnumeric_values() -> None:
    rows = [
        {"name": "INV-A", "AC_kW": "10", "Vmppt_min": 200, "Vmppt_max": 800, "Vdc_max": 1000, "Imax_mppt": 18, "n_mppt": 2, "price_COP": 9_000_000},
        {"name": "INV-A", "AC_kW": "banana", "Vmppt_min": 200, "Vmppt_max": 800, "Vdc_max": 1000, "Imax_mppt": 18, "n_mppt": 2, "price_COP": 9_000_000},
    ]

    _, issues = normalize_inverter_catalog_rows(rows)

    messages = [issue.message for issue in issues]
    assert any("Duplicados" in message for message in messages)
    assert any("debe ser numérico" in message for message in messages)


def test_comparison_outputs_are_stable_for_two_scenarios() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    variant_bundle = replace(_fast_bundle(), config={**_fast_bundle().config, "buy_tariff_COP_kWh": 1050.0})
    state = add_scenario(state, create_scenario_record("Variant", variant_bundle))

    scenario_ids = [scenario.scenario_id for scenario in state.scenarios]
    for scenario_id in scenario_ids:
        state = run_scenario_scan(state, scenario_id)
    state = set_comparison_scenarios(state, scenario_ids)

    rows = [state.get_scenario(scenario_id) for scenario_id in state.comparison_scenario_ids]
    table_a = build_comparison_table(rows)
    table_b = build_comparison_table(rows)
    pdt.assert_frame_equal(table_a, table_b)

    figures = build_comparison_figures(rows)
    assert len(figures["npv_overlay"].data) == 2
    assert len(figures["kpi_bar"].data) == 3


def test_export_scenario_workbook_contains_expected_sheets() -> None:
    state = _run_named_scenario("Export")
    scenario = state.get_scenario()
    payload = export_scenario_workbook(scenario)

    workbook = load_workbook(BytesIO(payload))
    assert workbook.sheetnames == ["Summary", "Config", "Inverters", "Batteries", "Candidates", "Monthly_Selected"]


def test_export_comparison_workbook_contains_expected_sheets() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    variant_bundle = replace(_fast_bundle(), config={**_fast_bundle().config, "sell_tariff_COP_kWh": 350.0})
    state = add_scenario(state, create_scenario_record("Variant", variant_bundle))
    for scenario in state.scenarios:
        state = run_scenario_scan(state, scenario.scenario_id)
    state = set_comparison_scenarios(state, [scenario.scenario_id for scenario in state.scenarios])

    selected = [state.get_scenario(scenario_id) for scenario_id in state.comparison_scenario_ids]
    payload = export_comparison_workbook(state, selected)

    workbook = load_workbook(BytesIO(payload))
    assert "Comparison_Summary" in workbook.sheetnames
    assert "Comparison_KPIs" in workbook.sheetnames
    candidate_sheets = [name for name in workbook.sheetnames if name.startswith("Candidates_")]
    assert len(candidate_sheets) == 2
