from __future__ import annotations

from dash import dash_table, dcc, html

from services.i18n import tr
from services.runtime_paths import is_frozen_runtime


def candidate_explorer_section() -> html.Div:
    open_button_style = {} if is_frozen_runtime() else {"display": "none"}
    return html.Div(
        id="candidate-selection-section",
        className="panel",
        children=[
            html.Div(
                className="section-head",
                children=[
                    html.H3(tr("workbench.candidate_explorer", "es"), id="candidate-explorer-title"),
                    html.Div(
                        className="controls",
                        children=[
                            html.Button(tr("workbench.export_scenario", "es"), id="scenario-export-btn", n_clicks=0, className="action-btn secondary"),
                            html.Button(tr("common.export_artifacts", "es"), id="scenario-artifacts-btn", n_clicks=0, className="action-btn tertiary"),
                            html.Button(
                                tr("common.open_exports_folder", "es"),
                                id="scenario-open-exports-btn",
                                n_clicks=0,
                                className="action-btn tertiary",
                                disabled=True,
                                style=open_button_style,
                            ),
                        ],
                    ),
                ],
            ),
            html.Div("", id="scenario-artifacts-progress", className="status-line", style={"display": "none"}),
            html.P(tr("workbench.export.note", "es"), id="candidate-export-note", className="section-copy"),
            html.P(tr("workbench.candidate_explorer.intro", "es"), id="candidate-explorer-intro", className="section-copy"),
            html.Div(tr("workbench.selected_design.summary", "es"), id="selected-candidate-kpi-title", className="selected-candidate-kpi-title"),
            html.Div(id="active-kpi-cards", className="kpi-grid"),
            dcc.Graph(id="active-npv-graph"),
            html.P(
                tr("workbench.candidate_selection.helper", "es"),
                id="candidate-selection-helper",
                className="section-copy candidate-selection-helper",
            ),
            html.Div(id="selected-candidate-banner", className="selected-candidate-banner"),
            dash_table.DataTable(
                id="active-candidate-table",
                data=[],
                columns=[],
                row_selectable="single",
                selected_rows=[],
                hidden_columns=["candidate_key", "scan_order", "best_battery_for_kwp"],
                sort_action="native",
                filter_action="native",
                page_size=12,
                style_table={"overflowX": "auto"},
                style_cell={"padding": "0.45rem", "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": 12},
                style_header={"backgroundColor": "#e2e8f0", "fontWeight": "bold"},
                tooltip_delay=0,
                tooltip_duration=None,
                tooltip_header={},
            ),
        ],
    )
