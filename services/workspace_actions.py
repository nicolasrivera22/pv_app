from __future__ import annotations

from dataclasses import replace
import logging
from typing import Any

import pandas as pd

from .config_metadata import update_config_table_values
from .io_excel import rebuild_config_bundle
from .scenario_session import update_scenario_bundle
from .types import LoadedConfigBundle
from .validation import (
    normalize_battery_catalog_rows,
    normalize_inverter_catalog_rows,
    normalize_panel_catalog_rows,
    normalize_price_table_rows,
    refresh_bundle_issues,
)
from .workbench_ui import collect_config_updates, frame_from_rows, rebuild_bundle_from_ui
from .workspace_drafts import WorkspaceDraftState, clear_workspace_draft, get_workspace_draft

logger = logging.getLogger(__name__)


TABLE_BUNDLE_ATTRS = {
    "inverter_catalog": "inverter_catalog",
    "battery_catalog": "battery_catalog",
    "panel_catalog": "panel_catalog",
    "month_profile": "month_profile_table",
    "sun_profile": "sun_profile_table",
    "cop_kwp_table": "cop_kwp_table",
    "cop_kwp_table_others": "cop_kwp_table_others",
    "demand_profile": "demand_profile_table",
    "demand_profile_general": "demand_profile_general_table",
    "demand_profile_weights": "demand_profile_weights_table",
}


def _normalize_state_compare_value(value):
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return int(number) if number.is_integer() else round(number, 10)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return ""
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        numeric_text = stripped.replace(",", "")
        try:
            number = float(numeric_text)
        except ValueError:
            return stripped
        return int(number) if number.is_integer() else round(number, 10)
    return value


def _normalized_records(rows: list[dict[str, Any]] | None, columns: list[str]) -> list[tuple[Any, ...]]:
    frame = frame_from_rows(rows, columns)
    return [
        tuple(_normalize_state_compare_value(record.get(column)) for column in columns)
        for record in frame.to_dict("records")
    ]


def config_overrides_for_fields(
    *,
    base_config: dict[str, Any],
    input_ids: list[dict[str, Any]] | None,
    input_values: list[Any] | None,
) -> tuple[dict[str, Any], set[str]]:
    if not input_ids:
        return {}, set()
    current_config = collect_config_updates(input_ids, input_values, base_config)
    owned_fields = {
        str(component_id.get("field", "")).strip()
        for component_id in (input_ids or [])
        if str(component_id.get("field", "")).strip()
    }
    overrides = {
        field: current_config.get(field)
        for field in owned_fields
        if _normalize_state_compare_value(current_config.get(field)) != _normalize_state_compare_value(base_config.get(field))
    }
    return overrides, owned_fields


