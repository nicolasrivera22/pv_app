from __future__ import annotations

from dash import dcc, html, register_page


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
                    html.H3("Redirigiendo a Supuestos"),
                    html.P(
                        "Las herramientas avanzadas ahora viven dentro de Supuestos. "
                        "Si la redirección no ocurre automáticamente, usa el enlace de abajo.",
                        className="section-copy",
                    ),
                    dcc.Link(
                        "Abrir Supuestos",
                        id="admin-redirect-link",
                        href="/assumptions#advanced-tools",
                        className="action-btn tertiary",
                    ),
                ],
            ),
        ],
    )
