from __future__ import annotations

from dash import html

from services.i18n import tr
from services.ui_mode import PageAccess


def render_ui_mode_gate(access: PageAccess, *, lang: str = "es", component_id: str | None = None) -> html.Div:
    actions: list = []
    if access.cta_target_mode and access.cta_label_key:
        actions.append(
            html.Button(
                tr(access.cta_label_key, lang),
                id={"type": "ui-mode-gate-cta", "page": access.page_key, "target_mode": access.cta_target_mode},
                n_clicks=0,
                className="action-btn",
            )
        )
    return html.Div(
        id=component_id,
        className="panel ui-mode-gate",
        children=[
            html.Div(tr("ui_mode.gate.eyebrow", lang), className="ui-mode-gate-eyebrow"),
            html.H3(tr(access.title_key or "", lang), className="ui-mode-gate-title"),
            html.P(tr(access.body_key or "", lang), className="section-copy section-copy-wide ui-mode-gate-copy"),
            html.Div(actions, className="controls ui-mode-gate-actions"),
        ],
    )
