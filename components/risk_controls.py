from __future__ import annotations

from dash import dcc, html

from services.i18n import tr
from services.runtime_paths import is_frozen_runtime


def _risk_mc_input(field: dict):
    component_id = {"type": "risk-mc-input", "field": field["field"]}
    kind = field["kind"]
    if kind == "dropdown":
        return dcc.Dropdown(
            id=component_id,
            options=field["options"],
            value=field["value"],
            clearable=False,
            className="text-input",
            disabled=field.get("disabled", False),
        )
    if kind == "number":
        input_control = dcc.Input(
            id=component_id,
            type="number",
            value=field["value"],
            step=field.get("input_step"),
            min=field.get("min"),
            max=field.get("max"),
            className="text-input text-input-affixed" if field.get("suffix") else "text-input",
            disabled=field.get("disabled", False),
        )
        if field.get("suffix"):
            return html.Div(
                className="assumption-input-shell",
                children=[
                    input_control,
                    html.Span(field["suffix"], className="input-affix"),
                ],
            )
        return input_control
    return dcc.Input(
        id=component_id,
        type="text",
        value=field["value"],
        className="text-input",
        disabled=field.get("disabled", False),
    )


def _risk_field_card_class(field: dict) -> str:
    classes = ["field-card"]
    if field.get("disabled"):
        classes.append("field-card-disabled")
    if field.get("emphasize") and not field.get("disabled"):
        classes.append("field-card-highlight")
    return " ".join(dict.fromkeys(classes))


def _risk_mc_field_card(field: dict) -> html.Div:
    help_icon = html.Span(
        className="field-help",
        children=[
            html.Span("ⓘ", className="field-help-trigger", tabIndex=0),
            html.Span(field["help"], className="field-help-tooltip"),
        ],
    )
    return html.Div(
        id={"type": "risk-mc-field-card", "field": field["field"]},
        className=_risk_field_card_class(field),
        children=[
            html.Label([field["label"], help_icon], className="input-label"),
            _risk_mc_input(field),
        ],
    )


def render_risk_monte_carlo_fields(fields: list[dict], *, empty_message: str) -> list[html.Div]:
    if not fields:
        return [html.Div(className="validation-empty", children=empty_message)]
    return [_risk_mc_field_card(field) for field in fields]


def risk_controls_section() -> html.Div:
    open_button_style = {} if is_frozen_runtime() else {"display": "none"}
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
                            html.Button(
                                tr("common.open_exports_folder", "es"),
                                id="risk-open-exports-btn",
                                n_clicks=0,
                                className="action-btn tertiary",
                                disabled=True,
                                style=open_button_style,
                            ),
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
            html.Div(
                className="subpanel",
                children=[
                    html.H4(tr("risk.monte_carlo_settings.title", "es"), id="risk-monte-carlo-title"),
                    html.P(tr("risk.monte_carlo_settings.help", "es"), id="risk-monte-carlo-help", className="section-copy section-copy-wide"),
                    html.Div(id="risk-monte-carlo-fields", className="assumption-grid"),
                ],
            ),
            html.Div(tr("risk.validation.none", "es"), id="risk-validation", className="validation-box"),
            html.Div(tr("risk.status.ready", "es"), id="risk-status", className="status-line"),
        ],
    )
