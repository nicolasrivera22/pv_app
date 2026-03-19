from __future__ import annotations

from dash import dcc, html

from .unifilar_diagram import unifilar_diagram_section
from services.i18n import tr


def selected_candidate_deep_dive_section() -> html.Div:
    return html.Div(
        id="selected-candidate-deep-dive-section",
        className="deep-dive-stack",
        children=[
            html.Div(
                className="panel",
                children=[
                    html.Div(
                        className="section-head",
                        children=[html.H3(tr("workbench.deep_dive.title", "es"), id="selected-candidate-deep-dive-title")],
                    ),
                    html.P(tr("workbench.deep_dive.note", "es"), id="selected-candidate-deep-dive-note", className="section-copy"),
                    html.Div(
                        className="chart-grid",
                        children=[
                            dcc.Graph(id="active-monthly-balance-graph"),
                            dcc.Graph(id="active-cash-flow-graph"),
                        ],
                    ),
                ],
            ),
            unifilar_diagram_section(),
            html.Div(
                className="panel",
                children=[
                    html.Div(
                        className="chart-grid",
                        children=[
                            dcc.Graph(id="active-annual-coverage-graph"),
                            dcc.Graph(id="active-battery-load-graph"),
                        ],
                    ),
                    html.Div(
                        className="subpanel",
                        children=[
                            dcc.Graph(id="active-typical-day-graph"),
                        ],
                    ),
                ],
            ),
        ],
    )
