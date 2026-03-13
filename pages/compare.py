from __future__ import annotations

import base64

from dash import Input, Output, State, callback, dash_table, dcc, html, register_page
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from services import (
    ScenarioSessionState,
    build_comparison_figures,
    build_comparison_table,
    build_session_comparison_rows,
    export_comparison_workbook,
    set_comparison_scenarios,
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
                        html.Div(className="section-head", children=[html.H2("Scenario comparison"), html.Button("Export comparison", id="comparison-export-btn", n_clicks=0, className="action-btn secondary")]),
                        html.P("Select at least two deterministic scenarios with completed runs to compare headline KPIs and NPV curves."),
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
                                html.H3("Comparison summary"),
                                dash_table.DataTable(
                                    id="comparison-summary-table",
                                    data=[],
                                    columns=[],
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
)
def populate_comparison(session_payload):
    state = _state(session_payload)
    options = []
    for scenario in state.scenarios:
        disabled = scenario.scan_result is None or scenario.dirty
        label = scenario.name if not disabled else f"{scenario.name} (rerun needed)"
        options.append({"label": label, "value": scenario.scenario_id, "disabled": disabled})

    selected_records = build_session_comparison_rows(state)
    comparison_table = build_comparison_table(selected_records)
    figures = build_comparison_figures(selected_records)
    columns = [{"name": column, "id": column} for column in comparison_table.columns]
    status = f"{len(selected_records)} scenario(s) selected for comparison."
    if len(selected_records) < 2:
        status = "Select at least two completed deterministic scenarios to compare."

    return (
        options,
        list(state.comparison_scenario_ids),
        status,
        comparison_table.to_dict("records"),
        columns,
        figures.get("kpi_bar", _empty_figure("Scenario KPI comparison", "Select scenarios to compare.")),
        figures.get("npv_overlay", _empty_figure("NPV vs kWp across scenarios", "Select scenarios to compare.")),
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
