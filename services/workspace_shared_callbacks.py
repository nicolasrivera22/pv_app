from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

from dash import ALL, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate

from components.scenario_controls import stacked_button_label
from .i18n import tr
from .project_io import delete_project, list_projects, open_project, save_project, save_project_as
from .runtime_paths import project_root
from .scenario_session import (
    add_scenario,
    create_scenario_record,
    default_scenario_name,
    delete_scenario,
    duplicate_scenario,
    rename_scenario,
    set_active_scenario,
)
from .session_state import commit_client_session, resolve_client_session
from .workbench_ui import workbench_status_message
from .workspace_drafts import clear_session_workspace_drafts, clear_workspace_draft
from .io_excel import load_config_from_excel, load_example_config


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


def _project_options():
    return [{"label": manifest.name, "value": manifest.slug} for manifest in list_projects()]


def _resolved_project_name(project_name_value, state) -> str:
    return (project_name_value or state.project_name or state.project_slug or "").strip()


def _project_is_bound(state) -> bool:
    return bool(str(state.project_slug or "").strip())


def _join_status_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _scenario_name_from_filename(filename: str | None, fallback: str) -> str:
    if filename:
        stem = Path(filename).stem.strip()
        if stem:
            return stem
    return fallback


def _workbench_state_chip(label: str, tone: str):
    from dash import html

    return html.Span(label, className=f"workbench-state-chip workbench-state-chip-{tone}")


def _workspace_state_strip_children(*, state, active, session_id: str, lang: str):
    from dash import html

    if active is None:
        return [_workbench_state_chip(tr("workbench.state.no_active", lang), "neutral")]

    from .workspace_drafts import has_workspace_draft

    has_draft = has_workspace_draft(session_id, active.scenario_id)
    project_saved = _project_is_bound(state) and not state.project_dirty
    scan_current = active.scan_result is not None and not active.dirty
    return [
        _workbench_state_chip(
            tr("workbench.state.pending_apply", lang) if has_draft else tr("workbench.state.applied", lang),
            "warning" if has_draft else "neutral",
        ),
        _workbench_state_chip(
            tr("workbench.state.project_saved", lang) if project_saved else tr("workbench.state.project_unsaved", lang),
            "success" if project_saved else "warning",
        ),
        _workbench_state_chip(
            tr("workbench.state.ready_to_run", lang) if scan_current else tr("workbench.state.scan_outdated", lang),
            "info" if scan_current else "warning",
        ),
    ]


@callback(
    Output("scenario-sidebar-title", "children"),
    Output("project-toolbar-title", "children"),
    Output("project-name-label", "children"),
    Output("project-name-input", "placeholder"),
    Output("project-dropdown-label", "children"),
    Output("project-dropdown", "placeholder"),
    Output("save-project-btn", "children"),
    Output("save-project-as-btn", "children"),
    Output("open-project-btn", "children"),
    Output("delete-project-btn", "children"),
    Output("scenario-start-title", "children"),
    Output("scenario-upload-title", "children"),
    Output("scenario-upload-copy", "children"),
    Output("scenario-upload-action", "children"),
    Output("new-scenario-btn", "children"),
    Output("duplicate-scenario-btn", "children"),
    Output("delete-scenario-btn", "children"),
    Output("active-scenario-label", "children"),
    Output("rename-scenario-input", "placeholder"),
    Output("rename-scenario-note", "children"),
    Output("rename-scenario-btn", "children"),
    Output("workspace-shell-title", "children"),
    Input("language-selector", "value"),
)
def translate_workspace_shell(language_value):
    lang = _lang(language_value)
    return (
        tr("workbench.sidebar.title", lang),
        tr("workbench.project.title", lang),
        tr("workbench.project.name", lang),
        tr("workbench.project.name_placeholder", lang),
        tr("workbench.project.open_label", lang),
        tr("workbench.project.none", lang),
        stacked_button_label(tr("workbench.project.save", lang)),
        stacked_button_label(tr("workbench.project.save_as", lang)),
        stacked_button_label(tr("workbench.project.open", lang)),
        stacked_button_label(tr("workbench.project.delete", lang)),
        tr("workbench.sidebar.start.title", lang),
        tr("workbench.import_excel.title", lang),
        tr("workbench.import_excel.copy", lang),
        tr("workbench.import_excel.action", lang),
        tr("workbench.load_example", lang),
        tr("workbench.duplicate", lang),
        tr("workbench.delete", lang),
        tr("workbench.active_scenario", lang),
        tr("workbench.rename_placeholder", lang),
        tr("workbench.rename_active_note", lang),
        tr("workbench.rename", lang),
        tr("workspace.shell.title", lang),
    )


