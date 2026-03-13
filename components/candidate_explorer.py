from __future__ import annotations

from dash import dash_table, dcc, html

from services.i18n import tr


def candidate_explorer_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.Div(
                className="section-head",
                children=[
                    html.H3(tr("workbench.candidate_explorer", "es"), id="candidate-explorer-title"),
                    html.Div(
                        className="controls",
                        children=[
                            html.Button(tr("workbench.export_scenario", "es"), id="scenario-export-btn", n_clicks=0, className="action-btn secondary"),
                            html.Button(tr("common.export_artifacts", "es"), id="scenario-artifacts-btn", n_clicks=0, className="action-btn tertiary"),
                        ],
                    ),
                ],
            ),
            html.Div(id="active-kpi-cards", className="kpi-grid"),
            dcc.Graph(id="active-npv-graph"),
            html.Div(className="chart-grid", children=[dcc.Graph(id="active-monthly-balance-graph"), dcc.Graph(id="active-cash-flow-graph")]),
            dash_table.DataTable(
                id="active-candidate-table",
                data=[],
                columns=[],
                row_selectable="single",
                selected_rows=[],
                hidden_columns=["candidate_key", "scan_order", "best_battery_for_kwp"],
                sort_action="native",
                filter_action="native",
                page_size=12,
                style_table={"overflowX": "auto"},
                style_cell={"padding": "0.45rem", "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": 12},
                style_header={"backgroundColor": "#e2e8f0", "fontWeight": "bold"},
                tooltip_duration=None,
                tooltip_header={},
            ),
        ],
    )
