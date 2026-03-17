from __future__ import annotations

from typing import Any

from dash import dcc, html
import pandas as pd
import plotly.graph_objects as go

from services.i18n import tr
from services.types import MonteCarloRunResult
from services.ui_schema import format_metric


def _risk_chart_card(*, graph_id: str, description_id: str, description_key: str) -> html.Div:
    return html.Div(
        id=f"{graph_id}-card",
        className="subpanel",
        style={
            "boxSizing": "border-box",
            "minWidth": 0,
            "maxWidth": "100%",
            "overflow": "hidden",
        },
        children=[
            html.P(tr(description_key, "es"), id=description_id, className="scenario-meta", style={"margin": 0}),
            dcc.Graph(id=graph_id, responsive=False, style={"minWidth": 0, "height": "420px"}),
        ],
    )


def risk_charts_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.H3(tr("risk.summary.title", "es"), id="risk-summary-title"),
            html.P(tr("risk.summary.note", "es"), id="risk-summary-note", className="section-copy"),
            html.Div(id="risk-summary-cards", className="kpi-grid"),
            html.H3(tr("risk.distributions.title", "es"), id="risk-distributions-title"),
            html.Div(
                id="risk-chart-stack",
                style={"display": "grid", "gap": "1rem", "width": "100%", "minWidth": 0},
                children=[
                    _risk_chart_card(
                        graph_id="risk-payback-histogram",
                        description_id="risk-payback-histogram-description",
                        description_key="risk.chart.payback_hist.description",
                    ),
                    _risk_chart_card(
                        graph_id="risk-npv-histogram",
                        description_id="risk-npv-histogram-description",
                        description_key="risk.chart.npv_hist.description",
                    ),
                    _risk_chart_card(
                        graph_id="risk-payback-ecdf",
                        description_id="risk-payback-ecdf-description",
                        description_key="risk.chart.payback_ecdf.description",
                    ),
                    _risk_chart_card(
                        graph_id="risk-npv-ecdf",
                        description_id="risk-npv-ecdf-description",
                        description_key="risk.chart.npv_ecdf.description",
                    ),
                ],
            ),
        ],
    )


def render_risk_summary_cards(result: MonteCarloRunResult, lang: str = "en") -> list[html.Div]:
    npv = result.summary.npv
    payback = result.summary.payback_years
    cards = [
        (tr("risk.card.mean_npv", lang), format_metric("NPV_COP", npv.mean, lang)),
        (tr("risk.card.median_npv", lang), format_metric("NPV_COP", npv.p50, lang)),
        (
            tr("risk.card.p5_p95_npv", lang),
            f"{format_metric('NPV_COP', npv.p5, lang)} / {format_metric('NPV_COP', npv.p95, lang)}",
        ),
        (
            tr("risk.card.prob_negative_npv", lang),
            format_metric("self_consumption_ratio", result.risk_metrics.probability_negative_npv, lang),
        ),
        (tr("risk.card.median_payback", lang), format_metric("payback_years", payback.p50, lang)),
        (
            tr("risk.card.prob_payback", lang),
            format_metric("self_consumption_ratio", result.risk_metrics.probability_payback_within_horizon, lang),
        ),
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


def build_histogram_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    x_title: str,
    lang: str = "en",
    empty_message: str | None = None,
    highlight_range: tuple[float, float] | None = None,
    density_frame: pd.DataFrame | None = None,
) -> go.Figure:
    if frame.empty:
        return empty_risk_figure(title, empty_message or tr("risk.empty.no_result", lang))
    centers = (frame["bin_left"] + frame["bin_right"]) / 2.0
    colors = ["#94a3b8"] * len(frame)
    if highlight_range is not None:
        left, right = highlight_range
        for index, row in enumerate(frame.to_dict("records")):
            if not (row["bin_right"] < left or row["bin_left"] > right):
                colors[index] = "#0f766e"
    figure = go.Figure(
        data=[
            go.Bar(
                x=centers,
                y=frame["probability"],
                marker={"color": colors},
                customdata=frame[["bin_left", "bin_right", "count"]],
                hovertemplate=f"{x_title}: %{{customdata[0]:,.2f}} - %{{customdata[1]:,.2f}}<br>{tr('risk.axis.probability', lang)}: %{{y:.2%}}<br>{tr('risk.axis.count', lang)}: %{{customdata[2]}}<extra></extra>",
            )
        ]
    )
    if density_frame is not None and not density_frame.empty:
        width = float((frame["bin_right"] - frame["bin_left"]).mean()) if not frame.empty else 1.0
        figure.add_scatter(
            x=density_frame["value"],
            y=density_frame["density"] * width,
            mode="lines",
            line={"color": "#0f172a", "width": 2},
            name="Curva suave" if lang == "es" else "Smooth curve",
            hovertemplate=f"{x_title}: %{{x:,.2f}}<br>{tr('risk.axis.probability', lang)}: %{{y:.2%}}<extra></extra>",
        )
    figure.update_layout(template="plotly_white", title=title)
    if highlight_range is not None:
        left, right = highlight_range
        figure.add_vrect(x0=left, x1=right, fillcolor="#0f766e", opacity=0.12, line_width=0)
    figure.update_xaxes(title=x_title)
    figure.update_yaxes(title=tr("risk.axis.probability", lang), tickformat=".0%")
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
    figure.update_yaxes(title=tr("risk.axis.cdf", lang), range=[0, 1], tickformat=".0%")
    return figure
