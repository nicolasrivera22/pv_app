from __future__ import annotations

from dash import dcc, html, register_page

from services.i18n import tr


register_page(__name__, path="/admin", name="Admin")


def layout():
    return html.Div(
        className="page page-admin-redirect",
        children=[
            dcc.Location(
                id="admin-redirect-location",
                href="/assumptions#advanced-tools",
                refresh=True,
            ),
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
                    dcc.Link(
                        tr("workspace.advanced.redirect.link", "es"),
                        id="admin-redirect-link",
                        href="/assumptions#advanced-tools",
                        className="action-btn tertiary",
                    ),
                ],
            ),
        ],
    )
