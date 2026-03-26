from __future__ import annotations

import base64

from dash import Input, Output, State, callback, ctx, dash_table, dcc, html, register_page
from dash.exceptions import PreventUpdate

from components import render_ui_mode_gate
from services import (
    MAX_COMPARE_DESIGNS,
    append_design_selection,
    build_available_design_rows,
    build_design_compare_state,
    build_design_comparison_figures,
    build_design_comparison_rows,
    build_display_columns,
    commit_client_session,
    export_design_comparison_workbook,
    remove_design_selection,
    resolve_scenario_session,
    resolve_design_selection,
    set_design_comparison_candidates,
    tr,
)
from services.ui_mode import (
    PAGE_COMPARE,
    UI_MODE_SIMPLE,
    gate_visibility_style,
    page_body_style,
    resolve_page_access,
    resolve_ui_mode_from_payload,
)

register_page(__name__, path="/compare", name="Compare")


AVAILABLE_VISIBLE_COLUMNS = [
    "kWp",
    "panel_count",
    "battery",
    "inverter_name",
    "NPV_COP",
    "payback_years",
    "capex_client",
    "self_consumption_ratio",
    "annual_import_kwh",
    "annual_export_kwh",
]
SELECTED_VISIBLE_COLUMNS = [
    "design_label",
    "kWp",
    "panel_count",
    "battery",
    "inverter_name",
    "NPV_COP",
    "payback_years",
    "capex_client",
    "self_consumption_ratio",
]
SUMMARY_VISIBLE_COLUMNS = [
    "design_label",
    "kWp",
    "panel_count",
    "battery",
    "inverter_name",
    "NPV_COP",
    "payback_years",
    "capex_client",
    "self_consumption_ratio",
    "self_sufficiency_ratio",
    "annual_import_kwh",
    "annual_export_kwh",
    "peak_ratio",
]


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _compare_page_access(session_payload) -> object:
    return resolve_page_access(PAGE_COMPARE, resolve_ui_mode_from_payload(session_payload))


def _download_payload(content: bytes, filename: str) -> dict:
    return {"content": base64.b64encode(content).decode("ascii"), "filename": filename, "base64": True}


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip())
    return cleaned.strip("_") or "comparison"


def _table_columns(column_keys: list[str], lang: str, *, include_remove: bool = False) -> tuple[list[dict], dict[str, str]]:
    columns, tooltips = build_display_columns(column_keys, lang)
    if include_remove:
        columns.append({"name": tr("compare.column.remove", lang), "id": "remove_action", "presentation": "markdown"})
        tooltips["remove_action"] = tr("compare.action.remove", lang)
    return columns, tooltips


