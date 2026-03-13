from __future__ import annotations

from dash import Dash, dcc, html, page_container


def create_app() -> Dash:
    app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)
    app.title = "PV Deterministic Workbench"

    app.layout = html.Div(
        className="app-shell",
        children=[
            dcc.Store(id="scenario-session-store", storage_type="memory"),
            html.Header(
                className="app-header",
                children=[
                    html.Div(
                        children=[
                            html.H1("PV deterministic workbench"),
                            html.P("Compare deterministic scenarios, edit assumptions, inspect candidates, and export results."),
                        ]
                    ),
                    html.Nav(
                        className="top-nav",
                        children=[
                            dcc.Link("Workbench", href="/", className="nav-link"),
                            dcc.Link("Compare", href="/compare", className="nav-link"),
                        ],
                    ),
                ],
            ),
            page_container,
        ],
    )

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
                .top-nav { display: flex; gap: 0.65rem; flex-wrap: wrap; }
                .nav-link { text-decoration: none; padding: 0.75rem 1rem; border-radius: 999px; background: rgba(255,255,255,0.82); color: #0f172a; font-weight: 600; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05); }
                .page { max-width: 1400px; margin: 0 auto; padding: 1rem 1.25rem 3rem; }
                .workbench-grid { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 1rem; align-items: start; }
                .main-stack { display: grid; gap: 1rem; }
                .controls { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.75rem; }
                .upload-box { border: 2px dashed #94a3b8; border-radius: 14px; padding: 1rem 1.15rem; background: rgba(255,255,255,0.92); min-width: 0; }
                .panel, .subpanel { background: rgba(255,255,255,0.92); border-radius: 20px; padding: 1rem; box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08); }
                .sidebar-panel { position: sticky; top: 1rem; }
                .section-head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.9rem; flex-wrap: wrap; }
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
                .link { text-decoration: underline; }
                .input-label { display: block; margin-bottom: 0.35rem; font-size: 0.92rem; font-weight: 600; color: #334155; }
                .text-input { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 12px; padding: 0.7rem 0.8rem; background: white; }
                .rename-row { display: grid; gap: 0.5rem; grid-template-columns: minmax(0, 1fr) auto; margin: 0.8rem 0; }
                .scenario-list { display: grid; gap: 0.5rem; margin-top: 0.8rem; }
                .scenario-pill { border-radius: 14px; padding: 0.75rem 0.9rem; background: #f8fafc; border: 1px solid #dbeafe; }
                .scenario-pill.active { border-color: #0f766e; background: #ecfeff; }
                .scenario-meta { color: #475569; font-size: 0.9rem; }
                .assumption-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; }
                .field-card { background: #f8fafc; border-radius: 14px; padding: 0.85rem; }
                .catalog-grid, .chart-grid, .compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem; }
                .compare-grid > .panel { min-height: 100%; }
                @media (max-width: 980px) { .workbench-grid { grid-template-columns: 1fr; } .sidebar-panel { position: static; } .app-header { align-items: start; flex-direction: column; } }
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


if __name__ == "__main__":
    app.run(debug=True)
