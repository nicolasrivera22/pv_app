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
    load_config_from_excel,
    load_example_config,
    set_admin_pin,
    verify_admin_pin,
)
from services.workspace_admin_callbacks import (
    populate_admin_page,
    render_admin_access_shell,
    setup_admin_session,
    translate_profile_table_activators,
    unlock_admin_session,
)


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


def test_admin_page_defaults_to_setup_shell_when_pin_missing(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    layout = admin_page.layout() if callable(admin_page.layout) else admin_page.layout

    assert _find_component(layout, "admin-access-shell") is not None
    assert _find_component(layout, "admin-setup-pin-input") is not None
    assert _find_component(layout, "admin-setup-confirm-input") is not None
    assert _find_component(layout, "admin-setup-btn") is not None
    assert _find_component(layout, "admin-pin-input") is None
    assert _find_component(layout, "profile-editor-title") is None


def test_render_admin_access_shell_shows_setup_when_pin_missing(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    client_state = bootstrap_client_session("es")

    rendered = render_admin_access_shell(client_state.to_payload(), "es", {"revision": 1})

    assert _find_component(rendered, "admin-setup-shell") is not None
    assert _find_component(rendered, "admin-setup-pin-input") is not None
    assert _find_component(rendered, "admin-pin-input") is None
    assert _find_component(rendered, "profile-editor-title") is None


def test_render_admin_access_shell_shows_unlock_when_pin_is_configured(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    set_admin_pin("2468")

    client_state = bootstrap_client_session("es")

    rendered = render_admin_access_shell(client_state.to_payload(), "es", {"revision": 1})

    assert _find_component(rendered, "admin-locked-shell") is not None
    assert _find_component(rendered, "admin-pin-input") is not None
    assert _find_component(rendered, "admin-setup-pin-input") is None
    assert _find_component(rendered, "profile-editor-title") is None


def test_render_admin_access_shell_exposes_secure_content_once_unlocked(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    client_state = bootstrap_client_session("es")
    set_admin_pin("2468")
    grant_admin_session_access(client_state.session_id)

    rendered = render_admin_access_shell(client_state.to_payload(), "es", {"revision": 1})

    assert _find_component(rendered, "admin-assumption-sections") is not None
    assert _find_component(rendered, "profile-editor-title") is not None
    assert _find_component(rendered, "inverter-table-editor") is not None
    assert _find_component(rendered, "admin-pin-input") is None
    assert _find_component(rendered, "profile-demand-legacy-shell") is None


def test_admin_profile_table_activator_translation_matches_visible_cards() -> None:
    activator_ids = [
        {"type": "profile-table-activate", "table": "month-profile-editor"},
        {"type": "profile-table-activate", "table": "sun-profile-editor"},
        {"type": "profile-table-activate", "table": "price-kwp-editor"},
        {"type": "profile-table-activate", "table": "price-kwp-others-editor"},
    ]

    assert translate_profile_table_activators("es", activator_ids) == ["Ver gráfica"] * 4
    assert translate_profile_table_activators("en", activator_ids) == ["Preview chart"] * 4


def test_setup_admin_session_rejects_empty_pin(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")

    meta = setup_admin_session(1, client_state.to_payload(), "", "")

    assert meta["message_key"] == "workspace.admin.setup.empty"
    assert meta["tone"] == "error"
    assert admin_pin_configured() is False
    assert is_admin_session_unlocked(client_state.session_id) is False


def test_setup_admin_session_rejects_whitespace_only_pin(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")

    meta = setup_admin_session(1, client_state.to_payload(), "   ", "   ")

    assert meta["message_key"] == "workspace.admin.setup.empty"
    assert meta["tone"] == "error"
    assert admin_pin_configured() is False
    assert is_admin_session_unlocked(client_state.session_id) is False


def test_setup_admin_session_rejects_non_digit_pin(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")

    meta = setup_admin_session(1, client_state.to_payload(), "12ab", "12ab")

    assert meta["message_key"] == "workspace.admin.setup.digits_only"
    assert meta["tone"] == "error"
    assert admin_pin_configured() is False
    assert is_admin_session_unlocked(client_state.session_id) is False


def test_setup_admin_session_rejects_short_pin(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")

    meta = setup_admin_session(1, client_state.to_payload(), "123", "123")

    assert meta["message_key"] == "workspace.admin.setup.too_short"
    assert meta["tone"] == "error"
    assert admin_pin_configured() is False
    assert is_admin_session_unlocked(client_state.session_id) is False


def test_setup_admin_session_rejects_mismatched_confirmation(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")

    meta = setup_admin_session(1, client_state.to_payload(), "1234", "5678")

    assert meta["message_key"] == "workspace.admin.setup.mismatch"
    assert meta["tone"] == "error"
    assert admin_pin_configured() is False
    assert is_admin_session_unlocked(client_state.session_id) is False


def test_setup_admin_session_trims_input_writes_hash_and_unlocks(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")

    meta = setup_admin_session(1, client_state.to_payload(), " 1234 ", "1234")

    assert meta["message_key"] == "workspace.admin.setup.success"
    assert meta["tone"] == "success"
    assert admin_pin_configured() is True
    assert verify_admin_pin("1234") is True
    assert is_admin_session_unlocked(client_state.session_id) is True
    text = admin_pin_path().read_text(encoding="utf-8")
    assert "1234" not in text
    assert '"hash"' in text
    assert '"salt"' in text


def test_setup_admin_session_does_not_overwrite_existing_pin(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")
    path = set_admin_pin("2468")
    before = path.read_text(encoding="utf-8")

    meta = setup_admin_session(1, client_state.to_payload(), "9999", "9999")

    assert meta["message_key"] == "workspace.admin.setup.already_configured"
    assert meta["tone"] == "info"
    assert path.read_text(encoding="utf-8") == before
    assert verify_admin_pin("2468") is True
    assert verify_admin_pin("9999") is False
    assert is_admin_session_unlocked(client_state.session_id) is False


def test_unlock_admin_session_grants_access_with_existing_pin(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")
    set_admin_pin("2468")

    meta = unlock_admin_session(1, client_state.to_payload(), "2468")

    assert meta["message_key"] == "workspace.admin.locked.unlocked"
    assert meta["tone"] == "success"
    assert is_admin_session_unlocked(client_state.session_id) is True


def test_unlock_admin_session_rejects_wrong_pin(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    client_state = bootstrap_client_session("es")
    set_admin_pin("2468")

    meta = unlock_admin_session(1, client_state.to_payload(), "1357")

    assert meta["message_key"] == "workspace.admin.locked.invalid"
    assert meta["tone"] == "error"
    assert is_admin_session_unlocked(client_state.session_id) is False


def test_populate_admin_page_returns_safe_empty_outputs_when_locked() -> None:
    clear_all_admin_session_access()
    clear_session_states()
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = commit_client_session(bootstrap_client_session("es"), state).to_payload()

    rendered_sections, disabled, inverter_rows, *_rest = populate_admin_page(payload, [], "es")

    assert disabled is True
    assert inverter_rows == []
    assert _find_pattern_component(rendered_sections, "admin-assumption-input") is None


def test_populate_admin_page_renders_visible_admin_tables_for_example_bundle(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    client_state = bootstrap_client_session("es")
    set_admin_pin("2468")
    grant_admin_session_access(client_state.session_id)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = commit_client_session(client_state, state).to_payload()

    rendered_sections, disabled, inverter_rows, inverter_columns, _inverter_tooltips, battery_rows, battery_columns, _battery_tooltips, month_rows, month_columns, _month_tooltips, sun_rows, sun_columns, _sun_tooltips, price_rows, price_columns, _price_tooltips, price_other_rows, price_other_columns, _price_other_tooltips = populate_admin_page(payload, [], "es")

    assert disabled is False
    assert inverter_rows
    assert battery_rows
    assert month_rows
    assert sun_rows
    assert price_rows
    assert price_other_rows
    assert inverter_columns
    assert battery_columns
    assert month_columns
    assert sun_columns
    assert price_columns
    assert price_other_columns
    assert _find_pattern_component(rendered_sections, "admin-assumption-input") is not None


def test_populate_admin_page_handles_excel_bundle_without_legacy_demand_shell(monkeypatch, tmp_path) -> None:
    clear_all_admin_session_access()
    clear_session_states()
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))

    client_state = bootstrap_client_session("es")
    set_admin_pin("2468")
    grant_admin_session_access(client_state.session_id)
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Importado", bundle))
    payload = commit_client_session(client_state, state).to_payload()

    rendered = render_admin_access_shell(payload, "es", {"revision": 1})
    outputs = populate_admin_page(payload, [], "es")

    assert _find_component(rendered, "profile-demand-legacy-shell") is None
    assert outputs[1] is False
    assert outputs[2]
    assert outputs[5]
    assert outputs[8]
    assert outputs[11]
    assert outputs[14]
    assert outputs[17]
