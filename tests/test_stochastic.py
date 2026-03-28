from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pandas.testing as pdt
import pytest

from services import (
    MONTE_CARLO_WARNING_THRESHOLD,
    load_example_config,
    prepare_risk_views,
    run_monte_carlo,
    run_scan,
    summarize_monte_carlo,
)


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
        "mc_n_simulations": 12,
    }
    return replace(bundle, config=config)


def _payback_sparse_bundle():
    bundle = _fast_bundle()
    config = {
        **bundle.config,
        "years": 1,
        "price_total_COP": 300_000_000.0,
        "price_per_kWp_COP": 15_000_000.0,
        "buy_tariff_COP_kWh": 300.0,
        "sell_tariff_COP_kWh": 50.0,
    }
    return replace(bundle, config=config)


def test_same_seed_reproduces_samples_and_summary() -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    candidate_key = baseline.best_candidate_key

    first = run_monte_carlo(bundle, selected_candidate_key=candidate_key, seed=7, n_simulations=10, return_samples=True, baseline_scan=baseline)
    second = run_monte_carlo(bundle, selected_candidate_key=candidate_key, seed=7, n_simulations=10, return_samples=True, baseline_scan=baseline)

    pdt.assert_frame_equal(first.samples.reset_index(drop=True), second.samples.reset_index(drop=True))
    pdt.assert_frame_equal(first.views.percentile_table.reset_index(drop=True), second.views.percentile_table.reset_index(drop=True))
    assert first.summary.npv.mean == second.summary.npv.mean
    assert first.risk_metrics == second.risk_metrics


def test_different_seed_changes_sampled_outcomes() -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    candidate_key = baseline.best_candidate_key

    first = run_monte_carlo(bundle, selected_candidate_key=candidate_key, seed=7, n_simulations=10, return_samples=True, baseline_scan=baseline)
    second = run_monte_carlo(bundle, selected_candidate_key=candidate_key, seed=8, n_simulations=10, return_samples=True, baseline_scan=baseline)

    assert not first.samples.equals(second.samples)


def test_monte_carlo_does_not_change_deterministic_baseline() -> None:
    bundle = _fast_bundle()
    before = run_scan(bundle)
    before_bundle_config = deepcopy(bundle.config)

    run_monte_carlo(bundle, selected_candidate_key=before.best_candidate_key, seed=3, n_simulations=8, return_samples=False, baseline_scan=before)
    after = run_scan(bundle)

    assert bundle.config == before_bundle_config
    assert before.best_candidate_key == after.best_candidate_key
    pdt.assert_frame_equal(
        before.candidates.sort_values("candidate_key").reset_index(drop=True),
        after.candidates.sort_values("candidate_key").reset_index(drop=True),
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"selected_candidate_key": None}, "diseño factible"),
        ({"selected_candidate_key": "missing"}, "diseño seleccionado"),
        ({"selected_candidate_key": "unused", "mode": "optimal_per_draw"}, "todavía no está disponible"),
        ({"selected_candidate_key": "unused", "seed": -1}, "semilla"),
        ({"selected_candidate_key": "unused", "n_simulations": 0}, "simulaciones"),
    ],
)
def test_validation_failures_are_explicit(kwargs, message) -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    if kwargs.get("selected_candidate_key") == "unused":
        kwargs["selected_candidate_key"] = baseline.best_candidate_key
    if kwargs.get("selected_candidate_key") == "missing":
        pass

    with pytest.raises(ValueError, match=message):
        run_monte_carlo(bundle, baseline_scan=baseline, **kwargs)


def test_result_shape_and_raw_sample_toggle() -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    result = run_monte_carlo(bundle, selected_candidate_key=baseline.best_candidate_key, seed=5, n_simulations=9, return_samples=False, baseline_scan=baseline)

    assert result.samples is None
    assert result.seed == 5
    assert result.n_simulations == 9
    assert result.selected_candidate_key == baseline.best_candidate_key
    assert set(result.active_uncertainty) == {"mc_PR_std", "mc_buy_std", "mc_sell_std", "mc_demand_std"}
    assert 0.0 <= result.risk_metrics.probability_negative_npv <= 1.0
    assert 0.0 <= result.risk_metrics.probability_payback_within_horizon <= 1.0
    assert result.summary.npv.n_total == 9
    assert result.summary.npv.p5 <= result.summary.npv.p50 <= result.summary.npv.p95