layout = html.Div(
    className="page",
    children=[
        html.Div(
            id="compare-mode-gate-shell",
            children=render_ui_mode_gate(resolve_page_access(PAGE_COMPARE, UI_MODE_SIMPLE), lang="es", component_id="compare-mode-gate"),
        ),
        html.Div(
            id="compare-page-content",
            style={"display": "none"},
            children=[
                dcc.Download(id="comparison-download"),
                html.Div(
                    className="main-stack",
                    children=[
                        html.Div(
                            className="panel",
                            children=[
                                html.Div(
                                    className="section-head",
                                    children=[
                                        html.H2(tr("compare.title", "es"), id="compare-page-title"),
                                        html.Div(
                                            className="controls",
                                            children=[
                                                html.Button(tr("compare.add", "es"), id="compare-add-btn", n_clicks=0, className="action-btn"),
                                                html.Button(tr("compare.clear", "es"), id="compare-clear-btn", n_clicks=0, className="action-btn secondary"),
                                                html.Button(tr("compare.export", "es"), id="comparison-export-btn", n_clicks=0, className="action-btn tertiary"),
                                            ],
                                        ),
                                    ],
                                ),
                                html.P(tr("compare.intro", "es"), id="compare-page-intro"),
                                html.P(tr("compare.flow_note", "es"), id="compare-flow-note", className="section-copy section-copy-wide"),
                                html.Div(className="scenario-meta", children=[html.Span(tr("compare.active_scenario", "es"), id="compare-active-scenario-label"), html.Span(" — ", className="scenario-sep"), html.Span("", id="compare-active-scenario-value")]),
                                html.Div("", id="comparison-export-progress", className="status-line", style={"display": "none"}),
                                html.Div(tr("compare.state.no_active", "es"), id="compare-status", className="status-line"),
                                html.Div("", id="compare-export-note", className="scenario-meta"),
                            ],
                        ),
                        html.Div(
                            className="compare-grid",
                            children=[
                                html.Div(
                                    className="panel",
                                    children=[
                                        html.H3(tr("compare.available", "es"), id="compare-available-title"),
                                        dash_table.DataTable(
                                            id="available-design-table",
                                            data=[],
                                            columns=[],
                                            hidden_columns=["candidate_key", "is_workbench_selected", "is_best_candidate"],
                                            row_selectable="multi",
                                            selected_rows=[],
                                            sort_action="native",
                                            filter_action="native",
                                            page_size=10,
                                            style_table={"overflowX": "auto"},
                                            style_cell={
                                                "padding": "0.45rem",
                                                "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif",
                                                "fontSize": 12,
                                                "color": "var(--color-text-primary)",
                                            },
                                            style_header={
                                                "backgroundColor": "var(--color-primary-soft)",
                                                "color": "var(--color-text-primary)",
                                                "fontWeight": "bold",
                                            },
                                            tooltip_delay=0,
                                            tooltip_duration=None,
                                            tooltip_header={},
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="panel",
                                    children=[
                                        html.H3(tr("compare.selected", "es"), id="compare-selected-title"),
                                        html.Div(tr("compare.selected.empty", "es"), id="compare-selected-empty", className="section-copy"),
                                        dash_table.DataTable(
                                            id="selected-design-table",
                                            data=[],
                                            columns=[],
                                            hidden_columns=["candidate_key"],
                                            page_size=10,
                                            style_table={"overflowX": "auto"},
                                            style_cell={
                                                "padding": "0.45rem",
                                                "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif",
                                                "fontSize": 12,
                                                "color": "var(--color-text-primary)",
                                            },
                                            style_header={
                                                "backgroundColor": "var(--color-primary-soft)",
                                                "color": "var(--color-text-primary)",
                                                "fontWeight": "bold",
                                            },
                                            tooltip_delay=0,
                                            tooltip_duration=None,
                                            tooltip_header={},
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        dcc.Loading(
                            type="default",
                            children=html.Div(
                                className="main-stack",
                                children=[
                                    html.Div(
                                        className="panel",
                                        children=[
                                            html.H3(tr("compare.summary", "es"), id="comparison-summary-title"),
                                            html.P(tr("compare.summary.note", "es"), id="compare-summary-note", className="section-copy section-copy-wide"),
                                            dash_table.DataTable(
                                                id="comparison-summary-table",
                                                data=[],
                                                columns=[],
                                                hidden_columns=["candidate_key"],
                                                sort_action="native",
                                                filter_action="native",
                                                page_size=10,
                                                style_table={"overflowX": "auto"},
                                                style_cell={
                                                    "padding": "0.45rem",
                                                    "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif",
                                                    "fontSize": 12,
                                                    "color": "var(--color-text-primary)",
                                                },
                                                style_header={
                                                    "backgroundColor": "var(--color-primary-soft)",
                                                    "color": "var(--color-text-primary)",
                                                    "fontWeight": "bold",
                                                },
                                                tooltip_delay=0,
                                                tooltip_duration=None,
                                                tooltip_header={},
                                            ),
                                        ],
                                    ),
                                    html.Div(className="compare-grid", children=[html.Div(className="panel", children=[dcc.Graph(id="comparison-annual-coverage-graph")]), html.Div(className="panel", children=[dcc.Graph(id="comparison-monthly-destination-graph")])]),
                                    html.Div(className="panel", children=[dcc.Graph(id="comparison-typical-day-graph")]),
                                    html.Div(className="panel", children=[dcc.Graph(id="comparison-npv-projection-graph")]),
                                ],
                            ),
                        ),
                    ],
                ),
            ],
        ),
    ],
)


@callback(
    Output("compare-mode-gate-shell", "children"),
    Output("compare-mode-gate-shell", "style"),
    Output("compare-page-content", "style"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def sync_compare_page_access(session_payload, language_value):
    lang = _lang(language_value)
    access = _compare_page_access(session_payload)
    gate_children = render_ui_mode_gate(access, lang=lang, component_id="compare-mode-gate") if access.is_gated else []
    return gate_children, gate_visibility_style(access), page_body_style(access)


@callback(
    Output("compare-page-title", "children"),
    Output("compare-page-intro", "children"),
    Output("compare-flow-note", "children"),
    Output("compare-active-scenario-label", "children"),
    Output("compare-available-title", "children"),
    Output("compare-selected-title", "children"),
    Output("comparison-summary-title", "children"),
    Output("compare-summary-note", "children"),
    Output("compare-add-btn", "children"),
    Output("compare-clear-btn", "children"),
    Output("comparison-export-btn", "children"),
    Output("comparison-export-progress", "children"),
    Output("compare-selected-empty", "children"),
    Input("language-selector", "value"),
)
def translate_compare_page(language_value):
    lang = _lang(language_value)
    return (
        tr("compare.title", lang),
        tr("compare.intro", lang),
        tr("compare.flow_note", lang),
        tr("compare.active_scenario", lang),
        tr("compare.available", lang),
        tr("compare.selected", lang),
        tr("compare.summary", lang),
        tr("compare.summary.note", lang),
        tr("compare.add", lang),
        tr("compare.clear", lang),
        tr("compare.export", lang),
        tr("compare.export_running", lang),
        tr("compare.selected.empty", lang),
    )


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("available-design-table", "selected_rows", allow_duplicate=True),
    Input("compare-add-btn", "n_clicks"),
    Input("compare-clear-btn", "n_clicks"),
    Input("selected-design-table", "active_cell"),
    State("available-design-table", "derived_virtual_selected_rows"),
    State("available-design-table", "derived_virtual_data"),
    State("available-design-table", "data"),
    State("selected-design-table", "data"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def mutate_design_comparison_selection(
    add_clicks,
    clear_clicks,
    selected_active_cell,
    available_selected_rows,
    available_rows,
    available_rows_raw,
    selected_rows,
    session_payload,
):
    if not _compare_page_access(session_payload).allowed:
        raise PreventUpdate
    trigger = ctx.triggered_id
    client_state, state = resolve_scenario_session(session_payload, ensure_scan=True, language="es")
    active = state.get_scenario()
    if active is None or active.scan_result is None or active.dirty:
        raise PreventUpdate

    current = resolve_design_selection(state, active)
    updated = current
    if trigger == "compare-add-btn":
        if not add_clicks or not available_selected_rows:
            raise PreventUpdate
        source_rows = available_rows or available_rows_raw or []
        keys_to_add = [
            str(source_rows[index]["candidate_key"])
            for index in available_selected_rows
            if source_rows and 0 <= index < len(source_rows)
        ]
        updated = append_design_selection(active, current, keys_to_add)
    elif trigger == "compare-clear-btn":
        if not clear_clicks:
            raise PreventUpdate
        updated = ()
    elif trigger == "selected-design-table":
        active_cell = selected_active_cell or {}
        if active_cell.get("column_id") != "remove_action":
            raise PreventUpdate
        row_index = int(active_cell.get("row", -1))
        if not selected_rows or row_index < 0 or row_index >= len(selected_rows):
            raise PreventUpdate
        updated = remove_design_selection(active, current, str(selected_rows[row_index]["candidate_key"]))
    else:
        raise PreventUpdate

    if updated == current and trigger != "compare-clear-btn":
        raise PreventUpdate
    next_state = set_design_comparison_candidates(state, active.scenario_id, updated)
    client_state = commit_client_session(client_state, next_state)
    return client_state.to_payload(), []


@callback(
    Output("compare-active-scenario-value", "children"),
    Output("compare-status", "children"),
    Output("compare-export-note", "children"),
    Output("available-design-table", "data"),
    Output("available-design-table", "columns"),
    Output("available-design-table", "tooltip_header"),
    Output("available-design-table", "style_data_conditional"),
    Output("available-design-table", "selected_rows"),
    Output("selected-design-table", "data"),
    Output("selected-design-table", "columns"),
    Output("selected-design-table", "tooltip_header"),
    Output("compare-selected-empty", "style"),
    Output("comparison-summary-table", "data"),
    Output("comparison-summary-table", "columns"),
    Output("comparison-summary-table", "tooltip_header"),
    Output("comparison-annual-coverage-graph", "figure"),
    Output("comparison-monthly-destination-graph", "figure"),
    Output("comparison-typical-day-graph", "figure"),
    Output("comparison-npv-projection-graph", "figure"),
    Output("compare-add-btn", "disabled"),
    Output("compare-clear-btn", "disabled"),
    Output("comparison-export-btn", "disabled"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_design_comparison(session_payload, language_value):
    lang = _lang(language_value)
    access = _compare_page_access(session_payload)
    available_columns, available_tooltips = _table_columns(AVAILABLE_VISIBLE_COLUMNS, lang)
    available_columns.extend(
        [
            {"name": "candidate_key", "id": "candidate_key"},
            {"name": "is_workbench_selected", "id": "is_workbench_selected"},
            {"name": "is_best_candidate", "id": "is_best_candidate"},
        ]
    )
    selected_columns, selected_tooltips = _table_columns(SELECTED_VISIBLE_COLUMNS, lang, include_remove=True)
    selected_columns.append({"name": "candidate_key", "id": "candidate_key"})
    summary_columns, summary_tooltips = _table_columns(SUMMARY_VISIBLE_COLUMNS, lang)
    summary_columns.append({"name": "candidate_key", "id": "candidate_key"})
    if access.is_gated:
        empty_message = tr(access.body_key or "ui_mode.gate.compare.body", lang)
        figures = build_design_comparison_figures(None, (), lang=lang, empty_message=empty_message)
        return (
            "—",
            empty_message,
            "",
            [],
            available_columns,
            available_tooltips,
            [],
            [],
            [],
            selected_columns,
            selected_tooltips,
            {"display": "block"},
            [],
            summary_columns,
            summary_tooltips,
            figures["annual_coverage"],
            figures["monthly_destination"],
            figures["typical_day"],
            figures["npv_projection"],
            True,
            True,
            True,
        )
    _, state = resolve_scenario_session(session_payload, ensure_scan=True, language=lang)
    active = state.get_scenario()
    selected_keys = resolve_design_selection(state, active) if active is not None else ()
    page_state = build_design_compare_state(active, selected_keys, lang=lang)

    active_name = active.name if active is not None else "—"
    if active is None or active.scan_result is None or active.dirty:
        figures = build_design_comparison_figures(active, (), lang=lang, empty_message=page_state.empty_message)
        return (
            active_name,
            page_state.status_message,
            page_state.export_message,
            [],
            available_columns,
            available_tooltips,
            [],
            [],
            [],
            selected_columns,
            selected_tooltips,
            {"display": "block"},
            [],
            summary_columns,
            summary_tooltips,
            figures["annual_coverage"],
            figures["monthly_destination"],
            figures["typical_day"],
            figures["npv_projection"],
            True,
            True,
            True,
        )

    available_rows = build_available_design_rows(active, lang=lang)
    selected_rows = build_design_comparison_rows(active, selected_keys, lang=lang)
    figures = build_design_comparison_figures(active, selected_keys, lang=lang, empty_message=page_state.empty_message)
    available_styles = [
        {
            "if": {"filter_query": "{is_workbench_selected} = true"},
            "backgroundColor": "var(--color-primary-soft)",
            "fontWeight": "bold",
        },
        {
            "if": {"filter_query": "{is_best_candidate} = true"},
            "backgroundColor": "var(--color-success-soft)",
        },
    ]
    selected_display = selected_rows.copy()
    if not selected_display.empty:
        selected_display["remove_action"] = tr("compare.action.remove", lang)
    add_disabled = not page_state.can_select or len(selected_keys) >= MAX_COMPARE_DESIGNS
    clear_disabled = len(selected_keys) == 0
    export_disabled = not page_state.can_export
    return (
        active.name,
        page_state.status_message,
        page_state.export_message,
        available_rows.to_dict("records"),
        available_columns,
        available_tooltips,
        available_styles,
        [],
        selected_display.to_dict("records"),
        selected_columns,
        selected_tooltips,
        {"display": "none"} if not selected_display.empty else {"display": "block"},
        selected_rows.to_dict("records"),
        summary_columns,
        summary_tooltips,
        figures["annual_coverage"],
        figures["monthly_destination"],
        figures["typical_day"],
        figures["npv_projection"],
        add_disabled,
        clear_disabled,
        export_disabled,
    )


@callback(
    Output("compare-status", "children", allow_duplicate=True),
    Output("comparison-download", "data"),
    Input("comparison-export-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("comparison-export-btn", "disabled"), True, False),
        (Output("comparison-export-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def export_design_comparison(n_clicks, session_payload, language_value):
    if not n_clicks:
        raise PreventUpdate
    if not _compare_page_access(session_payload).allowed:
        raise PreventUpdate
    lang = _lang(language_value)
    _, state = resolve_scenario_session(session_payload, ensure_scan=True, language=lang)
    active = state.get_scenario()
    if active is None or active.scan_result is None or active.dirty:
        raise PreventUpdate
    selected_keys = resolve_design_selection(state, active)
    if len(selected_keys) < 2:
        raise PreventUpdate
    content = export_design_comparison_workbook(active, selected_keys, lang=lang)
    filename = f"{_safe_name(active.name)}_design_comparison.xlsx"
    return tr("compare.export.done", lang, path=filename), _download_payload(content, filename)
