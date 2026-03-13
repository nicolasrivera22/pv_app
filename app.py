from __future__ import annotations

import base64
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, ctx, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from services import LoadedConfigBundle, ScanRunResult, load_config_from_excel, load_example_config, run_scan
from services.result_views import build_cash_flow, build_kpis, build_monthly_balance, build_npv_curve


def _issue_list(issues) -> html.Div:
    if not issues:
        return html.Div("No validation messages.", className="validation-empty")
    items = []
    for issue in issues:
        color = "#9f1239" if issue.level == "error" else "#92400e"
        items.append(html.Li(f"{issue.level.upper()} [{issue.field}] {issue.message}", style={"color": color}))
    return html.Ul(items, style={"margin": 0, "paddingLeft": "1.2rem"})


def _currency(value: float | None) -> str:
    if value is None:
        return "-"
    return f"COP {value:,.0f}"


def _number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}{suffix}"


def _empty_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def _build_npv_figure(candidates, selected_key: str) -> go.Figure:
    curve = build_npv_curve(candidates)
    figure = px.line(curve, x="kWp", y="NPV_COP", markers=True, template="plotly_white", title="NPV vs kWp")
    selected_row = curve[curve["candidate_key"] == selected_key]
    if not selected_row.empty:
        figure.add_scatter(
            x=selected_row["kWp"],
            y=selected_row["NPV_COP"],
            mode="markers",
            marker={"size": 14, "color": "#b91c1c"},
            name="Selected candidate",
        )
    figure.update_yaxes(title="NPV (COP)")
    figure.update_xaxes(title="Installed kWp")
    return figure


def _build_monthly_balance_figure(monthly_balance) -> go.Figure:
    melted = monthly_balance.melt(id_vars="Año_mes", var_name="series", value_name="kWh")
    figure = px.bar(
        melted,
        x="Año_mes",
        y="kWh",
        color="series",
        barmode="stack",
        template="plotly_white",
        title="Monthly energy balance (year 1)",
    )
    figure.update_xaxes(title="Month")
    figure.update_yaxes(title="kWh")
    return figure


def _build_cash_flow_figure(cash_flow) -> go.Figure:
    figure = px.line(
        cash_flow,
        x="Año_mes",
        y="cumulative_npv",
        template="plotly_white",
        title="Cumulative cash flow",
    )
    figure.add_hline(y=0, line_dash="dash", line_color="#334155")
    figure.update_xaxes(title="Month")
    figure.update_yaxes(title="Discounted cumulative cash flow (COP)")
    return figure


def _kpi_cards(kpis: dict[str, Any]) -> list[html.Div]:
    cards = [
        ("Best kWp", _number(kpis.get("best_kWp"), " kWp")),
        ("Battery", str(kpis.get("selected_battery", "-"))),
        ("NPV", _currency(kpis.get("NPV"))),
        ("Payback", _number(kpis.get("payback_years"), " years")),
        ("Self-consumption", _number(100 * float(kpis.get("self_consumption_ratio", 0.0)), "%")),
    ]
    return [
        html.Div(
            [html.Div(label, className="kpi-label"), html.Div(value, className="kpi-value")],
            className="kpi-card",
        )
        for label, value in cards
    ]


