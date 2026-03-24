from __future__ import annotations

from dash import dcc, html

from services.admin_access import ADMIN_PIN_SETUP_COMMAND
from services.i18n import tr

from .catalog_editor import catalog_editor_section
from .profile_editor import profile_editor_section


def admin_secure_content(*, lang: str = "es") -> html.Div:
    return html.Div(
        id="admin-unlocked-shell",
        children=[
            html.Div(
                className="panel secondary-panel",
                children=[
                    html.Div(tr("workspace.admin.session_unlocked", lang), id="admin-session-unlocked-note", className="status-line workspace-admin-note"),
                    html.Div(
                        className="controls",
                        children=[
                            dcc.Checklist(
                                id="admin-show-all",
                                value=[],
                                options=[{"label": tr("workbench.assumptions.show_all", lang), "value": "all"}],
                            ),
                            html.Button(tr("workbench.assumptions.apply", lang), id="apply-admin-btn", n_clicks=0, className="action-btn"),
                        ],
                    ),
                ],
            ),
            html.Div(className="panel assumption-editor-panel", children=[html.Div(id="admin-assumption-sections")]),
            profile_editor_section(),
            catalog_editor_section(),
        ],
    )


def admin_locked_card(
    *,
    lang: str = "es",
    configured: bool,
    status_key: str | None = None,
    tone: str = "neutral",
) -> html.Div:
    if not configured:
        message = tr("workspace.admin.locked.setup_missing", lang, command=ADMIN_PIN_SETUP_COMMAND)
        tone = "warning"
    elif status_key:
        message = tr(status_key, lang)
    else:
        message = tr("workspace.admin.locked.ready", lang)
        tone = "info"

    disabled = not configured
    return html.Div(
        id="admin-locked-shell",
        className="panel admin-lock-card",
        children=[
            html.H3(tr("workspace.admin.locked.title", lang), id="admin-locked-title"),
            html.P(tr("workspace.admin.locked.copy", lang), id="admin-locked-copy", className="section-copy"),
            html.Div(message, id="admin-lock-status", className=f"admin-lock-status admin-lock-status-{tone}"),
            html.Label(tr("workspace.admin.locked.pin_label", lang), htmlFor="admin-pin-input", className="input-label"),
            dcc.Input(
                id="admin-pin-input",
                type="password",
                placeholder=tr("workspace.admin.locked.pin_placeholder", lang),
                className="text-input",
                disabled=disabled,
            ),
            html.Div(
                className="controls",
                children=[
                    html.Button(
                        tr("workspace.admin.locked.unlock", lang),
                        id="admin-unlock-btn",
                        n_clicks=0,
                        className="action-btn",
                        disabled=disabled,
                    ),
                    dcc.Link(tr("nav.results", lang), href="/", className="action-btn tertiary workspace-admin-nav-link"),
                    dcc.Link(tr("nav.assumptions", lang), href="/assumptions", className="action-btn tertiary workspace-admin-nav-link"),
                ],
            ),
        ],
    )
