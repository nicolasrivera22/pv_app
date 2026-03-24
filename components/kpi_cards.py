from __future__ import annotations

from typing import Any

from dash import html

from services.ui_schema import format_metric, metric_label

def render_kpi_cards(
    kpis: dict[str, Any],
    lang: str = "es",
    *,
    label_overrides: dict[str, str] | None = None,
    notes: dict[str, str] | None = None,
) -> list[html.Div]:
    keys = [
        "best_kWp",
        "selected_battery",
        "NPV",
        "payback_years",
        "self_consumption_ratio",
        "self_sufficiency_ratio",
    ]
    labels = label_overrides or {}
    card_notes = notes or {}
    return [
        html.Div(
            [
                child
                for child in (
                    html.Div(labels.get(key, metric_label(key, lang)), className="kpi-label"),
                    html.Div(format_metric(key, kpis.get(key), lang), className="kpi-value"),
                    html.Div(card_notes[key], className="kpi-note") if card_notes.get(key) else None,
                )
                if child is not None
            ],
            className="kpi-card",
        )
        for key in keys
    ]