def test_manual_risk_overrides_change_simulated_design_metadata() -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    selected_detail = baseline.candidate_details[baseline.best_candidate_key]
    manual_k_wp = float(selected_detail["kWp"]) + 1.234
    available_batteries = [str(value) for value in bundle.battery_catalog["name"].astype(str).tolist()]
    battery_name = next((name for name in available_batteries if name != str(selected_detail["battery_name"])), available_batteries[0])
    overridden_bundle = replace(
        bundle,
        config={
            **bundle.config,
            "mc_use_manual_kWp": True,
            "mc_manual_kWp": manual_k_wp,
            "mc_battery_name": battery_name,
        },
    )

    result = run_monte_carlo(
        overridden_bundle,
        selected_candidate_key=baseline.best_candidate_key,
        seed=9,
        n_simulations=6,
        return_samples=True,
        baseline_scan=baseline,
    )

    assert result.selected_candidate_key == baseline.best_candidate_key
    assert result.selected_kWp != float(selected_detail["kWp"])
    assert result.selected_battery == battery_name
    assert result.samples is not None
    assert set(result.samples["kWp"]) == {result.selected_kWp}
    assert set(result.samples["battery"]) == {battery_name}


def test_payback_semantics_use_nan_for_missing_cases() -> None:
    bundle = _payback_sparse_bundle()
    baseline = run_scan(bundle)
    result = run_monte_carlo(bundle, selected_candidate_key=baseline.best_candidate_key, seed=2, n_simulations=6, return_samples=True, baseline_scan=baseline)

    payback = result.summary.payback_years
    assert payback.n_total == 6
    assert payback.n_finite + payback.n_missing == 6
    assert payback.percentiles_over_finite_values is True
    if payback.n_finite == 0:
        assert payback.mean is None
        assert payback.p50 is None
        assert result.risk_metrics.probability_payback_within_horizon == 0.0
    else:
        assert payback.p5 <= payback.p50 <= payback.p95


def test_prepare_risk_views_returns_compact_frames() -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    result = run_monte_carlo(bundle, selected_candidate_key=baseline.best_candidate_key, seed=11, n_simulations=15, return_samples=True, baseline_scan=baseline)

    views = prepare_risk_views(result, histogram_bins=8, ecdf_points=25)

    assert set(views.histograms) == {"NPV_COP", "payback_years"}
    assert set(views.ecdfs) == {"NPV_COP", "payback_years"}
    npv_hist = views.histograms["NPV_COP"]
    npv_ecdf = views.ecdfs["NPV_COP"]
    assert set(["bin_left", "bin_right", "count", "probability"]).issubset(npv_hist.columns)
    assert npv_ecdf["cdf"].is_monotonic_increasing
    assert len(npv_ecdf) <= 25
    assert "metric" in views.percentile_table.columns


def test_summarize_monte_carlo_returns_summary_object() -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    result = run_monte_carlo(bundle, selected_candidate_key=baseline.best_candidate_key, seed=13, n_simulations=7, return_samples=False, baseline_scan=baseline)

    summary = summarize_monte_carlo(result)
    assert summary is result.summary
    assert summary.annual_import_kwh.n_total == 7


def test_soft_warning_threshold_is_emitted(monkeypatch) -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)
    monkeypatch.setattr("services.stochastic_runner.MONTE_CARLO_WARNING_THRESHOLD", 5)

    result = run_monte_carlo(bundle, selected_candidate_key=baseline.best_candidate_key, seed=3, n_simulations=6, return_samples=False, baseline_scan=baseline)

    assert result.warnings
    assert "umbral recomendado" in result.warnings[0]
