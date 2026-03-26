from __future__ import annotations

from types import SimpleNamespace

from dash import dcc, html
from dash.exceptions import PreventUpdate

from components import candidate_explorer_section, run_scan_choice_dialog, selected_candidate_deep_dive_section
from services import (
    apply_workbench_editor_state,
    commit_client_session,
    export_deterministic_artifacts,
    internal_results_root,
    open_export_folder,
    project_exports_root,
    publish_export_artifacts,
    resolve_client_session,
    run_scenario_scan,
    save_project,
    set_active_scenario,
    tr,
    update_scenario_bundle,
)
from services.workspace_admin_callbacks import (
    add_battery_row,
    add_inverter_row,
    add_price_kwp_others_row,
    add_price_kwp_row,
    render_active_profile_chart,
    sanitize_active_profile_table,
    translate_profile_table_activators,
)
from services.workspace_assumptions_callbacks import (
    cancel_run_scan_choice,
    populate_assumptions_page,
    resolve_run_scan_choice,
    sync_assumption_context_ui,
    sync_run_scan_choice_dialog,
)
from services.workspace_results_callbacks import (
    _candidate_table_styles,
    _selected_candidate_banner,
    export_active_scenario,
    populate_results,
    sync_candidate_horizon_slider,
)


ctx = SimpleNamespace(triggered_id=None)


layout = html.Div(
    className="page compatibility-workbench-layout",
    children=[
        dcc.Store(id="active-profile-table-state", storage_type="memory", data={"table_id": None}),
        run_scan_choice_dialog(),
        html.Div(
            className="panel active-summary-card",
            children=[
                html.Div(
                    className="active-summary-top",
                    children=[
                        html.Div(
                            className="active-summary-content",
                            children=[
                                html.Div(tr("workbench.source_status", "es", value="config.xlsx"), id="active-source-status", className="status-line active-summary-meta"),
                                html.Div(tr("workbench.run_pending", "es"), id="active-run-status", className="status-line active-summary-meta"),
                                html.P(tr("workbench.scan_guidance", "es"), id="active-scan-guidance", className="active-summary-copy"),
                                html.Div(id="workbench-state-strip", className="workbench-state-strip"),
                            ],
                        ),
                        html.Div(
                            className="active-summary-actions",
                            children=[html.Button(tr("workbench.run_scan", "es"), id="run-active-scan-btn", n_clicks=0, className="action-btn")],
                        ),
                    ],
                )
            ],
        ),
        html.Div(
            id="deterministic-results-area",
            children=[candidate_explorer_section(), selected_candidate_deep_dive_section()],
        ),
    ],
)


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


def _project_is_bound(state) -> bool:
    return bool(str(state.project_slug or "").strip())


def _resolved_project_name(project_name_value, state) -> str:
    return (project_name_value or state.project_name or state.project_slug or "").strip()


def _bundle_has_errors(bundle) -> bool:
    return any(issue.level == "error" for issue in bundle.issues)


def _join_status_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _run_choice_state(*, open_dialog: bool = False) -> dict[str, bool]:
    return {"open": open_dialog}


def _normalize_state_compare_value(value):
    import pandas as pd

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return int(number) if number.is_integer() else round(number, 10)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return ""
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        numeric_text = stripped.replace(",", "")
        try:
            number = float(numeric_text)
        except ValueError:
            return stripped
        return int(number) if number.is_integer() else round(number, 10)
    return value


def _normalized_records(rows, columns: list[str]) -> list[tuple]:
    from services.workbench_ui import frame_from_rows

    frame = frame_from_rows(rows, columns)
    return [
        tuple(_normalize_state_compare_value(record.get(column)) for column in columns)
        for record in frame.to_dict("records")
    ]


def _config_has_unapplied_changes(current_config: dict, base_config: dict) -> bool:
    keys = set(base_config) | set(current_config)
    return any(
        _normalize_state_compare_value(current_config.get(key)) != _normalize_state_compare_value(base_config.get(key))
        for key in keys
    )