def table_draft_rows(
    *,
    base_bundle: LoadedConfigBundle,
    table_rows: dict[str, list[dict[str, Any]] | None],
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    draft_rows: dict[str, list[dict[str, Any]]] = {}
    owned_tables: set[str] = set()
    for table_key, rows in table_rows.items():
        if rows is None:
            logger.debug("table_draft_rows skipped unhydrated table=%s", table_key)
            continue
        bundle_attr = TABLE_BUNDLE_ATTRS[table_key]
        base_frame = getattr(base_bundle, bundle_attr)
        columns = list(base_frame.columns)
        owned_tables.add(table_key)
        if _normalized_records(rows, columns) == _normalized_records(base_frame.to_dict("records"), columns):
            continue
        draft_rows[table_key] = frame_from_rows(rows, columns).to_dict("records")
    logger.debug(
        "table_draft_rows prepared owned_tables=%s draft_rows=%s",
        sorted(owned_tables),
        {table_key: len(rows) for table_key, rows in draft_rows.items()},
    )
    return draft_rows, owned_tables


def overlay_bundle_with_draft(base_bundle: LoadedConfigBundle, draft: WorkspaceDraftState | None) -> LoadedConfigBundle:
    if draft is None:
        return base_bundle
    config = dict(base_bundle.config)
    config.update(draft.config_overrides)
    config_table = update_config_table_values(base_bundle.config_table, config)
    bundle = replace(base_bundle, config=config, config_table=config_table)
    replacements: dict[str, Any] = {}
    for table_key, bundle_attr in TABLE_BUNDLE_ATTRS.items():
        rows = draft.table_rows.get(table_key)
        if rows is None:
            continue
        base_frame = getattr(base_bundle, bundle_attr)
        replacements[bundle_attr] = frame_from_rows(rows, list(base_frame.columns))
    if replacements:
        bundle = replace(bundle, **replacements)
    return bundle


def resolve_workspace_bundle_for_display(
    session_id: str,
    scenario_id: str,
    base_bundle: LoadedConfigBundle,
) -> LoadedConfigBundle:
    draft_bundle = overlay_bundle_with_draft(base_bundle, get_workspace_draft(session_id, scenario_id))
    if draft_bundle is base_bundle:
        return base_bundle
    return rebuild_config_bundle(
        base_bundle,
        config=draft_bundle.config,
        config_table=draft_bundle.config_table,
        inverter_catalog=draft_bundle.inverter_catalog,
        battery_catalog=draft_bundle.battery_catalog,
        panel_catalog=draft_bundle.panel_catalog,
        demand_profile=draft_bundle.demand_profile_table,
        demand_profile_weights=draft_bundle.demand_profile_weights_table,
        demand_profile_general=draft_bundle.demand_profile_general_table,
        month_profile=draft_bundle.month_profile_table,
        sun_profile=draft_bundle.sun_profile_table,
        cop_kwp_table=draft_bundle.cop_kwp_table,
        cop_kwp_table_others=draft_bundle.cop_kwp_table_others,
    )


def _draft_table_rows_or_base(base_bundle: LoadedConfigBundle, draft: WorkspaceDraftState, table_key: str) -> list[dict[str, Any]]:
    rows = draft.table_rows.get(table_key)
    if rows is not None:
        return [dict(row) for row in rows]
    bundle_attr = TABLE_BUNDLE_ATTRS[table_key]
    base_frame = getattr(base_bundle, bundle_attr)
    return base_frame.to_dict("records")


def apply_workspace_draft_to_state(
    state,
    *,
    session_id: str,
    scenario_id: str,
):
    active = state.get_scenario(scenario_id)
    if active is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    base_bundle = active.config_bundle
    draft = get_workspace_draft(session_id, scenario_id)
    if draft is None:
        logger.debug("apply_workspace_draft_to_state no draft for scenario=%s", scenario_id)
        return state, active
    logger.debug(
        "apply_workspace_draft_to_state scenario=%s draft_rows=%s",
        scenario_id,
        {table_key: len(rows) for table_key, rows in draft.table_rows.items()},
    )

    config = dict(base_bundle.config)
    config.update(draft.config_overrides)
    inverter_rows = _draft_table_rows_or_base(base_bundle, draft, "inverter_catalog")
    battery_rows = _draft_table_rows_or_base(base_bundle, draft, "battery_catalog")
    panel_rows = _draft_table_rows_or_base(base_bundle, draft, "panel_catalog")
    price_rows = _draft_table_rows_or_base(base_bundle, draft, "cop_kwp_table")
    price_other_rows = _draft_table_rows_or_base(base_bundle, draft, "cop_kwp_table_others")
    inverter_catalog, inverter_issues = normalize_inverter_catalog_rows(inverter_rows)
    battery_catalog, battery_issues = normalize_battery_catalog_rows(battery_rows)
    panel_catalog, panel_issues = normalize_panel_catalog_rows(panel_rows)
    price_kwp_table, price_kwp_issues = normalize_price_table_rows(price_rows, "Precios_kWp_relativos")
    price_kwp_table_others, price_kwp_others_issues = normalize_price_table_rows(
        price_other_rows,
        "Precios_kWp_relativos_Otros",
    )

    bundle = rebuild_bundle_from_ui(
        base_bundle,
        config_updates=config,
        inverter_catalog=inverter_catalog,
        battery_catalog=battery_catalog,
        panel_catalog=panel_catalog,
        demand_profile=frame_from_rows(
            _draft_table_rows_or_base(base_bundle, draft, "demand_profile"),
            list(base_bundle.demand_profile_table.columns),
        ),
        demand_profile_weights=frame_from_rows(
            _draft_table_rows_or_base(base_bundle, draft, "demand_profile_weights"),
            list(base_bundle.demand_profile_weights_table.columns),
        ),
        demand_profile_general=frame_from_rows(
            _draft_table_rows_or_base(base_bundle, draft, "demand_profile_general"),
            list(base_bundle.demand_profile_general_table.columns),
        ),
        month_profile=frame_from_rows(
            _draft_table_rows_or_base(base_bundle, draft, "month_profile"),
            list(base_bundle.month_profile_table.columns),
        ),
        sun_profile=frame_from_rows(
            _draft_table_rows_or_base(base_bundle, draft, "sun_profile"),
            list(base_bundle.sun_profile_table.columns),
        ),
        cop_kwp_table=frame_from_rows(price_kwp_table.to_dict("records"), list(base_bundle.cop_kwp_table.columns)),
        cop_kwp_table_others=frame_from_rows(
            price_kwp_table_others.to_dict("records"),
            list(base_bundle.cop_kwp_table_others.columns),
        ),
    )
    bundle = refresh_bundle_issues(
        bundle,
        extra_issues=[*inverter_issues, *battery_issues, *panel_issues, *price_kwp_issues, *price_kwp_others_issues],
    )
    next_state = update_scenario_bundle(state, scenario_id, bundle)
    updated = next_state.get_scenario(scenario_id)
    clear_workspace_draft(session_id, scenario_id)
    if updated is None:
        raise KeyError(f"No existe el escenario '{scenario_id}'.")
    return next_state, updated
