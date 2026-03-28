from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pv_product.panel_catalog import MANUAL_PANEL_TOKEN, canonical_panel_name

ECONOMICS_ITEM_COLUMNS = ["stage", "name", "calculation_method", "value", "enabled", "notes"]
ECONOMICS_COST_COLUMNS = list(ECONOMICS_ITEM_COLUMNS)
ECONOMICS_PRICE_COLUMNS = list(ECONOMICS_ITEM_COLUMNS)

ECONOMICS_COST_PERCENT_METHODS = {"pct_of_technical_subtotal", "pct_of_running_subtotal"}
ECONOMICS_PRICE_PERCENT_METHODS = {"markup_pct", "discount_pct", "tax_pct"}


def default_economics_cost_items_rows() -> list[dict[str, Any]]:
    return [
        {"stage": "technical_cost", "name": "Panel hardware", "calculation_method": "per_panel", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "technical_cost", "name": "Inverter hardware", "calculation_method": "per_inverter", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "technical_cost", "name": "Battery hardware", "calculation_method": "per_battery_kwh", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "technical_cost", "name": "BOS", "calculation_method": "per_kwp", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed_cost", "name": "Engineering", "calculation_method": "fixed_project", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed_cost", "name": "Installation labor", "calculation_method": "per_kwp", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed_cost", "name": "Logistics", "calculation_method": "fixed_project", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed_cost", "name": "Contingency", "calculation_method": "pct_of_running_subtotal", "value": 0.0, "enabled": True, "notes": ""},
    ]


def default_economics_price_items_rows() -> list[dict[str, Any]]:
    return [
        {"stage": "commercial_offer", "name": "Commercial margin", "calculation_method": "markup_pct", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "final_sale_price", "name": "Customer discount", "calculation_method": "discount_pct", "value": 0.0, "enabled": True, "notes": ""},
        {"stage": "final_sale_price", "name": "Taxes", "calculation_method": "tax_pct", "value": 0.0, "enabled": True, "notes": ""},
    ]


def empty_economics_cost_items_table() -> pd.DataFrame:
    return pd.DataFrame(columns=ECONOMICS_COST_COLUMNS)


def empty_economics_price_items_table() -> pd.DataFrame:
    return pd.DataFrame(columns=ECONOMICS_PRICE_COLUMNS)


def default_economics_cost_items_table() -> pd.DataFrame:
    return pd.DataFrame(default_economics_cost_items_rows(), columns=ECONOMICS_COST_COLUMNS)


