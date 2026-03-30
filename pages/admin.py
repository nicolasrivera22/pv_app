from __future__ import annotations

from dash import dcc, html, register_page

from components.ui_mode_gate import render_ui_mode_gate
from components.workspace_frame import workspace_frame
import services.workspace_admin_callbacks as _workspace_admin_callbacks  # noqa: F401
import services.workspace_shared_callbacks as _workspace_shared_callbacks  # noqa: F401
from services.ui_mode import PAGE_ADMIN, UI_MODE_SIMPLE, resolve_page_access


register_page(__name__, path="/admin", name="Admin")


def layout():
    return workspace_frame(
        stores=[
            dcc.Store(id="active-profile-table-state", storage_type="memory", data={"table_id": None}),
            dcc.Store(id="admin-preview-candidate-key", storage_type="memory", data={"scenario_id": None, "candidate_key": None}),
            dcc.Store(id="admin-draft-meta", storage_type="memory", data={}),
            dcc.Store(id="admin-access-meta", storage_type="memory", data={"revision": 0, "message_key": None, "tone": "neutral"}),
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
                ],
            ),
            html.Div(
                id="admin-access-shell",
                children=render_ui_mode_gate(resolve_page_access(PAGE_ADMIN, UI_MODE_SIMPLE), lang="es", component_id="admin-mode-gate"),
            ),
        ],
    )