def create_app() -> Dash:
    app = Dash(__name__)
    app.title = "PV Sizing Dash MVP"

    app.layout = html.Div(
        className="page",
        children=[
            dcc.Store(id="config-store"),
            dcc.Store(id="scan-store"),
            html.H1("PV sizing deterministic MVP"),
            html.P("Upload the existing Excel workbook or load the bundled example, then run the deterministic scan."),
            html.Div(
                className="controls",
                children=[
                    dcc.Upload(
                        id="upload-config",
                        children=html.Div(["Drop Excel here or ", html.Span("select a file", className="link")]),
                        multiple=False,
                        className="upload-box",
                    ),
                    html.Button("Load example", id="load-example-btn", n_clicks=0, className="action-btn secondary"),
                    html.Button("Run deterministic scan", id="run-scan-btn", n_clicks=0, className="action-btn", disabled=True),
                ],
            ),
            html.Div(id="source-status", className="status-line"),
            html.Div(id="run-status", className="status-line"),
            html.H3("Validation"),
            html.Div(id="validation-messages", className="validation-box"),
            html.Div(id="kpi-cards", className="kpi-grid"),
            dcc.Graph(id="npv-graph", figure=_empty_figure("NPV vs kWp", "Run a scan to view results.")),
            dcc.Graph(id="monthly-balance-graph", figure=_empty_figure("Monthly energy balance", "No scenario selected.")),
            dcc.Graph(id="cash-flow-graph", figure=_empty_figure("Cumulative cash flow", "No scenario selected.")),
            html.H3("Candidate table"),
            dash_table.DataTable(
                id="candidate-table",
                data=[],
                columns=[],
                row_selectable="single",
                selected_rows=[],
                hidden_columns=["candidate_key"],
                sort_action="native",
                page_size=12,
                style_table={"overflowX": "auto"},
                style_cell={"padding": "0.5rem", "fontFamily": "monospace", "fontSize": 13},
                style_header={"backgroundColor": "#e2e8f0", "fontWeight": "bold"},
            ),
        ],
    )

    @callback(
        Output("config-store", "data"),
        Output("validation-messages", "children"),
        Output("source-status", "children"),
        Output("run-scan-btn", "disabled"),
        Input("upload-config", "contents"),
        Input("load-example-btn", "n_clicks"),
        State("upload-config", "filename"),
        prevent_initial_call=True,
    )
    def load_bundle(upload_contents, _load_clicks, filename):
        trigger = ctx.triggered_id
        if trigger not in {"upload-config", "load-example-btn"}:
            raise PreventUpdate

        try:
            if trigger == "upload-config":
                if not upload_contents:
                    raise PreventUpdate
                _, encoded = upload_contents.split(",", 1)
                bundle = load_config_from_excel(base64.b64decode(encoded))
                source_name = filename or bundle.source_name
            else:
                bundle = load_example_config()
                source_name = bundle.source_name
        except PreventUpdate:
            raise
        except Exception as exc:
            message = f"Failed to load configuration: {exc}"
            return None, _issue_list([]), message, True

        has_errors = any(issue.level == "error" for issue in bundle.issues)
        status = f"Loaded configuration from {source_name}."
        if bundle.issues:
            status += f" {len(bundle.issues)} validation message(s)."
        return bundle.to_payload(), _issue_list(bundle.issues), status, has_errors

    @callback(
        Output("scan-store", "data"),
        Output("run-status", "children"),
        Input("run-scan-btn", "n_clicks"),
        State("config-store", "data"),
        prevent_initial_call=True,
    )
    def execute_scan(n_clicks, config_payload):
        if not n_clicks or not config_payload:
            raise PreventUpdate
        bundle = LoadedConfigBundle.from_payload(config_payload)
        scan_result = run_scan(bundle)
        status = (
            f"Deterministic scan completed. "
            f"{len(scan_result.candidates)} feasible candidate(s), best={scan_result.best_candidate_key}."
        )
        return scan_result.to_payload(), status

    @callback(
        Output("candidate-table", "data"),
        Output("candidate-table", "columns"),
        Output("candidate-table", "selected_rows"),
        Input("scan-store", "data"),
    )
    def populate_candidate_table(scan_payload):
        if not scan_payload:
            return [], [], []
        scan_result = ScanRunResult.from_payload(scan_payload)
        table = scan_result.candidates.copy()
        columns = [{"name": column, "id": column} for column in table.columns]
        best_matches = table.index[table["candidate_key"] == scan_result.best_candidate_key].tolist()
        selected_rows = [best_matches[0]] if best_matches else []
        return table.to_dict("records"), columns, selected_rows

    @callback(
        Output("kpi-cards", "children"),
        Output("npv-graph", "figure"),
        Output("monthly-balance-graph", "figure"),
        Output("cash-flow-graph", "figure"),
        Input("scan-store", "data"),
        Input("candidate-table", "selected_rows"),
        State("candidate-table", "data"),
    )
    def refresh_results(scan_payload, selected_rows, table_rows):
        if not scan_payload:
            empty = _empty_figure("Results", "Run a scan to view results.")
            return [], empty, empty, empty

        scan_result = ScanRunResult.from_payload(scan_payload)
        selected_key = scan_result.best_candidate_key
        if selected_rows and table_rows:
            selected_key = table_rows[selected_rows[0]]["candidate_key"]

        detail = scan_result.candidate_details[selected_key]
        kpis = build_kpis(detail)
        monthly_balance = build_monthly_balance(detail["monthly"])
        cash_flow = build_cash_flow(detail["monthly"])
        return (
            _kpi_cards(kpis),
            _build_npv_figure(scan_result.candidates, selected_key),
            _build_monthly_balance_figure(monthly_balance),
            _build_cash_flow_figure(cash_flow),
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
                .page { max-width: 1200px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
                .controls { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; margin-bottom: 1rem; }
                .upload-box { border: 2px dashed #94a3b8; border-radius: 14px; padding: 1rem 1.25rem; background: rgba(255,255,255,0.9); min-width: 300px; }
                .action-btn { border: none; border-radius: 999px; padding: 0.8rem 1.2rem; background: #0f766e; color: white; font-weight: 600; cursor: pointer; }
                .action-btn.secondary { background: #334155; }
                .action-btn:disabled { background: #94a3b8; cursor: not-allowed; }
                .status-line { margin: 0.35rem 0; font-size: 0.95rem; }
                .validation-box { background: rgba(255,255,255,0.85); border-radius: 14px; padding: 1rem; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05); }
                .validation-empty { color: #475569; }
                .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem; margin: 1.5rem 0; }
                .kpi-card { background: white; border-radius: 18px; padding: 1rem; box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08); }
                .kpi-label { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em; color: #475569; }
                .kpi-value { margin-top: 0.45rem; font-size: 1.3rem; font-weight: 700; }
                .link { text-decoration: underline; }
                @media (max-width: 768px) { .page { padding: 1rem 0.8rem 2rem; } .upload-box { min-width: 0; width: 100%; } }
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
