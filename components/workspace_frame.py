from __future__ import annotations

from dash import dcc, html

from services.i18n import tr

from .scenario_controls import scenario_sidebar


def workspace_frame(*, children: list, stores: list | None = None) -> html.Div:
    return html.Div(
        className="page",
        children=[
            *(stores or []),
            html.Div(
                className="workbench-grid",
                children=[
                    html.Div(
                        className="workspace-sidebar-stack",
                        children=[
                            scenario_sidebar(),
                            html.Div(
                                className="panel secondary-panel workspace-internal-panel",
                                children=[
                                    html.H3(tr("workspace.internal.title", "es"), id="workspace-internal-title"),
                                    html.P(tr("workspace.internal.copy", "es"), id="workspace-internal-copy", className="section-copy"),
                                    dcc.Link(
                                        tr("workspace.internal.link", "es"),
                                        id="workspace-admin-link",
                                        href="/admin",
                                        className="link workspace-admin-link",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="main-stack",
                        children=[
                            html.Div(
                                className="panel active-summary-card workspace-status-card",
                                children=[
                                    html.Div(
                                        className="active-summary-top",
                                        children=[
                                            html.Div(
                                                className="active-summary-content",
                                                children=[
                                                    html.H2(tr("workspace.shell.title", "es"), id="workspace-shell-title"),
                                                    html.Div(tr("workbench.no_active_scenario", "es"), id="workspace-active-name", className="status-line active-summary-meta"),
                                                    html.Div(tr("workbench.run_pending", "es"), id="workspace-active-run-status", className="status-line active-summary-meta"),
                                                    html.Div(tr("workbench.project.unbound", "es"), id="workspace-project-status", className="status-line active-summary-meta"),
                                                    html.Div(
                                                        id="workspace-state-strip",
                                                        className="workbench-state-strip",
                                                        children=[
                                                            html.Span(
                                                                tr("workbench.state.no_active", "es"),
                                                                className="workbench-state-chip workbench-state-chip-neutral",
                                                            )
                                                        ],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            *children,
                        ],
                    ),
                ],
            ),
        ],
    )
