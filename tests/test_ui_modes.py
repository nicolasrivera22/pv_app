from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import app as app_module
from app import create_app, sync_nav_visibility, update_ui_mode
from pages.compare import sync_compare_page_access
from pages.risk import sync_risk_page_access
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
    should_show_internal_entry,
)
from services.workspace_assumptions_callbacks import sync_workspace_internal_entry


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

    assert resolve_page_access(PAGE_COMPARE, UI_MODE_SIMPLE).allowed is False
    assert resolve_page_access(PAGE_COMPARE, UI_MODE_PRO).allowed is True
    assert resolve_page_access(PAGE_RISK, UI_MODE_SIMPLE).cta_target_mode == UI_MODE_PRO
    assert resolve_page_access(PAGE_ADMIN, UI_MODE_PRO).allowed is False
    assert resolve_page_access(PAGE_ADMIN, UI_MODE_PRO).cta_target_mode == UI_MODE_ADMIN
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


def test_update_ui_mode_callbacks_only_change_ui_mode(monkeypatch) -> None:
    payload = _payload(UI_MODE_SIMPLE)

    monkeypatch.setattr(app_module, "ctx", SimpleNamespace(triggered_id="ui-mode-selector"))
    updated = update_ui_mode("pro", [], payload)
    assert updated["session_id"] == payload["session_id"]
    assert updated["ui_mode"] == "pro"
    assert updated["active_scenario_id"] == payload["active_scenario_id"]

    monkeypatch.setattr(app_module, "ctx", SimpleNamespace(triggered_id={"type": "ui-mode-gate-cta", "page": "admin", "target_mode": "admin"}))
    gated = update_ui_mode("pro", [1], updated)
    assert gated["session_id"] == payload["session_id"]
    assert gated["ui_mode"] == "admin"
