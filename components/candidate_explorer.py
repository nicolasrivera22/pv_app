from __future__ import annotations

from dash import dash_table, dcc, html

from services.i18n import tr
from services.runtime_paths import is_frozen_runtime

from .collapsible_section import collapsible_section


def candidate_explorer_section() -> html.Details:
    open_button_style = {} if is_frozen_runtime() else {"display": "none"}
    return collapsible_section(
        section_id="candidate-selection-section",
        summary_id="candidate-selection-summary",
        title_id="candidate-explorer-title",
        title=tr("workbench.candidate_explorer", "es"),
        open=True,
        title_level="h3",
        variant="primary",
        class_name="panel results-primary-section results-explorer-section",
        body_class_name="results-explorer-body",
        body=[
            html.Div(
                className="controls results-explorer-actions",
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
            html.Div("", id="scenario-artifacts-progress", className="status-line", style={"display": "none"}),
            html.P(tr("workbench.export.note", "es"), id="candidate-export-note", className="section-copy section-copy-wide"),
            html.P(tr("workbench.candidate_explorer.intro", "es"), id="candidate-explorer-intro", className="section-copy section-copy-wide"),
            html.Div(id="scan-summary-strip", className="scan-summary-strip"),
            html.Div(tr("workbench.selected_design.summary", "es"), id="selected-candidate-kpi-title", className="selected-candidate-kpi-title"),
            html.Div(id="active-kpi-cards", className="kpi-grid"),
            html.Div(
                id="candidate-horizon-shell",
                className="candidate-horizon-shell",
                children=[
                    html.Div(
                        id="candidate-horizon-toolbar",
                        className="candidate-horizon-toolbar",
                        style={"display": "none"},
                        children=[
                            html.Div(
                                className="candidate-explorer-toolbar-grid",
                                children=[
                                    html.Div(
                                        className="candidate-horizon-control",
                                        children=[
                                            html.Div(
                                                className="candidate-horizon-head",
                                                children=[
                                                    html.Label(
                                                        tr("workbench.horizon.label", "es"),
                                                        id="candidate-horizon-label",
                                                        className="candidate-horizon-label",
                                                        htmlFor="candidate-horizon-slider",
                                                    ),
                                                    html.Span("", id="candidate-horizon-value", className="candidate-horizon-value"),
                                                ],
                                            ),
                                            dcc.Slider(
                                                id="candidate-horizon-slider",
                                                min=1,
                                                max=1,
                                                step=1,
                                                value=1,
                                                marks={1: "1"},
                                                disabled=True,
                                                updatemode="drag",
                                            ),
                                            html.P(
                                                tr("workbench.horizon.helper", "es"),
                                                id="candidate-horizon-helper",
                                                className="candidate-horizon-helper",
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="candidate-family-control",
                                        children=[
                                            html.Label(
                                                tr("workbench.explorer.family.label", "es"),
                                                id="results-battery-family-label",
                                                className="candidate-horizon-label",
                                                htmlFor="results-battery-family-dropdown",
                                            ),
                                            dcc.Dropdown(
                                                id="results-battery-family-dropdown",
                                                options=[],
                                                value=None,
                                                clearable=False,
                                                disabled=True,
                                                className="candidate-family-dropdown",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.P(
                                "",
                                id="results-battery-family-helper",
                                className="candidate-family-helper",
                            ),
                        ],
                    ),
                    dcc.Graph(id="active-npv-graph"),
                ],
            ),
            html.P("", id="scan-discard-explainer", className="section-copy scan-discard-explainer", style={"display": "none"}),
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
                hidden_columns=[
                    "candidate_key",
                    "scan_order",
                    "best_battery_for_kwp",
                    "battery_family_key",
                    "battery_family_label",
                    "battery_kwh",
                ],
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
