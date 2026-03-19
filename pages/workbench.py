from __future__ import annotations

import base64
from pathlib import Path
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, register_page
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from components import (
    assumption_editor_section,
    candidate_explorer_section,
    catalog_editor_section,
    profile_editor_section,
    render_assumption_sections,
    render_kpi_cards,
    render_schematic_inspector,
    render_schematic_legend,
    selected_candidate_deep_dive_section,
    render_validation_panel,
    scenario_sidebar,
)
from services import (
    add_scenario,
    build_assumption_sections,
    build_display_columns,
    build_schematic_legend,
    build_table_display_columns,
    build_unifilar_model,
    commit_client_session,
    collect_config_updates,
    create_scenario_record,
    default_schematic_inspector,
    internal_results_root,
    default_scenario_name,
    delete_scenario,
    demand_profile_visibility,
    duplicate_scenario,
    export_deterministic_artifacts,
    export_scenario_workbook,
    format_metric,
    frame_from_rows,
    load_config_from_excel,
    load_example_config,
    list_projects,
    normalize_battery_catalog_rows,
    normalize_inverter_catalog_rows,
    normalize_price_table_rows,
    open_export_folder,
    open_project,
    publish_export_artifacts,
    project_exports_root,
    project_root,
    rebuild_bundle_from_ui,
    refresh_bundle_issues,
    rename_scenario,
    resolve_client_session,
    resolve_schematic_focus,
    resolve_schematic_inspector,
    resolve_scenario_session,
    resolve_selected_candidate_key_for_scenario,
    run_scenario_scan,
    save_project,
    save_project_as,
    set_active_scenario,
    to_cytoscape_elements,
    tr,
    update_scenario_bundle,
    update_selected_candidate,
)
from services.result_views import (
    build_annual_coverage_figure,
    build_battery_load_figure,
    build_cash_flow,
    build_cash_flow_figure,
    build_kpis,
    build_monthly_balance,
    build_monthly_balance_figure,
    build_npv_figure,
    build_typical_day_figure,
)
from services.validation import BATTERY_REQUIRED_COLUMNS, INVERTER_REQUIRED_COLUMNS

register_page(__name__, path="/", name="Workbench")

def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _empty_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


def _session_with_scan(payload, language_value: str | None):
    client_state, session_state = resolve_scenario_session(payload, ensure_scan=True, language=_lang(language_value))
    return client_state, session_state, session_state.get_scenario()


def _download_payload(content: bytes, filename: str) -> dict:
    return {"content": base64.b64encode(content).decode("ascii"), "filename": filename, "base64": True}


def _scenario_name_from_filename(filename: str | None, fallback: str) -> str:
    if filename:
        stem = Path(filename).stem.strip()
        if stem:
            return stem
    return fallback


def _project_options():
    return [{"label": manifest.name, "value": manifest.slug} for manifest in list_projects()]


def _blank_table_row(table_columns, table_rows=None) -> dict[str, str]:
    column_ids = [
        str(column.get("id", "")).strip()
        for column in (table_columns or [])
        if str(column.get("id", "")).strip()
    ]
    if not column_ids and table_rows:
        column_ids = [str(column).strip() for column in table_rows[0].keys() if str(column).strip()]
    return {column_id: "" for column_id in column_ids}


def _candidate_table_styles(selected_key: str, best_key: str) -> list[dict]:
    return [
        {
            "if": {"filter_query": f'{{candidate_key}} = "{best_key}"'},
            "backgroundColor": "#dcfce7",
            "fontWeight": "bold",
        },
        {
            "if": {"filter_query": "{best_battery_for_kwp} = true"},
            "backgroundColor": "#eff6ff",
        },
        {
            "if": {"filter_query": f'{{candidate_key}} = "{selected_key}"'},
            "backgroundColor": "#fee2e2",
            "borderTop": "2px solid #b91c1c",
            "borderBottom": "2px solid #b91c1c",
            "fontWeight": "bold",
        },
    ]


