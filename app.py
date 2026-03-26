from __future__ import annotations

from dataclasses import replace

from dash import ALL, Dash, Input, Output, State, callback, ctx, dcc, html, page_container
from dash.exceptions import PreventUpdate
from flask import jsonify, request, send_file

from services.desktop_lifecycle import desktop_lifecycle
from services.i18n import tr
from services.runtime_paths import assets_dir, bundled_quick_guide_path, configure_runtime_environment, pages_dir
from services.session_state import bootstrap_client_session
from services.types import ClientSessionState
from services.ui_mode import (
    PAGE_ASSUMPTIONS,
    PAGE_COMPARE,
    PAGE_HELP,
    PAGE_RESULTS,
    PAGE_RISK,
    nav_visibility_style,
    normalize_ui_mode,
    resolve_ui_mode_from_payload,
)


configure_runtime_environment()


NAV_LINK_TARGETS = (
    ("nav-results-link", "/", PAGE_RESULTS),
    ("nav-assumptions-link", "/assumptions", PAGE_ASSUMPTIONS),
    ("nav-compare-link", "/compare", PAGE_COMPARE),
    ("nav-risk-link", "/risk", PAGE_RISK),
    ("nav-help-link", "/help", PAGE_HELP),
)


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
    Input("ui-mode-selector", "value"),
    Input({"type": "ui-mode-gate-cta", "page": ALL, "target_mode": ALL}, "n_clicks"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def update_ui_mode(selector_value, _gate_clicks, session_payload: dict | None):
    trigger = ctx.triggered_id
    if trigger == "ui-mode-selector":
        next_mode = normalize_ui_mode(selector_value)
    elif isinstance(trigger, dict) and trigger.get("type") == "ui-mode-gate-cta":
        next_mode = normalize_ui_mode(trigger.get("target_mode"))
    else:
        raise PreventUpdate

    client_state = ClientSessionState.from_payload(session_payload)
    if client_state is None:
        client_state = bootstrap_client_session(language="es")
    if client_state.ui_mode == next_mode:
        raise PreventUpdate
    return replace(client_state, ui_mode=next_mode).to_payload()


if __name__ == "__main__":
    app.run(debug=True)
