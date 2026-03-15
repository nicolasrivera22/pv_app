from __future__ import annotations

from dash import Dash, Input, Output, callback, dcc, html, page_container

from services.i18n import tr
from services.runtime_paths import assets_dir, configure_runtime_environment, pages_dir
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
                                        dcc.Link(html.Span(tr("nav.workbench", "es"), id="nav-workbench-label"), href="/", className="nav-link"),
                                        dcc.Link(html.Span(tr("nav.compare", "es"), id="nav-compare-label"), href="/compare", className="nav-link"),
                                        dcc.Link(html.Span(tr("nav.risk", "es"), id="nav-risk-label"), href="/risk", className="nav-link"),
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

    app.index_string = """
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <style>
                body { font-family: "IBM Plex Sans", "Segoe UI", sans-serif; margin: 0; background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%); color: #0f172a; }
                .app-shell { min-height: 100vh; }
                .app-header { max-width: 1400px; margin: 0 auto; padding: 1.4rem 1.25rem 0.5rem; display: flex; gap: 1rem; align-items: end; justify-content: space-between; }
                .app-header h1 { margin: 0; }
                .app-header p { margin: 0.35rem 0 0; color: #475569; }
                .header-tools { display: flex; gap: 1rem; flex-wrap: wrap; align-items: end; }
                .language-box { min-width: 180px; }
                .language-select { min-width: 160px; }
                .top-nav { display: flex; gap: 0.65rem; flex-wrap: wrap; }
                .nav-link { text-decoration: none; padding: 0.75rem 1rem; border-radius: 999px; background: rgba(255,255,255,0.82); color: #0f172a; font-weight: 600; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05); }
                .page { max-width: 1400px; margin: 0 auto; padding: 1rem 1.25rem 3rem; }
                .workbench-grid { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 1rem; align-items: start; }
                .main-stack { display: grid; gap: 1rem; }
                .controls { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.75rem; }
                .upload-box { border: 2px dashed #94a3b8; border-radius: 14px; padding: 1rem 1.15rem; background: rgba(255,255,255,0.92); min-width: 0; }
                .panel, .subpanel { background: rgba(255,255,255,0.92); border-radius: 20px; padding: 1rem; box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08); }
                .secondary-panel { background: rgba(248,250,252,0.96); }
                .subpanel { border: 1px solid rgba(203,213,225,0.75); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35); }
                .sidebar-panel { position: sticky; top: 1rem; }
                .section-head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.9rem; flex-wrap: wrap; }
                .section-head h2, .section-head h3, .section-head h4 { margin: 0; }
                .action-btn { border: none; border-radius: 999px; padding: 0.75rem 1rem; background: #0f766e; color: white; font-weight: 600; cursor: pointer; }
                .action-btn.secondary { background: #334155; }
                .action-btn.tertiary { background: #cbd5e1; color: #0f172a; }
                .action-btn:disabled { background: #94a3b8; cursor: not-allowed; }
                .status-line { margin: 0.3rem 0; font-size: 0.95rem; color: #334155; }
                .validation-box { background: rgba(255,255,255,0.85); border-radius: 14px; padding: 1rem; box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.25); }
                .validation-empty { color: #475569; }
                .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem; margin: 0.75rem 0 1rem; }
                .kpi-card { background: white; border-radius: 18px; padding: 1rem; box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08); }
                .kpi-label { font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; color: #475569; }
                .kpi-value { margin-top: 0.45rem; font-size: 1.2rem; font-weight: 700; }
                .selected-candidate-kpi-title { margin: 0.25rem 0 0; font-size: 0.9rem; font-weight: 700; color: #334155; text-transform: uppercase; letter-spacing: 0.06em; }
                .candidate-selection-helper { margin-top: 0.25rem; padding: 0.75rem 0.9rem; border-radius: 14px; background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
                .selected-candidate-banner { display: flex; flex-wrap: wrap; gap: 0.65rem; margin: 0 0 1rem; }
                .selected-candidate-banner-item { display: inline-flex; flex-direction: column; gap: 0.18rem; padding: 0.7rem 0.85rem; border-radius: 14px; background: #f8fafc; border: 1px solid #dbeafe; min-width: 150px; }
                .selected-candidate-banner-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; font-weight: 700; }
                .selected-candidate-banner-value { color: #0f172a; font-weight: 600; }
                .link { text-decoration: underline; }
                .input-label { display: block; margin-bottom: 0.35rem; font-size: 0.92rem; font-weight: 600; color: #334155; }
                .text-input { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 12px; padding: 0.7rem 0.8rem; background: white; }
                .rename-row { display: grid; gap: 0.5rem; grid-template-columns: minmax(0, 1fr) auto; margin: 0.8rem 0; }
                .scenario-list { display: grid; gap: 0.5rem; margin-top: 0.8rem; }
                .scenario-pill { border-radius: 14px; padding: 0.75rem 0.9rem; background: #f8fafc; border: 1px solid #dbeafe; }
                .scenario-pill.active { border-color: #0f766e; background: #ecfeff; }
                .scenario-meta { color: #475569; font-size: 0.9rem; }
                .assumption-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; }
                .field-card { background: #f8fafc; border-radius: 14px; padding: 0.85rem; border: 1px solid rgba(203,213,225,0.7); }
                .advanced-card { background: rgba(248,250,252,0.85); border-style: dashed; }
                .section-copy { margin: 0 0 0.9rem; color: #475569; font-size: 0.93rem; max-width: 75ch; }
                .advanced-details summary { cursor: pointer; color: #334155; font-weight: 600; margin-bottom: 0.75rem; }
                .field-help { position: relative; display: inline-flex; align-items: center; margin-left: 0.35rem; }
                .field-help-trigger { display: inline-flex; align-items: center; justify-content: center; width: 1.2rem; height: 1.2rem; border-radius: 999px; background: #dbeafe; color: #1d4ed8; font-size: 0.75rem; font-weight: 700; cursor: help; }
                .field-help-tooltip { position: absolute; left: 0; top: calc(100% + 0.35rem); z-index: 30; min-width: 220px; max-width: 280px; padding: 0.55rem 0.7rem; border-radius: 10px; background: #0f172a; color: white; font-size: 0.8rem; line-height: 1.45; opacity: 0; pointer-events: none; transform: translateY(-2px); transition: opacity 100ms ease, transform 100ms ease; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.26); }
                .field-help:hover .field-help-tooltip, .field-help:focus-within .field-help-tooltip { opacity: 1; transform: translateY(0); }
                .catalog-grid, .chart-grid, .compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem; }
                .compare-grid > .panel { min-height: 100%; }
                .deep-dive-stack { display: grid; gap: 1rem; }
                .schematic-summary-chip { display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.45rem 0.8rem; border-radius: 999px; background: #eff6ff; color: #1d4ed8; font-weight: 600; width: fit-content; }
                .schematic-stack { display: grid; gap: 1rem; }
                .schematic-diagram-card, .schematic-detail-card, .schematic-legend-card { min-width: 0; width: 100%; }
                .schematic-diagram-card { padding: 0.2rem 0 0.1rem; }
                .schematic-detail-card, .schematic-legend-card { padding: 1rem 1.1rem; }
                .schematic-note { margin: 0.15rem 0 0; max-width: none; }
                .legend-list { display: flex; flex-wrap: wrap; gap: 0.75rem 0.9rem; align-items: stretch; }
                .legend-list-inline { justify-content: flex-start; }
                .legend-item { display: flex; align-items: center; gap: 0.7rem; color: #334155; padding: 0.55rem 0.8rem; border-radius: 14px; background: rgba(255,255,255,0.72); border: 1px solid rgba(203,213,225,0.82); flex: 1 1 220px; min-width: 220px; }
                .legend-swatch { display: inline-flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.03em; }
                .legend-node { width: 58px; height: 38px; border: 2px solid #cbd5e1; background-color: #fff; color: #0f172a; border-radius: 14px; background-repeat: no-repeat; background-position: center; background-size: 24px 24px; }
                .legend-role-pv { border-color: #f59e0b; background-color: #fffbeb; }
                .legend-role-inverter { border-color: #2563eb; background-color: #eff6ff; }
                .legend-role-battery { border-color: #7c3aed; background-color: #f5f3ff; }
                .legend-role-load { border-color: #16a34a; background-color: #f0fdf4; }
                .legend-role-grid { border-color: #1e293b; background-color: #e2e8f0; }
                .legend-line { width: 54px; height: 0; border-top: 4px solid #64748b; color: transparent; overflow: hidden; }
                .legend-connection-ac { border-top-color: #2563eb; }
                .legend-connection-dc { border-top-color: #7c3aed; }
                .inspector-body { display: grid; gap: 0.75rem; }
                .inspector-header { display: flex; align-items: center; gap: 0.8rem; }
                .inspector-header-copy { min-width: 0; display: grid; gap: 0.25rem; }
                .inspector-icon { width: 52px; height: 52px; border-radius: 16px; border: 1px solid rgba(148,163,184,0.4); background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(241,245,249,0.95)); background-repeat: no-repeat; background-position: center; background-size: 28px 28px; display: inline-flex; align-items: center; justify-content: center; color: #0f172a; font-weight: 700; flex-shrink: 0; }
                .inspector-kind-row { display: flex; flex-wrap: wrap; gap: 0.4rem; }
                .inspector-kind, .inspector-status { display: inline-flex; align-items: center; padding: 0.18rem 0.5rem; border-radius: 999px; font-size: 0.74rem; font-weight: 700; letter-spacing: 0.02em; }
                .inspector-kind { background: #e2e8f0; color: #334155; }
                .inspector-status { background: #ecfeff; color: #0f766e; }
                .inspector-focus-title { font-size: 1rem; font-weight: 700; color: #0f172a; }
                .inspector-description { margin: 0; color: #475569; line-height: 1.5; }
                .inspector-list { display: grid; gap: 0.4rem; }
                .inspector-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.75rem; padding: 0.35rem 0; border-bottom: 1px solid rgba(226, 232, 240, 0.9); }
                .inspector-row:last-child { border-bottom: none; }
                .inspector-label { font-weight: 600; color: #334155; }
                .inspector-value { color: #0f172a; text-align: right; }
                .inspector-note { padding: 0.7rem 0.8rem; border-radius: 12px; background: #fffbeb; color: #92400e; border: 1px solid #fde68a; line-height: 1.45; }
                @media (max-width: 720px) { .legend-item { min-width: 100%; flex-basis: 100%; } }
                @media (max-width: 980px) { .workbench-grid { grid-template-columns: 1fr; } .sidebar-panel { position: static; } .app-header { align-items: start; flex-direction: column; } .header-tools { width: 100%; align-items: start; } }
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    """
    return app


app = create_app()
server = app.server


@callback(
    Output("app-title", "children"),
    Output("app-subtitle", "children"),
    Output("language-label", "children"),
    Output("nav-workbench-label", "children"),
    Output("nav-compare-label", "children"),
    Output("nav-risk-label", "children"),
    Input("language-selector", "value"),
)
def translate_shell(language_value: str):
    lang = language_value if language_value in {"en", "es"} else "es"
    return (
        tr("app.title", lang),
        tr("app.subtitle", lang),
        tr("app.language", lang),
        tr("nav.workbench", lang),
        tr("nav.compare", lang),
        tr("nav.risk", lang),
    )


if __name__ == "__main__":
    app.run(debug=True)