def _selected_candidate_banner(detail: dict | None, *, lang: str = "es") -> list[html.Div]:
    fallback = "—"
    if not detail:
        return [
            html.Div(
                className="selected-candidate-banner-item",
                children=[
                    html.Span(tr("workbench.selected_design.banner.label", lang), className="selected-candidate-banner-label"),
                    html.Span(fallback, className="selected-candidate-banner-value"),
                ],
            )
        ]
    inverter_name = (((detail.get("inv_sel") or {}).get("inverter") or {}).get("name")) or fallback
    battery_name = format_metric("selected_battery", detail.get("battery_name", "None"), lang) if detail.get("battery_name") is not None else fallback
    npv_value = detail.get("summary", {}).get("cum_disc_final")
    kwp_value = detail.get("kWp")
    banner_values = [
        (tr("workbench.selected_design.banner.kwp", lang), f"{float(kwp_value):.3f} kWp" if kwp_value is not None else fallback),
        (tr("workbench.selected_design.banner.battery", lang), battery_name or fallback),
        (tr("workbench.selected_design.banner.inverter", lang), str(inverter_name)),
        (tr("workbench.selected_design.banner.npv", lang), format_metric("NPV_COP", npv_value, lang) if npv_value is not None else fallback),
    ]
    return [
        html.Div(
            className="selected-candidate-banner-item",
            children=[
                html.Span(label, className="selected-candidate-banner-label"),
                html.Span(value, className="selected-candidate-banner-value"),
            ],
        )
        for label, value in banner_values
    ]


