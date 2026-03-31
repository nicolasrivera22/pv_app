from __future__ import annotations

from dash import dcc, html

from services.i18n import tr

from .scenario_controls import scenario_sidebar


def _join_classes(*class_names: str | None) -> str:
    return " ".join(part for part in class_names if part and part.strip())


def workspace_frame(
    *,
    children: list,
    stores: list | None = None,
    show_internal_entry: bool = False,
    page_class_name: str | None = None,
    grid_class_name: str | None = None,
) -> html.Div:
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
                        style={"display": "none"},
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
        className=_join_classes("page", page_class_name),
        children=[
            *(stores or []),
            html.Div(
                className=_join_classes("workbench-grid", grid_class_name),
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
