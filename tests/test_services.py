from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pandas.testing as pdt

from services import ensure_template, load_config_from_excel, load_example_config, run_scan, run_scenario


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


def test_run_scenario_shapes_outputs() -> None:
    bundle = _fast_bundle()
    scenario = run_scenario(bundle)

    assert scenario.kpis["best_kWp"] > 0
    assert "selected_battery" in scenario.kpis
    assert "NPV" in scenario.kpis
    assert set(["Año_mes", "PV to load", "Battery to load", "Grid import"]).issubset(scenario.monthly_balance.columns)
    assert set(["Año_mes", "cumulative_npv", "monthly_savings"]).issubset(scenario.cash_flow.columns)
    assert isinstance(scenario.npv_curve, pd.DataFrame)


def test_scan_payload_round_trip_preserves_self_consumption_ratio() -> None:
    scan = run_scan(_fast_bundle())
    restored = type(scan).from_payload(scan.to_payload())

    assert restored.best_candidate_key == scan.best_candidate_key
    assert "self_consumption_ratio" in restored.candidate_details[restored.best_candidate_key]


def test_template_round_trip(tmp_path) -> None:
    template_path = tmp_path / "PV_inputs_template.xlsx"
    ensure_template(template_path)

    bundle = load_config_from_excel(template_path)

    assert bundle.inverter_catalog.empty is False
    assert bundle.battery_catalog.empty is False
    assert bundle.issues is not None
