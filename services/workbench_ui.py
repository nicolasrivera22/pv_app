from __future__ import annotations

from typing import Any

import pandas as pd

from .config_metadata import update_config_table_values
from .i18n import tr
from .io_excel import rebuild_config_bundle
from .types import LoadedConfigBundle
from .ui_schema import coerce_config_value


def frame_from_rows(rows: list[dict] | None, columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows or [])
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[columns].copy()


def collect_config_updates(
    input_ids: list[dict] | None,
    input_values: list[Any] | None,
    base_config: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(base_config)
    for component_id, value in zip(input_ids or [], input_values or []):
        field_key = str(component_id.get("field", "")).strip()
        if not field_key:
            continue
        updated[field_key] = coerce_config_value(field_key, value, base_config)
    return updated


def demand_profile_visibility(profile_mode: str) -> dict[str, dict[str, str]]:
    hidden = {"display": "none"}
    shown = {"display": "block"}
    visibility = {
        "demand-profile-panel": hidden,
        "demand-profile-general-panel": hidden,
        "demand-profile-weights-panel": hidden,
    }
    normalized = str(profile_mode or "").strip().lower()
    if normalized == "perfil hora dia de semana":
        visibility["demand-profile-panel"] = shown
    elif normalized == "perfil general":
        visibility["demand-profile-general-panel"] = shown
    else:
        visibility["demand-profile-weights-panel"] = shown
    return visibility


def rebuild_bundle_from_ui(
    base_bundle: LoadedConfigBundle,
    *,
    config_updates: dict[str, Any],
    inverter_catalog: pd.DataFrame,
    battery_catalog: pd.DataFrame,
    demand_profile: pd.DataFrame,
    demand_profile_weights: pd.DataFrame,
    demand_profile_general: pd.DataFrame,
    month_profile: pd.DataFrame,
    sun_profile: pd.DataFrame,
    cop_kwp_table: pd.DataFrame,
    cop_kwp_table_others: pd.DataFrame,
) -> LoadedConfigBundle:
    config_table = update_config_table_values(base_bundle.config_table, config_updates)
    return rebuild_config_bundle(
        base_bundle,
        config=config_updates,
        config_table=config_table,
        inverter_catalog=inverter_catalog,
        battery_catalog=battery_catalog,
        demand_profile=demand_profile,
        demand_profile_weights=demand_profile_weights,
        demand_profile_general=demand_profile_general,
        month_profile=month_profile,
        sun_profile=sun_profile,
        cop_kwp_table=cop_kwp_table,
        cop_kwp_table_others=cop_kwp_table_others,
    )


def workbench_status_message(key: str, lang: str = "es", **kwargs) -> str:
    return tr(key, lang, **kwargs)