layout = html.Div(
    className="page",
    children=[
        dcc.Download(id="scenario-download"),
        dcc.Store(id="workbench-latest-export-folder", storage_type="memory", data=""),
        html.Div(
            className="workbench-grid",
            children=[
                scenario_sidebar(),
                html.Div(
                    className="main-stack",
                    children=[
                        html.Div(
                            className="panel active-summary-card",
                            children=[
                                html.Div(
                                    className="active-summary-top",
                                    children=[
                                        html.Div(
                                            className="active-summary-content",
                                            children=[
                                                html.H2(tr("workbench.section.active", "es"), id="active-scenario-panel-title"),
                                                html.Div(tr("workbench.no_active_scenario", "es"), id="active-source-status", className="status-line active-summary-meta"),
                                                html.Div(tr("workbench.run_pending", "es"), id="active-run-status", className="status-line active-summary-meta"),
                                                html.Div(tr("workbench.run_running", "es"), id="active-run-progress", className="status-line active-summary-meta", style={"display": "none"}),
                                                html.P(tr("workbench.scan_guidance", "es"), id="active-scan-guidance", className="active-summary-copy"),
                                            ],
                                        ),
                                        html.Div(
                                            className="active-summary-actions",
                                            children=[html.Button(tr("workbench.run_scan", "es"), id="run-active-scan-btn", n_clicks=0, className="action-btn")],
                                        ),
                                    ],
                                ),
                                html.H3(tr("common.validation", "es"), id="active-validation-title"),
                                html.Div(render_validation_panel([], lang="es"), id="active-validation"),
                            ],
                        ),
                        assumption_editor_section(),
                        profile_editor_section(),
                        catalog_editor_section(),
                        dcc.Loading(
                            type="default",
                            children=html.Div(
                                id="deterministic-results-area",
                                children=[candidate_explorer_section(), selected_candidate_deep_dive_section()],
                            ),
                        ),
                    ],
                ),
            ],
        ),
    ],
)


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
    Output("scenario-upload-prefix", "children"),
    Output("scenario-upload-link", "children"),
    Output("load-example-btn", "children"),
    Output("duplicate-scenario-btn", "children"),
    Output("delete-scenario-btn", "children"),
    Output("active-scenario-label", "children"),
    Output("scenario-dropdown", "placeholder"),
    Output("set-active-scenario-btn", "children"),
    Output("rename-scenario-input", "placeholder"),
    Output("rename-scenario-btn", "children"),
    Output("active-scenario-panel-title", "children"),
    Output("run-active-scan-btn", "children"),
    Output("active-validation-title", "children"),
    Output("active-run-progress", "children"),
    Output("active-scan-guidance", "children"),
    Output("assumption-editor-title", "children"),
    Output("assumption-show-all", "options"),
    Output("apply-edits-btn", "children"),
    Output("profile-editor-title", "children"),
    Output("profile-editor-note", "children"),
    Output("month-profile-title", "children"),
    Output("month-profile-tooltip", "children"),
    Output("sun-profile-title", "children"),
    Output("sun-profile-tooltip", "children"),
    Output("price-kwp-title", "children"),
    Output("price-kwp-tooltip", "children"),
    Output("price-kwp-others-title", "children"),
    Output("price-kwp-others-tooltip", "children"),
    Output("demand-profile-title", "children"),
    Output("demand-profile-tooltip", "children"),
    Output("demand-profile-general-title", "children"),
    Output("demand-profile-general-tooltip", "children"),
    Output("demand-profile-weights-title", "children"),
    Output("demand-profile-weights-tooltip", "children"),
    Output("add-price-kwp-row-btn", "children"),
    Output("add-price-kwp-others-row-btn", "children"),
    Output("catalog-editor-title", "children"),
    Output("inverter-editor-title", "children"),
    Output("battery-editor-title", "children"),
    Output("add-inverter-row-btn", "children"),
    Output("add-battery-row-btn", "children"),
    Output("candidate-explorer-title", "children"),
    Output("candidate-export-note", "children"),
    Output("candidate-explorer-intro", "children"),
    Output("selected-candidate-kpi-title", "children"),
    Output("candidate-selection-helper", "children"),
    Output("selected-candidate-deep-dive-title", "children"),
    Output("selected-candidate-deep-dive-note", "children"),
    Output("scenario-export-btn", "children"),
    Output("scenario-artifacts-btn", "children"),
    Output("scenario-open-exports-btn", "children"),
    Output("scenario-artifacts-progress", "children"),
    Input("language-selector", "value"),
)
def translate_workbench_page(language_value):
    lang = _lang(language_value)
    return (
        tr("workbench.sidebar.title", lang),
        tr("workbench.project.title", lang),
        tr("workbench.project.name", lang),
        tr("workbench.project.name_placeholder", lang),
        tr("workbench.project.open_label", lang),
        tr("workbench.project.none", lang),
        tr("workbench.project.save", lang),
        tr("workbench.project.save_as", lang),
        tr("workbench.project.open", lang),
        tr("workbench.upload.prefix", lang),
        tr("workbench.upload.link", lang),
        tr("workbench.load_example", lang),
        tr("workbench.duplicate", lang),
        tr("workbench.delete", lang),
        tr("workbench.active_scenario", lang),
        tr("workbench.no_scenarios_loaded", lang),
        tr("workbench.set_active", lang),
        tr("workbench.rename_placeholder", lang),
        tr("workbench.rename", lang),
        tr("workbench.section.active", lang),
        tr("workbench.run_scan", lang),
        tr("common.validation", lang),
        tr("workbench.run_running", lang),
        tr("workbench.scan_guidance", lang),
        tr("workbench.assumptions", lang),
        [{"label": tr("workbench.assumptions.show_all", lang), "value": "all"}],
        tr("workbench.assumptions.apply", lang),
        tr("workbench.profiles", lang),
        tr("workbench.profiles.note", lang),
        tr("workbench.profiles.month", lang),
        tr("workbench.profiles.tooltip.month", lang),
        tr("workbench.profiles.sun", lang),
        tr("workbench.profiles.tooltip.sun", lang),
        tr("workbench.profiles.price", lang),
        tr("workbench.profiles.tooltip.price", lang),
        tr("workbench.profiles.price_others", lang),
        tr("workbench.profiles.tooltip.price_others", lang),
        tr("workbench.profiles.demand_weekday", lang),
        tr("workbench.profiles.tooltip.demand_weekday", lang),
        tr("workbench.profiles.demand_general", lang),
        tr("workbench.profiles.tooltip.demand_general", lang),
        tr("workbench.profiles.demand_weights", lang),
        tr("workbench.profiles.tooltip.demand_weights", lang),
        tr("workbench.profiles.add_row", lang),
        tr("workbench.profiles.add_row", lang),
        tr("workbench.catalogs", lang),
        tr("workbench.catalogs.inverters", lang),
        tr("workbench.catalogs.batteries", lang),
        tr("workbench.add_row", lang),
        tr("workbench.add_row", lang),
        tr("workbench.candidate_explorer", lang),
        tr("workbench.export.note", lang),
        tr("workbench.candidate_explorer.intro", lang),
        tr("workbench.selected_design.summary", lang),
        tr("workbench.candidate_selection.helper", lang),
        tr("workbench.deep_dive.title", lang),
        tr("workbench.deep_dive.note", lang),
        tr("workbench.export_scenario", lang),
        tr("common.export_artifacts", lang),
        tr("common.open_exports_folder", lang),
        tr("workbench.export_artifacts_running", lang),
    )


