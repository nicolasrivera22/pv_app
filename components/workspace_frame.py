from __future__ import annotations

from dash import dcc, html

from services.i18n import tr

from .scenario_controls import scenario_sidebar


def workspace_frame(*, children: list, stores: list | None = None, show_internal_entry: bool = False) -> html.Div:
    active_summary_children = [
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
        )
    ]
    if show_internal_entry:
        active_summary_children.append(
            html.Div(
                className="active-summary-actions workspace-shell-actions",
                children=[
                    html.Div(
                        id="workspace-admin-entry",
                        className="workspace-admin-entry",
                        children=[
                            html.Div(tr("workspace.internal.title", "es"), id="workspace-internal-title", className="workspace-admin-entry-title"),
                            html.Div(tr("workspace.internal.copy", "es"), id="workspace-internal-copy", className="workspace-admin-entry-copy"),
                            dcc.Link(
                                tr("workspace.internal.link", "es"),
                                id="workspace-admin-link",
                                href="/admin",
                                className="action-btn tertiary workspace-admin-link",
                            ),
                        ],
                    )
                ],
            )
        )
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
                                        children=active_summary_children,
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
