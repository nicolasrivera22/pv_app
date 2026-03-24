from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate

from components import render_assumption_sections, render_validation_panel
from .i18n import tr
from .project_io import save_project
from .scenario_session import run_scenario_scan
from .session_state import commit_client_session, resolve_client_session
from .ui_schema import assumption_context_map, build_assumption_sections
from .workbench_ui import collect_config_updates, workbench_status_message
from .workspace_actions import apply_workspace_draft_to_state, config_overrides_for_fields, resolve_workspace_bundle_for_display
from .workspace_drafts import bind_workspace_draft_project, upsert_workspace_draft
from .workspace_partitions import partition_assumption_sections


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


def _project_is_bound(state) -> bool:
    return bool(str(state.project_slug or "").strip())


def _resolved_project_name(project_name_value, state) -> str:
    return (project_name_value or state.project_name or state.project_slug or "").strip()


def _join_status_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _run_choice_state(*, open_dialog: bool = False) -> dict[str, bool]:
    return {"open": open_dialog}


def _bundle_has_errors(bundle) -> bool:
    return any(issue.level == "error" for issue in bundle.issues)


def _assumption_note_style(message: str) -> dict[str, str]:
    return {"display": "block"} if str(message or "").strip() else {"display": "none"}


def _assumption_card_class(field_key: str, *, disabled: bool = False, emphasize: bool = False) -> str:
    classes = ["field-card"]
    if disabled:
        classes.append("field-card-disabled")
    if emphasize and not disabled:
        classes.append("field-card-highlight")
    return " ".join(dict.fromkeys(classes))


@callback(
    Output("assumptions-page-title", "children"),
    Output("assumptions-page-copy", "children"),
    Output("assumptions-validation-title", "children"),
    Output("assumptions-show-all", "options"),
    Output("apply-assumptions-btn", "children"),
    Output("run-assumptions-scan-btn", "children"),
    Output("assumptions-run-progress", "children"),
    Input("language-selector", "value"),
)
def translate_assumptions_page(language_value):
    lang = _lang(language_value)
    return (
        tr("workspace.assumptions.title", lang),
        tr("workspace.assumptions.copy", lang),
        tr("common.validation", lang),
        [{"label": tr("workbench.assumptions.show_all", lang), "value": "all"}],
        tr("workbench.assumptions.apply", lang),
        tr("workbench.run_scan", lang),
        tr("workbench.run_running", lang),
    )


@callback(
    Output("assumptions-sections", "children"),
    Output("assumptions-validation", "children"),
    Output("apply-assumptions-btn", "disabled"),
    Output("run-assumptions-scan-btn", "disabled"),
    Input("scenario-session-store", "data"),
    Input("assumptions-show-all", "value"),
    Input("language-selector", "value"),
)
def populate_assumptions_page(session_payload, show_all_values, language_value):
    lang = _lang(language_value)
    client_state, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        return (
            render_assumption_sections(
                [],
                show_all=False,
                empty_message=tr("workbench.assumptions.none", lang),
                advanced_label=tr("workbench.assumptions.advanced", lang),
                input_id_type="assumptions-input",
                field_card_type="assumptions-field-card",
                context_note_type="assumptions-context-note",
            ),
            render_validation_panel([], lang=lang),
            True,
            True,
        )

    display_bundle = resolve_workspace_bundle_for_display(client_state.session_id, active.scenario_id, active.config_bundle)
    all_sections = build_assumption_sections(
        display_bundle,
        lang=lang,
        show_all="all" in (show_all_values or []),
    )
    partition = partition_assumption_sections(all_sections)
    has_errors = any(issue.level == "error" for issue in active.config_bundle.issues)
    return (
        render_assumption_sections(
            partition.client_safe_sections,
            show_all="all" in (show_all_values or []),
            empty_message=tr("workbench.assumptions.none", lang),
            advanced_label=tr("workbench.assumptions.advanced", lang),
            input_id_type="assumptions-input",
            field_card_type="assumptions-field-card",
            context_note_type="assumptions-context-note",
        ),
        render_validation_panel(active.config_bundle.issues, lang=lang),
        False,
        has_errors,
    )


