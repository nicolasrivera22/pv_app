from __future__ import annotations

from typing import Any
import unicodedata

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
    # TODO: tracker_simplified is a practical v1 yield assumption and may later
    # split into a separate tracking or mounting dimension.
    "tracker_simplified": {"es": "Seguidor simplificado", "en": "Simplified tracker"},
}

PANEL_TECHNOLOGY_FIELD_LABELS: dict[str, str] = {
    "es": "Tecnología de panel",
    "en": "Panel technology",
}

PANEL_TECHNOLOGY_CATALOG_LABELS_ES: dict[str, str] = {
    "standard": "estándar",
    "premium": "premium",
    "tracker_simplified": "seguidor simplificado",
}


def _technology_slug(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.strip().lower().replace("_", " ").split())


def _technology_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for mode, labels in PANEL_TECHNOLOGY_LABELS.items():
        aliases[_technology_slug(mode)] = mode
        aliases[_technology_slug(mode.replace("_", " "))] = mode
        for label in labels.values():
            aliases[_technology_slug(label)] = mode
    return aliases


PANEL_TECHNOLOGY_ALIASES = _technology_aliases()


def is_supported_panel_technology_mode(value: Any) -> bool:
    return _technology_slug(value) in PANEL_TECHNOLOGY_ALIASES


def normalize_panel_technology_mode(value: Any) -> str:
    alias = PANEL_TECHNOLOGY_ALIASES.get(_technology_slug(value))
    if alias in PANEL_TECHNOLOGY_FACTORS:
        return alias
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


def panel_technology_catalog_label(mode: Any, lang: str = "es") -> str:
    normalized = normalize_panel_technology_mode(mode)
    if lang == "es":
        return PANEL_TECHNOLOGY_CATALOG_LABELS_ES[normalized]
    return panel_technology_mode_label(normalized, lang)


def panel_technology_options(lang: str = "es") -> tuple[tuple[str, str], ...]:
    return tuple(
        (panel_technology_mode_label(mode, lang), mode)
        for mode in PANEL_TECHNOLOGY_FACTORS
    )