@callback(
    Output("project-dropdown", "options"),
    Output("project-dropdown", "value"),
    Output("project-name-input", "value"),
    Output("project-status", "children"),
    Output("scenario-dropdown", "options"),
    Output("scenario-dropdown", "value"),
    Output("rename-scenario-input", "value"),
    Output("scenario-overview-list", "children"),
    Output("active-source-status", "children"),
    Output("active-run-status", "children"),
    Output("active-validation", "children"),
    Output("run-active-scan-btn", "disabled"),
    Output("scenario-export-btn", "disabled"),
    Output("scenario-artifacts-btn", "disabled"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_scenario_shell(session_payload, language_value):
    lang = _lang(language_value)
    _, state = _session(session_payload, lang)
    project_options = _project_options()
    project_status = (
        tr("workbench.project.bound", lang, name=state.project_name or state.project_slug)
        if state.project_slug
        else tr("workbench.project.unbound", lang)
    )
    options = [{"label": scenario.name, "value": scenario.scenario_id} for scenario in state.scenarios]
    active = state.get_scenario()
    pills = []
    for scenario in state.scenarios:
        css = "scenario-pill active" if scenario.scenario_id == state.active_scenario_id else "scenario-pill"
        status = "sin ejecutar" if scenario.dirty and scenario.scan_result is None else ("requiere recálculo" if scenario.dirty else "listo")
        if lang == "en":
            status = "not run yet" if scenario.dirty and scenario.scan_result is None else ("rerun required" if scenario.dirty else "ready")
        pills.append(
            html.Div(
                className=css,
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
            options,
            None,
            "",
            pills,
            tr("workbench.no_active_scenario", lang),
            tr("workbench.run_pending", lang),
            render_validation_panel([], lang=lang),
            True,
            True,
            True,
        )

    if active.last_run_at:
        run_status = tr("workbench.last_run", lang, value=active.last_run_at)
    else:
        run_status = tr("workbench.run_not_executed", lang)
    validation_children = render_validation_panel(active.config_bundle.issues, lang=lang)
    has_errors = any(issue.level == "error" for issue in active.config_bundle.issues)
    export_disabled = active.dirty
    return (
        project_options,
        state.project_slug,
        state.project_name or "",
        project_status,
        options,
        active.scenario_id,
        active.name,
        pills,
        tr("workbench.source_status", lang, value=active.source_name),
        run_status,
        validation_children,
        has_errors,
        export_disabled,
        export_disabled,
    )


@callback(
    Output("scenario-open-exports-btn", "disabled"),
    Input("workbench-latest-export-folder", "data"),
)
def sync_workbench_export_folder_button(folder_path):
    return not bool(folder_path)


@callback(
    Output("assumption-sections", "children"),
    Input("scenario-session-store", "data"),
    Input("assumption-show-all", "value"),
    Input("language-selector", "value"),
)
def populate_assumptions(session_payload, show_all_values, language_value):
    lang = _lang(language_value)
    _, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        return render_assumption_sections(
            [],
            show_all=False,
            empty_message=tr("workbench.assumptions.none", lang),
            advanced_label=tr("workbench.assumptions.advanced", lang),
        )

    sections = build_assumption_sections(
        active.config_bundle,
        lang=lang,
        show_all="all" in (show_all_values or []),
        exclude_groups={"Monte Carlo"},
    )
    return render_assumption_sections(
        sections,
        show_all="all" in (show_all_values or []),
        empty_message=tr("workbench.assumptions.none", lang),
        advanced_label=tr("workbench.assumptions.advanced", lang),
    )


@callback(
    Output("inverter-table-editor", "data"),
    Output("inverter-table-editor", "columns"),
    Output("inverter-table-editor", "tooltip_header"),
    Output("battery-table-editor", "data"),
    Output("battery-table-editor", "columns"),
    Output("battery-table-editor", "tooltip_header"),
    Output("month-profile-editor", "data"),
    Output("month-profile-editor", "columns"),
    Output("month-profile-editor", "tooltip_header"),
    Output("sun-profile-editor", "data"),
    Output("sun-profile-editor", "columns"),
    Output("sun-profile-editor", "tooltip_header"),
    Output("price-kwp-editor", "data"),
    Output("price-kwp-editor", "columns"),
    Output("price-kwp-editor", "tooltip_header"),
    Output("price-kwp-others-editor", "data"),
    Output("price-kwp-others-editor", "columns"),
    Output("price-kwp-others-editor", "tooltip_header"),
    Output("demand-profile-editor", "data"),
    Output("demand-profile-editor", "columns"),
    Output("demand-profile-editor", "tooltip_header"),
    Output("demand-profile-general-editor", "data"),
    Output("demand-profile-general-editor", "columns"),
    Output("demand-profile-general-editor", "tooltip_header"),
    Output("demand-profile-weights-editor", "data"),
    Output("demand-profile-weights-editor", "columns"),
    Output("demand-profile-weights-editor", "tooltip_header"),
    Output("demand-profile-panel", "style"),
    Output("demand-profile-general-panel", "style"),
    Output("demand-profile-weights-panel", "style"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_editors(session_payload, language_value):
    lang = _lang(language_value)
    _, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        empty = ([], [], {})
        hidden = {"display": "none"}
        return (
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            hidden,
            hidden,
            hidden,
        )

    bundle = active.config_bundle
    visibility = demand_profile_visibility(str(bundle.config.get("use_excel_profile", "")))
    inverter_columns, inverter_tooltips = build_table_display_columns("inverter_catalog", list(bundle.inverter_catalog.columns), lang)
    battery_columns, battery_tooltips = build_table_display_columns("battery_catalog", list(bundle.battery_catalog.columns), lang)
    month_columns, month_tooltips = build_table_display_columns("month_profile", list(bundle.month_profile_table.columns), lang)
    sun_columns, sun_tooltips = build_table_display_columns("sun_profile", list(bundle.sun_profile_table.columns), lang)
    kwp_columns, kwp_tooltips = build_table_display_columns("cop_kwp", list(bundle.cop_kwp_table.columns), lang)
    kwp_other_columns, kwp_other_tooltips = build_table_display_columns("cop_kwp_others", list(bundle.cop_kwp_table_others.columns), lang)
    demand_columns, demand_tooltips = build_table_display_columns("demand_profile", list(bundle.demand_profile_table.columns), lang)
    demand_general_columns, demand_general_tooltips = build_table_display_columns("demand_profile_general", list(bundle.demand_profile_general_table.columns), lang)
    demand_weight_columns, demand_weight_tooltips = build_table_display_columns("demand_profile_weights", list(bundle.demand_profile_weights_table.columns), lang)
    return (
        bundle.inverter_catalog.to_dict("records"),
        inverter_columns,
        inverter_tooltips,
        bundle.battery_catalog.to_dict("records"),
        battery_columns,
        battery_tooltips,
        bundle.month_profile_table.to_dict("records"),
        month_columns,
        month_tooltips,
        bundle.sun_profile_table.to_dict("records"),
        sun_columns,
        sun_tooltips,
        bundle.cop_kwp_table.to_dict("records"),
        kwp_columns,
        kwp_tooltips,
        bundle.cop_kwp_table_others.to_dict("records"),
        kwp_other_columns,
        kwp_other_tooltips,
        bundle.demand_profile_table.to_dict("records"),
        demand_columns,
        demand_tooltips,
        bundle.demand_profile_general_table.to_dict("records"),
        demand_general_columns,
        demand_general_tooltips,
        bundle.demand_profile_weights_table.to_dict("records"),
        demand_weight_columns,
        demand_weight_tooltips,
        visibility["demand-profile-panel"],
        visibility["demand-profile-general-panel"],
        visibility["demand-profile-weights-panel"],
    )


@callback(
    Output("inverter-table-editor", "data", allow_duplicate=True),
    Input("add-inverter-row-btn", "n_clicks"),
    State("inverter-table-editor", "data"),
    prevent_initial_call=True,
)
def add_inverter_row(n_clicks, table_rows):
    if not n_clicks:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append({column: "" for column in INVERTER_REQUIRED_COLUMNS})
    return rows


@callback(
    Output("battery-table-editor", "data", allow_duplicate=True),
    Input("add-battery-row-btn", "n_clicks"),
    State("battery-table-editor", "data"),
    prevent_initial_call=True,
)
def add_battery_row(n_clicks, table_rows):
    if not n_clicks:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append({column: "" for column in BATTERY_REQUIRED_COLUMNS})
    return rows


@callback(
    Output("price-kwp-editor", "data", allow_duplicate=True),
    Input("add-price-kwp-row-btn", "n_clicks"),
    State("price-kwp-editor", "data"),
    State("price-kwp-editor", "columns"),
    prevent_initial_call=True,
)
def add_price_kwp_row(n_clicks, table_rows, table_columns):
    if not n_clicks:
        raise PreventUpdate
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("price-kwp-others-editor", "data", allow_duplicate=True),
    Input("add-price-kwp-others-row-btn", "n_clicks"),
    State("price-kwp-others-editor", "data"),
    State("price-kwp-others-editor", "columns"),
    prevent_initial_call=True,
)
def add_price_kwp_others_row(n_clicks, table_rows, table_columns):
    if not n_clicks:
        raise PreventUpdate
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("scenario-session-store", "data"),
    Output("workbench-status", "children"),
    Input("scenario-upload", "contents"),
    Input("load-example-btn", "n_clicks"),
    Input("duplicate-scenario-btn", "n_clicks"),
    Input("rename-scenario-btn", "n_clicks"),
    Input("delete-scenario-btn", "n_clicks"),
    Input("apply-edits-btn", "n_clicks"),
    Input("run-active-scan-btn", "n_clicks"),
    Input("set-active-scenario-btn", "n_clicks"),
    Input("save-project-btn", "n_clicks"),
    Input("save-project-as-btn", "n_clicks"),
    Input("open-project-btn", "n_clicks"),
    State("scenario-upload", "filename"),
    State("rename-scenario-input", "value"),
    State("scenario-dropdown", "value"),
    State("project-name-input", "value"),
    State("project-dropdown", "value"),
    State("scenario-session-store", "data"),
    State({"type": "assumption-input", "field": ALL}, "id"),
    State({"type": "assumption-input", "field": ALL}, "value"),
    State("inverter-table-editor", "data"),
    State("battery-table-editor", "data"),
    State("month-profile-editor", "data"),
    State("sun-profile-editor", "data"),
    State("price-kwp-editor", "data"),
    State("price-kwp-others-editor", "data"),
    State("demand-profile-editor", "data"),
    State("demand-profile-general-editor", "data"),
    State("demand-profile-weights-editor", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("run-active-scan-btn", "disabled"), True, False),
        (Output("active-run-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def mutate_session_state(
    upload_contents,
    _example_clicks,
    _duplicate_clicks,
    _rename_clicks,
    _delete_clicks,
    _apply_clicks,
    _run_clicks,
    _set_active_clicks,
    _save_project_clicks,
    _save_project_as_clicks,
    _open_project_clicks,
    upload_filename,
    rename_value,
    scenario_dropdown_value,
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

    try:
        if trigger == "scenario-upload":
            if not upload_contents:
                raise PreventUpdate
            _, encoded = upload_contents.split(",", 1)
            bundle = load_config_from_excel(base64.b64decode(encoded))
            scenario_name = _scenario_name_from_filename(upload_filename, default_scenario_name(state, prefix="Escenario" if lang == "es" else "Scenario"))
            record = create_scenario_record(scenario_name, bundle, source_name=upload_filename or bundle.source_name)
            state = add_scenario(state, record, make_active=True)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.loaded_workbook", lang, name=record.name)

        if trigger == "load-example-btn":
            bundle = load_example_config()
            name = default_scenario_name(state, prefix="Escenario" if lang == "es" else "Scenario")
            record = create_scenario_record(name, bundle, source_name=bundle.source_name)
            state = add_scenario(state, record, make_active=True)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.loaded_example", lang, name=record.name)

        if trigger == "open-project-btn":
            if not project_dropdown_value:
                raise ValueError(tr("workbench.project.select_required", lang))
            state = open_project(project_dropdown_value)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.project.opened", lang, name=state.project_name, path=str(project_root(state.project_slug)))

        if trigger in {"save-project-btn", "save-project-as-btn"}:
            resolved_name = (project_name_value or state.project_name or "").strip()
            if not resolved_name:
                raise ValueError(tr("workbench.project.name_required", lang))
            if trigger == "save-project-btn":
                state = save_project(state, project_name=resolved_name, language=lang)
            else:
                state = save_project_as(state, project_name=resolved_name, language=lang)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.project.saved", lang, name=state.project_name, path=str(project_root(state.project_slug)))

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
            state = delete_scenario(state, active.scenario_id)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.deleted", lang)

        if trigger == "set-active-scenario-btn":
            if scenario_dropdown_value == state.active_scenario_id:
                raise PreventUpdate
            state = set_active_scenario(state, scenario_dropdown_value)
            selected = state.get_scenario()
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.set_active_status", lang, name=selected.name) if selected else tr("workbench.no_active_scenario", lang)

        if trigger == "apply-edits-btn":
            config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
            inverter_catalog, inverter_issues = normalize_inverter_catalog_rows(inverter_rows)
            battery_catalog, battery_issues = normalize_battery_catalog_rows(battery_rows)
            price_kwp_table, price_kwp_issues = normalize_price_table_rows(price_kwp_rows, "Precios_kWp_relativos")
            price_kwp_table_others, price_kwp_others_issues = normalize_price_table_rows(
                price_kwp_others_rows,
                "Precios_kWp_relativos_Otros",
            )

            bundle = rebuild_bundle_from_ui(
                active.config_bundle,
                config_updates=config,
                inverter_catalog=inverter_catalog,
                battery_catalog=battery_catalog,
                demand_profile=frame_from_rows(demand_profile_rows, list(active.config_bundle.demand_profile_table.columns)),
                demand_profile_weights=frame_from_rows(demand_profile_weights_rows, list(active.config_bundle.demand_profile_weights_table.columns)),
                demand_profile_general=frame_from_rows(demand_profile_general_rows, list(active.config_bundle.demand_profile_general_table.columns)),
                month_profile=frame_from_rows(month_profile_rows, list(active.config_bundle.month_profile_table.columns)),
                sun_profile=frame_from_rows(sun_profile_rows, list(active.config_bundle.sun_profile_table.columns)),
                cop_kwp_table=frame_from_rows(price_kwp_table.to_dict("records"), list(active.config_bundle.cop_kwp_table.columns)),
                cop_kwp_table_others=frame_from_rows(
                    price_kwp_table_others.to_dict("records"),
                    list(active.config_bundle.cop_kwp_table_others.columns),
                ),
            )
            bundle = refresh_bundle_issues(
                bundle,
                extra_issues=[*inverter_issues, *battery_issues, *price_kwp_issues, *price_kwp_others_issues],
            )
            state = update_scenario_bundle(state, active.scenario_id, bundle)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.applied_edits", lang)

        if trigger == "run-active-scan-btn":
            state = run_scenario_scan(state, active.scenario_id)
            updated = state.get_scenario(active.scenario_id)
            client_state = commit_client_session(client_state, state)
            return client_state.to_payload(), tr("workbench.scan_completed", lang, name=updated.name)

    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), tr("common.action_failed", lang, error=exc)

    raise PreventUpdate


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Input("active-candidate-table", "selected_rows"),
    Input("active-npv-graph", "clickData"),
    State("active-candidate-table", "data"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def persist_selected_candidate(selected_rows, click_data, table_rows, session_payload):
    client_state, state, active = _session_with_scan(session_payload, None)
    if active is None or active.scan_result is None:
        raise PreventUpdate
    selected_key = resolve_selected_candidate_key_for_scenario(
        active.scan_result,
        active.selected_candidate_key,
        table_rows=table_rows,
        selected_rows=selected_rows,
        click_data=click_data,
    )
    if selected_key == active.selected_candidate_key:
        raise PreventUpdate
    state = update_selected_candidate(state, active.scenario_id, selected_key)
    client_state = commit_client_session(client_state, state)
    return client_state.to_payload()


@callback(
    Output("active-kpi-cards", "children"),
    Output("active-npv-graph", "figure"),
    Output("selected-candidate-banner", "children"),
    Output("active-monthly-balance-graph", "figure"),
    Output("active-cash-flow-graph", "figure"),
    Output("active-annual-coverage-graph", "figure"),
    Output("active-battery-load-graph", "figure"),
    Output("active-typical-day-graph", "figure"),
    Output("active-candidate-table", "data"),
    Output("active-candidate-table", "columns"),
    Output("active-candidate-table", "selected_rows"),
    Output("active-candidate-table", "style_data_conditional"),
    Output("active-candidate-table", "tooltip_header"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_results(session_payload, language_value):
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    empty = _empty_figure(tr("common.results", lang), tr("workbench.results.empty", lang))
    if active is None or active.scan_result is None:
        return [], empty, [], empty, empty, empty, empty, empty, [], [], [], [], {}

    scan = active.scan_result
    selected_key = resolve_selected_candidate_key_for_scenario(scan, active.selected_candidate_key)
    detail = scan.candidate_details[selected_key]
    kpis = build_kpis(detail)
    monthly_balance = build_monthly_balance(detail["monthly"], lang=lang)
    cash_flow = build_cash_flow(detail["monthly"])
    table = scan.candidates.copy()
    table["battery"] = table["battery"].replace({"None": tr("common.no_battery", lang)})
    visible_columns = [
        "kWp",
        "battery",
        "NPV_COP",
        "payback_years",
        "capex_client",
        "self_consumption_ratio",
        "self_sufficiency_ratio",
        "annual_import_kwh",
        "annual_export_kwh",
        "peak_ratio",
    ]
    columns, tooltip_header = build_display_columns(visible_columns, lang)
    columns.extend(
        [
            {"name": "candidate_key", "id": "candidate_key"},
            {"name": "scan_order", "id": "scan_order"},
            {"name": "best_battery_for_kwp", "id": "best_battery_for_kwp"},
        ]
    )
    selected_index = table.index[table["candidate_key"] == selected_key].tolist()
    best_key = scan.best_candidate_key
    styles = _candidate_table_styles(selected_key, best_key)
    module_power_w = float(active.config_bundle.config.get("P_mod_W", 0.0) or 0.0)
    return (
        render_kpi_cards(kpis, lang),
        build_npv_figure(
            table,
            selected_key=selected_key,
            lang=lang,
            module_power_w=module_power_w,
        ),
        _selected_candidate_banner(detail, lang=lang),
        build_monthly_balance_figure(monthly_balance, lang=lang),
        build_cash_flow_figure(cash_flow, lang=lang, k_wp=float(detail["kWp"]), module_power_w=module_power_w),
        build_annual_coverage_figure(detail, active.config_bundle.config, lang=lang),
        build_battery_load_figure(detail, active.config_bundle.config, lang=lang),
        build_typical_day_figure(detail, active, lang=lang),
        table.to_dict("records"),
        columns,
        [selected_index[0]] if selected_index else [],
        styles,
        tooltip_header,
    )


@callback(
    Output("unifilar-diagram-title", "children"),
    Output("unifilar-diagram-summary", "children"),
    Output("unifilar-diagram-empty", "children"),
    Output("unifilar-diagram-empty", "style"),
    Output("unifilar-diagram-note", "children"),
    Output("unifilar-diagram-shell", "style"),
    Output("active-unifilar-diagram", "elements"),
    Output("active-unifilar-diagram", "style"),
    Output("unifilar-legend-title", "children"),
    Output("unifilar-legend-items", "children"),
    Output("unifilar-inspector-title", "children"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_unifilar_diagram(session_payload, language_value):
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    title = tr("workbench.schematic.title", lang)
    empty_message = tr("workbench.schematic.empty", lang)
    legend_title = tr("workbench.schematic.legend.title", lang)
    inspector_title = tr("workbench.schematic.inspector.title", lang)
    legend_children = render_schematic_legend(build_schematic_legend(lang))
    if active is None or active.scan_result is None:
        return (
            title,
            "",
            empty_message,
            {"display": "block"},
            "",
            {"display": "none"},
            [],
            {"width": "100%", "height": "420px"},
            legend_title,
            legend_children,
            inspector_title,
        )

    selected_key = resolve_selected_candidate_key_for_scenario(active.scan_result, active.selected_candidate_key)
    model = build_unifilar_model(active, selected_key, lang=lang)
    return (
        title,
        model.string_summary,
        "",
        {"display": "none"},
        model.note,
        {"display": "block"},
        to_cytoscape_elements(model),
        {"width": "100%", "height": f"{model.diagram_height}px"},
        legend_title,
        legend_children,
        inspector_title,
    )


@callback(
    Output("unifilar-inspector-lock", "data"),
    Input("active-unifilar-diagram", "tapNodeData"),
    Input("scenario-session-store", "data"),
)
def sync_unifilar_inspector_lock(tap_node, session_payload):
    trigger = ctx.triggered_id
    if trigger == "active-unifilar-diagram" and tap_node and tap_node.get("id"):
        return {"node_id": str(tap_node["id"])}
    return None


@callback(
    Output("unifilar-inspector-body", "children"),
    Input("unifilar-inspector-lock", "data"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_unifilar_inspector(inspector_lock, session_payload, language_value):
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    if active is None or active.scan_result is None:
        return render_schematic_inspector(
            default_schematic_inspector(
                model=None,
                lang=lang,
            )
        )

    selected_key = resolve_selected_candidate_key_for_scenario(active.scan_result, active.selected_candidate_key)
    model = build_unifilar_model(active, selected_key, lang=lang)
    locked_node_id = str((inspector_lock or {}).get("node_id") or "") or None
    node_data, is_locked = resolve_schematic_focus(locked_node_id=locked_node_id, hover_node_data=None)
    inspector = resolve_schematic_inspector(node_data, model, lang=lang, locked=is_locked)
    return render_schematic_inspector(inspector)


@callback(
    Output("scenario-download", "data"),
    Input("scenario-export-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def export_active_scenario(n_clicks, session_payload):
    if not n_clicks:
        raise PreventUpdate
    _, state, active = _session_with_scan(session_payload, None)
    if active is None or active.scan_result is None or active.dirty:
        raise PreventUpdate
    content = export_scenario_workbook(active)
    filename = f"{active.name.replace(' ', '_')}_deterministic.xlsx"
    return _download_payload(content, filename)


@callback(
    Output("workbench-status", "children", allow_duplicate=True),
    Output("workbench-latest-export-folder", "data"),
    Input("scenario-artifacts-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("scenario-artifacts-btn", "disabled"), True, False),
        (Output("scenario-artifacts-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def export_active_artifacts(n_clicks, session_payload, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
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


@callback(
    Output("workbench-status", "children", allow_duplicate=True),
    Input("scenario-open-exports-btn", "n_clicks"),
    State("workbench-latest-export-folder", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
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