@callback(
    Output({"type": "assumptions-input", "field": ALL}, "disabled"),
    Output({"type": "assumptions-field-card", "field": ALL}, "className"),
    Output({"type": "assumptions-context-note", "group": ALL}, "children"),
    Output({"type": "assumptions-context-note", "group": ALL}, "style"),
    Input("scenario-session-store", "data"),
    Input({"type": "assumptions-input", "field": ALL}, "id"),
    Input({"type": "assumptions-input", "field": ALL}, "value"),
    Input("language-selector", "value"),
    State({"type": "assumptions-field-card", "field": ALL}, "id"),
    State({"type": "assumptions-context-note", "group": ALL}, "id"),
)
def sync_assumption_context_ui(
    session_payload,
    assumption_input_ids,
    assumption_values,
    language_value,
    assumption_card_ids,
    note_ids,
):
    lang = _lang(language_value)
    _, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        return [], [], [], []

    current_config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
    context = assumption_context_map(current_config, lang=lang)
    disabled_map = dict(context.get("field_disabled") or {})
    emphasis_map = dict(context.get("field_emphasis") or {})
    notes_map = dict(context.get("notes") or {})

    disabled_values = [
        bool(disabled_map.get((component_id or {}).get("field", ""), False))
        for component_id in (assumption_input_ids or [])
    ]
    card_classes = [
        _assumption_card_class(
            str((component_id or {}).get("field", "")),
            disabled=bool(disabled_map.get((component_id or {}).get("field", ""), False)),
            emphasize=bool(emphasis_map.get((component_id or {}).get("field", ""), False)),
        )
        for component_id in (assumption_card_ids or [])
    ]
    note_children = [
        notes_map.get(str((component_id or {}).get("group", "")), "")
        for component_id in (note_ids or [])
    ]
    note_styles = [_assumption_note_style(message) for message in note_children]
    return disabled_values, card_classes, note_children, note_styles


@callback(
    Output("assumptions-draft-meta", "data"),
    Input("scenario-session-store", "data"),
    Input({"type": "assumptions-input", "field": ALL}, "id"),
    Input({"type": "assumptions-input", "field": ALL}, "value"),
    prevent_initial_call=True,
)
def sync_assumptions_draft(session_payload, assumption_input_ids, assumption_values):
    client_state, state = _session(session_payload, None)
    active = state.get_scenario()
    if active is None or not assumption_input_ids:
        raise PreventUpdate
    overrides, owned_fields = config_overrides_for_fields(
        base_config=active.config_bundle.config,
        input_ids=assumption_input_ids,
        input_values=assumption_values,
    )
    draft = upsert_workspace_draft(
        client_state.session_id,
        active.scenario_id,
        config_overrides=overrides,
        owned_config_fields=owned_fields,
        project_slug=state.project_slug,
    )
    if draft is not None and state.project_slug:
        bind_workspace_draft_project(client_state.session_id, active.scenario_id, state.project_slug)
    return {"revision": 0 if draft is None else draft.revision}


@callback(
    Output("run-scan-choice-dialog", "style"),
    Output("run-scan-choice-title", "children"),
    Output("run-scan-choice-copy", "children"),
    Output("run-scan-save-and-run-btn", "children"),
    Output("run-scan-save-and-run-btn", "disabled"),
    Output("run-scan-run-unsaved-btn", "children"),
    Output("run-scan-cancel-btn", "children"),
    Input("run-scan-choice-state", "data"),
    Input("project-name-input", "value"),
    Input("language-selector", "value"),
)
def sync_run_scan_choice_dialog(dialog_state, project_name_value, language_value):
    lang = _lang(language_value)
    project_name = str(project_name_value or "").strip()
    copy = (
        tr("workbench.run_dialog.body_named", lang, name=project_name)
        if project_name
        else tr("workbench.run_dialog.body_unnamed", lang)
    )
    style = {"display": "flex"} if (dialog_state or {}).get("open") else {"display": "none"}
    return (
        style,
        tr("workbench.run_dialog.title", lang),
        copy,
        tr("workbench.run_dialog.save_and_run", lang),
        not bool(project_name),
        tr("workbench.run_dialog.run_without_saving", lang),
        tr("workbench.run_dialog.cancel", lang),
    )


