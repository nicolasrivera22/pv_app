from __future__ import annotations

from dash import dcc, html

from services.i18n import tr

from .catalog_editor import catalog_editor_section
from .economics_editor import economics_editor_section
from .profile_editor import resource_profile_editor_section


def admin_setup_card(
    *,
    lang: str = "es",
    status_key: str | None = None,
    tone: str = "neutral",
) -> html.Div:
    if status_key:
        message = tr(status_key, lang)
    else:
        message = tr("workspace.advanced.setup.ready", lang)
        tone = "info"

    return html.Div(
        id="admin-setup-shell",
        className="panel admin-lock-card",
        children=[
            html.H3(tr("workspace.advanced.setup.title", lang), id="admin-setup-title"),
            html.P(tr("workspace.advanced.setup.copy", lang), id="admin-setup-copy", className="section-copy"),
            html.Div(message, id="admin-setup-status", className=f"admin-lock-status admin-lock-status-{tone}"),
            html.Label(tr("workspace.advanced.setup.pin_label", lang), htmlFor="admin-setup-pin-input", className="input-label"),
            dcc.Input(
                id="admin-setup-pin-input",
                type="password",
                placeholder=tr("workspace.advanced.setup.pin_placeholder", lang),
                className="text-input",
            ),
            html.Label(
                tr("workspace.advanced.setup.confirm_label", lang),
                htmlFor="admin-setup-confirm-input",
                className="input-label",
            ),
            dcc.Input(
                id="admin-setup-confirm-input",
                type="password",
                placeholder=tr("workspace.advanced.setup.confirm_placeholder", lang),
                className="text-input",
            ),
            html.Div(
                className="controls",
                children=[
                    html.Button(
                        tr("workspace.advanced.setup.submit", lang),
                        id="admin-setup-btn",
                        n_clicks=0,
                        className="action-btn",
                    ),
                ],
            ),
        ],
    )


def admin_secure_content(*, lang: str = "es") -> html.Div:
    return html.Div(
        id="admin-unlocked-shell",
        children=[
            html.Div(
                className="panel secondary-panel",
                children=[
                    html.Div(tr("workspace.advanced.session_unlocked", lang), id="admin-session-unlocked-note", className="status-line workspace-admin-note"),
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
            economics_editor_section(lang=lang),
            html.Details(
                id="admin-assumptions-details",
                className="panel secondary-panel admin-auxiliary-details",
                open=False,
                children=[
                    html.Summary(
                        id="admin-assumptions-summary",
                        className="admin-auxiliary-summary",
                        children=[
                            html.Div(
                                className="admin-auxiliary-summary-copy",
                                children=[
                                    html.H3(tr("workspace.advanced.fields.title", lang), id="admin-assumptions-title"),
                                    html.P(
                                        tr("workspace.advanced.fields.copy", lang),
                                        id="admin-assumptions-copy",
                                        className="section-copy",
                                    ),
                                ],
                            )
                        ],
                    ),
                    html.Div(
                        className="assumption-editor-panel admin-auxiliary-body",
                        children=[html.Div(id="admin-assumption-sections")],
                    ),
                ],
            ),
            resource_profile_editor_section(lang=lang),
            catalog_editor_section(lang=lang),
        ],
    )


def admin_locked_card(
    *,
    lang: str = "es",
    status_key: str | None = None,
    tone: str = "neutral",
) -> html.Div:
    if status_key:
        message = tr(status_key, lang)
    else:
        message = tr("workspace.advanced.locked.ready", lang)
        tone = "info"

    return html.Div(
        id="admin-locked-shell",
        className="panel admin-lock-card",
        children=[
            html.H3(tr("workspace.advanced.locked.title", lang), id="admin-locked-title"),
            html.P(tr("workspace.advanced.locked.copy", lang), id="admin-locked-copy", className="section-copy"),
            html.Div(message, id="admin-lock-status", className=f"admin-lock-status admin-lock-status-{tone}"),
            html.Label(tr("workspace.advanced.locked.pin_label", lang), htmlFor="admin-pin-input", className="input-label"),
            dcc.Input(
                id="admin-pin-input",
                type="password",
                placeholder=tr("workspace.advanced.locked.pin_placeholder", lang),
                className="text-input",
                style={"padding-bottom": "0.5rem"}
            ),
            html.Div(
                className="controls",
                children=[
                    html.Button(
                        tr("workspace.advanced.locked.unlock", lang),
                        id="admin-unlock-btn",
                        n_clicks=0,
                        className="action-btn",
                    ),
                ],
            ),
        ],
    )


def build_admin_access_shell(
    *,
    lang: str = "es",
    configured: bool,
    unlocked: bool,
    status_key: str | None = None,
    tone: str = "neutral",
):
    if not configured:
        return admin_setup_card(lang=lang, status_key=status_key, tone=tone)
    if unlocked:
        return admin_secure_content(lang=lang)
    return admin_locked_card(lang=lang, status_key=status_key, tone=tone)
