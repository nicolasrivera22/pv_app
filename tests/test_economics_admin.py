from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dash.exceptions import PreventUpdate
import pandas as pd
import pandas.testing as pdt
import pytest

from components.economics_editor import economics_editor_section
from services import (
    ScenarioSessionState,
    add_scenario,
    bootstrap_client_session,
    clear_all_admin_session_access,
    clear_session_states,
    clear_workspace_drafts,
    commit_client_session,
    create_scenario_record,
    fingerprint_deterministic_input,
    get_workspace_draft,
    grant_admin_session_access,
    load_example_config,
    open_project,
    resolve_client_session,
    resolve_deterministic_scan,
    save_project,
    set_admin_pin,
)
from services.project_io import projects_root
from services.workspace_admin_callbacks import (
    apply_admin_edits,
    sync_admin_draft,
    sync_economics_hardware_costs,
)


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


def _find_component(node, component_id: str):
    if node is None:
        return None
    if isinstance(node, (list, tuple)):
        for child in node:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    if getattr(node, "id", None) == component_id:
        return node
    children = getattr(node, "children", None)
    return _find_component(children, component_id)


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


def test_example_bundle_uses_simple_seeded_economics_and_panel_price_is_not_authoritative() -> None:
    bundle = load_example_config()

    assert list(bundle.economics_cost_items_table.columns) == ["stage", "name", "basis", "amount_COP", "enabled", "notes"]
    assert list(bundle.economics_price_items_table.columns) == ["layer", "name", "method", "value", "enabled", "notes"]
    assert bundle.economics_cost_items_table.empty is False
    assert bundle.economics_price_items_table.empty is False
    assert "price_COP" in bundle.panel_catalog.columns
    assert float(bundle.panel_catalog.loc[0, "price_COP"]) >= 0.0

    panel_cost_row = next(
        row for row in bundle.economics_cost_items_table.to_dict("records") if str(row.get("name")) == "Panel hardware"
    )
    assert panel_cost_row["stage"] == "technical"
    assert panel_cost_row["basis"] == "per_panel"
    assert float(panel_cost_row["amount_COP"]) == pytest.approx(0.0)


def test_sync_admin_draft_tracks_economics_tables_with_simple_schema(monkeypatch, tmp_path) -> None:
    client_state, _state, active, payload = _admin_payload(monkeypatch, tmp_path)

    economics_cost_rows = active.config_bundle.economics_cost_items_table.to_dict("records")
    economics_price_rows = active.config_bundle.economics_price_items_table.to_dict("records")
    economics_cost_rows[0] = {**economics_cost_rows[0], "amount_COP": 777_000}
    economics_price_rows[0] = {**economics_price_rows[0], "value": 12}

    meta = sync_admin_draft(
        payload,
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
    )

    draft = get_workspace_draft(client_state.session_id, active.scenario_id)
    assert meta["revision"] > 0
    assert draft is not None
    assert draft.table_rows["economics_cost_items"][0]["amount_COP"] == pytest.approx(777_000)
    assert draft.table_rows["economics_price_items"][0]["method"] == "markup_pct"
    assert draft.table_rows["economics_price_items"][0]["value"] == pytest.approx(0.12)


