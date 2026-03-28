from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from app import create_app
from pages import admin as admin_page
from pages import assumptions as assumptions_page
from pages import results as results_page
from services import (
    ScenarioSessionState,
    ValidationIssue,
    add_scenario,
    apply_workspace_draft_to_state,
    bootstrap_client_session,
    build_assumption_sections,
    clear_session_workspace_drafts,
    clear_workspace_drafts,
    commit_client_session,
    create_scenario_record,
    get_workspace_draft,
    load_example_config,
    partition_assumption_sections,
    resolve_client_session,
    resolve_results_status_digest,
    upsert_workspace_draft,
)
from services.workspace_assumptions_callbacks import mutate_assumptions_state, sync_assumptions_demand_profile_views


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


def _find_matching_component(node, predicate):
    if predicate(node):
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_matching_component(child, predicate)
            if found is not None:
                return found
        return None
    return _find_matching_component(children, predicate)


def test_partition_assumption_sections_routes_safe_and_internal_groups() -> None:
    sections = build_assumption_sections(load_example_config(), lang="es", show_all=True)

    partition = partition_assumption_sections(sections)

    client_groups = {section["group_key"] for section in partition.client_safe_sections}
    admin_groups = {section["group_key"] for section in partition.admin_sections}
    client_fields = {
        field["field"]
        for section in partition.client_safe_sections
        for bucket in ("basic", "advanced")
        for field in section.get(bucket, [])
    }
    admin_fields = {
        field["field"]
        for section in partition.admin_sections
        for bucket in ("basic", "advanced")
        for field in section.get(bucket, [])
    }

    assert {"Demanda y Perfil", "Sol y módulos", "Semilla", "Restricción de Proporción Pico"} <= client_groups
    assert {"Economía", "Inversor", "Precios", "Monte Carlo"} <= admin_groups
    assert {"include_battery", "optimize_battery", "export_allowed", "panel_name", "panel_technology_mode"} <= client_fields
    assert {"battery_name", "bat_DoD", "bat_coupling", "bat_eta_rt"} <= admin_fields
    assert "pricing_mode" not in client_fields
    assert "mc_PR_std" not in client_fields
    assert "mc_PR_std" in admin_fields
    assert "price_total_COP" in admin_fields
    assert "panel_name" not in admin_fields
    assert "panel_technology_mode" not in admin_fields


def test_workspace_drafts_persist_per_scenario_and_clear_independently() -> None:
    clear_workspace_drafts()
    upsert_workspace_draft("session-1", "scenario-a", config_overrides={"E_month_kWh": 1200.0}, owned_config_fields={"E_month_kWh"})
    upsert_workspace_draft("session-1", "scenario-b", config_overrides={"PR": 0.8}, owned_config_fields={"PR"})

    assert get_workspace_draft("session-1", "scenario-a") is not None
    assert get_workspace_draft("session-1", "scenario-b") is not None

    clear_session_workspace_drafts("session-1")

    assert get_workspace_draft("session-1", "scenario-a") is None
    assert get_workspace_draft("session-1", "scenario-b") is None


def test_apply_workspace_draft_clears_only_committed_scenario() -> None:
    clear_workspace_drafts()
    base = ScenarioSessionState.empty()
    first = create_scenario_record("Base", _fast_bundle())
    second = create_scenario_record("Alt", _fast_bundle())
    state = add_scenario(base, first, make_active=True)
    state = add_scenario(state, second, make_active=False)

    upsert_workspace_draft("session-1", first.scenario_id, config_overrides={"E_month_kWh": 1500.0}, owned_config_fields={"E_month_kWh"})
    upsert_workspace_draft("session-1", second.scenario_id, config_overrides={"PR": 0.82}, owned_config_fields={"PR"})

    next_state, updated = apply_workspace_draft_to_state(state, session_id="session-1", scenario_id=first.scenario_id)

    assert updated.config_bundle.config["E_month_kWh"] == 1500.0
    assert get_workspace_draft("session-1", first.scenario_id) is None
    assert get_workspace_draft("session-1", second.scenario_id) is not None
    assert next_state.get_scenario(second.scenario_id) is not None


def test_results_status_digest_covers_empty_scan_stale_and_validation_states() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    active = state.get_scenario()
    assert active is not None

    no_active = resolve_results_status_digest(None)
    no_scan = resolve_results_status_digest(active)
    validation_blocked = resolve_results_status_digest(
        replace(
            active,
            config_bundle=replace(
                active.config_bundle,
                issues=(ValidationIssue(level="error", field="PR", message="Broken"),),
            ),
        )
    )
    stale = resolve_results_status_digest(replace(active, scan_result=object(), dirty=True))

    assert no_active is not None and no_active.state == "no_active"
    assert no_scan is not None and no_scan.state == "no_scan"
    assert stale is not None and stale.state == "stale"
    assert validation_blocked is not None and validation_blocked.state == "validation_blocked"


