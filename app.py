from __future__ import annotations

from dataclasses import replace
import multiprocessing

from dash import ALL, Dash, Input, Output, State, callback, ctx, dcc, html, no_update, page_container
from dash.exceptions import PreventUpdate
from flask import jsonify, request, send_file

from components.admin_view import build_admin_mode_dialog
from components.scenario_controls import run_scan_choice_dialog
from services.admin_access import is_admin_session_unlocked
from services.desktop_lifecycle import desktop_lifecycle
from services.i18n import tr
from services.runtime_paths import assets_dir, bundled_quick_guide_path, configure_runtime_environment, pages_dir
from services.session_state import bootstrap_client_session
from services.types import ClientSessionState
from services.ui_mode import (
    UI_MODE_ADMIN,
    UI_MODE_PRO,
    UI_MODE_SIMPLE,
    PAGE_ASSUMPTIONS,
    PAGE_COMPARE,
    PAGE_HELP,
    PAGE_RESULTS,
    PAGE_RISK,
    nav_visibility_style,
    normalize_ui_mode,
    resolve_ui_mode_from_payload,
)
from services.workspace_admin_callbacks import admin_access_meta, resolve_admin_access_view_state


configure_runtime_environment()


NAV_LINK_TARGETS = (
    ("nav-results-link", "/", PAGE_RESULTS),
    ("nav-assumptions-link", "/assumptions", PAGE_ASSUMPTIONS),
    ("nav-compare-link", "/compare", PAGE_COMPARE),
    ("nav-risk-link", "/risk", PAGE_RISK),
    ("nav-help-link", "/help", PAGE_HELP),
)
ADMIN_MODE_ORIGIN_SELECTOR = "mode_selector"
ADMIN_MODE_ORIGIN_ROUTE = "admin_route"
ADMIN_MODE_SUCCESS_MESSAGE_KEYS = {
    "workspace.advanced.setup.success",
    "workspace.advanced.locked.unlocked",
}


def _admin_mode_dialog_state(
    *,
    open_dialog: bool = False,
    origin: str | None = None,
    return_mode: str | None = UI_MODE_SIMPLE,
    post_unlock_href: str | None = None,
) -> dict[str, object]:
    return {
        "open": bool(open_dialog),
        "origin": None if not origin else str(origin),
        "return_mode": normalize_ui_mode(return_mode),
        "post_unlock_href": None if not post_unlock_href else str(post_unlock_href),
    }


def _normalize_pathname(pathname: str | None) -> str:
    normalized = str(pathname or "").strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized or "/"


def _nav_link_class_name(current_pathname: str | None, target_pathname: str) -> str:
    current = _normalize_pathname(current_pathname)
    target = _normalize_pathname(target_pathname)
    if target == "/":
        is_active = current == target
    else:
        is_active = current == target or current.startswith(f"{target}/")
    return "nav-link nav-link-active" if is_active else "nav-link"