@callback(
    Output("project-dropdown", "options"),
    Output("project-dropdown", "value"),
    Output("project-name-input", "value"),
    Output("project-status", "children"),
    Output("project-empty-note", "children"),
    Output("project-empty-note", "style"),
    Output("rename-scenario-input", "value"),
    Output("duplicate-scenario-btn", "disabled"),
    Output("delete-scenario-btn", "disabled"),
    Output("rename-scenario-btn", "disabled"),
    Output("scenario-rename-shell", "style"),
    Output("scenario-overview-list", "children"),
    Output("scenario-start-copy", "children"),
    Output("scenario-start-card", "style"),
    Output("scenario-empty-note", "children"),
    Output("scenario-empty-note", "style"),
    Output("workspace-active-name", "children"),
    Output("workspace-active-run-status", "children"),
    Output("workspace-project-status", "children"),
    Output("workspace-state-strip", "children"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_workspace_shell(session_payload, language_value):
    from dash import html

    lang = _lang(language_value)
    client_state, state = _session(session_payload, lang)
    project_options = _project_options()
    project_empty_note = tr("workbench.project.empty_note", lang)
    project_empty_style = {"display": "block"} if not project_options else {"display": "none"}
    project_status = (
        tr("workbench.project.bound", lang, name=state.project_name or state.project_slug)
        if state.project_slug
        else tr("workbench.project.unbound", lang)
    )
    active = state.get_scenario()
    pills = []
    for scenario in state.scenarios:
        css = "scenario-pill active" if scenario.scenario_id == state.active_scenario_id else "scenario-pill"
        if scenario.dirty and scenario.scan_result is None:
            status = tr("workspace.scenario_status.not_run", lang)
        elif scenario.dirty:
            status = tr("workspace.scenario_status.rerun", lang)
        else:
            status = tr("workspace.scenario_status.ready", lang)
        pills.append(
            html.Button(
                id={"type": "scenario-pill", "scenario_id": scenario.scenario_id},
                className=css,
                n_clicks=0,
                type="button",
                children=[
                    html.Div(scenario.name),
                    html.Div(f"{scenario.source_name} · {status}", className="scenario-meta"),
                ],
            )
        )

    if active is None:
        return (
            project_options,
            state.project_slug,
            state.project_name or "",
            project_status,
            project_empty_note,
            project_empty_style,
            "",
            True,
            True,
            True,
            {"display": "none"},
            pills,
            tr("workbench.sidebar.start.copy", lang),
            {"display": "grid"},
            tr("workbench.no_active_scenario", lang),
            {"display": "block"},
            tr("workbench.no_active_scenario", lang),
            tr("workbench.run_pending", lang),
            project_status,
            _workspace_state_strip_children(state=state, active=None, session_id=client_state.session_id, lang=lang),
        )

    run_status = tr("workbench.last_run", lang, value=active.last_run_at) if active.last_run_at else tr("workbench.run_not_executed", lang)
    return (
        project_options,
        state.project_slug,
        state.project_name or "",
        project_status,
        project_empty_note,
        project_empty_style,
        active.name,
        False,
        False,
        False,
        {"display": "grid"},
        pills,
        tr("workbench.sidebar.start.copy", lang),
        {"display": "none"},
        "",
        {"display": "none"},
        tr("workspace.shell.active", lang, name=active.name, source=active.source_name),
        run_status,
        project_status,
        _workspace_state_strip_children(state=state, active=active, session_id=client_state.session_id, lang=lang),
    )


@callback(
    Output("scenario-session-store", "data"),
    Output("workbench-status", "children"),
    Input("scenario-upload", "contents"),
    Input("new-scenario-btn", "n_clicks"),
    Input("duplicate-scenario-btn", "n_clicks"),
    Input("rename-scenario-btn", "n_clicks"),
    Input("delete-scenario-btn", "n_clicks"),
    Input({"type": "scenario-pill", "scenario_id": ALL}, "n_clicks"),
    Input("save-project-btn", "n_clicks"),
    Input("save-project-as-btn", "n_clicks"),
    Input("open-project-btn", "n_clicks"),
    Input("delete-project-btn", "n_clicks"),
    State("scenario-upload", "filename"),
    State("rename-scenario-input", "value"),
    State("project-name-input", "value"),
    State("project-dropdown", "value"),
    State("scenario-session-store", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def mutate_workspace_session(
    upload_contents,
    _new_scenario_clicks,
    _duplicate_clicks,
    _rename_clicks,
    _delete_clicks,
    _scenario_pill_clicks,
    _save_project_clicks,
    _save_project_as_clicks,
    _open_project_clicks,
    _delete_project_clicks,
    upload_filename,
    rename_value,
    project_name_value,
    project_dropdown_value,
    session_payload,
    language_value,
):
    lang = _lang(language_value)
    trigger = ctx.triggered_id
    client_state, state = _session(session_payload, lang)
    try:
        if trigger == "scenario-upload":
            if not upload_contents:
                raise PreventUpdate
            _, encoded = upload_contents.split(",", 1)
            bundle = load_config_from_excel(base64.b64decode(encoded))
            scenario_name = _scenario_name_from_filename(
                upload_filename,
                default_scenario_name(state, prefix="Escenario" if lang == "es" else "Scenario"),
            )
            record = create_scenario_record(scenario_name, bundle, source_name=upload_filename or bundle.source_name)
            state = add_scenario(state, record, make_active=True)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.loaded_workbook", lang, name=record.name)

        if trigger == "new-scenario-btn":
            bundle = load_example_config()
            name = default_scenario_name(state, prefix="Escenario" if lang == "es" else "Scenario")
            record = create_scenario_record(name, bundle, source_name=bundle.source_name)
            state = add_scenario(state, record, make_active=True)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.loaded_example", lang, name=record.name)

        if trigger == "open-project-btn":
            if not project_dropdown_value:
                raise ValueError(tr("workbench.project.select_required", lang))
            clear_session_workspace_drafts(client_state.session_id)
            state = open_project(project_dropdown_value)
            client_state = commit_client_session(client_state, state)
            return (
                client_state.to_payload(),
                tr("workbench.project.opened", lang, name=state.project_name, path=str(project_root(state.project_slug))),
            )

        if trigger == "delete-project-btn":
            if not project_dropdown_value:
                raise ValueError(tr("workbench.project.delete_select_required", lang))
            deleted_name = delete_project(project_dropdown_value)
            if state.project_slug == project_dropdown_value:
                state = replace(state, project_slug=None, project_name=None, project_dirty=True)
            client_state = commit_client_session(client_state, state)
            return (
                client_state.to_payload(),
                tr("workbench.project.deleted", lang, name=deleted_name),
            )

        if isinstance(trigger, str) and trigger in {"save-project-btn", "save-project-as-btn"}:
            resolved_name = _resolved_project_name(project_name_value, state)
            if not resolved_name:
                raise ValueError(tr("workbench.project.name_required", lang))
            if trigger == "save-project-btn":
                state = save_project(state, project_name=resolved_name, language=lang)
            else:
                state = save_project_as(state, project_name=resolved_name, language=lang)
            client_state = commit_client_session(client_state, state)
            return (
                client_state.to_payload(),
                tr("workbench.project.saved", lang, name=state.project_name, path=str(project_root(state.project_slug))),
            )

        active = state.get_scenario()
        if active is None:
            raise PreventUpdate

        if trigger == "duplicate-scenario-btn":
            state = duplicate_scenario(state, active.scenario_id)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.duplicated", lang)

        if trigger == "rename-scenario-btn":
            state = rename_scenario(state, active.scenario_id, rename_value or active.name)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.renamed", lang)

        if trigger == "delete-scenario-btn":
            clear_workspace_draft(client_state.session_id, active.scenario_id)
            state = delete_scenario(state, active.scenario_id)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.deleted", lang)

        if isinstance(trigger, dict) and trigger.get("type") == "scenario-pill":
            selected_scenario_id = str(trigger.get("scenario_id", "")).strip()
            if not selected_scenario_id or selected_scenario_id == state.active_scenario_id:
                raise PreventUpdate
            state = set_active_scenario(state, selected_scenario_id)
            selected = state.get_scenario()
            client_state = commit_client_session(client_state, state)
            return (
                client_state.to_payload(),
                tr("workbench.set_active_status", lang, name=selected.name) if selected else tr("workbench.no_active_scenario", lang),
            )
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc)

    raise PreventUpdate
