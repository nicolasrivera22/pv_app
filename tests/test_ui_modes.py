from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import app as app_module
from dash import no_update

from app import (
    cancel_admin_mode_dialog,
    create_app,
    finalize_admin_mode_unlock,
    sync_admin_mode_dialog,
    sync_nav_visibility,
    update_ui_mode,
)
from pages.compare import sync_compare_page_access
from pages.risk import sync_risk_page_access
from services import clear_all_admin_session_access, grant_admin_session_access, set_admin_pin
from services.session_state import bootstrap_client_session
from services.ui_mode import (
    PAGE_ADMIN,
    PAGE_COMPARE,
    PAGE_HELP,
    PAGE_RESULTS,
    PAGE_RISK,
    UI_MODE_ADMIN,
    UI_MODE_PRO,
    UI_MODE_SIMPLE,
    is_nav_page_visible,
    normalize_ui_mode,
    resolve_page_access,
    should_show_admin_surface,
    should_show_internal_entry,
)
from services.workspace_admin_callbacks import admin_access_meta
from services.workspace_assumptions_callbacks import sync_assumptions_admin_surface_visibility, sync_workspace_internal_entry


def _payload(ui_mode: str = UI_MODE_SIMPLE) -> dict:
    return replace(bootstrap_client_session("es"), ui_mode=ui_mode).to_payload()


def _find_pattern_component(node, component_type: str):
    if isinstance(node, (list, tuple)):
        for child in node:
            found = _find_pattern_component(child, component_type)
            if found is not None:
                return found
        return None
    component_id = getattr(node, "id", None)
    if isinstance(component_id, dict) and component_id.get("type") == component_type:
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_pattern_component(child, component_type)
            if found is not None:
                return found
        return None
    return _find_pattern_component(children, component_type)


def _find_component(node, component_id: str):
    if isinstance(node, (list, tuple)):
        for child in node:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    if getattr(node, "id", None) == component_id:
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    return _find_component(children, component_id)


def test_ui_mode_helpers_define_expected_visibility_rules() -> None:
    assert normalize_ui_mode(None) == UI_MODE_SIMPLE
    assert normalize_ui_mode("ADMIN") == UI_MODE_ADMIN
    assert normalize_ui_mode("unexpected") == UI_MODE_SIMPLE

    assert is_nav_page_visible(PAGE_RESULTS, UI_MODE_SIMPLE) is True
    assert is_nav_page_visible(PAGE_HELP, UI_MODE_SIMPLE) is True
    assert is_nav_page_visible(PAGE_COMPARE, UI_MODE_SIMPLE) is False
    assert is_nav_page_visible(PAGE_RISK, UI_MODE_SIMPLE) is False
    assert is_nav_page_visible(PAGE_COMPARE, UI_MODE_PRO) is True
    assert is_nav_page_visible(PAGE_RISK, UI_MODE_ADMIN) is True

    assert should_show_internal_entry(UI_MODE_SIMPLE) is False
    assert should_show_internal_entry(UI_MODE_PRO) is False
    assert should_show_internal_entry(UI_MODE_ADMIN) is True
    assert should_show_admin_surface(UI_MODE_SIMPLE) is False
    assert should_show_admin_surface(UI_MODE_PRO) is False
    assert should_show_admin_surface(UI_MODE_ADMIN) is True

    assert resolve_page_access(PAGE_COMPARE, UI_MODE_SIMPLE).allowed is False
    assert resolve_page_access(PAGE_COMPARE, UI_MODE_PRO).allowed is True
    assert resolve_page_access(PAGE_RISK, UI_MODE_SIMPLE).cta_target_mode == UI_MODE_PRO
    assert resolve_page_access(PAGE_ADMIN, UI_MODE_PRO).allowed is True
    assert resolve_page_access(PAGE_ADMIN, UI_MODE_ADMIN).allowed is True


