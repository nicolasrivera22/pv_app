from __future__ import annotations

from dash import dcc, html

from services.i18n import tr


def scenario_sidebar() -> html.Div:
    return html.Div(
        className="panel sidebar-panel",
        children=[
            html.H2(tr("workbench.sidebar.title", "es"), id="scenario-sidebar-title"),
            html.Div(
                className="subpanel secondary-panel",
                children=[
                    html.Div(
                        className="section-head",
                        children=[html.H3(tr("workbench.project.title", "es"), id="project-toolbar-title")],
                    ),
                    html.Label(tr("workbench.project.name", "es"), id="project-name-label", className="input-label"),
                    dcc.Input(
                        id="project-name-input",
                        type="text",
                        placeholder=tr("workbench.project.name_placeholder", "es"),
                        className="text-input",
                    ),
                    html.Label(tr("workbench.project.open_label", "es"), id="project-dropdown-label", className="input-label", style={"marginTop": "0.75rem"}),
                    dcc.Dropdown(id="project-dropdown", placeholder=tr("workbench.project.none", "es")),
                    html.Div(
                        className="controls",
                        style={"marginTop": "0.75rem"},
                        children=[
                            html.Button(tr("workbench.project.save", "es"), id="save-project-btn", n_clicks=0, className="action-btn secondary"),
                            html.Button(tr("workbench.project.save_as", "es"), id="save-project-as-btn", n_clicks=0, className="action-btn tertiary"),
                            html.Button(tr("workbench.project.open", "es"), id="open-project-btn", n_clicks=0, className="action-btn tertiary"),
                        ],
                    ),
                    html.Div(tr("workbench.project.unbound", "es"), id="project-status", className="status-line"),
                ],
            ),
            dcc.Upload(
                id="scenario-upload",
                children=html.Div(
                    [
                        html.Span(tr("workbench.upload.prefix", "es"), id="scenario-upload-prefix"),
                        html.Span(tr("workbench.upload.link", "es"), id="scenario-upload-link", className="link"),
                    ]
                ),
                multiple=False,
                className="upload-box",
            ),
            html.Div(
                className="controls",
                children=[
                    html.Button(tr("workbench.load_example", "es"), id="load-example-btn", n_clicks=0, className="action-btn secondary"),
                    html.Button(tr("workbench.duplicate", "es"), id="duplicate-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                    html.Button(tr("workbench.delete", "es"), id="delete-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                ],
            ),
            html.Label(tr("workbench.active_scenario", "es"), id="active-scenario-label", className="input-label"),
            html.Div(
                className="rename-row",
                children=[
                    dcc.Dropdown(id="scenario-dropdown", placeholder=tr("workbench.no_scenarios_loaded", "es")),
                    html.Button(tr("workbench.set_active", "es"), id="set-active-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                ],
            ),
            html.Div(className="rename-row", children=[
                dcc.Input(id="rename-scenario-input", type="text", placeholder=tr("workbench.rename_placeholder", "es"), className="text-input"),
                html.Button(tr("workbench.rename", "es"), id="rename-scenario-btn", n_clicks=0, className="action-btn tertiary"),
            ]),
            html.Div(id="scenario-overview-list", className="scenario-list"),
            html.Div(tr("workbench.run_pending", "es"), id="workbench-status", className="status-line"),
        ],
    )
