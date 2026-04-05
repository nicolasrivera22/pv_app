from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import services.workspace_results_callbacks as results_callbacks
from services.candidate_financials import get_candidate_financial_snapshot_cache
from services import (
    ScenarioSessionState,
    add_scenario,
    bootstrap_client_session,
    build_results_explorer_dataset,
    commit_client_session,
    create_scenario_record,
    get_results_explorer_dataset_cache,
    load_example_config,
    run_scenario_scan,
)


def _fast_bundle():
    bundle = load_example_config()
    return replace(
        bundle,
        config={
            **bundle.config,
            "years": 5,
            "modules_span_each_side": 4,
            "kWp_min": 6.0,
            "kWp_max": 30.0,
        },
    )


def _session_payload(state, *, lang: str = "es") -> dict:
    return commit_client_session(bootstrap_client_session(lang), state).to_payload()


def _measure(label: str, fn) -> tuple[str, float]:
    started = perf_counter()
    fn()
    return label, perf_counter() - started


def main() -> None:
    get_results_explorer_dataset_cache().clear()
    get_candidate_financial_snapshot_cache().clear()

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Benchmark", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    active = state.get_scenario()
    if active is None:
        raise RuntimeError("No active scenario available for benchmark.")
    payload = _session_payload(state)

    timings: dict[str, float] = {}

    label, seconds = _measure("build_results_explorer_dataset_cold", lambda: build_results_explorer_dataset(active))
    timings[label] = seconds
    label, seconds = _measure("build_results_explorer_dataset_warm", lambda: build_results_explorer_dataset(active))
    timings[label] = seconds

    store = results_callbacks.sync_results_explorer_state(payload, "es", {})
    label, seconds = _measure("sync_results_explorer_state_warm", lambda: results_callbacks.sync_results_explorer_state(payload, "es", store))
    timings[label] = seconds
    label, seconds = _measure(
        "populate_results_explorer_controls_warm",
        lambda: results_callbacks.populate_results_explorer_controls(payload, "es", store),
    )
    timings[label] = seconds

    label, seconds = _measure("populate_results_warm", lambda: results_callbacks.populate_results(payload, "es", 5, store))
    timings[label] = seconds
    outputs = results_callbacks.populate_results(payload, "es", 5, store)
    options, selected_value, _disabled = results_callbacks.populate_results_explorer_controls(payload, "es", store)
    alternative_subset = next((option["value"] for option in options if option["value"] != selected_value), None)
    if alternative_subset is not None:
        original_ctx = results_callbacks.ctx
        try:
            results_callbacks.ctx = SimpleNamespace(triggered_id="results-battery-family-dropdown")
            label, seconds = _measure(
                "persist_selected_candidate_slicer_warm",
                lambda: results_callbacks.persist_selected_candidate(
                    alternative_subset,
                    outputs[13],
                    None,
                    5,
                    store,
                    outputs[11],
                    payload,
                    "es",
                ),
            )
            timings[label] = seconds
        finally:
            results_callbacks.ctx = original_ctx

    print(
        json.dumps(
            {
                "scenario_id": active.scenario_id,
                "scan_fingerprint": active.scan_fingerprint,
                "candidate_count": len(active.scan_result.candidate_details) if active.scan_result is not None else 0,
                "timings_seconds": timings,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
