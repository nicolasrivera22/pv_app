from __future__ import annotations

import math
from dataclasses import replace

import pytest

import services.deterministic_executor as deterministic_executor
from pv_product.hardware import compute_kwp_seed, peak_ratio_ok
from pv_product.panel_technology import (
    DEFAULT_PANEL_TECHNOLOGY_MODE,
    panel_technology_factor,
    resolve_generation_pr,
)
from services import load_config_from_excel, load_example_config, run_scan
from services.deterministic_executor import DeterministicScanTask, evaluate_deterministic_scan_task
from services.io_excel import _normalize_config_value


def _fixed_design_bundle(mode: str | None, *, include_battery: bool = False, optimize_battery: bool = False):
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 1,
        "include_battery": include_battery,
        "optimize_battery": optimize_battery,
        "kWp_seed_mode": "manual",
        "kWp_seed_manual_kWp": 15.0,
        "modules_span_each_side": 0,
        "kWp_min": 15.0,
        "kWp_max": 15.0,
    }
    if mode is None:
        config.pop("panel_technology_mode", None)
    else:
        config["panel_technology_mode"] = mode
    config_table = bundle.config_table.copy()
    if not config_table.empty and "Item" in config_table.columns:
        items = config_table["Item"].astype(str).str.strip()
        config_table = config_table.loc[items != "panel_technology_mode"].copy()
    return replace(bundle, config=config, config_table=config_table)


def _annual_generation_kwh(scan) -> float:
    detail = scan.candidate_details[scan.best_candidate_key]
    return float(detail["monthly"]["Generacion_PV_AC_kWh"].iloc[:12].sum())


def test_panel_technology_factors_and_normalization_are_centralized() -> None:
    assert DEFAULT_PANEL_TECHNOLOGY_MODE == "standard"
    assert panel_technology_factor("standard") == pytest.approx(1.00)
    assert panel_technology_factor("premium") == pytest.approx(1.03)
    assert panel_technology_factor("tracker_simplified") == pytest.approx(1.08)

    normalized_missing, missing_error = _normalize_config_value("panel_technology_mode", None)
    normalized_invalid, invalid_error = _normalize_config_value("panel_technology_mode", "not-a-mode")

    assert normalized_missing == "standard"
    assert normalized_invalid == "standard"
    assert missing_error is None
    assert invalid_error is None
    assert load_config_from_excel("PV_inputs.xlsx").config["panel_technology_mode"] == "standard"


def test_standard_mode_preserves_legacy_baseline_behavior() -> None:
    legacy_like_scan = run_scan(_fixed_design_bundle(None))
    standard_scan = run_scan(_fixed_design_bundle("standard"))

    assert legacy_like_scan.best_candidate_key == standard_scan.best_candidate_key
    assert legacy_like_scan.seed_kwp == pytest.approx(standard_scan.seed_kwp)
    assert _annual_generation_kwh(legacy_like_scan) == pytest.approx(_annual_generation_kwh(standard_scan))
    assert legacy_like_scan.candidates.reset_index(drop=True).equals(
        standard_scan.candidates.reset_index(drop=True)
    )


def test_panel_technology_increases_generation_in_expected_order() -> None:
    standard_scan = run_scan(_fixed_design_bundle("standard"))
    premium_scan = run_scan(_fixed_design_bundle("premium"))
    tracker_scan = run_scan(_fixed_design_bundle("tracker_simplified"))

    standard_generation = _annual_generation_kwh(standard_scan)
    premium_generation = _annual_generation_kwh(premium_scan)
    tracker_generation = _annual_generation_kwh(tracker_scan)

    assert premium_generation > standard_generation
    assert tracker_generation > premium_generation


def test_compute_kwp_seed_uses_resolved_generation_pr() -> None:
    bundle = load_example_config()
    base_cfg = {
        **bundle.config,
        "E_month_kWh": 2000.0,
        "HSP": 5.5,
        "PR": 0.80,
        "P_mod_W": 1.0,
        "kWp_seed_mode": "auto",
    }

    seeds = {}
    for mode in ("standard", "premium", "tracker_simplified"):
        cfg = {**base_cfg, "panel_technology_mode": mode}
        expected = max(
            math.ceil(
                1e3
                * (cfg["E_month_kWh"] / (resolve_generation_pr(cfg["PR"], mode) * cfg["HSP"] * 30.0))
                / cfg["P_mod_W"]
            )
            * cfg["P_mod_W"]
            / 1e3,
            0.1,
        )
        seeds[mode] = compute_kwp_seed(cfg)
        assert seeds[mode] == pytest.approx(expected)

    assert seeds["premium"] < seeds["standard"]
    assert seeds["tracker_simplified"] < seeds["premium"]


def test_peak_ratio_uses_resolved_generation_pr() -> None:
    bundle = load_example_config()
    base_cfg = {
        **bundle.config,
        "deg_rate": 0.0,
        "limit_peak_ratio_enable": False,
    }

    ratios: dict[str, float] = {}
    for mode in ("standard", "premium", "tracker_simplified"):
        cfg = {**base_cfg, "panel_technology_mode": mode}
        _, ratios[mode] = peak_ratio_ok(
            cfg,
            5.0,
            {"inverter": {"AC_kW": 100.0}},
            bundle.solar_profile,
            bundle.hsp_month,
            bundle.demand_month_factor,
            dow24=bundle.demand_profile_7x24,
            day_w=bundle.day_weights,
        )

    assert ratios["premium"] == pytest.approx(
        ratios["standard"] * panel_technology_factor("premium"),
        rel=1e-6,
    )
    assert ratios["tracker_simplified"] == pytest.approx(
        ratios["standard"] * panel_technology_factor("tracker_simplified"),
        rel=1e-6,
    )
    assert ratios["premium"] > ratios["standard"]
    assert ratios["tracker_simplified"] > ratios["premium"]


def test_deterministic_task_resolves_generation_pr_once_before_battery_loop(monkeypatch) -> None:
    bundle = _fixed_design_bundle("premium", include_battery=True, optimize_battery=True)
    calls: list[tuple[float, str | None]] = []
    original = deterministic_executor.resolve_generation_pr

    def _wrapped(base_pr: float, mode: str | None) -> float:
        calls.append((base_pr, mode))
        return original(base_pr, mode)

    monkeypatch.setattr(deterministic_executor, "resolve_generation_pr", _wrapped)

    battery_options = tuple(
        [
            {"name": "BAT-0", "nom_kWh": 0.0, "max_kW": 0.0, "max_ch_kW": 0.0, "max_dis_kW": 0.0, "price_COP": 0.0},
            *[row.to_dict() for _, row in bundle.battery_catalog.iterrows()],
        ]
    )
    task = DeterministicScanTask(
        task_index=0,
        k_wp=15.0,
        cfg=bundle.config,
        inv_catalog=bundle.inverter_catalog,
        battery_options=battery_options,
        demand_profile_7x24=bundle.demand_profile_7x24,
        day_weights=bundle.day_weights,
        solar_profile=bundle.solar_profile,
        hsp_month=bundle.hsp_month,
        demand_month_factor=bundle.demand_month_factor,
        cop_kwp_table=bundle.cop_kwp_table,
        cop_kwp_table_others=bundle.cop_kwp_table_others,
    )

    result = evaluate_deterministic_scan_task(task)

    assert calls == [(bundle.config["PR"], "premium")]
    assert result.discarded_point is None
    assert len(result.detail_rows) > 1
