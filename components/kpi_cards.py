from __future__ import annotations

from typing import Any

from dash import html


def _currency(value: float | None) -> str:
    if value is None:
        return "-"
    return f"COP {value:,.0f}"


def _number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}{suffix}"


def render_kpi_cards(kpis: dict[str, Any]) -> list[html.Div]:
    cards = [
        ("Best kWp", _number(kpis.get("best_kWp"), " kWp")),
        ("Battery", str(kpis.get("selected_battery", "-"))),
        ("NPV", _currency(kpis.get("NPV"))),
        ("Payback", _number(kpis.get("payback_years"), " years")),
        ("Self-consumption", _number(100 * float(kpis.get("self_consumption_ratio", 0.0)), "%")),
        ("Self-sufficiency", _number(100 * float(kpis.get("self_sufficiency_ratio", 0.0)), "%")),
    ]
    return [
        html.Div(
            [html.Div(label, className="kpi-label"), html.Div(value, className="kpi-value")],
            className="kpi-card",
        )
        for label, value in cards
    ]