def default_economics_price_items_table() -> pd.DataFrame:
    return pd.DataFrame(default_economics_price_items_rows(), columns=ECONOMICS_PRICE_COLUMNS)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _strip_text(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _coerce_enabled(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if _is_missing(value):
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "si", "sí", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _coerce_numeric(value: Any) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1].strip()
        if cleaned == "":
            return None
        value = cleaned
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_frame(
    source: pd.DataFrame | list[dict[str, Any]] | None,
    *,
    columns: list[str],
    percent_methods: set[str],
    editor_values: bool,
) -> pd.DataFrame:
    if source is None:
        return pd.DataFrame(columns=columns)
    frame = source.copy() if isinstance(source, pd.DataFrame) else pd.DataFrame(source)
    for column in columns:
        if column not in frame.columns:
            frame[column] = np.nan
    frame = frame[columns].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame[columns] = frame[columns].replace(r"^\s*$", np.nan, regex=True)
    frame = frame.loc[~frame[columns].isna().all(axis=1)].reset_index(drop=True)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame = frame.astype(object)

    for index in frame.index:
        method = _strip_text(frame.at[index, "calculation_method"])
        value = _coerce_numeric(frame.at[index, "value"])
        if value is not None and method in percent_methods:
            if editor_values:
                value = value / 100.0 if abs(value) > 1.0 else value
            else:
                value = value * 100.0
        frame.at[index, "stage"] = _strip_text(frame.at[index, "stage"])
        frame.at[index, "name"] = _strip_text(frame.at[index, "name"])
        frame.at[index, "calculation_method"] = method
        frame.at[index, "value"] = value
        frame.at[index, "enabled"] = _coerce_enabled(frame.at[index, "enabled"])
        frame.at[index, "notes"] = _strip_text(frame.at[index, "notes"])
    return frame[columns].copy()


def normalize_economics_cost_items_frame(frame: pd.DataFrame | list[dict[str, Any]] | None) -> pd.DataFrame:
    return _normalize_frame(
        frame,
        columns=ECONOMICS_COST_COLUMNS,
        percent_methods=ECONOMICS_COST_PERCENT_METHODS,
        editor_values=True,
    )


def normalize_economics_price_items_frame(frame: pd.DataFrame | list[dict[str, Any]] | None) -> pd.DataFrame:
    return _normalize_frame(
        frame,
        columns=ECONOMICS_PRICE_COLUMNS,
        percent_methods=ECONOMICS_PRICE_PERCENT_METHODS,
        editor_values=True,
    )


def economics_cost_items_rows_to_editor(frame: pd.DataFrame | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return _normalize_frame(
        frame,
        columns=ECONOMICS_COST_COLUMNS,
        percent_methods=ECONOMICS_COST_PERCENT_METHODS,
        editor_values=False,
    ).to_dict("records")


def economics_price_items_rows_to_editor(frame: pd.DataFrame | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return _normalize_frame(
        frame,
        columns=ECONOMICS_PRICE_COLUMNS,
        percent_methods=ECONOMICS_PRICE_PERCENT_METHODS,
        editor_values=False,
    ).to_dict("records")


def economics_cost_items_rows_from_editor(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return normalize_economics_cost_items_frame(rows).to_dict("records")


def economics_price_items_rows_from_editor(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return normalize_economics_price_items_frame(rows).to_dict("records")


def _positive_numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    numeric = pd.to_numeric(frame[column], errors="coerce")
    return numeric.loc[numeric > 0].dropna()


def _median_or_zero(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(series.median())


def _selected_or_catalog_panel_price(config: dict[str, Any], panel_catalog: pd.DataFrame) -> float:
    if panel_catalog.empty:
        return 0.0
    numeric_prices = _positive_numeric_series(panel_catalog, "price_COP")
    selected_name = canonical_panel_name(config.get("panel_name"))
    if selected_name and selected_name != canonical_panel_name(MANUAL_PANEL_TOKEN) and {"name", "price_COP"}.issubset(panel_catalog.columns):
        for row in panel_catalog.to_dict("records"):
            if canonical_panel_name(row.get("name")) != selected_name:
                continue
            price = _coerce_numeric(row.get("price_COP"))
            if price is not None and price > 0:
                return float(price)
            break
    return _median_or_zero(numeric_prices)


def seed_hardware_cost_rows_from_catalogs(
    cost_items: pd.DataFrame | list[dict[str, Any]] | None,
    *,
    config: dict[str, Any],
    inverter_catalog: pd.DataFrame,
    battery_catalog: pd.DataFrame,
    panel_catalog: pd.DataFrame,
) -> pd.DataFrame:
    frame = normalize_economics_cost_items_frame(cost_items)
    if frame.empty:
        frame = default_economics_cost_items_table()

    panel_price = _selected_or_catalog_panel_price(config, panel_catalog)
    inverter_price = _median_or_zero(_positive_numeric_series(inverter_catalog, "price_COP"))

    battery_frame = battery_catalog.copy()
    if battery_frame.empty or not {"price_COP", "nom_kWh"}.issubset(battery_frame.columns):
        battery_unit_price = 0.0
    else:
        battery_frame["price_COP"] = pd.to_numeric(battery_frame["price_COP"], errors="coerce")
        battery_frame["nom_kWh"] = pd.to_numeric(battery_frame["nom_kWh"], errors="coerce")
        battery_frame = battery_frame.loc[(battery_frame["price_COP"] > 0) & (battery_frame["nom_kWh"] > 0)].copy()
        battery_unit_price = _median_or_zero(battery_frame["price_COP"] / battery_frame["nom_kWh"]) if not battery_frame.empty else 0.0

    updates = {
        "Panel hardware": ("technical_cost", "per_panel", panel_price),
        "Inverter hardware": ("technical_cost", "per_inverter", inverter_price),
        "Battery hardware": ("technical_cost", "per_battery_kwh", battery_unit_price),
    }

    names = frame["name"].astype(str).str.strip().tolist()
    for name, (stage, calculation_method, value) in updates.items():
        if name in names:
            index = names.index(name)
            frame.at[index, "stage"] = stage
            frame.at[index, "calculation_method"] = calculation_method
            frame.at[index, "value"] = float(value)
            frame.at[index, "enabled"] = _coerce_enabled(frame.at[index, "enabled"])
            continue
        frame.loc[len(frame)] = {
            "stage": stage,
            "name": name,
            "calculation_method": calculation_method,
            "value": float(value),
            "enabled": True,
            "notes": "",
        }
        names.append(name)
    return frame[ECONOMICS_COST_COLUMNS].reset_index(drop=True)
