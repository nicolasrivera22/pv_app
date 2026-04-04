from __future__ import annotations

from dash import dcc, html

from .unifilar_diagram import unifilar_diagram_section
from .collapsible_section import collapsible_section
from services.i18n import tr


def selected_candidate_deep_dive_section() -> html.Div:
    return html.Div(
        id="selected-candidate-deep-dive-section",
        className="deep-dive-stack",
        children=[
            collapsible_section(
                section_id="selected-candidate-analysis-section",
                summary_id="selected-candidate-analysis-summary",
                title_id="selected-candidate-deep-dive-title",
                title=tr("workbench.deep_dive.title", "es"),
                open=False,
                title_level="h3",
                variant="primary",
                class_name="panel results-primary-section selected-candidate-analysis-section",
                body_class_name="results-analysis-body",
                body=[
                    html.P(tr("workbench.deep_dive.note", "es"), id="selected-candidate-deep-dive-note", className="section-copy"),
                    html.Div(
                        className="chart-grid",
                        children=[
                            dcc.Graph(id="active-monthly-balance-graph"),
                            dcc.Graph(id="active-cash-flow-graph"),
                        ],
                    ),
                ],
            ),
            unifilar_diagram_section(),
            collapsible_section(
                section_id="selected-candidate-behavior-section",
                summary_id="selected-candidate-behavior-summary",
                title_id="selected-candidate-behavior-title",
                title=tr("workbench.results.behavior.title", "es"),
                open=False,
                title_level="h3",
                variant="primary",
                class_name="panel results-primary-section selected-candidate-behavior-section",
                body_class_name="results-behavior-body",
                body=[
                    html.P(
                        tr("workbench.results.behavior.note", "es"),
                        id="selected-candidate-behavior-note",
                        className="section-copy results-behavior-note",
                    ),
                    html.Div(
                        className="subpanel results-behavior-panel",
                        children=[dcc.Graph(id="active-annual-coverage-graph", style={"height": "380px"})],
                    ),
                    html.Div(
                        className="subpanel results-behavior-panel",
                        children=[dcc.Graph(id="active-typical-day-graph", style={"height": "380px"})],
                    ),
                ],
            ),
        ],
    )
