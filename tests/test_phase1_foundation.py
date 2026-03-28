from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

import services.scenario_runner as scenario_runner
from services import (
    add_scenario,
    build_assumption_sections,
    bootstrap_client_session,
    commit_client_session,
    collect_config_updates,
    configure_runtime_environment,
    create_scenario_record,
    fingerprint_deterministic_input,
    frame_from_rows,
    get_deterministic_cache,
    list_projects,
    load_example_config,
    open_project,
    project_exports_root,
    projects_root,
    prune_session_states,
    rebuild_bundle_from_ui,
    resolve_client_session,
    resolve_deterministic_scan,
    run_deterministic_scan_tasks,
    run_scenario_scan,
    save_project,
    set_active_scenario,
    set_design_comparison_candidates,
    update_scenario_risk_config,
    update_selected_candidate,
    update_scenario_bundle,
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


def _assumption_field_value(sections: list[dict], field_key: str):
    for section in sections:
        for bucket in ("basic", "advanced"):
            for field in section.get(bucket, []):
                if field.get("field") == field_key:
                    return field.get("value")
    raise AssertionError(f"Field {field_key!r} not found in assumption sections")


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
    assert payload["ui_mode"] == "simple"


def test_client_session_ui_mode_round_trips_and_falls_back_to_simple() -> None:
    client_state = bootstrap_client_session("es")

    assert client_state.ui_mode == "simple"
    assert type(client_state).from_payload(client_state.to_payload()).ui_mode == "simple"

    pro_state = replace(client_state, ui_mode="pro")
    admin_state = replace(client_state, ui_mode="admin")
    invalid_payload = {**client_state.to_payload(), "ui_mode": "internal"}

    assert type(client_state).from_payload(pro_state.to_payload()).ui_mode == "pro"
    assert type(client_state).from_payload(admin_state.to_payload()).ui_mode == "admin"
    assert type(client_state).from_payload(invalid_payload).ui_mode == "simple"


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

    noisy = replace(
        bundle,
        config={
            **bundle.config,
            "mc_PR_std": 0.9,
            "mc_buy_std": 0.8,
            "mc_n_simulations": 999,
            "mc_use_manual_kWp": True,
            "mc_manual_kWp": 22.5,
            "mc_battery_name": "BAT-TEST",
        },
    )
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
    assert first is not second
    assert first.best_candidate_key == second.best_candidate_key
    pdt.assert_frame_equal(first.candidates.reset_index(drop=True), second.candidates.reset_index(drop=True))


def test_deterministic_cache_get_returns_isolated_scan_result_copy() -> None:
    bundle = _fast_bundle()
    fingerprint = fingerprint_deterministic_input(bundle)
    original = resolve_deterministic_scan(bundle, allow_parallel=False)
    cached = get_deterministic_cache().get(fingerprint)

    assert cached is not None
    candidate_key = cached.best_candidate_key
    original_npv = float(cached.candidates.loc[0, "NPV_COP"])
    original_summary_npv = float(cached.candidate_details[candidate_key]["summary"]["cum_disc_final"])
    original_monthly_value = cached.candidate_details[candidate_key]["monthly"].iloc[0, 0]

    cached.candidates.loc[0, "NPV_COP"] = -1.0
    cached.candidate_details[candidate_key]["summary"]["cum_disc_final"] = -2.0
    cached.candidate_details[candidate_key]["monthly"].iloc[0, 0] = "MUTATED"

    fresh = get_deterministic_cache().get(fingerprint)

    assert fresh is not None
    assert fresh is not cached
    assert original is not fresh
    assert float(fresh.candidates.loc[0, "NPV_COP"]) == original_npv
    assert float(fresh.candidate_details[candidate_key]["summary"]["cum_disc_final"]) == original_summary_npv
    assert fresh.candidate_details[candidate_key]["monthly"].iloc[0, 0] == original_monthly_value


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
    assert (canonical_root / "Panel_Catalog.csv").exists()

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


def test_project_save_materializes_panel_technology_mode_without_persisting_derived_factor(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    base_bundle = _fast_bundle()
    config_table = base_bundle.config_table.copy()
    if not config_table.empty and "Item" in config_table.columns:
        config_table = config_table.loc[
            config_table["Item"].astype(str).str.strip() != "panel_technology_mode"
        ].copy()
    bundle = replace(
        base_bundle,
        config={**base_bundle.config, "panel_name": "__manual__", "panel_technology_mode": "premium"},
        config_table=config_table,
    )

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", bundle))
    saved = save_project(state, project_name="Proyecto Panel", language="es")

    config_csv = projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id / "Config.csv"
    persisted = pd.read_csv(config_csv)
    items = persisted["Item"].astype(str).str.strip().tolist()
    panel_row = persisted.loc[persisted["Item"].astype(str).str.strip() == "panel_technology_mode"].iloc[0]

    assert "panel_technology_mode" in items
    assert panel_row["Valor"] == "premium"
    assert "effective_pr" not in items
    assert "panel_generation_factor" not in items

    reopened = open_project(saved.project_slug)
    reopened_active = reopened.get_scenario(reopened.active_scenario_id)

    assert reopened_active is not None
    assert reopened_active.config_bundle.config["panel_name"] == "__manual__"
    assert reopened_active.config_bundle.config["panel_technology_mode"] == "premium"


def test_project_save_persists_selected_panel_name_and_panel_catalog(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    bundle = _fast_bundle()
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", bundle))
    saved = save_project(state, project_name="Proyecto Paneles", language="es")

    root = projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id
    config_csv = pd.read_csv(root / "Config.csv")
    panel_catalog_csv = pd.read_csv(root / "Panel_Catalog.csv")
    panel_row = config_csv.loc[config_csv["Item"].astype(str).str.strip() == "panel_name"].iloc[0]

    assert panel_row["Valor"] == bundle.config["panel_name"]
    assert panel_catalog_csv.empty is False

    reopened = open_project(saved.project_slug)
    reopened_active = reopened.get_scenario(reopened.active_scenario_id)

    assert reopened_active is not None
    assert reopened_active.config_bundle.config["panel_name"] == bundle.config["panel_name"]
    assert reopened_active.config_bundle.panel_catalog.empty is False


def test_manual_panel_mode_does_not_refresh_compatibility_rows_from_catalog_on_save(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    bundle = _fast_bundle()
    custom = replace(
        bundle,
        config={
            **bundle.config,
            "panel_name": "__manual__",
            "P_mod_W": 777.0,
            "Voc25": 58.0,
            "Vmp25": 47.0,
            "Isc": 15.5,
            "panel_technology_mode": "premium",
        },
    )

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", custom))
    saved = save_project(state, project_name="Proyecto Manual", language="es")
    config_csv = pd.read_csv(projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id / "Config.csv")
    values = {
        row["Item"].strip(): row["Valor"]
        for _, row in config_csv.iterrows()
        if isinstance(row.get("Item"), str)
    }

    assert values["panel_name"] == "__manual__"
    assert float(values["P_mod_W"]) == pytest.approx(777.0)
    assert float(values["Voc25"]) == pytest.approx(58.0)
    assert float(values["Vmp25"]) == pytest.approx(47.0)
    assert float(values["Isc"]) == pytest.approx(15.5)
    assert values["panel_technology_mode"] == "premium"


def test_invalid_real_panel_selection_does_not_overwrite_compatibility_rows_on_save(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    bundle = _fast_bundle()
    invalid = replace(
        bundle,
        config={
            **bundle.config,
            "panel_name": "Panel inexistente",
            "P_mod_W": 711.0,
            "Voc25": 57.0,
            "Vmp25": 46.0,
            "Isc": 15.1,
            "panel_technology_mode": "premium",
        },
    )

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", invalid))
    saved = save_project(state, project_name="Proyecto Panel Invalido", language="es")
    config_csv = pd.read_csv(projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id / "Config.csv")
    values = {
        row["Item"].strip(): row["Valor"]
        for _, row in config_csv.iterrows()
        if isinstance(row.get("Item"), str)
    }

    assert values["panel_name"] == "Panel inexistente"
    assert float(values["P_mod_W"]) == pytest.approx(711.0)
    assert float(values["Voc25"]) == pytest.approx(57.0)
    assert float(values["Vmp25"]) == pytest.approx(46.0)
    assert float(values["Isc"]) == pytest.approx(15.1)
    assert values["panel_technology_mode"] == "premium"


def test_ui_mode_does_not_persist_into_project_manifest(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    saved = save_project(state, project_name="Proyecto Demo", language="es")
    manifest_payload = read_project_manifest(saved.project_slug).to_payload()
    raw = json.dumps(manifest_payload, ensure_ascii=False)

    assert "ui_mode" not in raw


def test_apply_no_battery_edit_persists_through_project_save_and_reopen(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    bundle = _fast_bundle()
    seeded_bundle = replace(bundle, config={**bundle.config, "include_battery": True, "optimize_battery": False, "battery_name": ""})
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", seeded_bundle))
    state = save_project(state, project_name="Proyecto Sin Bateria", language="es")

    reopened = open_project(state.project_slug)
    active = reopened.get_scenario()
    assert active is not None
    assert active.config_bundle.config["battery_name"] == ""

    config_updates = collect_config_updates(
        [{"field": "include_battery"}, {"field": "battery_name"}],
        [False, ""],
        active.config_bundle.config,
    )
    assert config_updates["include_battery"] is False

    rebuilt_bundle = rebuild_bundle_from_ui(
        active.config_bundle,
        config_updates=config_updates,
        inverter_catalog=active.config_bundle.inverter_catalog,
        battery_catalog=active.config_bundle.battery_catalog,
        demand_profile=frame_from_rows(active.config_bundle.demand_profile_table.to_dict("records"), list(active.config_bundle.demand_profile_table.columns)),
        demand_profile_weights=frame_from_rows(active.config_bundle.demand_profile_weights_table.to_dict("records"), list(active.config_bundle.demand_profile_weights_table.columns)),
        demand_profile_general=frame_from_rows(active.config_bundle.demand_profile_general_table.to_dict("records"), list(active.config_bundle.demand_profile_general_table.columns)),
        month_profile=frame_from_rows(active.config_bundle.month_profile_table.to_dict("records"), list(active.config_bundle.month_profile_table.columns)),
        sun_profile=frame_from_rows(active.config_bundle.sun_profile_table.to_dict("records"), list(active.config_bundle.sun_profile_table.columns)),
        cop_kwp_table=frame_from_rows(active.config_bundle.cop_kwp_table.to_dict("records"), list(active.config_bundle.cop_kwp_table.columns)),
        cop_kwp_table_others=frame_from_rows(active.config_bundle.cop_kwp_table_others.to_dict("records"), list(active.config_bundle.cop_kwp_table_others.columns)),
    )
    updated_state = update_scenario_bundle(reopened, active.scenario_id, rebuilt_bundle)
    updated_active = updated_state.get_scenario(active.scenario_id)
    assert updated_active is not None
    assert updated_active.config_bundle.config["include_battery"] is False

    sections = build_assumption_sections(updated_active.config_bundle, lang="es", show_all=False)
    assert _assumption_field_value(sections, "include_battery") is False

    saved_again = save_project(updated_state, project_name=updated_state.project_name, language="es")
    reopened_again = open_project(saved_again.project_slug)
    reloaded_active = reopened_again.get_scenario(active.scenario_id)
    assert reloaded_active is not None
    assert reloaded_active.config_bundle.config["include_battery"] is False
    assert reloaded_active.config_bundle.config["battery_name"] == ""


def test_workbench_assumptions_can_hide_monte_carlo_group() -> None:
    sections = build_assumption_sections(
        load_example_config(),
        lang="en",
        show_all=True,
        exclude_groups={"Monte Carlo"},
    )

    groups = {section["group"] for section in sections}
    fields = {
        field["field"]
        for section in sections
        for bucket in ("basic", "advanced")
        for field in section.get(bucket, [])
    }

    assert "Monte Carlo" not in groups
    assert "mc_PR_std" not in fields
    assert "mc_n_simulations" not in fields


def test_risk_config_updates_preserve_scan_and_round_trip(tmp_path, monkeypatch) -> None:
    _patch_user_root(monkeypatch, tmp_path)

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    clean = state.get_scenario()
    assert clean is not None and clean.scan_result is not None

    original_scan = clean.scan_result
    original_candidate = clean.selected_candidate_key
    original_run_at = clean.last_run_at
    battery_name = str(clean.config_bundle.battery_catalog.iloc[0]["name"])

    updated = update_scenario_risk_config(
        state,
        clean.scenario_id,
        {
            "mc_PR_std": 0.12,
            "mc_buy_std": 0.08,
            "mc_n_simulations": 250,
            "mc_use_manual_kWp": True,
            "mc_manual_kWp": 18.5,
            "mc_battery_name": battery_name,
        },
    )
    updated_scenario = updated.get_scenario(clean.scenario_id)
    assert updated_scenario is not None

    assert updated_scenario.dirty is False
    assert updated_scenario.scan_result is original_scan
    assert updated_scenario.selected_candidate_key == original_candidate
    assert updated_scenario.last_run_at == original_run_at
    assert updated_scenario.config_bundle.config["mc_manual_kWp"] == pytest.approx(18.5)
    assert updated_scenario.config_bundle.config["mc_battery_name"] == battery_name
    assert updated.project_dirty is True

    saved = save_project(updated, project_name="Risk Config Demo", language="en")
    reopened = open_project(saved.project_slug)
    reopened_scenario = reopened.get_scenario(clean.scenario_id)
    assert reopened_scenario is not None
    assert reopened_scenario.dirty is False
    assert reopened_scenario.scan_result is None
    assert reopened_scenario.config_bundle.config["mc_PR_std"] == pytest.approx(0.12)
    assert reopened_scenario.config_bundle.config["mc_n_simulations"] == 250
    assert reopened_scenario.config_bundle.config["mc_use_manual_kWp"] is True
    assert reopened_scenario.config_bundle.config["mc_manual_kWp"] == pytest.approx(18.5)
    assert reopened_scenario.config_bundle.config["mc_battery_name"] == battery_name


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