def _table_has_unapplied_changes(rows, base_frame) -> bool:
    columns = list(base_frame.columns)
    return _normalized_records(rows, columns) != _normalized_records(base_frame.to_dict("records"), columns)


def sync_workbench_state_strip(
    session_payload,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    month_profile_rows,
    sun_profile_rows,
    price_kwp_rows,
    price_kwp_others_rows,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
    language_value,
):
    from services.workbench_ui import collect_config_updates

    lang = _lang(language_value)
    _, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        return [html.Span(tr("workbench.state.no_active", lang), className="workbench-state-chip workbench-state-chip-neutral")]

    bundle = active.config_bundle
    current_config = collect_config_updates(assumption_input_ids, assumption_values, bundle.config)
    has_unapplied_changes = _config_has_unapplied_changes(current_config, bundle.config) or any(
        _table_has_unapplied_changes(rows, base_frame)
        for rows, base_frame in [
            (inverter_rows, bundle.inverter_catalog),
            (battery_rows, bundle.battery_catalog),
            (month_profile_rows, bundle.month_profile_table),
            (sun_profile_rows, bundle.sun_profile_table),
            (price_kwp_rows, bundle.cop_kwp_table),
            (price_kwp_others_rows, bundle.cop_kwp_table_others),
            (demand_profile_rows, bundle.demand_profile_table),
            (demand_profile_general_rows, bundle.demand_profile_general_table),
            (demand_profile_weights_rows, bundle.demand_profile_weights_table),
        ]
    )
    project_saved = _project_is_bound(state) and not state.project_dirty and not has_unapplied_changes
    scan_current = not active.dirty and not has_unapplied_changes
    return [
        html.Span(
            tr("workbench.state.pending_apply", lang) if has_unapplied_changes else tr("workbench.state.applied", lang),
            className=f"workbench-state-chip {'workbench-state-chip-warning' if has_unapplied_changes else 'workbench-state-chip-neutral'}",
        ),
        html.Span(
            tr("workbench.state.project_saved", lang) if project_saved else tr("workbench.state.project_unsaved", lang),
            className=f"workbench-state-chip {'workbench-state-chip-success' if project_saved else 'workbench-state-chip-warning'}",
        ),
        html.Span(
            tr("workbench.state.ready_to_run", lang) if scan_current else tr("workbench.state.scan_outdated", lang),
            className=f"workbench-state-chip {'workbench-state-chip-info' if scan_current else 'workbench-state-chip-warning'}",
        ),
    ]


def populate_assumptions(session_payload, show_all_values, language_value):
    return populate_assumptions_page(session_payload, show_all_values, language_value)[0]


def sync_active_profile_table(
    _activator_clicks,
    month_active_cell,
    sun_active_cell,
    price_active_cell,
    price_others_active_cell,
    active_state,
):
    trigger = ctx.triggered_id
    current_table_id = str((active_state or {}).get("table_id") or "").strip() or None
    profile_table_ids = (
        "month-profile-editor",
        "sun-profile-editor",
        "price-kwp-editor",
        "price-kwp-others-editor",
    )
    activator_clicks = {
        table_id: int(clicks or 0)
        for table_id, clicks in zip(profile_table_ids, _activator_clicks or [])
    }
    active_cells = {
        "month-profile-editor": month_active_cell,
        "sun-profile-editor": sun_active_cell,
        "price-kwp-editor": price_active_cell,
        "price-kwp-others-editor": price_others_active_cell,
    }
    if isinstance(trigger, dict) and trigger.get("type") == "profile-table-activate":
        table_id = str(trigger.get("table", "")).strip() or None
        if table_id is None:
            raise PreventUpdate
        if activator_clicks.get(table_id, 0) <= 0:
            raise PreventUpdate
        if table_id == current_table_id:
            return {"table_id": None}
        return {"table_id": table_id}
    if isinstance(trigger, str) and trigger in active_cells:
        if not active_cells.get(trigger) or trigger == current_table_id:
            raise PreventUpdate
        return {"table_id": trigger}
    raise PreventUpdate