def test_app_layout_shows_mode_label_and_defaults_to_simple() -> None:
    app = create_app()
    layout = app.layout() if callable(app.layout) else app.layout

    mode_label = _find_component(layout, "ui-mode-label")
    mode_selector = _find_component(layout, "ui-mode-selector")
    compare_link = _find_component(layout, "nav-compare-link")
    risk_link = _find_component(layout, "nav-risk-link")

    assert mode_label is not None
    assert mode_label.children == "Modo"
    assert mode_selector is not None
    assert mode_selector.value == "simple"
    assert compare_link.style == {"display": "none"}
    assert risk_link.style == {"display": "none"}


def test_nav_visibility_callback_hides_compare_and_risk_only_in_simple() -> None:
    simple_styles = sync_nav_visibility(_payload(UI_MODE_SIMPLE))
    admin_styles = sync_nav_visibility(_payload(UI_MODE_ADMIN))

    assert simple_styles[0] == {}
    assert simple_styles[1] == {}
    assert simple_styles[2] == {"display": "none"}
    assert simple_styles[3] == {"display": "none"}
    assert simple_styles[4] == {}

    assert admin_styles[2] == {}
    assert admin_styles[3] == {}


def test_internal_entry_visibility_callback_only_shows_in_admin() -> None:
    assert sync_workspace_internal_entry(_payload(UI_MODE_SIMPLE)) == {"display": "none"}
    assert sync_workspace_internal_entry(_payload(UI_MODE_PRO)) == {"display": "none"}
    assert sync_workspace_internal_entry(_payload(UI_MODE_ADMIN)) == {}


def test_assumptions_admin_surface_visibility_callback_only_shows_in_admin() -> None:
    assert sync_assumptions_admin_surface_visibility(_payload(UI_MODE_SIMPLE)) == ({"display": "none"}, {"display": "none"})
    assert sync_assumptions_admin_surface_visibility(_payload(UI_MODE_PRO)) == ({"display": "none"}, {"display": "none"})
    assert sync_assumptions_admin_surface_visibility(_payload(UI_MODE_ADMIN)) == ({}, {})


def test_compare_and_risk_gate_callbacks_only_gate_simple_mode() -> None:
    compare_gate, compare_gate_style, compare_body_style = sync_compare_page_access(_payload(UI_MODE_SIMPLE), "es")
    compare_allowed_gate, compare_allowed_style, compare_allowed_body = sync_compare_page_access(_payload(UI_MODE_PRO), "es")
    risk_gate, risk_gate_style, risk_body_style = sync_risk_page_access(_payload(UI_MODE_SIMPLE), "es")
    _risk_allowed_gate, risk_allowed_style, risk_allowed_body = sync_risk_page_access(_payload(UI_MODE_ADMIN), "es")

    assert compare_gate_style == {}
    assert compare_body_style == {"display": "none"}
    assert _find_pattern_component(compare_gate, "ui-mode-gate-cta") is not None
    assert compare_allowed_gate == []
    assert compare_allowed_style == {"display": "none"}
    assert compare_allowed_body == {}

    assert risk_gate_style == {}
    assert risk_body_style == {"display": "none"}
    assert _find_pattern_component(risk_gate, "ui-mode-gate-cta") is not None
    assert risk_allowed_style == {"display": "none"}
    assert risk_allowed_body == {}


def test_update_ui_mode_switches_between_client_and_pro_without_admin_side_effects(monkeypatch) -> None:
    payload = _payload(UI_MODE_SIMPLE)

    monkeypatch.setattr(app_module, "ctx", SimpleNamespace(triggered_id="ui-mode-selector"))
    updated, dialog_state, meta, href = update_ui_mode("pro", [], None, payload, {})
    assert updated["session_id"] == payload["session_id"]
    assert updated["ui_mode"] == "pro"
    assert updated["active_scenario_id"] == payload["active_scenario_id"]
    assert dialog_state["open"] is False
    assert meta["message_key"] is None
    assert href is no_update


def test_update_ui_mode_attempting_admin_while_locked_opens_modal_without_changing_mode(monkeypatch) -> None:
    clear_all_admin_session_access()
    payload = _payload(UI_MODE_SIMPLE)

    monkeypatch.setattr(app_module, "ctx", SimpleNamespace(triggered_id="ui-mode-selector"))
    updated, dialog_state, meta, href = update_ui_mode("admin", [], None, payload, {})

    assert updated is no_update
    assert dialog_state["open"] is True
    assert dialog_state["origin"] == "mode_selector"
    assert dialog_state["return_mode"] == "simple"
    assert dialog_state["post_unlock_href"] is None
    assert meta["message_key"] is None
    assert href is no_update


