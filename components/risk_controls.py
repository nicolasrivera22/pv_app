from __future__ import annotations

from dash import dcc, html

from services.i18n import tr


def risk_controls_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.Div(
                className="section-head",
                children=[
                    html.H2(tr("risk.page_title", "es"), id="risk-page-title"),
                    html.Div(
                        className="controls",
                        children=[
                            html.Button(tr("risk.run", "es"), id="risk-run-btn", n_clicks=0, className="action-btn"),
                            html.Button(tr("risk.export_artifacts", "es"), id="risk-export-artifacts-btn", n_clicks=0, className="action-btn tertiary"),
                        ],
                    ),
                ],
            ),
            html.P(tr("risk.page_intro", "es"), id="risk-page-intro"),
            html.P(tr("risk.mode_note", "es"), id="risk-mode-note", className="scenario-meta"),
            html.Div("", id="risk-export-progress", className="status-line", style={"display": "none"}),
            html.Div(
                className="assumption-grid",
                children=[
                    html.Div(
                        className="field-card",
                        children=[
                            html.Label(tr("risk.scenario.label", "es"), id="risk-scenario-label", className="input-label"),
                            dcc.Dropdown(id="risk-scenario-dropdown", placeholder=tr("risk.placeholder.scenario", "es")),
                        ],
                    ),
                    html.Div(
                        className="field-card",
                        children=[
                            html.Label(tr("risk.candidate.label", "es"), id="risk-candidate-label", className="input-label"),
                            dcc.Dropdown(id="risk-candidate-dropdown", placeholder=tr("risk.placeholder.candidate", "es")),
                        ],
                    ),
                    html.Div(
                        className="field-card",
                        children=[
                            html.Label(tr("risk.n_simulations.label", "es"), id="risk-n-simulations-label", className="input-label"),
                            dcc.Input(id="risk-n-simulations-input", type="number", min=1, step=1, value=None, className="text-input"),
                        ],
                    ),
                    html.Div(
                        className="field-card",
                        children=[
                            html.Label(tr("risk.seed.label", "es"), id="risk-seed-label", className="input-label"),
                            dcc.Input(id="risk-seed-input", type="number", min=0, step=1, value=0, className="text-input"),
                            html.Div(tr("risk.seed.help", "es"), id="risk-seed-help", className="scenario-meta"),
                        ],
                    ),
                    html.Div(
                        className="field-card advanced-card",
                        children=[
                            html.Label(tr("risk.retain_samples.label", "es"), id="risk-retain-samples-label", className="input-label"),
                            dcc.Checklist(id="risk-retain-samples", value=[], options=[{"label": tr("risk.retain_samples.option", "es"), "value": "retain"}]),
                            html.Div(tr("risk.retain_samples.help", "es"), id="risk-retain-samples-help", className="scenario-meta"),
                        ],
                    ),
                ],
            ),
            html.Div(tr("risk.validation.none", "es"), id="risk-validation", className="validation-box"),
            html.Div(tr("risk.status.ready", "es"), id="risk-status", className="status-line"),
        ],
    )
