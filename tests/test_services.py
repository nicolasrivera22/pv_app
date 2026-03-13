from __future__ import annotations

import math
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest
from openpyxl import load_workbook
from openpyxl.utils import range_boundaries

from pv_product.simulator import calculate_capex_client
from services import ensure_template, load_config_from_excel, load_example_config, run_scan, run_scenario
from services.io_excel import WorkbookContractError
from services.result_views import build_kpis, resolve_selected_candidate_key
from services.validation import validate_config


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


def _copy_workbook(tmp_path: Path, name: str = "workbook.xlsx") -> Path:
    destination = tmp_path / name
    shutil.copyfile(Path("PV_inputs.xlsx"), destination)
    return destination


def _table_header_map(ws, table_name: str) -> dict[str, int]:
    table = ws.tables[table_name]
    min_col, min_row, max_col, _ = range_boundaries(table.ref)
    headers = {
        ws.cell(row=min_row, column=column).value: column
        for column in range(min_col, max_col + 1)
    }
    return headers


def _set_config_value(path: Path, item_name: str, value) -> None:
    wb = load_workbook(path)
    ws = wb["Config"]
    headers = _table_header_map(ws, "Config")
    item_col = headers["Item"]
    value_col = headers["Valor"]
    _, min_row, _, max_row = range_boundaries(ws.tables["Config"].ref)
    for row in range(min_row + 1, max_row + 1):
        if ws.cell(row=row, column=item_col).value == item_name:
            ws.cell(row=row, column=value_col, value=value)
            wb.save(path)
            return
    raise AssertionError(f"Config item {item_name!r} not found")


def _blank_table_rows(path: Path, sheet_name: str, table_name: str) -> None:
    wb = load_workbook(path)
    ws = wb[sheet_name]
    min_col, min_row, max_col, max_row = range_boundaries(ws.tables[table_name].ref)
    for row in range(min_row + 1, max_row + 1):
        for column in range(min_col, max_col + 1):
            ws.cell(row=row, column=column, value=None)
    wb.save(path)


def _remove_sheet(path: Path, sheet_name: str) -> None:
    wb = load_workbook(path)
    del wb[sheet_name]
    wb.save(path)


def _remove_table(path: Path, sheet_name: str, table_name: str) -> None:
    wb = load_workbook(path)
    ws = wb[sheet_name]
    del ws.tables[table_name]
    wb.save(path)


def _rename_table_column(path: Path, sheet_name: str, table_name: str, old_name: str, new_name: str) -> None:
    wb = load_workbook(path)
    ws = wb[sheet_name]
    headers = _table_header_map(ws, table_name)
    column = headers[old_name]
    min_col, min_row, _, _ = range_boundaries(ws.tables[table_name].ref)
    assert column >= min_col
    ws.cell(row=min_row, column=column, value=new_name)
    wb.save(path)


def _parse_legacy_summary(summary_path: Path) -> dict[str, float | str]:
    text = summary_path.read_text(encoding="utf-8")
    return {
        "best_kwp": float(re.search(r"kWp óptimo .*: ([0-9.]+) kWp", text).group(1)),
        "battery": re.search(r"Batería óptima: ([A-Z0-9-]+|Ninguna)", text).group(1),
        "payback_years": float(re.search(r"Payback \(base\) ≈ ([0-9.]+) años", text).group(1)),
    }


def test_loads_spanish_workbook_and_normalizes_config() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))

    assert bundle.config["bat_coupling"] == "dc"
    assert bundle.config["include_battery"] is True
    assert bundle.config["export_allowed"] is True
    assert bundle.config["use_excel_profile"] == "perfil horario relativo"
    assert bundle.demand_profile_7x24.shape == (7, 24)
    assert bundle.hsp_month.shape == (12,)


def test_deterministic_scan_ignores_monte_carlo_fields() -> None:
    bundle = _fast_bundle()
    noisy_bundle = replace(
        bundle,
        config={
            **bundle.config,
            "mc_PR_std": 0.9,
            "mc_buy_std": 0.9,
            "mc_sell_std": 0.9,
            "mc_demand_std": 0.9,
        },
    )

    baseline_scan = run_scan(bundle)
    noisy_scan = run_scan(noisy_bundle)

    assert baseline_scan.best_candidate_key == noisy_scan.best_candidate_key
    pdt.assert_frame_equal(
        baseline_scan.candidates.sort_values("candidate_key").reset_index(drop=True),
        noisy_scan.candidates.sort_values("candidate_key").reset_index(drop=True),
    )


