from __future__ import annotations

from dataclasses import replace

import pytest

from services import create_scenario_record, load_example_config, resolve_deterministic_scan
from services.economics_tables import economics_price_items_rows_from_editor, normalize_economics_price_items_with_issues
from services.economics_engine import (
    PREVIEW_STATE_CANDIDATE_MISSING,
    PREVIEW_STATE_READY,
    PREVIEW_STATE_RERUN_REQUIRED,
    EconomicsQuantities,
    calculate_economics_result,
    economics_preview_warning_messages,
    resolve_battery_hardware_price,
    resolve_economics_preview,
    resolve_inverter_count,
    resolve_economics_quantities,
    resolve_inverter_hardware_price,
    resolve_panel_hardware_price,
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
        panel_name="PANEL-A",
    )
    cost_rows = [
        {"stage": "technical", "name": "Panel hardware", "basis": "per_panel", "amount_COP": 100.0, "enabled": True, "notes": ""},
        {"stage": "technical", "name": "Inverter hardware", "basis": "per_inverter", "amount_COP": 2_000.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "BOS", "basis": "per_kwp", "amount_COP": 300.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "Engineering", "basis": "fixed_project", "amount_COP": 5_000.0, "enabled": True, "notes": ""},
    ]
    price_rows = [
        {"layer": "tax", "name": "IVA", "method": "tax_pct", "value": 0.19, "enabled": True, "notes": ""},
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
    assert result.taxable_base_COP == pytest.approx(12_000.0)
    assert result.tax_total_COP == pytest.approx(2_280.0)
    assert result.subtotal_with_tax_COP == pytest.approx(14_280.0)
    assert result.commercial_adjustment_COP == pytest.approx(1_928.0)
    assert result.post_tax_adjustments_total_COP == pytest.approx(2_028.0)
    assert result.commercial_offer_COP == pytest.approx(16_208.0)
    assert result.sale_adjustment_COP == pytest.approx(100.0)
    assert result.final_price_COP == pytest.approx(16_308.0)
    assert result.final_price_per_kwp_COP == pytest.approx(1_630.8)

    assert [row.source_row for row in result.cost_rows] == [1, 2, 3, 4]
    assert [row.source_row for row in result.price_rows] == [1, 2, 3, 4]
    assert result.cost_rows[0].line_amount_COP == pytest.approx(2_000.0)
    assert result.price_rows[0].base_amount_COP == pytest.approx(12_000.0)
    assert result.price_rows[0].line_amount_COP == pytest.approx(2_280.0)
    assert result.price_rows[1].base_amount_COP == pytest.approx(14_280.0)
    assert result.price_rows[1].line_amount_COP == pytest.approx(1_428.0)


def test_calculate_economics_result_adds_multiple_tax_rows_over_same_taxable_base() -> None:
    quantities = EconomicsQuantities(
        candidate_key="12.000::",
        kWp=10.0,
        panel_count=20,
        inverter_count=1,
        battery_kwh=0.0,
        battery_name="",
        inverter_name="INV-A",
        panel_name="PANEL-A",
    )

    result = calculate_economics_result(
        economics_cost_items=[
            {"stage": "technical", "name": "Panel hardware", "basis": "per_panel", "amount_COP": 100.0, "enabled": True, "notes": ""},
        ],
        economics_price_items=[
            {"layer": "tax", "name": "IVA", "method": "tax_pct", "value": 0.19, "enabled": True, "notes": ""},
            {"layer": "tax", "name": "Municipal", "method": "tax_pct", "value": 0.01, "enabled": True, "notes": ""},
        ],
        quantities=quantities,
    )

    assert result.cost_total_COP == pytest.approx(2_000.0)
    assert result.taxable_base_COP == pytest.approx(2_000.0)
    assert result.tax_total_COP == pytest.approx(400.0)
    assert result.subtotal_with_tax_COP == pytest.approx(2_400.0)
    assert [row.line_amount_COP for row in result.price_rows] == pytest.approx([380.0, 20.0])
    assert all(row.base_amount_COP == pytest.approx(2_000.0) for row in result.price_rows)


def test_calculate_economics_result_uses_canonical_layer_order_not_csv_row_order() -> None:
    quantities = EconomicsQuantities(
        candidate_key="12.000::",
        kWp=10.0,
        panel_count=20,
        inverter_count=1,
        battery_kwh=0.0,
        battery_name="",
        inverter_name="INV-A",
        panel_name="PANEL-A",
    )
    price_rows = [
        {"layer": "sale", "name": "Closing", "method": "fixed_project", "value": 50.0, "enabled": True, "notes": ""},
        {"layer": "commercial", "name": "Margin", "method": "markup_pct", "value": 0.10, "enabled": True, "notes": ""},
        {"layer": "tax", "name": "IVA", "method": "tax_pct", "value": 0.19, "enabled": True, "notes": ""},
    ]

    result = calculate_economics_result(
        economics_cost_items=[
            {"stage": "technical", "name": "Panel hardware", "basis": "per_panel", "amount_COP": 100.0, "enabled": True, "notes": ""},
        ],
        economics_price_items=price_rows,
        quantities=quantities,
    )

    assert [row.stage_or_layer for row in result.price_rows] == ["tax", "commercial", "sale"]
    assert [row.source_row for row in result.price_rows] == [3, 2, 1]
    assert result.tax_total_COP == pytest.approx(380.0)
    assert result.subtotal_with_tax_COP == pytest.approx(2_380.0)
    assert result.commercial_adjustment_COP == pytest.approx(238.0)
    assert result.final_price_COP == pytest.approx(2_668.0)


def test_tax_percent_editor_values_round_trip_as_human_percentages() -> None:
    rows = [
        {
            "layer": "Impuestos",
            "name": "IVA",
            "method": "Impuesto porcentual",
            "value": 1,
            "enabled": True,
            "notes": "",
        }
    ]

    normalized = economics_price_items_rows_from_editor(rows)

    assert normalized[0]["layer"] == "tax"
    assert normalized[0]["method"] == "tax_pct"
    assert float(normalized[0]["value"]) == pytest.approx(0.01)


def test_invalid_tax_layer_method_combinations_are_disabled_during_normalization() -> None:
    frame, issues = normalize_economics_price_items_with_issues(
        [
            {"layer": "tax", "name": "IVA fijo", "method": "fixed_project", "value": 1000.0, "enabled": True, "notes": ""},
            {"layer": "commercial", "name": "Bad tax", "method": "tax_pct", "value": 0.19, "enabled": True, "notes": ""},
        ]
    )

    assert len(frame) == 2
    assert bool(frame.iloc[0]["enabled"]) is False
    assert bool(frame.iloc[1]["enabled"]) is False
    assert "combinación inválida" in issues[0]
    assert "combinación inválida" in issues[1]


def test_calculate_economics_result_uses_selected_hardware_rate_without_overwriting_manual_amount() -> None:
    quantities = EconomicsQuantities(
        candidate_key="12.000::",
        kWp=10.0,
        panel_count=20,
        inverter_count=1,
        battery_kwh=5.0,
        battery_name="BAT-A",
        inverter_name="INV-A",
        panel_name="PANEL-A",
    )
    cost_rows = [
        {
            "stage": "technical",
            "name": "Panel hardware renamed",
            "basis": "per_panel",
            "amount_COP": 123.0,
            "source_mode": "selected_hardware",
            "hardware_binding": "panel",
            "enabled": True,
            "notes": "",
        }
    ]

    result = calculate_economics_result(
        economics_cost_items=cost_rows,
        economics_price_items=[],
        quantities=quantities,
        hardware_prices={
            "panel": resolve_panel_hardware_price(
                {"panel_name": "BASE-600W Standard"},
                load_example_config().panel_catalog,
            )
        },
    )

    assert result.technical_subtotal_COP == pytest.approx(20 * 620_000.0)
    assert result.cost_rows[0].unit_rate_COP == pytest.approx(620_000.0)
    assert result.cost_rows[0].value_source == "selected_panel_catalog"
    assert result.cost_rows[0].hardware_name == "BASE-600W Standard"


def test_resolve_panel_hardware_price_uses_selected_catalog_panel() -> None:
    bundle = load_example_config()

    resolved = resolve_panel_hardware_price(bundle.config, bundle.panel_catalog)

    assert resolved.value_source == "selected_panel_catalog"
    assert resolved.hardware_name == bundle.config["panel_name"]
    assert resolved.unit_rate_COP == pytest.approx(620_000.0)


def test_resolve_inverter_hardware_price_prefers_candidate_detail_before_catalog_lookup() -> None:
    bundle = load_example_config()
    detail = {"inv_sel": {"inverter": {"name": "INV-10k", "price_COP": 8_888_000.0}}}

    resolved = resolve_inverter_hardware_price(detail, bundle.inverter_catalog)

    assert resolved.value_source == "selected_inverter_catalog"
    assert resolved.hardware_name == "INV-10k"
    assert resolved.unit_rate_COP == pytest.approx(8_888_000.0)


def test_resolve_battery_hardware_price_falls_back_to_catalog_lookup() -> None:
    bundle = load_example_config()
    detail = {"battery_name": "BAT-10", "battery": {"name": "BAT-10", "nom_kWh": 10.0}}

    resolved = resolve_battery_hardware_price(detail, bundle.battery_catalog)

    assert resolved.value_source == "selected_battery_catalog"
    assert resolved.hardware_name == "BAT-10"
    assert resolved.unit_rate_COP == pytest.approx(12_500_000.0)


def test_resolve_economics_quantities_prefers_nominal_energy_over_power_fields() -> None:
    detail = {
        "kWp": 12.0,
        "battery_name": "BAT-ENERGY",
        "battery": {"name": "BAT-ENERGY", "nom_kWh": 10.0, "max_kW": 80.0, "max_ch_kW": 80.0, "max_dis_kW": 80.0},
        "inv_sel": {"N_mod": 24, "inverter": {"name": "INV-RAW"}},
    }
    config = {"P_mod_W": 500.0}

    quantities = resolve_economics_quantities(
        candidate_key="12.000::BAT-ENERGY",
        detail=detail,
        config=config,
    )

    assert quantities.battery_kwh == pytest.approx(10.0)
    assert quantities.battery_energy_missing_with_power is False


def test_resolve_economics_quantities_supports_explicit_energy_aliases_without_inferring_from_power() -> None:
    detail = {
        "kWp": 12.0,
        "battery_name": "BAT-ALIAS",
        "battery": {"name": "BAT-ALIAS", "nominal_kWh": 12.5, "max_kW": 80.0, "max_ch_kW": 80.0, "max_dis_kW": 80.0},
        "inv_sel": {"N_mod": 24, "inverter": {"name": "INV-RAW"}},
    }
    config = {"P_mod_W": 500.0}

    quantities = resolve_economics_quantities(
        candidate_key="12.000::BAT-ALIAS",
        detail=detail,
        config=config,
    )

    assert quantities.battery_kwh == pytest.approx(12.5)
    assert quantities.battery_energy_missing_with_power is False


def test_manual_per_battery_kwh_keeps_using_battery_energy() -> None:
    quantities = EconomicsQuantities(
        candidate_key="12.000::BAT-A",
        kWp=10.0,
        panel_count=20,
        inverter_count=1,
        battery_kwh=35.0,
        battery_name="BAT-A",
        inverter_name="INV-A",
        panel_name="PANEL-A",
    )

    result = calculate_economics_result(
        economics_cost_items=[
            {
                "stage": "technical",
                "name": "Battery adder manual",
                "basis": "per_battery_kwh",
                "amount_COP": 1_000.0,
                "source_mode": "manual",
                "hardware_binding": "battery",
                "enabled": True,
                "notes": "",
            }
        ],
        economics_price_items=[],
        quantities=quantities,
    )

    assert result.cost_rows[0].multiplier == pytest.approx(35.0)
    assert result.cost_rows[0].line_amount_COP == pytest.approx(35_000.0)


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
    assert preview.candidate_source == "selected"


def test_resolve_economics_preview_marks_selected_even_when_selected_matches_best() -> None:
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
    assert preview.candidate_source == "selected"


def test_resolve_economics_preview_marks_best_fallback_only_when_selected_is_missing() -> None:
    bundle = _fast_bundle()
    scan_result = resolve_deterministic_scan(bundle, allow_parallel=False)
    scenario = replace(
        create_scenario_record("Base", bundle),
        scan_result=scan_result,
        selected_candidate_key="missing-key",
        dirty=False,
    )

    preview = resolve_economics_preview(
        scenario,
        economics_cost_items=bundle.economics_cost_items_table,
        economics_price_items=bundle.economics_price_items_table,
    )

    assert preview.state == PREVIEW_STATE_READY
    assert preview.candidate_key == scan_result.best_candidate_key
    assert preview.candidate_source == "best_fallback"


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
    assert preview.candidate_source is None
    assert preview.result is None


def test_resolve_economics_quantities_keeps_raw_equipment_names() -> None:
    detail = {
        "kWp": 12.0,
        "battery_name": "BAT-RAW",
        "battery": {"nom_kWh": 9.5},
        "inv_sel": {"N_mod": 24, "inverter": {"name": "INV-RAW"}},
    }
    config = {"P_mod_W": 500.0}

    quantities = resolve_economics_quantities(
        candidate_key="12.000::BAT-RAW",
        detail=detail,
        config=config,
    )

    assert quantities.battery_name == "BAT-RAW"
    assert quantities.inverter_name == "INV-RAW"


def test_economics_preview_warning_messages_report_selected_hardware_none_without_fallback() -> None:
    bundle = _fast_bundle()
    scan_result = resolve_deterministic_scan(bundle, allow_parallel=False)
    scenario = replace(
        create_scenario_record("Base", bundle),
        scan_result=scan_result,
        selected_candidate_key=scan_result.best_candidate_key,
        dirty=False,
    )
    cost_rows = bundle.economics_cost_items_table.to_dict("records")
    cost_rows[0] = {
        **cost_rows[0],
        "source_mode": "selected_hardware",
        "hardware_binding": "none",
        "amount_COP": 777_000.0,
    }

    preview = resolve_economics_preview(
        scenario,
        economics_cost_items=cost_rows,
        economics_price_items=bundle.economics_price_items_table,
    )

    assert preview.state == PREVIEW_STATE_READY
    assert preview.result is not None
    assert preview.result.cost_rows[0].value_source == "unavailable"
    assert preview.result.cost_rows[0].unit_rate_COP == pytest.approx(0.0)
    assert preview.result.cost_rows[0].line_amount_COP == pytest.approx(0.0)
    assert economics_preview_warning_messages(preview) == (
        "Economics_Cost_Items fila 1: 'selected_hardware' requiere un 'hardware_binding' distinto de 'none'.",
    )


def test_selected_battery_hardware_uses_one_unit_not_energy_kwh() -> None:
    quantities = EconomicsQuantities(
        candidate_key="12.000::BAT-10",
        kWp=10.0,
        panel_count=20,
        inverter_count=1,
        battery_kwh=35.0,
        battery_name="BAT-10",
        inverter_name="INV-A",
        panel_name="PANEL-A",
    )

    result = calculate_economics_result(
        economics_cost_items=[
            {
                "stage": "technical",
                "name": "Battery hardware",
                "basis": "per_battery_kwh",
                "amount_COP": 0.0,
                "source_mode": "selected_hardware",
                "hardware_binding": "battery",
                "enabled": True,
                "notes": "",
            }
        ],
        economics_price_items=[],
        quantities=quantities,
        hardware_prices={
            "battery": resolve_battery_hardware_price(
                {"battery_name": "BAT-10", "battery": {"name": "BAT-10", "nom_kWh": 10.0}},
                load_example_config().battery_catalog,
            )
        },
    )

    assert result.cost_rows[0].multiplier == pytest.approx(1.0)
    assert result.cost_rows[0].unit_rate_COP == pytest.approx(12_500_000.0)
    assert result.cost_rows[0].line_amount_COP == pytest.approx(12_500_000.0)


def test_preview_battery_energy_warning_does_not_turn_selected_battery_price_into_per_kw_cost() -> None:
    bundle = _fast_bundle()
    scan_result = resolve_deterministic_scan(bundle, allow_parallel=False)
    candidate_key = scan_result.best_candidate_key
    assert candidate_key is not None
    original_detail = dict(scan_result.candidate_details[candidate_key])
    mutated_detail = {
        **original_detail,
        "battery_name": "BAT-POWER-ONLY",
        "battery": {
            "name": "BAT-POWER-ONLY",
            "price_COP": 12_500_000.0,
            "max_kW": 80.0,
            "max_ch_kW": 80.0,
            "max_dis_kW": 80.0,
        },
    }
    scenario = replace(
        create_scenario_record("Base", bundle),
        scan_result=replace(
            scan_result,
            candidate_details={**scan_result.candidate_details, candidate_key: mutated_detail},
        ),
        selected_candidate_key=candidate_key,
        dirty=False,
    )

    preview = resolve_economics_preview(
        scenario,
        economics_cost_items=bundle.economics_cost_items_table,
        economics_price_items=bundle.economics_price_items_table,
    )

    assert preview.state == PREVIEW_STATE_READY
    assert preview.result is not None
    battery_row = next(row for row in preview.result.cost_rows if row.rule == "per_battery_kwh")
    assert battery_row.multiplier == pytest.approx(1.0)
    assert battery_row.unit_rate_COP == pytest.approx(12_500_000.0)
    assert battery_row.line_amount_COP == pytest.approx(12_500_000.0)
    assert economics_preview_warning_messages(preview) == (
        "Economics_Cost_Items fila 3: la batería seleccionada tiene campos de potencia pero no una energía válida ('nom_kWh' o alias soportado); la cantidad energética quedará en 0 kWh.",
    )
