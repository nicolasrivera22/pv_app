from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .panel_technology import (
    DEFAULT_PANEL_TECHNOLOGY_MODE,
    panel_technology_catalog_label,
    normalize_panel_technology_mode,
)
from .utils import DEFAULT_CONFIG

MANUAL_PANEL_TOKEN = "__manual__"
DEFAULT_BASELINE_PANEL_NAME = "BASE-600W Standard"

PANEL_SELECTION_MANUAL = "manual"
PANEL_SELECTION_CATALOG = "catalog"
PANEL_SELECTION_INVALID = "invalid"

PANEL_CATALOG_COLUMNS: tuple[str, ...] = (
    "name",
    "P_mod_W",
    "Voc25",
    "Vmp25",
    "Isc",
    "length_m",
    "width_m",
    "panel_technology_mode",
    "price_COP",
)

PANEL_DERIVED_CONFIG_FIELDS: tuple[str, ...] = (
    "P_mod_W",
    "Voc25",
    "Vmp25",
    "Isc",
    "panel_technology_mode",
)

PANEL_MANUAL_LABELS: dict[str, str] = {
    "es": "Configurar manualmente",
    "en": "Configure manually",
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def canonical_panel_name(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip().casefold()


def normalize_panel_name(value: Any) -> str:
    if _is_missing(value):
        return MANUAL_PANEL_TOKEN
    normalized = str(value).strip()
    if canonical_panel_name(normalized) == MANUAL_PANEL_TOKEN:
        return MANUAL_PANEL_TOKEN
    if normalized.startswith("__") or normalized.endswith("__"):
        return MANUAL_PANEL_TOKEN
    return normalized


def manual_panel_label(lang: str = "es") -> str:
    return PANEL_MANUAL_LABELS.get(lang, PANEL_MANUAL_LABELS["es"])


def manual_panel_option(lang: str = "es") -> tuple[str, str]:
    return manual_panel_label(lang), MANUAL_PANEL_TOKEN


def default_panel_catalog_rows() -> list[dict[str, Any]]:
    return [
        {
            "name": DEFAULT_BASELINE_PANEL_NAME,
            "P_mod_W": float(DEFAULT_CONFIG["P_mod_W"]),
            "Voc25": float(DEFAULT_CONFIG["Voc25"]),
            "Vmp25": float(DEFAULT_CONFIG["Vmp25"]),
            "Isc": float(DEFAULT_CONFIG["Isc"]),
            "length_m": 2.278,
            "width_m": 1.134,
            "panel_technology_mode": panel_technology_catalog_label(DEFAULT_CONFIG["panel_technology_mode"], "es"),
            "price_COP": 620_000.0,
        },
        {
            "name": "PREM-620 Premium",
            "P_mod_W": 620.0,
            "Voc25": 52.0,
            "Vmp25": 43.0,
            "Isc": 14.4,
            "length_m": 2.384,
            "width_m": 1.303,
            "panel_technology_mode": panel_technology_catalog_label("premium", "es"),
            "price_COP": 710_000.0,
        },
        {
            "name": "TRACK-600 Simplified",
            "P_mod_W": 600.0,
            "Voc25": 50.0,
            "Vmp25": 41.0,
            "Isc": 14.0,
            "length_m": 2.278,
            "width_m": 1.134,
            "panel_technology_mode": panel_technology_catalog_label("tracker_simplified", "es"),
            "price_COP": 660_000.0,
        },
    ]


def default_panel_catalog_frame() -> pd.DataFrame:
    return pd.DataFrame(default_panel_catalog_rows(), columns=list(PANEL_CATALOG_COLUMNS))


def panel_catalog_options(panel_catalog: pd.DataFrame, *, lang: str = "es") -> tuple[tuple[str, str], ...]:
    options: list[tuple[str, str]] = [manual_panel_option(lang)]
    if panel_catalog.empty or "name" not in panel_catalog.columns:
        return tuple(options)
    seen: set[str] = set()
    for raw_name in panel_catalog["name"].tolist():
        name = str(raw_name).strip()
        canonical = canonical_panel_name(name)
        if not name or canonical in seen or canonical == canonical_panel_name(MANUAL_PANEL_TOKEN):
            continue
        seen.add(canonical)
        options.append((name, name))
    return tuple(options)


@dataclass(frozen=True)
class PanelSelectionResolution:
    selection_mode: str
    normalized_panel_name: str
    selected_panel_name: str | None
    panel_row: dict[str, Any] | None
    effective_fields: dict[str, Any]
    panel_area_m2: float | None
    error_message: str | None = None


def _catalog_row_lookup(panel_catalog: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if panel_catalog.empty:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for row in panel_catalog.to_dict("records"):
        canonical = canonical_panel_name(row.get("name"))
        if not canonical or canonical in lookup:
            continue
        lookup[canonical] = dict(row)
    return lookup


def resolve_selected_panel(config: dict[str, Any], panel_catalog: pd.DataFrame) -> PanelSelectionResolution:
    # Panel rows own module/electrical specs and panel-side technology mode.
    # System-level PR stays outside the catalog as a separate assumption.
    normalized_panel_name = normalize_panel_name(config.get("panel_name"))
    manual_fields = {
        "P_mod_W": config.get("P_mod_W"),
        "Voc25": config.get("Voc25"),
        "Vmp25": config.get("Vmp25"),
        "Isc": config.get("Isc"),
        "panel_technology_mode": normalize_panel_technology_mode(config.get("panel_technology_mode")),
    }
    if normalized_panel_name == MANUAL_PANEL_TOKEN:
        return PanelSelectionResolution(
            selection_mode=PANEL_SELECTION_MANUAL,
            normalized_panel_name=MANUAL_PANEL_TOKEN,
            selected_panel_name=None,
            panel_row=None,
            effective_fields=manual_fields,
            panel_area_m2=None,
        )

    row = _catalog_row_lookup(panel_catalog).get(canonical_panel_name(normalized_panel_name))
    if row is None:
        return PanelSelectionResolution(
            selection_mode=PANEL_SELECTION_INVALID,
            normalized_panel_name=normalized_panel_name,
            selected_panel_name=None,
            panel_row=None,
            effective_fields=manual_fields,
            panel_area_m2=None,
            error_message="panel_name no existe en el catálogo de paneles.",
        )

    length_m = float(row["length_m"])
    width_m = float(row["width_m"])
    return PanelSelectionResolution(
        selection_mode=PANEL_SELECTION_CATALOG,
        normalized_panel_name=normalized_panel_name,
        selected_panel_name=str(row["name"]).strip(),
        panel_row=row,
        effective_fields={
            "P_mod_W": float(row["P_mod_W"]),
            "Voc25": float(row["Voc25"]),
            "Vmp25": float(row["Vmp25"]),
            "Isc": float(row["Isc"]),
            "panel_technology_mode": normalize_panel_technology_mode(row.get("panel_technology_mode")),
        },
        # Explainability-only metadata in this phase. This must not change scan
        # bounds, packing, or any hidden feasibility filters.
        panel_area_m2=length_m * width_m,
    )


def apply_panel_selection(config: dict[str, Any], panel_catalog: pd.DataFrame) -> tuple[dict[str, Any], PanelSelectionResolution]:
    resolved = resolve_selected_panel(config, panel_catalog)
    effective_config = dict(config)
    effective_config["panel_name"] = resolved.normalized_panel_name
    if resolved.panel_area_m2 is not None:
        effective_config["panel_area_m2"] = float(resolved.panel_area_m2)
    else:
        effective_config.pop("panel_area_m2", None)
    if resolved.selection_mode == PANEL_SELECTION_CATALOG:
        for key, value in resolved.effective_fields.items():
            effective_config[key] = value
    return effective_config, resolved
