from __future__ import annotations

from typing import Any

DEFAULT_PANEL_TECHNOLOGY_MODE = "standard"

# Yield-only assumption for v1. These factors do not change module wattage,
# panel counts, footprint, stringing, or inverter compatibility semantics.
PANEL_TECHNOLOGY_FACTORS: dict[str, float] = {
    "standard": 1.00,
    "premium": 1.03,
    "tracker_simplified": 1.08,
}

PANEL_TECHNOLOGY_LABELS: dict[str, dict[str, str]] = {
    "standard": {"es": "Estándar", "en": "Standard"},
    "premium": {"es": "Premium", "en": "Premium"},
    "tracker_simplified": {"es": "Tracker simplificado", "en": "Simplified tracker"},
}

PANEL_TECHNOLOGY_FIELD_LABELS: dict[str, str] = {
    "es": "Tecnología de panel",
    "en": "Panel technology",
}


def normalize_panel_technology_mode(value: Any) -> str:
    if isinstance(value, str):
        mode = value.strip().lower()
        if mode in PANEL_TECHNOLOGY_FACTORS:
            return mode
    return DEFAULT_PANEL_TECHNOLOGY_MODE


def panel_technology_factor(mode: Any) -> float:
    normalized = normalize_panel_technology_mode(mode)
    return float(PANEL_TECHNOLOGY_FACTORS[normalized])


def resolve_generation_pr(base_pr: float, mode: Any) -> float:
    return float(base_pr) * panel_technology_factor(mode)


def panel_technology_mode_label(mode: Any, lang: str = "es") -> str:
    normalized = normalize_panel_technology_mode(mode)
    labels = PANEL_TECHNOLOGY_LABELS[normalized]
    return labels.get(lang, labels["es"])


def panel_technology_field_label(lang: str = "es") -> str:
    return PANEL_TECHNOLOGY_FIELD_LABELS.get(lang, PANEL_TECHNOLOGY_FIELD_LABELS["es"])


def panel_technology_options(lang: str = "es") -> tuple[tuple[str, str], ...]:
    return tuple(
        (panel_technology_mode_label(mode, lang), mode)
        for mode in PANEL_TECHNOLOGY_FACTORS
    )