def test_apply_admin_edits_persists_economics_tables_and_normalizes_markup_percent(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Economics Admin", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    economics_cost_rows = active.config_bundle.economics_cost_items_table.to_dict("records")
    economics_price_rows = active.config_bundle.economics_price_items_table.to_dict("records")
    economics_cost_rows[0] = {**economics_cost_rows[0], "amount_COP": 777_000}
    economics_price_rows[0] = {**economics_price_rows[0], "value": 19}

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
    assert float(updated_active.config_bundle.economics_cost_items_table.iloc[0]["amount_COP"]) == pytest.approx(777_000)
    assert float(updated_active.config_bundle.economics_price_items_table.iloc[0]["value"]) == pytest.approx(0.19)
    assert list(updated_active.config_bundle.economics_cost_items_table.columns) == ["stage", "name", "basis", "amount_COP", "enabled", "notes"]
    assert list(updated_active.config_bundle.economics_price_items_table.columns) == ["layer", "name", "method", "value", "enabled", "notes"]

    reopened = open_project(updated_state.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert float(reopened_active.config_bundle.economics_cost_items_table.iloc[0]["amount_COP"]) == pytest.approx(777_000)
    assert float(reopened_active.config_bundle.economics_price_items_table.iloc[0]["value"]) == pytest.approx(0.19)


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
    assert list(reopened_active.config_bundle.economics_cost_items_table.columns) == ["stage", "name", "basis", "amount_COP", "enabled", "notes"]
    assert list(reopened_active.config_bundle.economics_price_items_table.columns) == ["layer", "name", "method", "value", "enabled", "notes"]
    assert "Panel hardware" in reopened_active.config_bundle.economics_cost_items_table["name"].astype(str).tolist()
    assert "Margen comercial" in reopened_active.config_bundle.economics_price_items_table["name"].astype(str).tolist()


def test_open_rich_economics_schema_migrates_in_memory_only_and_rewrites_on_save(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    saved = save_project(state, project_name="Proyecto Economics Rich", language="es")
    root = projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id
    cost_path = root / "Economics_Cost_Items.csv"
    price_path = root / "Economics_Price_Items.csv"

    pd.DataFrame(
        [
            {"stage": "technical_cost", "name": "Panel hardware", "calculation_method": "per_panel", "value": 555_000, "enabled": True, "notes": ""},
            {"stage": "installed_cost", "name": "Legacy contingency", "calculation_method": "pct_of_running_subtotal", "value": 0.12, "enabled": True, "notes": "legacy"},
        ],
        columns=["stage", "name", "calculation_method", "value", "enabled", "notes"],
    ).to_csv(cost_path, index=False)
    pd.DataFrame(
        [
            {"stage": "commercial_offer", "name": "Commercial margin", "calculation_method": "markup_pct", "value": 0.19, "enabled": True, "notes": ""},
            {"stage": "final_sale_price", "name": "Taxes", "calculation_method": "tax_pct", "value": 0.16, "enabled": True, "notes": "legacy tax"},
        ],
        columns=["stage", "name", "calculation_method", "value", "enabled", "notes"],
    ).to_csv(price_path, index=False)

    original_cost_text = cost_path.read_text(encoding="utf-8")
    original_price_text = price_path.read_text(encoding="utf-8")

    reopened = open_project(saved.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert cost_path.read_text(encoding="utf-8") == original_cost_text
    assert price_path.read_text(encoding="utf-8") == original_price_text
    assert list(reopened_active.config_bundle.economics_cost_items_table.columns) == ["stage", "name", "basis", "amount_COP", "enabled", "notes"]
    assert list(reopened_active.config_bundle.economics_price_items_table.columns) == ["layer", "name", "method", "value", "enabled", "notes"]
    assert reopened_active.config_bundle.economics_cost_items_table.iloc[0]["stage"] == "technical"
    assert reopened_active.config_bundle.economics_cost_items_table.iloc[0]["basis"] == "per_panel"
    assert float(reopened_active.config_bundle.economics_cost_items_table.iloc[0]["amount_COP"]) == pytest.approx(555_000)
    assert bool(reopened_active.config_bundle.economics_cost_items_table.iloc[1]["enabled"]) is False
    assert "pct_of_running_subtotal" in str(reopened_active.config_bundle.economics_cost_items_table.iloc[1]["notes"])
    assert reopened_active.config_bundle.economics_price_items_table.iloc[0]["layer"] == "commercial"
    assert reopened_active.config_bundle.economics_price_items_table.iloc[0]["method"] == "markup_pct"
    assert float(reopened_active.config_bundle.economics_price_items_table.iloc[0]["value"]) == pytest.approx(0.19)
    assert bool(reopened_active.config_bundle.economics_price_items_table.iloc[1]["enabled"]) is False
    assert "tax_pct" in str(reopened_active.config_bundle.economics_price_items_table.iloc[1]["notes"])
    assert any(issue.field == "economics_cost_items" for issue in reopened_active.config_bundle.issues)
    assert any(issue.field == "economics_price_items" for issue in reopened_active.config_bundle.issues)

    save_project(reopened, language="es")
    rewritten_cost = pd.read_csv(cost_path)
    rewritten_price = pd.read_csv(price_path)

    assert list(rewritten_cost.columns) == ["stage", "name", "basis", "amount_COP", "enabled", "notes"]
    assert list(rewritten_price.columns) == ["layer", "name", "method", "value", "enabled", "notes"]
    assert "calculation_method" not in rewritten_cost.columns
    assert "calculation_method" not in rewritten_price.columns


def test_sync_economics_hardware_costs_is_hidden_and_inert(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _admin_payload(monkeypatch, tmp_path)
    section = economics_editor_section(lang="es")
    button = _find_component(section, "sync-economics-hardware-costs-btn")

    assert button is not None
    assert button.disabled is True
    assert button.style == {"display": "none"}

    with pytest.raises(PreventUpdate):
        sync_economics_hardware_costs(
            1,
            payload,
            [],
            [],
            active.config_bundle.inverter_catalog.to_dict("records"),
            active.config_bundle.battery_catalog.to_dict("records"),
            active.config_bundle.panel_catalog.to_dict("records"),
            active.config_bundle.economics_cost_items_table.to_dict("records"),
        )


def test_economics_changes_do_not_affect_deterministic_fingerprint_or_scan() -> None:
    bundle = _fast_bundle()
    baseline_fingerprint = fingerprint_deterministic_input(bundle)
    baseline_scan = resolve_deterministic_scan(bundle, allow_parallel=False)

    changed_costs = bundle.economics_cost_items_table.copy()
    changed_prices = bundle.economics_price_items_table.copy()
    changed_costs.at[0, "amount_COP"] = 999_999.0
    changed_prices.at[0, "value"] = 0.22
    changed_bundle = replace(
        bundle,
        economics_cost_items_table=changed_costs,
        economics_price_items_table=changed_prices,
    )

    assert fingerprint_deterministic_input(changed_bundle) == baseline_fingerprint

    changed_scan = resolve_deterministic_scan(changed_bundle, allow_parallel=False)
    assert changed_scan.best_candidate_key == baseline_scan.best_candidate_key
    pdt.assert_frame_equal(changed_scan.candidates, baseline_scan.candidates)
