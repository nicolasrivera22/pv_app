from __future__ import annotations

from dash import html, register_page

from services.i18n import tr


register_page(__name__, path="/admin", name="Admin")


def layout():
    return html.Div(
        className="page page-admin-redirect",
        children=[
            html.Div(
                id="admin-redirect-fallback",
                className="panel secondary-panel admin-redirect-fallback",
                children=[
                    html.H3(tr("workspace.advanced.redirect.title", "es"), id="admin-redirect-title"),
                    html.P(
                        tr("workspace.advanced.redirect.copy", "es"),
                        id="admin-redirect-copy",
                        className="section-copy",
                    ),
                    html.Button(
                        tr("workspace.advanced.redirect.enter", "es"),
                        id="admin-redirect-enter-btn",
                        n_clicks=0,
                        className="action-btn tertiary",
                    ),
                ],
            ),
        ],
    )
