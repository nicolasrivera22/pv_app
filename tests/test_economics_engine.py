from __future__ import annotations

from dataclasses import replace

import pytest

from services import create_scenario_record, load_example_config, resolve_deterministic_scan
from services.economics_engine import (
    PREVIEW_STATE_CANDIDATE_MISSING,
    PREVIEW_STATE_READY,
    PREVIEW_STATE_RERUN_REQUIRED,
    EconomicsQuantities,
    calculate_economics_result,
    resolve_economics_preview,
    resolve_inverter_count,
    resolve_panel_count,
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


def test_calculate_economics_result_builds_cost_and_price_chain() -> None:
    quantities = EconomicsQuantities(
        candidate_key="12.000::",
        kWp=10.0,
        panel_count=20,
        inverter_count=1,
        battery_kwh=5.0,
        battery_name="",
        inverter_name="INV-A",
    )
    cost_rows = [
        {"stage": "technical", "name": "Panel hardware", "basis": "per_panel", "amount_COP": 100.0, "enabled": True, "notes": ""},
        {"stage": "technical", "name": "Inverter hardware", "basis": "per_inverter", "amount_COP": 2_000.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "BOS", "basis": "per_kwp", "amount_COP": 300.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "Engineering", "basis": "fixed_project", "amount_COP": 5_000.0, "enabled": True, "notes": ""},
    ]
    price_rows = [
        {"layer": "commercial", "name": "Margin", "method": "markup_pct", "value": 0.10, "enabled": True, "notes": ""},
        {"layer": "commercial", "name": "Offer fee", "method": "fixed_project", "value": 500.0, "enabled": True, "notes": ""},
        {"layer": "sale", "name": "Final adder", "method": "per_kwp", "value": 10.0, "enabled": True, "notes": ""},
    ]

    result = calculate_economics_result(
        economics_cost_items=cost_rows,
        economics_price_items=price_rows,
        quantities=quantities,
    )

    assert result.technical_subtotal_COP == pytest.approx(4_000.0)
    assert result.installed_subtotal_COP == pytest.approx(8_000.0)
    assert result.cost_total_COP == pytest.approx(12_000.0)
    assert result.commercial_adjustment_COP == pytest.approx(1_700.0)
    assert result.commercial_offer_COP == pytest.approx(13_700.0)
    assert result.sale_adjustment_COP == pytest.approx(100.0)
    assert result.final_price_COP == pytest.approx(13_800.0)
    assert result.final_price_per_kwp_COP == pytest.approx(1_380.0)

    assert [row.source_row for row in result.cost_rows] == [1, 2, 3, 4]
    assert [row.source_row for row in result.price_rows] == [1, 2, 3]
    assert result.cost_rows[0].line_amount_COP == pytest.approx(2_000.0)
    assert result.price_rows[0].base_amount_COP == pytest.approx(12_000.0)
    assert result.price_rows[0].line_amount_COP == pytest.approx(1_200.0)


def test_resolve_panel_count_uses_n_mod_before_fallback() -> None:
    detail = {"kWp": 10.0, "inv_sel": {"N_mod": 33}}
    config = {"P_mod_W": 500.0}

    assert resolve_panel_count(detail, config) == 33


def test_resolve_panel_count_falls_back_to_kwp_and_module_power() -> None:
    detail = {"kWp": 11.0, "inv_sel": {}}
    config = {"P_mod_W": 550.0}

    assert resolve_panel_count(detail, config) == 20


def test_resolve_inverter_count_helper_uses_explicit_one_or_zero() -> None:
    assert resolve_inverter_count({"inv_sel": {"inverter_count": 2, "inverter": {"name": "INV-A"}}}) == 2
    assert resolve_inverter_count({"inv_sel": {"inverter": {"name": "INV-A"}}}) == 1
    assert resolve_inverter_count({"inv_sel": {}}) == 0


def test_resolve_economics_preview_returns_ready_for_scanned_scenario() -> None:
    bundle = _fast_bundle()
    scan_result = resolve_deterministic_scan(bundle, allow_parallel=False)
    scenario = replace(
        create_scenario_record("Base", bundle),
        scan_result=scan_result,
        selected_candidate_key=scan_result.best_candidate_key,
        dirty=False,
    )

    preview = resolve_economics_preview(
        scenario,
        economics_cost_items=bundle.economics_cost_items_table,
        economics_price_items=bundle.economics_price_items_table,
    )

    assert preview.state == PREVIEW_STATE_READY
    assert preview.result is not None
    assert preview.result.quantities.candidate_key == scan_result.best_candidate_key


def test_resolve_economics_preview_blocks_when_dirty() -> None:
    bundle = _fast_bundle()
    scan_result = resolve_deterministic_scan(bundle, allow_parallel=False)
    scenario = replace(
        create_scenario_record("Base", bundle),
        scan_result=scan_result,
        selected_candidate_key=scan_result.best_candidate_key,
        dirty=True,
    )

    preview = resolve_economics_preview(
        scenario,
        economics_cost_items=bundle.economics_cost_items_table,
        economics_price_items=bundle.economics_price_items_table,
    )

    assert preview.state == PREVIEW_STATE_RERUN_REQUIRED
    assert preview.result is None


def test_resolve_economics_preview_reports_candidate_missing_when_no_key_is_resolvable() -> None:
    bundle = _fast_bundle()
    scan_result = resolve_deterministic_scan(bundle, allow_parallel=False)
    scenario = replace(
        create_scenario_record("Base", bundle),
        scan_result=replace(scan_result, best_candidate_key=None),
        selected_candidate_key=None,
        dirty=False,
    )

    preview = resolve_economics_preview(
        scenario,
        economics_cost_items=bundle.economics_cost_items_table,
        economics_price_items=bundle.economics_price_items_table,
    )

    assert preview.state == PREVIEW_STATE_CANDIDATE_MISSING
    assert preview.result is None