def test_page_wrappers_render_split_sections(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    results_layout = results_page.layout() if callable(results_page.layout) else results_page.layout
    assumptions_layout = assumptions_page.layout() if callable(assumptions_page.layout) else assumptions_page.layout
    admin_layout = admin_page.layout() if callable(admin_page.layout) else admin_page.layout

    assert _find_component(results_layout, "deterministic-results-area") is not None
    assert _find_component(results_layout, "results-status-digest") is not None
    assert _find_component(results_layout, "workspace-admin-entry") is None
    assert _find_component(results_layout, "assumptions-sections") is None
    assert _find_component(results_layout, "inverter-table-editor") is None

    assert _find_component(assumptions_layout, "assumptions-sections") is not None
    assert _find_component(assumptions_layout, "assumptions-validation") is not None
    assert _find_component(assumptions_layout, "apply-assumptions-btn") is not None
    assert _find_component(assumptions_layout, "run-assumptions-scan-btn") is not None
    assert _find_component(assumptions_layout, "assumptions-general-tab") is not None
    assert _find_component(assumptions_layout, "assumptions-demand-tab") is not None
    assert _find_component(assumptions_layout, "workspace-admin-entry") is not None
    assert _find_component(assumptions_layout, "assumptions-demand-profile-mode-selector") is not None
    assert _find_component(assumptions_layout, "inverter-table-editor") is None

    assert _find_component(admin_layout, "admin-access-shell") is not None
    assert _find_component(admin_layout, "admin-gating-note") is not None
    assert _find_component(admin_layout, "admin-mode-gate") is not None
    assert _find_component(admin_layout, "admin-setup-pin-input") is None
    assert _find_component(admin_layout, "admin-pin-input") is None
    assert _find_component(admin_layout, "profile-editor-title") is None
    assert _find_component(admin_layout, "inverter-table-editor") is None
    assert _find_component(admin_layout, "apply-admin-btn") is None
    assert _find_component(admin_layout, "run-assumptions-scan-btn") is None
    assert _find_component(admin_layout, "workspace-admin-entry") is None


def test_assumptions_demand_tab_places_summary_strip_above_tables() -> None:
    assumptions_layout = assumptions_page.layout() if callable(assumptions_page.layout) else assumptions_page.layout

    control_strip = _find_component(assumptions_layout, "assumptions-demand-profile-control-strip")
    relative_grid = _find_component(assumptions_layout, "assumptions-demand-profile-relative-grid")
    weekday_table = _find_component(assumptions_layout, "assumptions-demand-profile-editor")
    total_table = _find_component(assumptions_layout, "assumptions-demand-profile-general-editor")
    relative_table = _find_component(assumptions_layout, "assumptions-demand-profile-weights-editor")

    assert control_strip is not None
    assert [child.id for child in control_strip.children[0].children] == [
        "assumptions-demand-profile-energy-shell",
        "assumptions-demand-profile-alpha-shell",
        "assumptions-demand-profile-type-shell",
    ]
    assert [child.id for child in relative_grid.children] == [
        "assumptions-demand-profile-weights-card",
        "assumptions-demand-profile-weights-preview-card",
    ]
    assert weekday_table.page_size == 24
    assert "DOW" in weekday_table.hidden_columns
    assert total_table.page_size == 24
    assert relative_table.page_size == 24


def test_top_nav_exposes_results_and_assumptions_but_not_admin() -> None:
    app = create_app()
    layout = app.layout() if callable(app.layout) else app.layout

    assert _find_component(layout, "nav-results-label") is not None
    assert _find_component(layout, "nav-assumptions-label") is not None
    assert _find_component(layout, "workspace-admin-link") is None


def test_admin_page_gracefully_handles_direct_access_without_active_scenario(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    payload = commit_client_session(bootstrap_client_session("es"), ScenarioSessionState.empty()).to_payload()

    rendered = admin_page.layout() if callable(admin_page.layout) else admin_page.layout

    assert _find_component(rendered, "admin-gating-note") is not None
    assert _find_component(rendered, "admin-mode-gate") is not None
    assert _find_component(rendered, "admin-setup-pin-input") is None
    assert payload["active_scenario_id"] is None


def test_assumptions_demand_tab_reacts_with_preview_and_chart() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = commit_client_session(bootstrap_client_session("es"), state).to_payload()

    outputs = sync_assumptions_demand_profile_views(
        "perfil hora dia de semana",
        "mixta",
        0.5,
        1200,
        None,
        None,
        None,
        "demand",
        "es",
        payload,
        [{"Dia": "Lunes", "DOW": 1, "HOUR": 0, "RES": 10, "IND": 5}],
        None,
        None,
    )

    weekday_rows, _total_rows, total_preview_rows, *_rest = outputs
    energy_value = outputs[10]
    energy_disabled = outputs[12]
    chart_style = outputs[19]
    chart_figure = outputs[-1]

    assert weekday_rows[0]["TOTAL_kWh"] == 15
    assert total_preview_rows[0]["HOUR"] == 0
    assert abs(total_preview_rows[0]["TOTAL_kWh"] - (15 / 7)) < 1e-9
    assert energy_value == 64.29
    assert energy_disabled is True
    assert chart_style["display"] == "grid"
    assert len(chart_figure.data) == 1


def test_apply_assumptions_persists_demand_mode_and_keeps_run_flow(monkeypatch) -> None:
    clear_workspace_drafts()
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    active = state.get_scenario()
    assert active is not None
    relative_rows = active.config_bundle.demand_profile_weights_table.to_dict("records")
    payload = commit_client_session(bootstrap_client_session("es"), state).to_payload()

    monkeypatch.setattr("services.workspace_assumptions_callbacks.ctx", SimpleNamespace(triggered_id="apply-assumptions-btn"))

    updated_payload, status, dialog_state = mutate_assumptions_state(
        1,
        0,
        payload,
        None,
        [],
        [],
        "perfil horario relativo",
        0.35,
        900,
        None,
        None,
        relative_rows,
        "es",
    )

    _client_state, updated_state = resolve_client_session(updated_payload, language="es")
    active = updated_state.get_scenario()

    assert active is not None
    assert active.config_bundle.config["use_excel_profile"] == "perfil horario relativo"
    assert "aplic" in status.lower()
    assert "ejecut" in status.lower() or "rerun" in status.lower()
    assert dialog_state == {"open": False}