def mutate_session_state(
    upload_contents,
    _new_scenario_clicks,
    _duplicate_clicks,
    _rename_clicks,
    _delete_clicks,
    _scenario_pill_clicks,
    _apply_clicks,
    _run_clicks,
    _save_project_clicks,
    _save_project_as_clicks,
    _open_project_clicks,
    upload_filename,
    rename_value,
    project_name_value,
    project_dropdown_value,
    session_payload,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    month_profile_rows,
    sun_profile_rows,
    price_kwp_rows,
    price_kwp_others_rows,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
    language_value,
):
    lang = _lang(language_value)
    trigger = ctx.triggered_id
    client_state, state = _session(session_payload, lang)
    closed_dialog = _run_choice_state()
    active = state.get_scenario()
    if active is None and not (isinstance(trigger, dict) and trigger.get("type") == "scenario-pill"):
        raise PreventUpdate
    try:
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
                closed_dialog,
            )

        bundle = apply_workbench_editor_state(
            active.config_bundle,
            assumption_input_ids=assumption_input_ids,
            assumption_values=assumption_values,
            inverter_rows=inverter_rows,
            battery_rows=battery_rows,
            month_profile_rows=month_profile_rows,
            sun_profile_rows=sun_profile_rows,
            price_kwp_rows=price_kwp_rows,
            price_kwp_others_rows=price_kwp_others_rows,
            demand_profile_rows=demand_profile_rows,
            demand_profile_general_rows=demand_profile_general_rows,
            demand_profile_weights_rows=demand_profile_weights_rows,
        )
        state = update_scenario_bundle(state, active.scenario_id, bundle)
        updated_active = state.get_scenario(active.scenario_id) or active

        if trigger == "apply-edits-btn":
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

        if trigger == "run-active-scan-btn":
            if _project_is_bound(state):
                saved = False
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
        return client_state.to_payload(), tr("common.action_failed", lang, error=exc), closed_dialog
    raise PreventUpdate


def export_active_artifacts(n_clicks, session_payload, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    _, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None or active.scan_result is None or active.dirty:
        raise PreventUpdate
    output_root = project_exports_root(state.project_slug) if state.project_slug else internal_results_root()
    paths = export_deterministic_artifacts(active, output_root=output_root)
    publish_result = publish_export_artifacts(
        paths,
        project_slug=state.project_slug,
        scenario_slug=active.name or active.scenario_id,
        export_kind="deterministic",
    )
    if publish_result.published_root is not None:
        published_path = str(publish_result.published_root.resolve())
        return tr("workbench.export_artifacts_done", lang, path=published_path), published_path
    if publish_result.publish_error:
        return (
            tr(
                "workbench.export_artifacts_partial",
                lang,
                path=str(publish_result.internal_root.resolve()),
                error=publish_result.publish_error,
            ),
            "",
        )
    return tr("workbench.export_artifacts_done", lang, path=str(publish_result.display_root.resolve())), ""


def open_workbench_exports_folder(n_clicks, folder_path, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    if not folder_path:
        return tr("common.exports_folder_unavailable", lang, error=tr("common.exports_folder_none", lang))
    try:
        open_export_folder(folder_path)
    except (FileNotFoundError, OSError, RuntimeError) as exc:
        return tr("common.exports_folder_unavailable", lang, error=str(exc))
    return tr("common.exports_folder_opened", lang, path=folder_path)


__all__ = [
    "_candidate_table_styles",
    "_selected_candidate_banner",
    "_session",
    "add_battery_row",
    "add_inverter_row",
    "add_price_kwp_others_row",
    "add_price_kwp_row",
    "cancel_run_scan_choice",
    "ctx",
    "export_active_artifacts",
    "export_active_scenario",
    "layout",
    "mutate_session_state",
    "open_workbench_exports_folder",
    "populate_assumptions",
    "populate_results",
    "render_active_profile_chart",
    "resolve_run_scan_choice",
    "sanitize_active_profile_table",
    "sync_active_profile_table",
    "sync_assumption_context_ui",
    "sync_candidate_horizon_slider",
    "sync_run_scan_choice_dialog",
    "sync_workbench_state_strip",
    "translate_profile_table_activators",
]
