from __future__ import annotations

from dash import dcc, html


def scenario_sidebar() -> html.Div:
    return html.Div(
        className="panel sidebar-panel",
        children=[
            html.H2(id="scenario-sidebar-title"),
            dcc.Upload(
                id="scenario-upload",
                children=html.Div([html.Span(id="scenario-upload-prefix"), html.Span(id="scenario-upload-link", className="link")]),
                multiple=False,
                className="upload-box",
            ),
            html.Div(
                className="controls",
                children=[
                    html.Button(id="load-example-btn", n_clicks=0, className="action-btn secondary"),
                    html.Button(id="duplicate-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                    html.Button(id="delete-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                ],
            ),
            html.Label(id="active-scenario-label", className="input-label"),
            html.Div(
                className="rename-row",
                children=[
                    dcc.Dropdown(id="scenario-dropdown", placeholder="No scenarios loaded"),
                    html.Button(id="set-active-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                ],
            ),
            html.Div(className="rename-row", children=[
                dcc.Input(id="rename-scenario-input", type="text", placeholder="Scenario name", className="text-input"),
                html.Button(id="rename-scenario-btn", n_clicks=0, className="action-btn tertiary"),
            ]),
            html.Div(id="scenario-overview-list", className="scenario-list"),
            html.Div(id="workbench-status", className="status-line"),
        ],
    )
