from __future__ import annotations

from dash import dcc, html


def scenario_sidebar() -> html.Div:
    return html.Div(
        className="panel sidebar-panel",
        children=[
            html.H2("Scenarios"),
            dcc.Upload(
                id="scenario-upload",
                children=html.Div(["Drop Excel here or ", html.Span("select a file", className="link")]),
                multiple=False,
                className="upload-box",
            ),
            html.Div(
                className="controls",
                children=[
                    html.Button("Load example", id="load-example-btn", n_clicks=0, className="action-btn secondary"),
                    html.Button("Duplicate", id="duplicate-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                    html.Button("Delete", id="delete-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                ],
            ),
            html.Label("Active scenario", className="input-label"),
            html.Div(
                className="rename-row",
                children=[
                    dcc.Dropdown(id="scenario-dropdown", placeholder="No scenarios loaded"),
                    html.Button("Set active", id="set-active-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                ],
            ),
            html.Div(className="rename-row", children=[
                dcc.Input(id="rename-scenario-input", type="text", placeholder="Scenario name", className="text-input"),
                html.Button("Rename", id="rename-scenario-btn", n_clicks=0, className="action-btn tertiary"),
            ]),
            html.Div(id="scenario-overview-list", className="scenario-list"),
            html.Div(id="workbench-status", className="status-line"),
        ],
    )
