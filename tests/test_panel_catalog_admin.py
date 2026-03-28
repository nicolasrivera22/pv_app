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
    get_workspace_draft,
    grant_admin_session_access,
    load_example_config,
    open_project,
    resolve_client_session,
    save_project,
    set_admin_pin,
)
from services.validation import PANEL_REQUIRED_COLUMNS
from services.workspace_admin_callbacks import add_panel_row, apply_admin_edits, sync_admin_draft


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


def test_add_panel_row_appends_blank_required_columns() -> None:
    rows = add_panel_row(1, [])

    assert rows == [{column: "" for column in PANEL_REQUIRED_COLUMNS}]


def test_sync_admin_draft_tracks_panel_catalog_changes(monkeypatch, tmp_path) -> None:
    client_state, state, active, payload = _admin_payload(monkeypatch, tmp_path)
    panel_rows = active.config_bundle.panel_catalog.to_dict("records")
    panel_rows[0] = {**panel_rows[0], "name": "BASE-600W Edited"}

    meta = sync_admin_draft(
        payload,
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        panel_rows,
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        active.config_bundle.cop_kwp_table.to_dict("records"),
        active.config_bundle.cop_kwp_table_others.to_dict("records"),
        active.config_bundle.economics_cost_items_table.to_dict("records"),
        active.config_bundle.economics_price_items_table.to_dict("records"),
    )

    draft = get_workspace_draft(client_state.session_id, active.scenario_id)
    assert meta["revision"] > 0
    assert draft is not None
    assert "panel_catalog" in draft.table_rows
    assert draft.table_rows["panel_catalog"][0]["name"] == "BASE-600W Edited"


def test_apply_admin_edits_persists_panel_catalog_changes_across_save_and_reopen(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Panel Admin", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    panel_rows = active.config_bundle.panel_catalog.to_dict("records")
    panel_rows.append(
        {
            "name": "ADMIN-640 Premium",
            "P_mod_W": 640.0,
            "Voc25": 53.2,
            "Vmp25": 44.1,
            "Isc": 14.9,
            "length_m": 2.41,
            "width_m": 1.31,
            "panel_technology_mode": "premium",
        }
    )

    next_payload, _status = apply_admin_edits(
        1,
        payload,
        "Proyecto Panel Admin",
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        panel_rows,
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        active.config_bundle.cop_kwp_table.to_dict("records"),
        active.config_bundle.cop_kwp_table_others.to_dict("records"),
        active.config_bundle.economics_cost_items_table.to_dict("records"),
        active.config_bundle.economics_price_items_table.to_dict("records"),
        "es",
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    assert "ADMIN-640 Premium" in updated_active.config_bundle.panel_catalog["name"].astype(str).tolist()

    reopened = open_project(updated_state.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert "ADMIN-640 Premium" in reopened_active.config_bundle.panel_catalog["name"].astype(str).tolist()
