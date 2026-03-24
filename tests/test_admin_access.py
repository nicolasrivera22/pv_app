from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app import create_app
from pages import admin as admin_page
from services import (
    ScenarioSessionState,
    add_scenario,
    admin_pin_configured,
    admin_pin_path,
    bootstrap_client_session,
    clear_admin_session_access,
    clear_all_admin_session_access,
    clear_session_states,
    commit_client_session,
    create_scenario_record,
    grant_admin_session_access,
    is_admin_session_unlocked,
    load_example_config,
    set_admin_pin,
    verify_admin_pin,
)
from services.workspace_admin_callbacks import populate_admin_page, render_admin_access_shell


_APP = create_app()


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


def test_admin_pin_path_resolves_outside_repo_in_source_mode(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    monkeypatch.delenv("PVW_PRIVATE_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    path = admin_pin_path()

    assert path.name == "admin_pin.json"
    assert Path.cwd().resolve() not in path.parents


def test_admin_pin_round_trip_stores_only_hash(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    path = set_admin_pin("2468")

    assert admin_pin_configured() is True
    assert verify_admin_pin("2468") is True
    assert verify_admin_pin("1357") is False
    text = path.read_text(encoding="utf-8")
    assert "2468" not in text
    assert '"hash"' in text
    assert '"salt"' in text


def test_missing_admin_pin_fails_closed(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    assert admin_pin_configured() is False
    assert verify_admin_pin("2468") is False


def test_admin_unlock_registry_is_scoped_per_session() -> None:
    clear_all_admin_session_access()

    grant_admin_session_access("session-a")

    assert is_admin_session_unlocked("session-a") is True
    assert is_admin_session_unlocked("session-b") is False

    clear_admin_session_access("session-a")

    assert is_admin_session_unlocked("session-a") is False


def test_admin_page_defaults_to_locked_shell(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    layout = admin_page.layout() if callable(admin_page.layout) else admin_page.layout

    assert _find_component(layout, "admin-access-shell") is not None
    assert _find_component(layout, "admin-pin-input") is not None
    assert _find_component(layout, "admin-unlock-btn") is not None
    assert _find_component(layout, "profile-editor-title") is None


def test_render_admin_access_shell_exposes_secure_content_once_unlocked(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    client_state = bootstrap_client_session("es")
    grant_admin_session_access(client_state.session_id)

    rendered = render_admin_access_shell(client_state.to_payload(), "es", {"revision": 1})

    assert _find_component(rendered, "admin-assumption-sections") is not None
    assert _find_component(rendered, "profile-editor-title") is not None
    assert _find_component(rendered, "inverter-table-editor") is not None
    assert _find_component(rendered, "admin-pin-input") is None


def test_populate_admin_page_returns_safe_empty_outputs_when_locked() -> None:
    clear_all_admin_session_access()
    clear_session_states()
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = commit_client_session(bootstrap_client_session("es"), state).to_payload()

    rendered_sections, disabled, inverter_rows, *_rest = populate_admin_page(payload, [], "es")

    assert disabled is True
    assert inverter_rows == []
    assert _find_component(rendered_sections, "admin-assumption-input") is None
