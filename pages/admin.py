from __future__ import annotations

from dash import dcc, html, register_page

from components.admin_view import admin_locked_card
from services.admin_access import admin_pin_configured
from components.workspace_frame import workspace_frame
import services.workspace_admin_callbacks as _workspace_admin_callbacks  # noqa: F401
import services.workspace_shared_callbacks as _workspace_shared_callbacks  # noqa: F401


register_page(__name__, path="/admin", name="Admin")


def layout():
    return workspace_frame(
        stores=[
            dcc.Store(id="active-profile-table-state", storage_type="memory", data={"table_id": None}),
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
                children=[
                    admin_locked_card(
                        lang="es",
                        configured=admin_pin_configured(),
                    )
                ],
            ),
        ],
    )