def test_update_ui_mode_attempting_admin_when_unlocked_switches_directly(monkeypatch) -> None:
    clear_all_admin_session_access()
    payload = _payload(UI_MODE_SIMPLE)
    grant_admin_session_access(payload["session_id"])

    monkeypatch.setattr(app_module, "ctx", SimpleNamespace(triggered_id="ui-mode-selector"))
    updated, dialog_state, meta, href = update_ui_mode("admin", [], None, payload, {})

    assert updated["session_id"] == payload["session_id"]
    assert updated["ui_mode"] == "admin"
    assert dialog_state["open"] is False
    assert meta["message_key"] is None
    assert href is no_update


def test_update_ui_mode_from_admin_route_keeps_attempt_origin_and_target(monkeypatch) -> None:
    clear_all_admin_session_access()
    payload = _payload(UI_MODE_PRO)

    monkeypatch.setattr(app_module, "ctx", SimpleNamespace(triggered_id="admin-redirect-enter-btn"))
    updated, dialog_state, meta, href = update_ui_mode("pro", [], 1, payload, {})

    assert updated is no_update
    assert dialog_state["open"] is True
    assert dialog_state["origin"] == "admin_route"
    assert dialog_state["return_mode"] == "pro"
    assert dialog_state["post_unlock_href"] == "/assumptions#advanced-tools"
    assert meta["message_key"] is None
    assert href is no_update


def test_sync_admin_mode_dialog_renders_setup_and_unlock_variants(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    payload = _payload(UI_MODE_SIMPLE)
    dialog_state = {"open": True, "origin": "mode_selector", "return_mode": "simple", "post_unlock_href": None}

    setup_style, setup_children = sync_admin_mode_dialog(dialog_state, payload, "es", admin_access_meta())
    assert setup_style == {"display": "flex"}
    assert _find_component(setup_children, "admin-setup-pin-input") is not None
    assert _find_component(setup_children, "admin-mode-dialog-cancel-btn") is not None

    set_admin_pin("2468")
    locked_style, locked_children = sync_admin_mode_dialog(dialog_state, payload, "es", admin_access_meta())
    assert locked_style == {"display": "flex"}
    assert _find_component(locked_children, "admin-pin-input") is not None
    assert _find_component(locked_children, "admin-mode-dialog-cancel-btn") is not None


def test_cancel_admin_mode_dialog_clears_attempt_and_feedback() -> None:
    dialog_state, meta = cancel_admin_mode_dialog(1, _payload(UI_MODE_PRO))

    assert dialog_state["open"] is False
    assert dialog_state["return_mode"] == "pro"
    assert meta["message_key"] is None


def test_finalize_admin_mode_unlock_promotes_admin_without_navigation_for_dropdown_origin() -> None:
    payload = _payload(UI_MODE_SIMPLE)

    updated, dialog_state, meta, href = finalize_admin_mode_unlock(
        admin_access_meta("workspace.advanced.locked.unlocked", tone="success"),
        payload,
        {"open": True, "origin": "mode_selector", "return_mode": "simple", "post_unlock_href": None},
    )

    assert updated["ui_mode"] == "admin"
    assert dialog_state["open"] is False
    assert meta["message_key"] is None
    assert href is no_update


def test_finalize_admin_mode_unlock_navigates_to_host_for_admin_route_origin() -> None:
    payload = _payload(UI_MODE_SIMPLE)

    updated, dialog_state, meta, href = finalize_admin_mode_unlock(
        admin_access_meta("workspace.advanced.setup.success", tone="success"),
        payload,
        {"open": True, "origin": "admin_route", "return_mode": "simple", "post_unlock_href": "/assumptions#advanced-tools"},
    )

    assert updated["ui_mode"] == "admin"
    assert dialog_state["open"] is False
    assert meta["message_key"] is None
    assert href == "/assumptions#advanced-tools"
