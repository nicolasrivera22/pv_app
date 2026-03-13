from __future__ import annotations

from typing import Any

from dash import html

from services.ui_schema import format_metric, metric_label

def render_kpi_cards(kpis: dict[str, Any], lang: str = "es") -> list[html.Div]:
    keys = [
        "best_kWp",
        "selected_battery",
        "NPV",
        "payback_years",
        "self_consumption_ratio",
        "self_sufficiency_ratio",
    ]
    cards = [
        (metric_label(key, lang), format_metric(key, kpis.get(key), lang))
        for key in keys
    ]
    return [
        html.Div(
            [html.Div(label, className="kpi-label"), html.Div(value, className="kpi-value")],
            className="kpi-card",
        )
        for label, value in cards
    ]
