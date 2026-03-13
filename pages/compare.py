from __future__ import annotations

import base64

from dash import Input, Output, State, callback, dash_table, dcc, html, register_page
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from services import (
    ScenarioSessionState,
    build_comparison_figures,
    build_comparison_table,
    build_display_columns,
    build_session_comparison_rows,
    export_comparison_workbook,
    set_comparison_scenarios,
    tr,
)

register_page(__name__, path="/compare", name="Compare")


def _state(payload) -> ScenarioSessionState:
    return ScenarioSessionState.from_payload(payload)


def _empty_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def _download_payload(content: bytes, filename: str) -> dict:
    return {"content": base64.b64encode(content).decode("ascii"), "filename": filename, "base64": True}


layout = html.Div(
    className="page",
    children=[
        dcc.Download(id="comparison-download"),
        html.Div(
            className="main-stack",
            children=[
                html.Div(
                    className="panel",
                    children=[
                        html.Div(className="section-head", children=[html.H2(id="compare-page-title"), html.Button(id="comparison-export-btn", n_clicks=0, className="action-btn secondary")]),
                        html.P(id="compare-page-intro"),
                        dcc.Checklist(id="compare-scenario-checklist", className="scenario-list"),
                        html.Div(id="compare-status", className="status-line"),
                    ],
                ),
                html.Div(
                    className="compare-grid",
                    children=[
                        html.Div(
                            className="panel",
                            children=[
                                html.H3(id="comparison-summary-title"),
                                dash_table.DataTable(
                                    id="comparison-summary-table",
                                    data=[],
                                    columns=[],
                                    hidden_columns=["scenario_id", "candidate_key"],
                                    sort_action="native",
                                    filter_action="native",
                                    page_size=10,
                                    style_table={"overflowX": "auto"},
                                    style_cell={"padding": "0.45rem", "fontFamily": "monospace", "fontSize": 12},
                                    style_header={"backgroundColor": "#e2e8f0", "fontWeight": "bold"},
                                ),
                            ],
                        ),
                        html.Div(className="panel", children=[dcc.Graph(id="comparison-kpi-graph")]),
                    ],
                ),
                html.Div(className="panel", children=[dcc.Graph(id="comparison-npv-graph")]),
            ],
        ),
    ],
)


@callback(
    Output("compare-page-title", "children"),
    Output("comparison-export-btn", "children"),
    Output("compare-page-intro", "children"),
    Output("comparison-summary-title", "children"),
    Input("language-selector", "value"),
)
def translate_compare_page(language_value):
    lang = language_value if language_value in {"en", "es"} else "es"
    return (
        tr("compare.title", lang),
        tr("compare.export", lang),
        tr("compare.intro", lang),
        tr("compare.summary", lang),
    )


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Input("compare-scenario-checklist", "value"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def update_comparison_selection(selected_ids, session_payload):
    state = _state(session_payload)
    updated = set_comparison_scenarios(state, selected_ids or [])
    if updated.comparison_scenario_ids == state.comparison_scenario_ids:
        raise PreventUpdate
    return updated.to_payload()


@callback(
    Output("compare-scenario-checklist", "options"),
    Output("compare-scenario-checklist", "value"),
    Output("compare-status", "children"),
    Output("comparison-summary-table", "data"),
    Output("comparison-summary-table", "columns"),
    Output("comparison-kpi-graph", "figure"),
    Output("comparison-npv-graph", "figure"),
    Output("comparison-export-btn", "disabled"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_comparison(session_payload, language_value):
    lang = language_value if language_value in {"en", "es"} else "es"
    state = _state(session_payload)
    options = []
    for scenario in state.scenarios:
        disabled = scenario.scan_result is None or scenario.dirty
        label = scenario.name if not disabled else tr("compare.rerun_needed", lang, name=scenario.name)
        options.append({"label": label, "value": scenario.scenario_id, "disabled": disabled})

    selected_records = build_session_comparison_rows(state)
    comparison_table = build_comparison_table(selected_records)
    figures = build_comparison_figures(selected_records, lang=lang)
    visible_columns = ["scenario", "best_kWp", "battery", "NPV_COP", "payback_years", "self_consumption_ratio", "self_sufficiency_ratio", "annual_import_kwh", "annual_export_kwh"]
    columns, tooltip_header = build_display_columns(visible_columns, lang)
    columns.extend([{"name": "scenario_id", "id": "scenario_id"}, {"name": "candidate_key", "id": "candidate_key"}])
    status = tr("compare.status.selected", lang, count=len(selected_records))
    if len(selected_records) < 2:
        status = tr("compare.status.none", lang)

    return (
        options,
        list(state.comparison_scenario_ids),
        status,
        comparison_table.to_dict("records"),
        columns,
        figures.get("kpi_bar", _empty_figure(tr("compare.figure.kpi_title", lang), tr("compare.figure.empty_message", lang))),
        figures.get("npv_overlay", _empty_figure(tr("compare.figure.npv_title", lang), tr("compare.figure.empty_message", lang))),
        len(selected_records) < 2,
    )


@callback(
    Output("comparison-download", "data"),
    Input("comparison-export-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def export_comparison(n_clicks, session_payload):
    if not n_clicks:
        raise PreventUpdate
    state = _state(session_payload)
    selected_records = build_session_comparison_rows(state)
    if len(selected_records) < 2:
        raise PreventUpdate
    content = export_comparison_workbook(state, selected_records)
    return _download_payload(content, "scenario_comparison.xlsx")
