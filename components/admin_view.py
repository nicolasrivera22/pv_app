from __future__ import annotations

from dash import dcc, html

from services.i18n import tr

from .catalog_editor import catalog_editor_section
from .economics_editor import economics_editor_section
from .profile_editor import resource_profile_editor_section


def _status_message(status_key: str | None, *, lang: str) -> str | None:
    normalized = str(status_key or "").strip()
    return tr(normalized, lang) if normalized else None


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


def build_admin_access_summary(
    *,
    lang: str = "es",
    access_mode: str,
    preview_state: str | None = None,
    scenario_name: str | None = None,
    candidate_key: str | None = None,
    status_key: str | None = None,
    tone: str = "neutral",
) -> html.Div:
    status_label_key = {
        "setup_required": "workspace.advanced.entry.status.setup_required",
        "locked": "workspace.advanced.entry.status.locked",
        "unlocked": "workspace.advanced.entry.status.unlocked",
    }.get(access_mode, "workspace.advanced.entry.status.locked")
    summary_key = {
        "setup_required": "workspace.advanced.entry.summary.setup_required",
        "locked": "workspace.advanced.entry.summary.locked",
        "unlocked": "workspace.advanced.entry.summary.unlocked",
    }.get(access_mode, "workspace.advanced.entry.summary.locked")
    cta_key = {
        "setup_required": "workspace.advanced.entry.cta.setup_required",
        "locked": "workspace.advanced.entry.cta.locked",
        "unlocked": "workspace.advanced.entry.cta.unlocked",
    }.get(access_mode, "workspace.advanced.entry.cta.locked")
    status_class = {
        "setup_required": "workbench-state-chip-warning",
        "locked": "workbench-state-chip-info",
        "unlocked": "workbench-state-chip-success",
    }.get(access_mode, "workbench-state-chip-info")
    context_line: str | None = None
    if access_mode == "unlocked":
        if preview_state == "ready" and scenario_name and candidate_key:
            context_line = tr(
                "workspace.advanced.entry.context.active_design",
                lang,
                scenario_name=scenario_name,
                candidate_key=candidate_key,
            )
        elif preview_state == "rerun_required" and scenario_name:
            context_line = tr(
                "workspace.advanced.entry.context.rerun_required",
                lang,
                scenario_name=scenario_name,
            )
        elif preview_state == "candidate_missing" and scenario_name:
            context_line = tr(
                "workspace.advanced.entry.context.candidate_missing",
                lang,
                scenario_name=scenario_name,
            )
        elif scenario_name:
            context_line = tr(
                "workspace.advanced.entry.context.pre_scan",
                lang,
                scenario_name=scenario_name,
            )
        else:
            context_line = tr("workspace.advanced.entry.context.no_scenario", lang)

    meta_message = _status_message(status_key, lang=lang)
    children = [
        html.Div(tr("workspace.advanced.entry.eyebrow", lang), className="assumptions-advanced-entry-eyebrow"),
        html.Div(
            className="assumptions-advanced-entry-head",
            children=[
                html.Div(
                    className="assumptions-advanced-entry-copy",
                    children=[
                        html.H3(tr("workspace.advanced.title", lang), id="assumptions-advanced-tools-entry-title"),
                        html.P(
                            tr(summary_key, lang),
                            id="assumptions-advanced-tools-entry-summary",
                            className="section-copy assumptions-advanced-entry-summary",
                        ),
                    ],
                ),
                html.Span(
                    tr(status_label_key, lang),
                    id="assumptions-advanced-tools-entry-status",
                    className=f"workbench-state-chip {status_class}",
                ),
            ],
        ),
    ]
    if meta_message:
        children.append(
            html.Div(
                meta_message,
                id="assumptions-advanced-tools-entry-meta",
                className=f"assumptions-advanced-entry-meta assumptions-advanced-entry-meta-{tone}",
            )
        )
    children.append(
        html.Div(
            className="assumptions-advanced-entry-footer",
            children=[
                html.A(
                    tr(cta_key, lang),
                    id="assumptions-advanced-tools-entry-link",
                    href="#advanced-tools",
                    className="action-btn tertiary assumptions-advanced-entry-link",
                ),
                html.Div(
                    context_line or "",
                    id="assumptions-advanced-tools-entry-context",
                    className="assumptions-advanced-entry-context",
                ),
            ],
        )
    )
    return html.Div(
        id="assumptions-advanced-tools-entry-card",
        className=f"panel secondary-panel assumptions-advanced-entry-card assumptions-advanced-entry-card-mode-{access_mode}",
        children=children,
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
    access_mode: str,
    status_key: str | None = None,
    tone: str = "neutral",
):
    if access_mode == "setup_required":
        return admin_setup_card(lang=lang, status_key=status_key, tone=tone)
    if access_mode == "unlocked":
        return admin_secure_content(lang=lang)
    return admin_locked_card(lang=lang, status_key=status_key, tone=tone)
