from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from services import (
    ScenarioSessionState,
    add_scenario,
    build_risk_metadata_rows,
    build_risk_result_store_payload,
    clear_missing_risk_result_payload,
    clear_expired_risk_results,
    clear_risk_results,
    create_scenario_record,
    get_risk_result,
    load_example_config,
    prepare_percentile_table_for_display,
    ready_risk_scenarios,
    resolve_default_risk_candidate,
    resolve_default_risk_scenario,
    run_monte_carlo,
    run_scenario_scan,
    store_risk_result,
    tr,
    validate_risk_run_inputs,
)

_RISK_CHARTS_SPEC = importlib.util.spec_from_file_location(
    "risk_charts_for_tests",
    Path(__file__).resolve().parents[1] / "components" / "risk_charts.py",
)
assert _RISK_CHARTS_SPEC is not None and _RISK_CHARTS_SPEC.loader is not None
_RISK_CHARTS = importlib.util.module_from_spec(_RISK_CHARTS_SPEC)
_RISK_CHARTS_SPEC.loader.exec_module(_RISK_CHARTS)
build_ecdf_figure = _RISK_CHARTS.build_ecdf_figure
build_histogram_figure = _RISK_CHARTS.build_histogram_figure


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
        "mc_n_simulations": 10,
    }
    return replace(bundle, config=config)


def _run_ready_scenario(name: str = "Risk base"):
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record(name, _fast_bundle()))
    return run_scenario_scan(state, state.active_scenario_id)


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_risk_results()
    yield
    clear_risk_results()


def test_translation_helper_supports_spanish_and_fallback() -> None:
    assert tr("nav.risk", "es") == "Riesgo"
    assert tr("risk.page_title", "fr") == tr("risk.page_title", "es")
    assert tr("missing.translation", "es") == "missing.translation"


def test_default_risk_selection_prefers_selected_candidate_then_best() -> None:
    state = _run_ready_scenario()
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None

    non_best = next(key for key in scenario.scan_result.candidate_details if key != scenario.scan_result.best_candidate_key)
    selected = replace(scenario, selected_candidate_key=non_best)
    assert resolve_default_risk_candidate(selected) == non_best

    fallback = replace(scenario, selected_candidate_key="missing")
    assert resolve_default_risk_candidate(fallback) == scenario.scan_result.best_candidate_key
    assert resolve_default_risk_scenario(state, preferred_id="missing") == scenario.scenario_id


def test_ready_scenarios_filter_and_validation_are_explicit() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Dirty", _fast_bundle()))
    scenario = state.get_scenario()
    assert scenario is not None
    assert ready_risk_scenarios(state) == []

    issues = validate_risk_run_inputs(scenario, None, 0, -1, lang="en")
    assert any("fresh deterministic run" in issue for issue in issues)
    assert any("design" in issue.lower() for issue in issues)
    assert any("Simulation count" in issue for issue in issues)
    assert any("Seed" in issue for issue in issues)


def test_browser_payload_stays_compact() -> None:
    payload = build_risk_result_store_payload(
        result_id="mc-123",
        scenario_id="scenario-1",
        candidate_key="12.000::BAT-0",
        n_simulations=100,
        seed=0,
        retain_samples=False,
        mc_settings={"mc_PR_std": 0.1},
        status="ok",
        errors=[],
        warnings=["warn"],
    )

    assert set(payload) == {
        "result_id",
        "scenario_id",
        "candidate_key",
        "n_simulations",
        "seed",
        "retain_samples",
        "mc_settings",
        "status",
        "errors",
        "warnings",
    }
    assert "samples" not in payload
    assert "views" not in payload


def test_missing_result_payload_clears_stale_reference_with_friendly_message() -> None:
    payload = clear_missing_risk_result_payload(
        {
            "result_id": "mc-123",
            "scenario_id": "scenario-1",
            "candidate_key": "12.000::BAT-0",
            "n_simulations": 100,
            "seed": 0,
            "retain_samples": True,
            "mc_settings": {"mc_PR_std": 0.1},
        },
        lang="es",
    )

    assert payload["result_id"] is None
    assert payload["retain_samples"] is True
    assert payload["mc_settings"] == {"mc_PR_std": 0.1}
    assert "ya no está disponible" in payload["status"]
    assert payload["errors"]


def test_registry_stores_server_side_results_and_prunes() -> None:
    state = _run_ready_scenario()
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None
    candidate_key = resolve_default_risk_candidate(scenario)

    first = run_monte_carlo(
        scenario.config_bundle,
        selected_candidate_key=candidate_key,
        seed=1,
        n_simulations=6,
        return_samples=True,
        baseline_scan=scenario.scan_result,
    )
    second = run_monte_carlo(
        scenario.config_bundle,
        selected_candidate_key=candidate_key,
        seed=2,
        n_simulations=6,
        return_samples=True,
        baseline_scan=scenario.scan_result,
    )

    first_id = store_risk_result(first)
    second_id = store_risk_result(second)
    assert get_risk_result(first_id) is first
    assert get_risk_result(first_id).samples is not None

    clear_expired_risk_results(max_entries=1)
    assert get_risk_result(first_id) is first
    assert get_risk_result(second_id) is None


def test_risk_display_helpers_build_metadata_tables_and_figures() -> None:
    state = _run_ready_scenario()
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None
    candidate_key = resolve_default_risk_candidate(scenario)

    result = run_monte_carlo(
        scenario.config_bundle,
        selected_candidate_key=candidate_key,
        seed=3,
        n_simulations=8,
        return_samples=False,
        baseline_scan=scenario.scan_result,
    )
    result_id = store_risk_result(result)
    stored = get_risk_result(result_id)
    assert stored is not None

    metadata = build_risk_metadata_rows(scenario, stored, lang="en")
    percentile_table = prepare_percentile_table_for_display(stored.views, lang="en")

    assert list(metadata.columns) == ["label", "value"]
    assert "Scenario" in metadata["label"].tolist()
    assert "NPV [COP]" in percentile_table["metric"].tolist()

    npv_hist = build_histogram_figure(
        stored.views.histograms["NPV_COP"],
        title="NPV histogram",
        x_title="NPV (COP)",
        lang="en",
    )
    payback_ecdf = build_ecdf_figure(
        stored.views.ecdfs["payback_years"],
        title="Payback ECDF",
        x_title="Payback (years)",
        lang="en",
        empty_message="No payback",
    )

    assert len(npv_hist.data) == 1
    assert npv_hist.layout.title.text == "NPV histogram"
    assert payback_ecdf.layout.title.text == "Payback ECDF"
