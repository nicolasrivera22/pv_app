from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from pv_product.panel_catalog import (
    MANUAL_PANEL_TOKEN,
    PANEL_DERIVED_CONFIG_FIELDS,
    normalize_panel_name,
    resolve_selected_panel,
)
from pv_product.panel_technology import (
    DEFAULT_PANEL_TECHNOLOGY_MODE,
    normalize_panel_technology_mode,
)

_PANEL_TECHNOLOGY_ITEM = "panel_technology_mode"
_PANEL_NAME_ITEM = "panel_name"
_PANEL_GROUP = "Sol y módulos"
_PANEL_TECHNOLOGY_DESCRIPTION = (
    "Supuesto simple de tecnología del panel; solo ajusta el rendimiento de generación."
)
_PANEL_NAME_DESCRIPTION = (
    "Modelo de panel seleccionado para el escenario. Usa el catálogo o cambia a configuración manual."
)
_PANEL_COMPATIBILITY_DESCRIPTIONS: dict[str, str] = {
    "P_mod_W": "Potencia nominal del módulo usada por el escenario.",
    "Voc25": "Voltaje de circuito abierto del módulo a 25 °C.",
    "Vmp25": "Voltaje de máxima potencia del módulo a 25 °C.",
    "Isc": "Corriente de cortocircuito del módulo.",
    "panel_technology_mode": _PANEL_TECHNOLOGY_DESCRIPTION,
}


def _config_key(item: str) -> str:
    return "bat_coupling" if item == "coupling" else item


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _ensure_config_columns(config_table: pd.DataFrame) -> pd.DataFrame:
    table = config_table.copy()
    for column in ("Grupo", "Descripción", "Item", "Valor", "Unidad"):
        if column not in table.columns:
            table[column] = ""
    return table


@dataclass(frozen=True)
class ConfigFieldMeta:
    item: str
    config_key: str
    group: str
    description: str
    unit: str
    order: int
    value: Any
    supported: bool


def _panel_technology_row(config: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    row = {column: "" for column in columns}
    row["Grupo"] = _PANEL_GROUP
    row["Descripción"] = _PANEL_TECHNOLOGY_DESCRIPTION
    row["Item"] = _PANEL_TECHNOLOGY_ITEM
    row["Valor"] = normalize_panel_technology_mode(
        config.get(_PANEL_TECHNOLOGY_ITEM, DEFAULT_PANEL_TECHNOLOGY_MODE)
    )
    row["Unidad"] = ""
    return row


def _panel_name_row(config: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    row = {column: "" for column in columns}
    row["Grupo"] = _PANEL_GROUP
    row["Descripción"] = _PANEL_NAME_DESCRIPTION
    row["Item"] = _PANEL_NAME_ITEM
    row["Valor"] = normalize_panel_name(config.get(_PANEL_NAME_ITEM, MANUAL_PANEL_TOKEN))
    row["Unidad"] = ""
    return row


def _compatibility_row(item: str, value: Any, columns: list[str]) -> dict[str, Any]:
    row = {column: "" for column in columns}
    row["Grupo"] = _PANEL_GROUP
    row["Descripción"] = _PANEL_COMPATIBILITY_DESCRIPTIONS.get(item, "")
    row["Item"] = item
    row["Valor"] = value
    row["Unidad"] = ""
    return row


def _insert_row(
    table: pd.DataFrame,
    row: dict[str, Any],
    *,
    insert_after_items: tuple[str, ...] = (),
    insert_before_items: tuple[str, ...] = (),
) -> pd.DataFrame:
    items = table["Item"].map(_safe_text)
    insert_at = len(table)
    for item in insert_before_items:
        matches = items[items == item].index.tolist()
        if matches:
            insert_at = matches[0]
            break
    else:
        for item in insert_after_items:
            matches = items[items == item].index.tolist()
            if matches:
                insert_at = matches[-1] + 1
    row_frame = pd.DataFrame([row], columns=table.columns)
    return pd.concat([table.iloc[:insert_at], row_frame, table.iloc[insert_at:]], ignore_index=True)


def _table_with_virtual_panel_rows(
    config_table: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    if config_table.empty:
        return config_table.copy()

    table = _ensure_config_columns(config_table)
    items = table["Item"].map(_safe_text)
    if not (items == _PANEL_TECHNOLOGY_ITEM).any():
        table = _insert_row(
            table,
            _panel_technology_row(config, list(table.columns)),
            insert_after_items=("PR",),
        )
        items = table["Item"].map(_safe_text)
    if not (items == _PANEL_NAME_ITEM).any():
        table = _insert_row(
            table,
            _panel_name_row(config, list(table.columns)),
            insert_after_items=(_PANEL_TECHNOLOGY_ITEM, "PR"),
            insert_before_items=("P_mod_W", "Voc25", "Vmp25", "Isc"),
        )
    return table


def extract_config_metadata(config_table: pd.DataFrame, config: dict[str, Any]) -> list[ConfigFieldMeta]:
    if config_table.empty:
        return []

    table = _table_with_virtual_panel_rows(config_table, config)
    if "Grupo" not in table.columns:
        table["Grupo"] = ""
    table["Grupo"] = table["Grupo"].ffill().fillna("")
    metadata: list[ConfigFieldMeta] = []
    for order, (_, row) in enumerate(table.iterrows()):
        item = _safe_text(row.get("Item", ""))
        if not item:
            continue
        config_key = _config_key(item)
        metadata.append(
            ConfigFieldMeta(
                item=item,
                config_key=config_key,
                group=_safe_text(row.get("Grupo", "")),
                description=_safe_text(row.get("Descripción", "")),
                unit=_safe_text(row.get("Unidad", "")),
                order=order,
                value=config.get(config_key, row.get("Valor")),
                supported=config_key in config,
            )
        )
    return metadata


def materialize_panel_config_rows(
    config_table: pd.DataFrame,
    config: dict[str, Any],
    panel_catalog: pd.DataFrame,
) -> pd.DataFrame:
    table = _table_with_virtual_panel_rows(config_table, config)
    if table.empty:
        return table

    table = update_config_table_values(table, config)
    resolution = resolve_selected_panel(config, panel_catalog)
    if resolution.selection_mode != "catalog":
        return table

    items = table["Item"].map(_safe_text)
    for item in PANEL_DERIVED_CONFIG_FIELDS:
        value = resolution.effective_fields[item]
        matches = items[items == item].index.tolist()
        if matches:
            table.at[matches[0], "Valor"] = value
            continue
        table = _insert_row(
            table,
            _compatibility_row(item, value, list(table.columns)),
            insert_after_items=(_PANEL_NAME_ITEM,),
            insert_before_items=("a_Voc_pct", "ILR_min", "ILR_max"),
        )
        items = table["Item"].map(_safe_text)
    return table


def update_config_table_values(config_table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if config_table.empty:
        return config_table.copy()

    table = config_table.copy()
    if "Valor" not in table.columns:
        table["Valor"] = ""
    else:
        table["Valor"] = table["Valor"].astype(object)
    for index, row in table.iterrows():
        item = str(row.get("Item", "")).strip()
        if not item:
            continue
        config_key = _config_key(item)
        if config_key in config:
            table.at[index, "Valor"] = config[config_key]
    return table
