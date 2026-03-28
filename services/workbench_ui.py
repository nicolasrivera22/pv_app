from __future__ import annotations

from typing import Any

import pandas as pd

from .config_metadata import update_config_table_values
from .i18n import tr
from .io_excel import rebuild_config_bundle
from .types import LoadedConfigBundle
from .ui_schema import coerce_config_value, parse_assumption_input_value
from .validation import (
    normalize_battery_catalog_rows,
    normalize_inverter_catalog_rows,
    normalize_panel_catalog_rows,
    normalize_price_table_rows,
    refresh_bundle_issues,
)


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
        updated[field_key] = coerce_config_value(field_key, parse_assumption_input_value(field_key, value), base_config)
    return updated


def demand_profile_visibility(profile_mode: str) -> dict[str, dict[str, str]]:
    hidden = {"display": "none"}
    shown = {"display": "block"}
    visibility = {
        "demand-profile-panel": hidden,
        "demand-profile-general-panel": hidden,
        "demand-profile-general-preview-panel": hidden,
        "demand-profile-weights-panel": hidden,
    }
    normalized = str(profile_mode or "").strip().lower()
    if normalized == "perfil hora dia de semana":
        visibility["demand-profile-panel"] = shown
        visibility["demand-profile-general-preview-panel"] = shown
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
    panel_catalog: pd.DataFrame | None = None,
    demand_profile: pd.DataFrame,
    demand_profile_weights: pd.DataFrame,
    demand_profile_general: pd.DataFrame,
    month_profile: pd.DataFrame,
    sun_profile: pd.DataFrame,
    cop_kwp_table: pd.DataFrame,
    cop_kwp_table_others: pd.DataFrame,
    economics_cost_items: pd.DataFrame | None = None,
    economics_price_items: pd.DataFrame | None = None,
) -> LoadedConfigBundle:
    config_table = update_config_table_values(base_bundle.config_table, config_updates)
    return rebuild_config_bundle(
        base_bundle,
        config=config_updates,
        config_table=config_table,
        inverter_catalog=inverter_catalog,
        battery_catalog=battery_catalog,
        panel_catalog=panel_catalog if panel_catalog is not None else base_bundle.panel_catalog,
        demand_profile=demand_profile,
        demand_profile_weights=demand_profile_weights,
        demand_profile_general=demand_profile_general,
        month_profile=month_profile,
        sun_profile=sun_profile,
        cop_kwp_table=cop_kwp_table,
        cop_kwp_table_others=cop_kwp_table_others,
        economics_cost_items=economics_cost_items if economics_cost_items is not None else base_bundle.economics_cost_items_table,
        economics_price_items=economics_price_items if economics_price_items is not None else base_bundle.economics_price_items_table,
    )


def apply_workbench_editor_state(
    base_bundle: LoadedConfigBundle,
    *,
    assumption_input_ids: list[dict] | None,
    assumption_values: list[Any] | None,
    inverter_rows: list[dict] | None,
    battery_rows: list[dict] | None,
    panel_rows: list[dict] | None,
    month_profile_rows: list[dict] | None,
    sun_profile_rows: list[dict] | None,
    price_kwp_rows: list[dict] | None,
    price_kwp_others_rows: list[dict] | None,
    demand_profile_rows: list[dict] | None,
    demand_profile_general_rows: list[dict] | None,
    demand_profile_weights_rows: list[dict] | None,
) -> LoadedConfigBundle:
    config = collect_config_updates(assumption_input_ids, assumption_values, base_bundle.config)
    inverter_catalog, inverter_issues = normalize_inverter_catalog_rows(inverter_rows)
    battery_catalog, battery_issues = normalize_battery_catalog_rows(battery_rows)
    panel_catalog_rows = panel_rows if panel_rows is not None else base_bundle.panel_catalog.to_dict("records")
    panel_catalog, panel_issues = normalize_panel_catalog_rows(panel_catalog_rows)
    price_kwp_table, price_kwp_issues = normalize_price_table_rows(price_kwp_rows, "Precios_kWp_relativos")
    price_kwp_table_others, price_kwp_others_issues = normalize_price_table_rows(
        price_kwp_others_rows,
        "Precios_kWp_relativos_Otros",
    )

    bundle = rebuild_bundle_from_ui(
        base_bundle,
        config_updates=config,
        inverter_catalog=inverter_catalog,
        battery_catalog=battery_catalog,
        panel_catalog=panel_catalog,
        demand_profile=frame_from_rows(demand_profile_rows, list(base_bundle.demand_profile_table.columns)),
        demand_profile_weights=frame_from_rows(demand_profile_weights_rows, list(base_bundle.demand_profile_weights_table.columns)),
        demand_profile_general=frame_from_rows(demand_profile_general_rows, list(base_bundle.demand_profile_general_table.columns)),
        month_profile=frame_from_rows(month_profile_rows, list(base_bundle.month_profile_table.columns)),
        sun_profile=frame_from_rows(sun_profile_rows, list(base_bundle.sun_profile_table.columns)),
        cop_kwp_table=frame_from_rows(price_kwp_table.to_dict("records"), list(base_bundle.cop_kwp_table.columns)),
        cop_kwp_table_others=frame_from_rows(
            price_kwp_table_others.to_dict("records"),
            list(base_bundle.cop_kwp_table_others.columns),
        ),
    )
    return refresh_bundle_issues(
        bundle,
        extra_issues=[*inverter_issues, *battery_issues, *panel_issues, *price_kwp_issues, *price_kwp_others_issues],
    )


def workbench_status_message(key: str, lang: str = "es", **kwargs) -> str:
    return tr(key, lang, **kwargs)
