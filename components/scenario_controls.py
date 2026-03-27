from __future__ import annotations

from dash import dcc, html

from services.i18n import tr


def stacked_button_label(label: str) -> html.Span:
    parts = [part for part in str(label or "").split(" ") if part]
    if not parts:
        parts = [""]
    return html.Span(
        className="stacked-button-label",
        children=[html.Span(part, className="stacked-button-word") for part in parts],
    )


def run_scan_choice_dialog() -> html.Div:
    return html.Div(
        id="run-scan-choice-dialog",
        className="dialog-backdrop",
        style={"display": "none"},
        children=[
            html.Div(
                className="panel dialog-card",
                children=[
                    html.H3(tr("workbench.run_dialog.title", "es"), id="run-scan-choice-title"),
                    html.P(tr("workbench.run_dialog.body_unnamed", "es"), id="run-scan-choice-copy", className="section-copy"),
                    html.Div(
                        className="controls",
                        children=[
                            html.Button(
                                tr("workbench.run_dialog.save_and_run", "es"),
                                id="run-scan-save-and-run-btn",
                                n_clicks=0,
                                className="action-btn",
                            ),
                            html.Button(
                                tr("workbench.run_dialog.run_without_saving", "es"),
                                id="run-scan-run-unsaved-btn",
                                n_clicks=0,
                                className="action-btn secondary",
                            ),
                            html.Button(
                                tr("workbench.run_dialog.cancel", "es"),
                                id="run-scan-cancel-btn",
                                n_clicks=0,
                                className="action-btn tertiary",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def scenario_sidebar() -> html.Div:
    return html.Div(
        className="panel sidebar-panel",
        children=[
            html.H2(tr("workbench.sidebar.title", "es"), id="scenario-sidebar-title"),

            # ── Project workspace subsection ──
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
                        style={"padding": "0.1rem"},
                    ),
                    html.Label(tr("workbench.project.open_label", "es"), id="project-dropdown-label", className="input-label", style={"marginTop": "0.75rem"}),
                    dcc.Dropdown(id="project-dropdown", placeholder=tr("workbench.project.none", "es")),
                    html.Div(
                        "",
                        id="project-empty-note",
                        className="status-line sidebar-note",
                        style={"display": "none"},
                    ),
                    html.Div(
                        className="project-action-grid",
                        style={"marginTop": "0.75rem"},
                        children=[
                            html.Button(stacked_button_label(tr("workbench.project.save", "es")), id="save-project-btn", n_clicks=0, className="action-btn project-action-btn"),
                            html.Button(stacked_button_label(tr("workbench.project.open", "es")), id="open-project-btn", n_clicks=0, className="action-btn secondary project-action-btn"),
                            html.Button(stacked_button_label(tr("workbench.project.save_as", "es")), id="save-project-as-btn", n_clicks=0, className="action-btn tertiary project-action-btn"),
                            html.Button(stacked_button_label(tr("workbench.project.delete", "es")), id="delete-project-btn", n_clicks=0, className="action-btn tertiary project-action-btn"),
                        ],
                    ),
                    html.Div(tr("workbench.project.unbound", "es"), id="project-status", className="status-line"),
                ],
            ),

            # ── Active scenario subsection ──
            html.Div(
                className="subpanel secondary-panel sidebar-scenario-section",
                children=[
                    html.Div(
                        className="section-head",
                        children=[html.H3(tr("workbench.active_scenario", "es"), id="active-scenario-label")],
                    ),
                    html.Div(
                        id="scenario-start-card",
                        className="sidebar-start-card",
                        children=[
                            html.H4(tr("workbench.sidebar.start.title", "es"), id="scenario-start-title"),
                            html.P("", id="scenario-start-copy", className="section-copy sidebar-start-copy"),
                        ],
                    ),
                    dcc.Upload(
                        id="scenario-upload",
                        children=html.Div(
                            className="upload-box-content",
                            children=[
                                html.Div(tr("workbench.import_excel.title", "es"), id="scenario-upload-title", className="upload-box-title"),
                                html.Div(tr("workbench.import_excel.copy", "es"), id="scenario-upload-copy", className="upload-box-copy"),
                                html.Div(tr("workbench.import_excel.action", "es"), id="scenario-upload-action", className="upload-box-action"),
                            ],
                        ),
                        multiple=False,
                        className="upload-box",
                    ),
                    html.Div(
                        className="controls",
                        children=[
                            html.Button(tr("workbench.load_example", "es"), id="new-scenario-btn", n_clicks=0, className="action-btn"),
                            html.Button(tr("workbench.duplicate", "es"), id="duplicate-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                            html.Button(tr("workbench.delete", "es"), id="delete-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                        ],
                    ),
                    html.Div(id="scenario-overview-list", className="scenario-list"),
                    html.Div("", id="scenario-empty-note", className="status-line sidebar-note", style={"display": "none"}),
                    html.Div(
                        id="scenario-rename-shell",
                        className="sidebar-rename-shell",
                        children=[
                            html.Div(tr("workbench.rename_active_note", "es"), id="rename-scenario-note", className="status-line sidebar-note"),
                            html.Div(className="rename-row", children=[
                                dcc.Input(id="rename-scenario-input", type="text", placeholder=tr("workbench.rename_placeholder", "es"), className="text-input"),
                                html.Button(tr("workbench.rename", "es"), id="rename-scenario-btn", n_clicks=0, className="action-btn tertiary"),
                            ]),
                        ],
                    ),
                    html.Div(tr("workbench.run_pending", "es"), id="workbench-status", className="status-line"),
                ],
            ),
        ],
    )
