from __future__ import annotations

from typing import Any

from dash import dcc, html
import pandas as pd
import plotly.graph_objects as go

from services.i18n import tr
from services.types import MonteCarloRunResult


def risk_charts_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.H3(id="risk-summary-title"),
            html.Div(id="risk-summary-cards", className="kpi-grid"),
            html.H3(id="risk-distributions-title"),
            html.Div(
                className="chart-grid",
                children=[
                    dcc.Graph(id="risk-npv-histogram"),
                    dcc.Graph(id="risk-npv-ecdf"),
                    dcc.Graph(id="risk-payback-histogram"),
                    dcc.Graph(id="risk-payback-ecdf"),
                ],
            ),
        ],
    )


def _currency(value: float | None) -> str:
    if value is None:
        return "-"
    return f"COP {value:,.0f}"


def _number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}{suffix}"


def _percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{100 * value:,.1f}%"


def render_risk_summary_cards(result: MonteCarloRunResult, lang: str = "en") -> list[html.Div]:
    npv = result.summary.npv
    payback = result.summary.payback_years
    cards = [
        (tr("risk.card.mean_npv", lang), _currency(npv.mean)),
        (tr("risk.card.median_npv", lang), _currency(npv.p50)),
        (tr("risk.card.p5_p95_npv", lang), f"{_currency(npv.p5)} / {_currency(npv.p95)}"),
        (tr("risk.card.prob_negative_npv", lang), _percent(result.risk_metrics.probability_negative_npv)),
        (tr("risk.card.median_payback", lang), _number(payback.p50, tr("risk.value.years_suffix", lang))),
        (tr("risk.card.prob_payback", lang), _percent(result.risk_metrics.probability_payback_within_horizon)),
    ]
    return [
        html.Div(
            [html.Div(label, className="kpi-label"), html.Div(value, className="kpi-value")],
            className="kpi-card",
        )
        for label, value in cards
    ]


def empty_risk_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def build_histogram_figure(frame: pd.DataFrame, *, title: str, x_title: str, lang: str = "en", empty_message: str | None = None) -> go.Figure:
    if frame.empty:
        return empty_risk_figure(title, empty_message or tr("risk.empty.no_result", lang))
    centers = (frame["bin_left"] + frame["bin_right"]) / 2.0
    figure = go.Figure(
        data=[
            go.Bar(
                x=centers,
                y=frame["probability"],
                customdata=frame[["bin_left", "bin_right", "count"]],
                hovertemplate=f"{x_title}: %{{customdata[0]:,.2f}} - %{{customdata[1]:,.2f}}<br>{tr('risk.axis.probability', lang)}: %{{y:.2%}}<br>{tr('risk.axis.count', lang)}: %{{customdata[2]}}<extra></extra>",
            )
        ]
    )
    figure.update_layout(template="plotly_white", title=title)
    figure.update_xaxes(title=x_title)
    figure.update_yaxes(title=tr("risk.axis.probability", lang))
    return figure


def build_ecdf_figure(frame: pd.DataFrame, *, title: str, x_title: str, lang: str = "en", empty_message: str | None = None) -> go.Figure:
    if frame.empty:
        return empty_risk_figure(title, empty_message or tr("risk.empty.no_result", lang))
    figure = go.Figure(
        data=[
            go.Scatter(
                x=frame["value"],
                y=frame["cdf"],
                mode="lines",
                hovertemplate=f"{x_title}: %{{x:,.2f}}<br>{tr('risk.axis.cdf', lang)}: %{{y:.2%}}<extra></extra>",
            )
        ]
    )
    figure.update_layout(template="plotly_white", title=title)
    figure.update_xaxes(title=x_title)
    figure.update_yaxes(title=tr("risk.axis.cdf", lang), range=[0, 1])
    return figure
