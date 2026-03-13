from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


def _config_key(item: str) -> str:
    return "bat_coupling" if item == "coupling" else item


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


def extract_config_metadata(config_table: pd.DataFrame, config: dict[str, Any]) -> list[ConfigFieldMeta]:
    if config_table.empty:
        return []

    table = config_table.copy()
    if "Grupo" not in table.columns:
        table["Grupo"] = ""
    table["Grupo"] = table["Grupo"].ffill().fillna("")
    metadata: list[ConfigFieldMeta] = []
    for order, (_, row) in enumerate(table.iterrows()):
        item = str(row.get("Item", "")).strip()
        if not item:
            continue
        config_key = _config_key(item)
        metadata.append(
            ConfigFieldMeta(
                item=item,
                config_key=config_key,
                group=str(row.get("Grupo", "") or "").strip(),
                description=str(row.get("Descripción", "") or "").strip(),
                unit=str(row.get("Unidad", "") or "").strip(),
                order=order,
                value=config.get(config_key, row.get("Valor")),
                supported=config_key in config,
            )
        )
    return metadata


def update_config_table_values(config_table: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if config_table.empty:
        return config_table.copy()

    table = config_table.copy()
    if "Valor" not in table.columns:
        table["Valor"] = ""
    for index, row in table.iterrows():
        item = str(row.get("Item", "")).strip()
        if not item:
            continue
        config_key = _config_key(item)
        if config_key in config:
            table.at[index, "Valor"] = config[config_key]
    return table