def create_app() -> Dash:
    app = Dash(
        __name__,
        use_pages=True,
        suppress_callback_exceptions=True,
        assets_folder=str(assets_dir()),
        pages_folder=str(pages_dir()),
    )
    app.title = tr("app.title", "es")

    @app.server.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    @app.server.route("/__desktop/health")
    def desktop_health():
        return jsonify(desktop_lifecycle.health_payload())

    def _desktop_request_payload() -> dict[str, str]:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            return {str(key): str(value) for key, value in payload.items() if value is not None}
        if request.form:
            return {str(key): str(value) for key, value in request.form.items() if value is not None}
        return {}

    @app.server.route("/__desktop/client/heartbeat", methods=["POST"])
    def desktop_client_heartbeat():
        payload = _desktop_request_payload()
        client_id = str(payload.get("client_id") or "")
        token = str(payload.get("instance_token") or "")
        if not desktop_lifecycle.auto_shutdown_enabled:
            return jsonify({"status": "disabled"}), 200
        if not desktop_lifecycle.record_heartbeat(client_id, token):
            return jsonify({"status": "token_mismatch"}), 409
        return jsonify({"status": "ok", "active_client_count": desktop_lifecycle.active_client_count()})

    @app.server.route("/__desktop/client/disconnect", methods=["POST"])
    def desktop_client_disconnect():
        payload = _desktop_request_payload()
        client_id = str(payload.get("client_id") or "")
        token = str(payload.get("instance_token") or "")
        if not desktop_lifecycle.auto_shutdown_enabled:
            return jsonify({"status": "disabled"}), 200
        if not desktop_lifecycle.record_disconnect(client_id, token):
            return jsonify({"status": "token_mismatch"}), 409
        return jsonify({"status": "ok", "active_client_count": desktop_lifecycle.active_client_count()})

    @app.server.route("/help/guia-rapida")
    def quick_guide():
        guide_path = bundled_quick_guide_path()
        if not guide_path.exists():
            return tr("help.missing", "es"), 404
        return send_file(guide_path, mimetype="text/html")

    def _layout():
        client_state = bootstrap_client_session(language="es")
        return html.Div(
            className="app-shell",
            children=[
                dcc.Location(id="app-location"),
                dcc.Store(
                    id="scenario-session-store",
                    storage_type="session",
                    data=client_state.to_payload(),
                ),
                dcc.Store(
                    id="admin-access-meta",
                    storage_type="memory",
                    data=admin_access_meta(),
                ),
                dcc.Store(
                    id="admin-mode-dialog-state",
                    storage_type="memory",
                    data=_admin_mode_dialog_state(return_mode=client_state.ui_mode),
                ),
                dcc.Store(
                    id="run-scan-choice-state",
                    storage_type="memory",
                    data={"open": False, "suggested_project_name": ""},
                ),
                dcc.Store(
                    id="project-name-draft-store",
                    storage_type="memory",
                    data={"value": ""},
                ),
                html.Div(
                    id="admin-mode-dialog",
                    className="dialog-backdrop",
                    style={"display": "none"},
                ),
                run_scan_choice_dialog(),
                html.Header(
                    className="app-header",
                    children=[
                        html.Div(
                            children=[
                                html.H1(tr("app.title", "es"), id="app-title"),
                                html.P(tr("app.subtitle", "es"), id="app-subtitle"),
                            ]
                        ),
                        html.Div(
                            className="header-tools",
                            children=[
                                html.Div(
                                    className="language-box",
                                    children=[
                                        html.Label(tr("app.language", "es"), id="language-label", htmlFor="language-selector", className="input-label"),
                                        dcc.Dropdown(
                                            id="language-selector",
                                            options=[
                                                {"label": "English", "value": "en"},
                                                {"label": "Español", "value": "es"},
                                            ],
                                            value="es",
                                            clearable=False,
                                            className="language-select",
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="mode-box",
                                    children=[
                                        html.Label(tr("ui_mode.label", "es"), id="ui-mode-label", htmlFor="ui-mode-selector", className="input-label"),
                                        dcc.Dropdown(
                                            id="ui-mode-selector",
                                            options=[
                                                {"label": tr("ui_mode.option.simple", "es"), "value": "simple"},
                                                {"label": tr("ui_mode.option.pro", "es"), "value": "pro"},
                                                {"label": tr("ui_mode.option.admin", "es"), "value": "admin"},
                                            ],
                                            value=client_state.ui_mode,
                                            clearable=False,
                                            className="mode-select",
                                        ),
                                    ],
                                ),
                                html.Nav(
                                    className="top-nav",
                                    children=[
                                        dcc.Link(
                                            html.Span(tr("nav.results", "es"), id="nav-results-label"),
                                            id="nav-results-link",
                                            href="/",
                                            className="nav-link",
                                            style=nav_visibility_style(PAGE_RESULTS, client_state.ui_mode),
                                        ),
                                        dcc.Link(
                                            html.Span(tr("nav.assumptions", "es"), id="nav-assumptions-label"),
                                            id="nav-assumptions-link",
                                            href="/assumptions",
                                            className="nav-link",
                                            style=nav_visibility_style(PAGE_ASSUMPTIONS, client_state.ui_mode),
                                        ),
                                        dcc.Link(
                                            html.Span(tr("nav.compare", "es"), id="nav-compare-label"),
                                            id="nav-compare-link",
                                            href="/compare",
                                            className="nav-link",
                                            style=nav_visibility_style(PAGE_COMPARE, client_state.ui_mode),
                                        ),
                                        dcc.Link(
                                            html.Span(tr("nav.risk", "es"), id="nav-risk-label"),
                                            id="nav-risk-link",
                                            href="/risk",
                                            className="nav-link",
                                            style=nav_visibility_style(PAGE_RISK, client_state.ui_mode),
                                        ),
                                        dcc.Link(
                                            html.Span(tr("nav.help", "es"), id="nav-help-label"),
                                            id="nav-help-link",
                                            href="/help",
                                            className="nav-link",
                                            style=nav_visibility_style(PAGE_HELP, client_state.ui_mode),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                page_container,
            ],
        )

    app.layout = _layout
    return app


app = create_app()
server = app.server


@callback(
    Output("app-title", "children"),
    Output("app-subtitle", "children"),
    Output("language-label", "children"),
    Output("ui-mode-label", "children"),
    Output("ui-mode-selector", "options"),
    Output("nav-results-label", "children"),
    Output("nav-assumptions-label", "children"),
    Output("nav-compare-label", "children"),
    Output("nav-risk-label", "children"),
    Output("nav-help-label", "children"),
    Input("language-selector", "value"),
)
def translate_shell(language_value: str):
    lang = language_value if language_value in {"en", "es"} else "es"
    return (
        tr("app.title", lang),
        tr("app.subtitle", lang),
        tr("app.language", lang),
        tr("ui_mode.label", lang),
        [
            {"label": tr("ui_mode.option.simple", lang), "value": "simple"},
            {"label": tr("ui_mode.option.pro", lang), "value": "pro"},
            {"label": tr("ui_mode.option.admin", lang), "value": "admin"},
        ],
        tr("nav.results", lang),
        tr("nav.assumptions", lang),
        tr("nav.compare", lang),
        tr("nav.risk", lang),
        tr("nav.help", lang),
    )


@callback(
    Output("nav-results-link", "className"),
    Output("nav-assumptions-link", "className"),
    Output("nav-compare-link", "className"),
    Output("nav-risk-link", "className"),
    Output("nav-help-link", "className"),
    Input("app-location", "pathname"),
)
def sync_active_nav(pathname: str | None):
    return tuple(_nav_link_class_name(pathname, target) for _, target, _ in NAV_LINK_TARGETS)


@callback(
    Output("nav-results-link", "style"),
    Output("nav-assumptions-link", "style"),
    Output("nav-compare-link", "style"),
    Output("nav-risk-link", "style"),
    Output("nav-help-link", "style"),
    Input("scenario-session-store", "data"),
)
def sync_nav_visibility(session_payload: dict | None):
    ui_mode = resolve_ui_mode_from_payload(session_payload)
    return tuple(nav_visibility_style(page_key, ui_mode) for _, _target, page_key in NAV_LINK_TARGETS)


@callback(
    Output("ui-mode-selector", "value"),
    Input("scenario-session-store", "data"),
)
def sync_ui_mode_selector(session_payload: dict | None):
    return resolve_ui_mode_from_payload(session_payload)


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("admin-mode-dialog-state", "data", allow_duplicate=True),
    Output("admin-access-meta", "data", allow_duplicate=True),
    Output("app-location", "href", allow_duplicate=True),
    Input("ui-mode-selector", "value"),
    Input({"type": "ui-mode-gate-cta", "page": ALL, "target_mode": ALL}, "n_clicks"),
    Input("admin-redirect-enter-btn", "n_clicks", allow_optional=True),
    State("scenario-session-store", "data"),
    State("admin-mode-dialog-state", "data"),
    prevent_initial_call=True,
)
def update_ui_mode(selector_value, _gate_clicks, _admin_route_clicks, session_payload: dict | None, _dialog_state):
    trigger = ctx.triggered_id
    client_state = ClientSessionState.from_payload(session_payload)
    if client_state is None:
        client_state = bootstrap_client_session(language="es")
    current_mode = normalize_ui_mode(client_state.ui_mode)
    cleared_dialog_state = _admin_mode_dialog_state(return_mode=current_mode)

    if trigger == "ui-mode-selector":
        next_mode = normalize_ui_mode(selector_value)
        origin = ADMIN_MODE_ORIGIN_SELECTOR
        post_unlock_href = None
    elif isinstance(trigger, dict) and trigger.get("type") == "ui-mode-gate-cta":
        next_mode = normalize_ui_mode(trigger.get("target_mode"))
        origin = ADMIN_MODE_ORIGIN_SELECTOR
        post_unlock_href = None
    elif trigger == "admin-redirect-enter-btn":
        next_mode = UI_MODE_ADMIN
        origin = ADMIN_MODE_ORIGIN_ROUTE
        post_unlock_href = "/assumptions#advanced-tools"
    else:
        raise PreventUpdate

    if next_mode in {UI_MODE_SIMPLE, UI_MODE_PRO}:
        if current_mode == next_mode:
            raise PreventUpdate
        return (
            replace(client_state, ui_mode=next_mode).to_payload(),
            _admin_mode_dialog_state(return_mode=next_mode),
            admin_access_meta(),
            no_update,
        )

    if is_admin_session_unlocked(client_state.session_id):
        next_payload = no_update if current_mode == UI_MODE_ADMIN else replace(client_state, ui_mode=UI_MODE_ADMIN).to_payload()
        href = post_unlock_href or no_update
        if next_payload is no_update and href is no_update:
            raise PreventUpdate
        return (
            next_payload,
            _admin_mode_dialog_state(return_mode=UI_MODE_ADMIN),
            admin_access_meta(),
            href,
        )

    return (
        no_update,
        _admin_mode_dialog_state(
            open_dialog=True,
            origin=origin,
            return_mode=current_mode,
            post_unlock_href=post_unlock_href,
        ),
        admin_access_meta(),
        no_update,
    )


@callback(
    Output("admin-mode-dialog", "style"),
    Output("admin-mode-dialog", "children"),
    Input("admin-mode-dialog-state", "data"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
    Input("admin-access-meta", "data"),
)
def sync_admin_mode_dialog(dialog_state, session_payload, language_value, access_meta):
    if not isinstance(dialog_state, dict) or not bool(dialog_state.get("open")):
        return {"display": "none"}, []
    view_state = resolve_admin_access_view_state(session_payload, language_value, access_meta)
    return {
        "display": "flex",
    }, [
        build_admin_mode_dialog(
            lang=str(view_state["lang"]),
            access_mode=str(view_state["access_mode"]),
            status_key=view_state["status_key"],
            tone=str(view_state["tone"]),
        )
    ]


@callback(
    Output("admin-mode-dialog-state", "data", allow_duplicate=True),
    Output("admin-access-meta", "data", allow_duplicate=True),
    Input("admin-mode-dialog-cancel-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def cancel_admin_mode_dialog(_cancel_clicks, session_payload):
    return (
        _admin_mode_dialog_state(return_mode=resolve_ui_mode_from_payload(session_payload)),
        admin_access_meta(),
    )


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("admin-mode-dialog-state", "data", allow_duplicate=True),
    Output("admin-access-meta", "data", allow_duplicate=True),
    Output("app-location", "href", allow_duplicate=True),
    Input("admin-access-meta", "data"),
    State("scenario-session-store", "data"),
    State("admin-mode-dialog-state", "data"),
    prevent_initial_call=True,
)
def finalize_admin_mode_unlock(access_meta, session_payload, dialog_state):
    if not isinstance(dialog_state, dict) or not bool(dialog_state.get("open")):
        raise PreventUpdate
    message_key = str((access_meta or {}).get("message_key") or "").strip()
    if message_key not in ADMIN_MODE_SUCCESS_MESSAGE_KEYS:
        raise PreventUpdate

    client_state = ClientSessionState.from_payload(session_payload)
    if client_state is None:
        client_state = bootstrap_client_session(language="es")
    current_mode = normalize_ui_mode(client_state.ui_mode)
    next_payload = no_update if current_mode == UI_MODE_ADMIN else replace(client_state, ui_mode=UI_MODE_ADMIN).to_payload()
    href = (
        str(dialog_state.get("post_unlock_href") or "").strip() or no_update
        if str(dialog_state.get("origin") or "").strip() == ADMIN_MODE_ORIGIN_ROUTE
        else no_update
    )
    return (
        next_payload,
        _admin_mode_dialog_state(return_mode=UI_MODE_ADMIN),
        admin_access_meta(),
        href,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app.run(debug=True)