def _sync_current_assumptions_slice(client_state, state, active, assumption_input_ids, assumption_values):
    overrides, owned_fields = config_overrides_for_fields(
        base_config=active.config_bundle.config,
        input_ids=assumption_input_ids,
        input_values=assumption_values,
    )
    upsert_workspace_draft(
        client_state.session_id,
        active.scenario_id,
        config_overrides=overrides,
        owned_config_fields=owned_fields,
        project_slug=state.project_slug,
    )


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("workbench-status", "children", allow_duplicate=True),
    Output("run-scan-choice-state", "data"),
    Input("apply-assumptions-btn", "n_clicks"),
    Input("run-assumptions-scan-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("project-name-input", "value"),
    State({"type": "assumptions-input", "field": ALL}, "id"),
    State({"type": "assumptions-input", "field": ALL}, "value"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("run-assumptions-scan-btn", "disabled"), True, False),
        (Output("assumptions-run-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def mutate_assumptions_state(
    _apply_clicks,
    _run_clicks,
    session_payload,
    project_name_value,
    assumption_input_ids,
    assumption_values,
    language_value,
):
    lang = _lang(language_value)
    trigger = ctx.triggered_id
    client_state, state = _session(session_payload, lang)
    closed_dialog = _run_choice_state()
    try:
        active = state.get_scenario()
        if active is None:
            raise PreventUpdate

        _sync_current_assumptions_slice(client_state, state, active, assumption_input_ids, assumption_values)
        state, updated_active = apply_workspace_draft_to_state(
            state,
            session_id=client_state.session_id,
            scenario_id=active.scenario_id,
        )

        if trigger == "apply-assumptions-btn":
            saved = False
            if _project_is_bound(state):
                state = save_project(state, project_name=_resolved_project_name(project_name_value, state), language=lang)
                saved = True
            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.saved", lang) if saved else "",
                tr("workbench.run_flow.needs_rerun", lang),
            )
            return client_state.to_payload(), status, closed_dialog

        if trigger == "run-assumptions-scan-btn":
            if _project_is_bound(state):
                saved = False
                if _project_is_bound(state):
                    state = save_project(state, project_name=_resolved_project_name(project_name_value, state), language=lang)
                    updated_active = state.get_scenario(updated_active.scenario_id) or updated_active
                    saved = True
                if _bundle_has_errors(updated_active.config_bundle):
                    client_state = commit_client_session(client_state, state)
                    status = _join_status_parts(
                        tr("workbench.run_flow.applied", lang),
                        tr("workbench.run_flow.saved", lang) if saved else "",
                        tr("workbench.run_flow.validation_blocked", lang),
                    )
                    return client_state.to_payload(), status, closed_dialog
                state = run_scenario_scan(state, updated_active.scenario_id)
                updated = state.get_scenario(updated_active.scenario_id) or updated_active
                client_state = commit_client_session(client_state, state)
                status = _join_status_parts(
                    tr("workbench.run_flow.applied", lang),
                    tr("workbench.run_flow.saved", lang) if saved else "",
                    tr("workbench.run_flow.ran", lang, name=updated.name),
                )
                return client_state.to_payload(), status, closed_dialog

            if _bundle_has_errors(updated_active.config_bundle):
                client_state = commit_client_session(client_state, state)
                status = _join_status_parts(
                    tr("workbench.run_flow.applied", lang),
                    tr("workbench.run_flow.validation_blocked", lang),
                )
                return client_state.to_payload(), status, closed_dialog

            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.choose_save", lang),
            )
            return client_state.to_payload(), status, _run_choice_state(open_dialog=True)
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc), closed_dialog
    raise PreventUpdate


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("workbench-status", "children", allow_duplicate=True),
    Output("run-scan-choice-state", "data", allow_duplicate=True),
    Input("run-scan-save-and-run-btn", "n_clicks"),
    Input("run-scan-run-unsaved-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("project-name-input", "value"),
    State("run-scan-choice-state", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("run-assumptions-scan-btn", "disabled"), True, False),
        (Output("assumptions-run-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def resolve_run_scan_choice(
    _save_and_run_clicks,
    _run_without_saving_clicks,
    session_payload,
    project_name_value,
    dialog_state,
    language_value,
):
    lang = _lang(language_value)
    trigger = ctx.triggered_id
    client_state, state = _session(session_payload, lang)
    closed_dialog = _run_choice_state()

    if not (dialog_state or {}).get("open"):
        raise PreventUpdate

    try:
        active = state.get_scenario()
        if active is None:
            raise PreventUpdate

        if _bundle_has_errors(active.config_bundle):
            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.validation_blocked", lang),
            )
            return client_state.to_payload(), status, closed_dialog

        if trigger == "run-scan-save-and-run-btn":
            resolved_name = _resolved_project_name(project_name_value, state)
            if not resolved_name:
                return no_update, tr("workbench.run_dialog.name_required", lang), dialog_state
            state = save_project(state, project_name=resolved_name, language=lang)
            active = state.get_scenario(active.scenario_id) or active
            state = run_scenario_scan(state, active.scenario_id)
            updated = state.get_scenario(active.scenario_id) or active
            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.saved", lang),
                tr("workbench.run_flow.ran", lang, name=updated.name),
            )
            return client_state.to_payload(), status, closed_dialog

        if trigger == "run-scan-run-unsaved-btn":
            state = run_scenario_scan(state, active.scenario_id)
            updated = state.get_scenario(active.scenario_id) or active
            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.ran_without_saving", lang, name=updated.name),
            )
            return client_state.to_payload(), status, closed_dialog
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc), closed_dialog
    raise PreventUpdate


@callback(
    Output("workbench-status", "children", allow_duplicate=True),
    Output("run-scan-choice-state", "data", allow_duplicate=True),
    Input("run-scan-cancel-btn", "n_clicks"),
    State("run-scan-choice-state", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def cancel_run_scan_choice(_cancel_clicks, dialog_state, language_value):
    if not (dialog_state or {}).get("open"):
        raise PreventUpdate
    lang = _lang(language_value)
    status = _join_status_parts(
        tr("workbench.run_flow.applied", lang),
        tr("workbench.run_flow.cancelled", lang),
    )
    return status, _run_choice_state()
