from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from pv_product.panel_technology import (
    DEFAULT_PANEL_TECHNOLOGY_MODE,
    normalize_panel_technology_mode,
)

_PANEL_TECHNOLOGY_ITEM = "panel_technology_mode"
_PANEL_TECHNOLOGY_GROUP = "Sol y módulos"
_PANEL_TECHNOLOGY_DESCRIPTION = (
    "Supuesto simple de tecnología del panel; solo ajusta el rendimiento de generación."
)


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
    row["Grupo"] = _PANEL_TECHNOLOGY_GROUP
    row["Descripción"] = _PANEL_TECHNOLOGY_DESCRIPTION
    row["Item"] = _PANEL_TECHNOLOGY_ITEM
    row["Valor"] = normalize_panel_technology_mode(
        config.get(_PANEL_TECHNOLOGY_ITEM, DEFAULT_PANEL_TECHNOLOGY_MODE)
    )
    row["Unidad"] = ""
    return row


def _table_with_virtual_panel_technology_row(
    config_table: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    if config_table.empty:
        return config_table.copy()

    table = config_table.copy()
    for column in ("Grupo", "Descripción", "Item", "Valor", "Unidad"):
        if column not in table.columns:
            table[column] = ""

    items = table["Item"].map(_safe_text)
    if (items == _PANEL_TECHNOLOGY_ITEM).any():
        return table

    insert_after = items[items == "PR"].index.tolist()
    insert_at = insert_after[0] + 1 if insert_after else len(table)
    row = pd.DataFrame([_panel_technology_row(config, list(table.columns))], columns=table.columns)
    return pd.concat([table.iloc[:insert_at], row, table.iloc[insert_at:]], ignore_index=True)


def extract_config_metadata(config_table: pd.DataFrame, config: dict[str, Any]) -> list[ConfigFieldMeta]:
    if config_table.empty:
        return []

    table = _table_with_virtual_panel_technology_row(config_table, config)
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


def materialize_panel_technology_mode_row(config_table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    return _table_with_virtual_panel_technology_row(config_table, config)


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