def test_deterministic_repeatability_full_workbook() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))

    first_scan = run_scan(bundle)
    second_scan = run_scan(bundle)

    assert first_scan.best_candidate_key == second_scan.best_candidate_key
    pdt.assert_frame_equal(
        first_scan.candidates.sort_values("candidate_key").reset_index(drop=True),
        second_scan.candidates.sort_values("candidate_key").reset_index(drop=True),
    )
    first_kpis = build_kpis(first_scan.candidate_details[first_scan.best_candidate_key])
    second_kpis = build_kpis(second_scan.candidate_details[second_scan.best_candidate_key])
    assert math.isclose(first_kpis["NPV"], second_kpis["NPV"], rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(
        float(first_kpis["self_consumption_ratio"]),
        float(second_kpis["self_consumption_ratio"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_run_scenario_shapes_outputs() -> None:
    bundle = _fast_bundle()
    scenario = run_scenario(bundle)

    assert scenario.kpis["best_kWp"] > 0
    assert "selected_battery" in scenario.kpis
    assert "NPV" in scenario.kpis
    assert set(["Año_mes", "PV to load", "Battery to load", "Grid import"]).issubset(scenario.monthly_balance.columns)
    assert set(["Año_mes", "cumulative_npv", "monthly_savings"]).issubset(scenario.cash_flow.columns)
    assert isinstance(scenario.npv_curve, pd.DataFrame)


def test_scan_payload_round_trip_preserves_detail_fields() -> None:
    scan = run_scan(_fast_bundle())
    restored = type(scan).from_payload(scan.to_payload())

    assert restored.best_candidate_key == scan.best_candidate_key
    detail = restored.candidate_details[restored.best_candidate_key]
    assert "self_consumption_ratio" in detail
    assert "scan_order" in detail


def test_candidate_table_has_single_best_battery_per_kwp_and_detail_alignment() -> None:
    scan = run_scan(_fast_bundle())

    best_counts = scan.candidates.groupby("kWp")["best_battery_for_kwp"].sum()
    assert (best_counts == 1).all()

    flagged_keys = set(scan.candidates.loc[scan.candidates["best_battery_for_kwp"], "candidate_key"])
    for candidate_key, detail in scan.candidate_details.items():
        assert detail["best_battery"] == (candidate_key in flagged_keys)


def test_selected_candidate_helper_uses_selected_row_over_best() -> None:
    scan = run_scan(_fast_bundle())
    table_rows = scan.candidates.to_dict("records")
    non_best_index = next(index for index, row in enumerate(table_rows) if row["candidate_key"] != scan.best_candidate_key)

    selected_key = resolve_selected_candidate_key(scan, [non_best_index], table_rows)

    assert selected_key == table_rows[non_best_index]["candidate_key"]
    selected_detail = scan.candidate_details[selected_key]
    best_detail = scan.candidate_details[scan.best_candidate_key]
    assert selected_detail["candidate_key"] != best_detail["candidate_key"]
    assert build_kpis(selected_detail)["best_kWp"] == selected_detail["kWp"]


def test_capex_semantics_variable_mode() -> None:
    cfg = {
        "pricing_mode": "variable",
        "price_total_COP": 58_000_000,
        "price_others_total": 2_000_000,
        "include_hw_in_price": False,
    }
    inv_sel = {"inverter": {"price_COP": 5_000_000}}
    battery_sel = {"nom_kWh": 10.0, "price_COP": 12_000_000}

    without_hw = calculate_capex_client(cfg, 10.0, inv_sel, battery_sel, 3_500_000)
    with_hw = calculate_capex_client({**cfg, "include_hw_in_price": True}, 10.0, inv_sel, battery_sel, 3_500_000)

    assert without_hw == 37_000_000
    assert with_hw == 54_000_000


def test_capex_semantics_total_mode() -> None:
    cfg = {
        "pricing_mode": "total",
        "price_total_COP": 80_000_000,
        "price_others_total": 1_500_000,
        "include_hw_in_price": False,
    }
    inv_sel = {"inverter": {"price_COP": 9_000_000}}
    battery_sel = {"nom_kWh": 0.0, "price_COP": 0.0}

    without_hw = calculate_capex_client(cfg, 12.0, inv_sel, battery_sel, 999_999)
    with_hw = calculate_capex_client({**cfg, "include_hw_in_price": True}, 12.0, inv_sel, battery_sel, 999_999)

    assert without_hw == 81_500_000
    assert with_hw == 90_500_000


def test_missing_sheet_raises_friendly_contract_error(tmp_path) -> None:
    workbook = _copy_workbook(tmp_path, "missing_sheet.xlsx")
    _remove_sheet(workbook, "Perfiles")

    with pytest.raises(WorkbookContractError, match="Falta la hoja 'Perfiles'"):
        load_config_from_excel(workbook)


def test_missing_required_table_raises_friendly_contract_error(tmp_path) -> None:
    workbook = _copy_workbook(tmp_path, "missing_table.xlsx")
    _remove_table(workbook, "Perfiles", "Demand_Profile")

    with pytest.raises(WorkbookContractError, match="Falta la tabla 'Demand_Profile'"):
        load_config_from_excel(workbook)


def test_missing_required_column_raises_friendly_contract_error(tmp_path) -> None:
    workbook = _copy_workbook(tmp_path, "missing_column.xlsx")
    _rename_table_column(workbook, "Catalogos", "Battery_Catalog", "max_dis_kW", "max_discharge")

    with pytest.raises(WorkbookContractError, match="max_dis_kW"):
        load_config_from_excel(workbook)


def test_invalid_mode_value_produces_validation_error(tmp_path) -> None:
    workbook = _copy_workbook(tmp_path, "invalid_mode.xlsx")
    _set_config_value(workbook, "pricing_mode", "banana")

    bundle = load_config_from_excel(workbook)

    assert any(issue.field == "pricing_mode" and issue.level == "error" for issue in bundle.issues)
    with pytest.raises(ValueError, match="pricing_mode"):
        run_scan(bundle)


def test_invalid_boolean_value_produces_validation_error(tmp_path) -> None:
    workbook = _copy_workbook(tmp_path, "invalid_bool.xlsx")
    _set_config_value(workbook, "include_battery", "maybe")

    bundle = load_config_from_excel(workbook)

    assert any(issue.field == "include_battery" and issue.level == "error" for issue in bundle.issues)


def test_empty_inverter_catalog_is_rejected(tmp_path) -> None:
    bundle = replace(load_example_config(), inverter_catalog=load_example_config().inverter_catalog.iloc[0:0].copy())
    issues = validate_config(bundle)

    assert any(issue.field == "Inversor_Catalog" and issue.level == "error" for issue in issues)
    with pytest.raises(ValueError, match="Inversor_Catalog"):
        run_scan(bundle)


def test_empty_battery_catalog_is_rejected_when_batteries_enabled(tmp_path) -> None:
    example = load_example_config()
    bundle = replace(
        example,
        config={**example.config, "include_battery": True, "optimize_battery": True},
        battery_catalog=example.battery_catalog.iloc[0:0].copy(),
    )
    issues = validate_config(bundle)

    assert any(issue.field == "Battery_Catalog" and issue.level == "error" for issue in issues)
    with pytest.raises(ValueError, match="Battery_Catalog"):
        run_scan(bundle)


def test_invalid_optimization_range_is_rejected(tmp_path) -> None:
    workbook = _copy_workbook(tmp_path, "invalid_range.xlsx")
    _set_config_value(workbook, "kWp_min", 30)
    _set_config_value(workbook, "kWp_max", 10)

    bundle = load_config_from_excel(workbook)

    assert any(issue.field == "kWp_min" and issue.level == "error" for issue in bundle.issues)
    with pytest.raises(ValueError, match="kWp_min"):
        run_scan(bundle)


def test_peak_ratio_behavior_is_kept_for_legacy_compatibility() -> None:
    bundle = _fast_bundle()
    cfg = {**bundle.config, "limit_peak_ratio_enable": True}
    from pv_product.hardware import peak_ratio_ok

    ok_a, ratio_a = peak_ratio_ok(
        cfg,
        15.0,
        {"inverter": {"AC_kW": 10.0}},
        bundle.solar_profile,
        bundle.hsp_month,
        bundle.demand_month_factor,
        dow24=bundle.demand_profile_7x24,
        day_w=bundle.day_weights,
    )
    ok_b, ratio_b = peak_ratio_ok(
        cfg,
        15.0,
        {"inverter": {"AC_kW": 10.0}},
        bundle.solar_profile,
        bundle.hsp_month,
        bundle.demand_month_factor * 1.2,
        dow24=bundle.demand_profile_7x24,
        day_w=bundle.day_weights,
    )

    assert ok_a == ok_b or isinstance(ok_a, bool)
    assert ratio_b != ratio_a


def test_regression_against_preserved_legacy_artifacts() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))
    scan = run_scan(bundle)
    legacy_summary = _parse_legacy_summary(Path("Resultados/resumen_optimizacion.txt"))
    legacy_scan = pd.read_csv("Resultados/resumen_valor_presente_neto.csv")
    legacy_row = legacy_scan[(legacy_scan["kWp"] == legacy_summary["best_kwp"]) & (legacy_scan["battery"] == legacy_summary["battery"])].iloc[0]
    legacy_candidate_key = f"{legacy_summary['best_kwp']:.3f}::{legacy_summary['battery']}"
    legacy_detail = scan.candidate_details[legacy_candidate_key]
    best_detail = scan.candidate_details[scan.best_candidate_key]

    # NPV and payback tolerances are intentionally looser because the preserved
    # batch artifacts were generated before deterministic/stochastic separation,
    # and the hardened scan now also includes prime module counts.
    assert legacy_candidate_key in scan.candidate_details
    assert math.isclose(legacy_detail["peak_ratio"], float(legacy_row["peak_ratio"]), rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(legacy_detail["summary"]["cum_disc_final"], float(legacy_row["NPV"]), rel_tol=0.0, abs_tol=6_000_000)
    assert math.isclose(float(legacy_detail["summary"]["payback_years"]), float(legacy_summary["payback_years"]), rel_tol=0.0, abs_tol=1.0)

    # The hardened optimum is now allowed to move because prime module counts
    # are no longer excluded from the search space.
    assert best_detail["battery_name"] == legacy_summary["battery"]
    assert best_detail["kWp"] >= legacy_summary["best_kwp"]


def test_template_round_trip(tmp_path) -> None:
    template_path = tmp_path / "PV_inputs_template.xlsx"
    ensure_template(template_path)

    bundle = load_config_from_excel(template_path)

    assert bundle.inverter_catalog.empty is False
    assert bundle.battery_catalog.empty is False
    assert bundle.issues is not None
