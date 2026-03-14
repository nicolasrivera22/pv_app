from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pandas.testing as pdt
import pytest

import services.scenario_runner as scenario_runner
from services import (
    add_scenario,
    bootstrap_client_session,
    commit_client_session,
    configure_runtime_environment,
    create_scenario_record,
    fingerprint_deterministic_input,
    get_deterministic_cache,
    list_projects,
    load_example_config,
    open_project,
    project_exports_root,
    projects_root,
    prune_session_states,
    resolve_client_session,
    resolve_deterministic_scan,
    run_deterministic_scan_tasks,
    run_scenario_scan,
    save_project,
    set_active_scenario,
    set_design_comparison_candidates,
    update_selected_candidate,
)
from services.cache import DETERMINISTIC_CACHE_SCHEMA_VERSION
from services.project_io import read_project_manifest
from services.risk_registry import clear_risk_results
from services.scenario_session import hydrate_scenario_scan
from services.session_state import clear_session_states, get_session_state
from services.types import ScenarioSessionState


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


@pytest.fixture(autouse=True)
def _clear_runtime_state():
    clear_session_states()
    clear_risk_results()
    get_deterministic_cache().clear()
    yield
    clear_session_states()
    clear_risk_results()
    get_deterministic_cache().clear()


def _patch_user_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("services.runtime_paths.user_root", lambda: tmp_path)


def test_client_session_payload_omits_heavy_deterministic_blobs() -> None:
    client_state = bootstrap_client_session("es")
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)

    payload = commit_client_session(client_state, state).to_payload()
    raw = json.dumps(payload, ensure_ascii=False)

    assert "config_bundle" not in raw
    assert "scan_result" not in raw
    assert "candidate_details" not in raw
    assert "monthly" not in raw
    assert payload["active_scenario_id"] == state.active_scenario_id
    assert payload["selected_candidate_keys"]


