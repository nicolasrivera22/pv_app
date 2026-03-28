from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from services import (
    ScenarioSessionState,
    add_scenario,
    bootstrap_client_session,
    clear_all_admin_session_access,
    clear_session_states,
    clear_workspace_drafts,
    commit_client_session,
    create_scenario_record,
    grant_admin_session_access,
    load_example_config,
    open_project,
    resolve_client_session,
    save_project,
    set_admin_pin,
)
from services.project_io import projects_root
from services.workspace_admin_callbacks import apply_admin_edits, sync_economics_hardware_costs


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


def _admin_client_state(lang: str = "es"):
    return replace(bootstrap_client_session(lang), ui_mode="admin")


def _patch_user_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    monkeypatch.setattr("services.runtime_paths.user_root", lambda: tmp_path)


@pytest.fixture(autouse=True)
def _clear_runtime_state():
    clear_all_admin_session_access()
    clear_session_states()
    clear_workspace_drafts()
    yield
    clear_all_admin_session_access()
    clear_session_states()
    clear_workspace_drafts()


def _admin_payload(monkeypatch, tmp_path: Path):
    _patch_user_root(monkeypatch, tmp_path)
    client_state = _admin_client_state("es")
    set_admin_pin("2468")
    grant_admin_session_access(client_state.session_id)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None
    return client_state, state, active, payload


def test_example_bundle_exposes_seeded_economics_tables_and_panel_costs() -> None:
    bundle = load_example_config()

    assert bundle.economics_cost_items_table.empty is False
    assert bundle.economics_price_items_table.empty is False
    assert {"Panel hardware", "Inverter hardware", "Battery hardware"}.issubset(
        set(bundle.economics_cost_items_table["name"].astype(str))
    )
    assert "price_COP" in bundle.panel_catalog.columns
    assert float(bundle.panel_catalog.loc[0, "price_COP"]) >= 0


def test_apply_admin_edits_persists_economics_tables_and_normalizes_percent_inputs(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Economics Admin", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    economics_cost_rows = active.config_bundle.economics_cost_items_table.to_dict("records")
    economics_price_rows = active.config_bundle.economics_price_items_table.to_dict("records")
    economics_cost_rows[-1] = {**economics_cost_rows[-1], "value": 12}
    economics_price_rows[-1] = {**economics_price_rows[-1], "value": 19}

    next_payload, _status = apply_admin_edits(
        1,
        payload,
        "Proyecto Economics Admin",
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        active.config_bundle.cop_kwp_table.to_dict("records"),
        active.config_bundle.cop_kwp_table_others.to_dict("records"),
        economics_cost_rows,
        economics_price_rows,
        "es",
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    assert float(updated_active.config_bundle.economics_cost_items_table.iloc[-1]["value"]) == pytest.approx(0.12)
    assert float(updated_active.config_bundle.economics_price_items_table.iloc[-1]["value"]) == pytest.approx(0.19)

    reopened = open_project(updated_state.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert float(reopened_active.config_bundle.economics_cost_items_table.iloc[-1]["value"]) == pytest.approx(0.12)
    assert float(reopened_active.config_bundle.economics_price_items_table.iloc[-1]["value"]) == pytest.approx(0.19)


def test_open_project_without_economics_csv_defaults_new_tables(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    saved = save_project(state, project_name="Proyecto Legacy Economics", language="es")
    root = projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id
    (root / "Economics_Cost_Items.csv").unlink()
    (root / "Economics_Price_Items.csv").unlink()

    reopened = open_project(saved.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert reopened_active.config_bundle.economics_cost_items_table.empty is False
    assert reopened_active.config_bundle.economics_price_items_table.empty is False


def test_sync_economics_hardware_costs_seeds_from_current_catalogs(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _admin_payload(monkeypatch, tmp_path)

    inverter_rows = [
        {"name": "INV-COST", "AC_kW": 10.0, "Vmppt_min": 200, "Vmppt_max": 800, "Vdc_max": 1000, "Imax_mppt": 18, "n_mppt": 2, "price_COP": 9_000_000},
    ]
    battery_rows = [
        {"name": "BAT-COST", "nom_kWh": 10.0, "max_kW": 5.0, "max_ch_kW": 5.0, "max_dis_kW": 5.0, "price_COP": 12_500_000},
    ]
    panel_rows = active.config_bundle.panel_catalog.to_dict("records")
    panel_rows[0] = {**panel_rows[0], "price_COP": 555_000}

    seeded_rows = sync_economics_hardware_costs(
        1,
        payload,
        [],
        [],
        inverter_rows,
        battery_rows,
        panel_rows,
        active.config_bundle.economics_cost_items_table.to_dict("records"),
    )
    seeded_lookup = {row["name"]: row for row in seeded_rows}

    assert float(seeded_lookup["Panel hardware"]["value"]) == pytest.approx(555_000)
    assert float(seeded_lookup["Inverter hardware"]["value"]) == pytest.approx(9_000_000)
    assert float(seeded_lookup["Battery hardware"]["value"]) == pytest.approx(1_250_000)
