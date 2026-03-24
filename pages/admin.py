from __future__ import annotations

from dash import dcc, html, register_page

from components import catalog_editor_section, profile_editor_section
from components.workspace_frame import workspace_frame
import services.workspace_admin_callbacks as _workspace_admin_callbacks  # noqa: F401
import services.workspace_shared_callbacks as _workspace_shared_callbacks  # noqa: F401


register_page(__name__, path="/admin", name="Admin")


layout = workspace_frame(
    stores=[
        dcc.Store(id="active-profile-table-state", storage_type="memory", data={"table_id": None}),
        dcc.Store(id="admin-draft-meta", storage_type="memory", data={}),
    ],
    children=[
        html.Div(
            className="panel",
            children=[
                html.Div(
                    className="section-head",
                    children=[html.H2("Admin", id="admin-page-title")],
                ),
                html.P("", id="admin-page-copy", className="section-copy section-copy-wide"),
                html.Div(id="admin-gating-note", className="status-line workspace-admin-note"),
                html.Div(
                    className="controls",
                    children=[
                        dcc.Checklist(id="admin-show-all", value=[]),
                        html.Button("", id="apply-admin-btn", n_clicks=0, className="action-btn"),
                    ],
                ),
            ],
        ),
        html.Div(className="panel assumption-editor-panel", children=[html.Div(id="admin-assumption-sections")]),
        profile_editor_section(),
        catalog_editor_section(),
    ],
)