def test_session_lifecycle_reuses_refresh_id_and_reopens_project_when_registry_missing(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    first = bootstrap_client_session("es")
    second = bootstrap_client_session("es")
    assert first.session_id != second.session_id

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = save_project(state, project_name="Demo", language="es")
    client_state = commit_client_session(first, state)

    refreshed_client, refreshed_state = resolve_client_session(client_state.to_payload(), language="es")
    assert refreshed_client.session_id == client_state.session_id
    assert refreshed_state.project_slug == state.project_slug

    clear_session_states()
    reopened_client, reopened_state = resolve_client_session(client_state.to_payload(), language="es")
    assert reopened_client.session_id != client_state.session_id
    assert reopened_state.project_slug == state.project_slug
    assert len(reopened_state.scenarios) == 1


def test_session_registry_prunes_by_lru_and_idle_age(monkeypatch) -> None:
    first = bootstrap_client_session("es")
    second = bootstrap_client_session("es")
    third = bootstrap_client_session("es")

    assert get_session_state(first.session_id) is not None
    prune_session_states(max_entries=2, idle_ttl_seconds=10_000)
    assert get_session_state(first.session_id) is not None
    assert get_session_state(second.session_id) is None
    assert get_session_state(third.session_id) is not None

    current_time = [100.0]
    monkeypatch.setattr("services.session_state.time.time", lambda: current_time[0])
    stale = bootstrap_client_session("es")
    current_time[0] = 200.0
    prune_session_states(max_entries=10, idle_ttl_seconds=50)
    assert get_session_state(stale.session_id) is None


def test_deterministic_fingerprint_tracks_material_inputs_and_ignores_monte_carlo_fields(monkeypatch) -> None:
    bundle = _fast_bundle()
    baseline = fingerprint_deterministic_input(bundle)

    noisy = replace(bundle, config={**bundle.config, "mc_PR_std": 0.9, "mc_buy_std": 0.8, "mc_n_simulations": 999})
    assert fingerprint_deterministic_input(noisy) == baseline

    repriced = replace(bundle, cop_kwp_table=bundle.cop_kwp_table.assign(PRECIO_POR_KWP=bundle.cop_kwp_table["PRECIO_POR_KWP"] + 1))
    assert fingerprint_deterministic_input(repriced) != baseline

    monkeypatch.setattr("services.cache.DETERMINISTIC_CACHE_SCHEMA_VERSION", DETERMINISTIC_CACHE_SCHEMA_VERSION + 1)
    assert fingerprint_deterministic_input(bundle) != baseline


def test_resolve_deterministic_scan_reuses_cache(monkeypatch) -> None:
    bundle = _fast_bundle()
    call_count = {"count": 0}
    original = scenario_runner._build_scan_result

    def _wrapped(config_bundle, *, allow_parallel):
        call_count["count"] += 1
        return original(config_bundle, allow_parallel=allow_parallel)

    monkeypatch.setattr(scenario_runner, "_build_scan_result", _wrapped)

    first = resolve_deterministic_scan(bundle, allow_parallel=False)
    second = resolve_deterministic_scan(bundle, allow_parallel=False)

    assert call_count["count"] == 1
    assert first is second


def test_project_round_trip_uses_canonical_csv_tables_and_restores_workspace(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    base = state.get_scenario()
    assert base is not None and base.scan_result is not None
    alt_key = next(key for key in base.scan_result.candidate_details if key != base.scan_result.best_candidate_key)
    state = update_selected_candidate(state, base.scenario_id, alt_key)
    state = set_design_comparison_candidates(state, base.scenario_id, list(base.scan_result.candidate_details)[:2])

    variant_bundle = replace(base.config_bundle, config={**base.config_bundle.config, "buy_tariff_COP_kWh": 1050.0})
    state = add_scenario(state, create_scenario_record("Variante", variant_bundle), make_active=True)
    state = set_active_scenario(state, base.scenario_id)

    saved = save_project(state, project_name="Proyecto Demo", language="es")
    manifest = read_project_manifest(saved.project_slug)
    canonical_root = projects_root() / saved.project_slug / "inputs" / base.scenario_id

    assert manifest.name == "Proyecto Demo"
    assert (canonical_root / "Config.csv").exists()
    assert (canonical_root / "Inversor_Catalog.csv").exists()
    assert (canonical_root / "Battery_Catalog.csv").exists()

    reopened = open_project(saved.project_slug)
    reopened_base = reopened.get_scenario(base.scenario_id)
    assert reopened.project_dirty is False
    assert reopened.project_name == "Proyecto Demo"
    assert reopened.active_scenario_id == base.scenario_id
    assert reopened.design_comparison_candidate_keys[base.scenario_id]
    assert reopened_base is not None
    assert reopened_base.scan_result is None
    assert reopened_base.selected_candidate_key == alt_key
    assert reopened_base.dirty is False

    hydrated = hydrate_scenario_scan(reopened, base.scenario_id)
    hydrated_base = hydrated.get_scenario(base.scenario_id)
    assert hydrated_base is not None and hydrated_base.scan_result is not None
    assert hydrated_base.selected_candidate_key == alt_key


def test_project_dirty_only_tracks_persisted_workspace_state(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = save_project(state, project_name="Demo", language="es")
    assert state.project_dirty is False

    clean = run_scenario_scan(state, state.active_scenario_id)
    assert clean.project_dirty is False

    variant = add_scenario(clean, create_scenario_record("Variant", _fast_bundle()))
    saved_again = save_project(variant, project_name="Demo", language="es")
    active_switched = set_active_scenario(saved_again, saved_again.scenarios[0].scenario_id)
    assert active_switched.project_dirty is True

    client = bootstrap_client_session("es")
    committed = commit_client_session(client, saved_again)
    _, resolved_state = resolve_client_session(committed.to_payload(), language="en")
    assert resolved_state.project_dirty is False


def test_runtime_paths_create_project_workspace_and_runtime_cache(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)

    root = projects_root()
    exports = project_exports_root("demo")
    configure_runtime_environment()

    assert root == (tmp_path / "proyectos").resolve()
    assert exports == (tmp_path / "proyectos" / "demo" / "exports" / "Resultados").resolve()
    assert Path(os.environ["MPLCONFIGDIR"]).exists()


def test_parallel_deterministic_executor_matches_serial_and_falls_back(monkeypatch) -> None:
    bundle = _fast_bundle()
    monkeypatch.setattr("services.deterministic_executor.sys.frozen", False, raising=False)

    seed_serial, serial_rows = run_deterministic_scan_tasks(bundle, allow_parallel=False, max_workers=1)
    seed_parallel, parallel_rows = run_deterministic_scan_tasks(bundle, allow_parallel=True, max_workers=2)

    assert seed_serial == seed_parallel
    assert len(serial_rows) == len(parallel_rows)
    for left, right in zip(serial_rows, parallel_rows):
        assert left["kWp"] == right["kWp"]
        assert left["battery"]["name"] == right["battery"]["name"]
        assert left["summary"]["cum_disc_final"] == pytest.approx(right["summary"]["cum_disc_final"])
        assert left["summary"]["payback_years"] == right["summary"]["payback_years"]
        pdt.assert_frame_equal(left["df"].reset_index(drop=True), right["df"].reset_index(drop=True))

    monkeypatch.setattr("services.deterministic_executor._run_tasks_parallel", lambda tasks, max_workers: (_ for _ in ()).throw(RuntimeError("boom")))
    fallback_seed, fallback_rows = run_deterministic_scan_tasks(bundle, allow_parallel=True, max_workers=2)
    assert fallback_seed == seed_serial
    assert len(fallback_rows) == len(serial_rows)


def test_list_projects_reads_saved_manifests(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    saved = save_project(state, project_name="Proyecto Uno", language="es")

    manifests = list_projects()

    assert [manifest.slug for manifest in manifests] == [saved.project_slug]
