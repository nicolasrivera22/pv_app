from __future__ import annotations

from dash import Dash, Input, Output, callback, dcc, html, page_container
from flask import jsonify, request, send_file

from services.desktop_lifecycle import desktop_lifecycle
from services.i18n import tr
from services.runtime_paths import assets_dir, bundled_quick_guide_path, configure_runtime_environment, pages_dir
from services.session_state import bootstrap_client_session


configure_runtime_environment()


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
                                html.Nav(
                                    className="top-nav",
                                    children=[
                                        dcc.Link(html.Span(tr("nav.results", "es"), id="nav-results-label"), href="/", className="nav-link"),
                                        dcc.Link(html.Span(tr("nav.assumptions", "es"), id="nav-assumptions-label"), href="/assumptions", className="nav-link"),
                                        dcc.Link(html.Span(tr("nav.compare", "es"), id="nav-compare-label"), href="/compare", className="nav-link"),
                                        dcc.Link(html.Span(tr("nav.risk", "es"), id="nav-risk-label"), href="/risk", className="nav-link"),
                                        dcc.Link(html.Span(tr("nav.help", "es"), id="nav-help-label"), href="/help", className="nav-link"),
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
        tr("nav.results", lang),
        tr("nav.assumptions", lang),
        tr("nav.compare", lang),
        tr("nav.risk", lang),
        tr("nav.help", lang),
    )


if __name__ == "__main__":
    app.run(debug=True)
