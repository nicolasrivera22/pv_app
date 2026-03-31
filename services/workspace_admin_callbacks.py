from __future__ import annotations

from datetime import datetime
import logging
import time

from dash import ALL, Input, Output, State, callback, ctx, dash_table, html
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.graph_objects as go

from components.admin_view import build_admin_access_shell
from components.assumption_editor import render_assumption_sections
from .admin_access import (
    admin_pin_configured,
    grant_admin_session_access,
    is_admin_session_unlocked,
    set_admin_pin,
    verify_admin_pin,
)
from .economics_tables import (
    economics_ui_label,
    economics_cost_items_rows_from_editor,
    economics_cost_items_rows_to_editor,
    economics_price_items_rows_from_split_editors,
    economics_price_items_rows_to_section_editor,
)
from .economics_engine import (
    PREVIEW_STATE_CANDIDATE_MISSING,
    PREVIEW_STATE_NO_SCAN,
    PREVIEW_STATE_READY,
    PREVIEW_STATE_RERUN_REQUIRED,
    EconomicsPreviewResult,
    economics_preview_warning_messages,
    resolve_economics_preview,
)
from .i18n import tr
from .profile_charts import build_profile_chart
from .project_io import save_project
from .scenario_session import (
    PreparedEconomicsRuntimePriceBridge,
    apply_prepared_economics_runtime_price_bridge,
    prepare_economics_runtime_price_bridge,
    resolve_runtime_price_bridge_state,
)
from .session_state import commit_client_session, resolve_client_session
from .ui_schema import assumption_context_map, build_assumption_sections, build_table_display_columns, format_metric
from .validation import (
    BATTERY_REQUIRED_COLUMNS,
    INVERTER_REQUIRED_COLUMNS,
    PANEL_REQUIRED_COLUMNS,
    localize_validation_message,
)
from .types import ValidationIssue
from .workbench_ui import collect_config_updates, workbench_status_message
from .workspace_actions import (
    apply_workspace_draft_to_state,
    resolve_workspace_bundle_for_display,
    table_draft_rows,
)
from .workspace_drafts import bind_workspace_draft_project, upsert_workspace_draft
from .workspace_partitions import partition_assumption_sections

logger = logging.getLogger(__name__)


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


def _admin_session(payload, language_value: str | None):
    client_state, state = _session(payload, language_value)
    return client_state, state, is_admin_session_unlocked(client_state.session_id)


def _admin_locked_meta(message_key: str | None = None, *, tone: str = "neutral") -> dict[str, object]:
    return {
        "revision": time.time(),
        "message_key": message_key,
        "tone": tone,
    }


def _validate_admin_setup_pin(pin_value, confirm_value) -> str:
    pin = str(pin_value or "").strip()
    confirm = str(confirm_value or "").strip()
    if not pin:
        raise ValueError("workspace.advanced.setup.empty")
    if not pin.isdigit():
        raise ValueError("workspace.advanced.setup.digits_only")
    if len(pin) < 4:
        raise ValueError("workspace.advanced.setup.too_short")
    if pin != confirm:
        raise ValueError("workspace.advanced.setup.mismatch")
    return pin


PROFILE_MAIN_TABLE_IDS = (
    "month-profile-editor",
    "sun-profile-editor",
)
PROFILE_TABLE_IDS = PROFILE_MAIN_TABLE_IDS
PROFILE_ACTIVATOR_TABLE_IDS = PROFILE_MAIN_TABLE_IDS
PROFILE_CARD_BASE_CLASS = "profile-table-card-shell"
PROFILE_CARD_ACTIVE_CLASS = f"{PROFILE_CARD_BASE_CLASS} profile-table-card-active"
ADMIN_PREVIEW_SOURCE_WORKBENCH = "workbench_seeded"
ADMIN_PREVIEW_SOURCE_LOCAL = "admin_local"
ADMIN_REQUIRED_TABLE_KEYS = (
    "inverter_catalog",
    "battery_catalog",
    "panel_catalog",
    "month_profile",
    "sun_profile",
    "economics_cost_items",
    "economics_price_items",
)
ECONOMICS_BRIDGE_TABLE_KEYS = {"economics_cost_items", "economics_price_items"}


def _project_is_bound(state) -> bool:
    return bool(str(state.project_slug or "").strip())


def _resolved_project_name(project_name_value, state) -> str:
    return (project_name_value or state.project_name or state.project_slug or "").strip()


def _join_status_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _format_timestamp_text(value: str | None) -> str:
    return str(value or "").replace("T", " ").strip()


def _admin_current_changes(
    active,
    *,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
):
    normalized_cost_rows = (
        active.config_bundle.economics_cost_items_table.to_dict("records")
        if economics_cost_rows is None
        else economics_cost_items_rows_from_editor(economics_cost_rows)
    )
    if economics_tax_rows is None and economics_adjustment_rows is None:
        normalized_price_rows = active.config_bundle.economics_price_items_table.to_dict("records")
    else:
        normalized_price_rows = _combined_price_editor_rows_or_none(economics_tax_rows, economics_adjustment_rows)
    table_rows = _admin_table_rows_payload(
        inverter_rows,
        battery_rows,
        panel_rows,
        month_profile_rows,
        sun_profile_rows,
        normalized_cost_rows,
        normalized_price_rows,
    )
    unhydrated_tables = _unhydrated_admin_tables(table_rows)
    current_config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
    owned_fields = {
        str(component_id.get("field", "")).strip()
        for component_id in (assumption_input_ids or [])
        if str(component_id.get("field", "")).strip()
    }
    overrides = {
        field: current_config.get(field)
        for field in owned_fields
        if _normalize_compare_value(current_config.get(field)) != _normalize_compare_value(active.config_bundle.config.get(field))
    }
    rows_payload: dict[str, list[dict[str, object]]] = {}
    owned_tables: set[str] = set()
    if not unhydrated_tables:
        rows_payload, owned_tables = table_draft_rows(
            base_bundle=active.config_bundle,
            table_rows=table_rows,
        )
    return {
        "normalized_cost_rows": normalized_cost_rows,
        "normalized_price_rows": normalized_price_rows,
        "unhydrated_tables": unhydrated_tables,
        "overrides": overrides,
        "owned_fields": owned_fields,
        "rows_payload": rows_payload,
        "owned_tables": owned_tables,
    }


def _has_non_economics_pending_changes(changes: dict[str, object]) -> bool:
    if changes.get("overrides"):
        return True
    rows_payload = changes.get("rows_payload") or {}
    return any(table_key not in ECONOMICS_BRIDGE_TABLE_KEYS for table_key in rows_payload)


def _resolve_economics_bridge_context(
    active,
    *,
    candidate_key: str | None = None,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
    applied_at: str | None = None,
):
    changes = _admin_current_changes(
        active,
        assumption_input_ids=assumption_input_ids,
        assumption_values=assumption_values,
        inverter_rows=inverter_rows,
        battery_rows=battery_rows,
        panel_rows=panel_rows,
        month_profile_rows=month_profile_rows,
        sun_profile_rows=sun_profile_rows,
        economics_cost_rows=economics_cost_rows,
        economics_tax_rows=economics_tax_rows,
        economics_adjustment_rows=economics_adjustment_rows,
    )
    prepared = prepare_economics_runtime_price_bridge(
        active,
        candidate_key=candidate_key,
        economics_cost_items=changes["normalized_cost_rows"],
        economics_price_items=changes["normalized_price_rows"],
        applied_at=applied_at,
    )
    if changes["unhydrated_tables"]:
        blocker_key = "workspace.admin.economics.bridge.cta.loading"
    elif _has_non_economics_pending_changes(changes):
        blocker_key = "workspace.admin.economics.bridge.cta.blocked_non_economics"
    elif prepared.blocker_key == "warnings":
        blocker_key = "workspace.admin.economics.bridge.cta.blocked_warnings"
    elif not prepared.applied:
        blocker_key = f"workspace.admin.economics.bridge.cta.state.{prepared.preview_state}"
    else:
        blocker_key = None
    return {
        **changes,
        "prepared": prepared,
        "live_warnings": prepared.warning_messages,
        "eligible": blocker_key is None,
        "blocker_key": blocker_key,
    }


def _economics_bridge_cta_text(bridge_context: dict[str, object], *, lang: str) -> str:
    blocker_key = bridge_context.get("blocker_key")
    if blocker_key:
        return tr(str(blocker_key), lang)
    prepared = bridge_context.get("prepared")
    if not isinstance(prepared, PreparedEconomicsRuntimePriceBridge) or prepared.final_price_COP is None:
        return tr("workspace.admin.economics.bridge.cta.loading", lang)
    return tr(
        "workspace.admin.economics.bridge.cta.ready",
        lang,
        final_price=_format_cop(prepared.final_price_COP, lang),
    )


def _admin_table_rows_payload(
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_price_rows,
) -> dict[str, list[dict[str, object]] | None]:
    return {
        "inverter_catalog": inverter_rows,
        "battery_catalog": battery_rows,
        "panel_catalog": panel_rows,
        "month_profile": month_profile_rows,
        "sun_profile": sun_profile_rows,
        "economics_cost_items": economics_cost_rows,
        "economics_price_items": economics_price_rows,
    }


def _combined_price_editor_rows_or_none(
    economics_tax_rows,
    economics_adjustment_rows,
) -> list[dict[str, object]] | None:
    if economics_tax_rows is None or economics_adjustment_rows is None:
        return None
    return economics_price_items_rows_from_split_editors(economics_tax_rows, economics_adjustment_rows)


def _unhydrated_admin_tables(table_rows: dict[str, list[dict[str, object]] | None]) -> tuple[str, ...]:
    return tuple(table_key for table_key in ADMIN_REQUIRED_TABLE_KEYS if table_rows.get(table_key) is None)


def _active_profile_table_state(table_id: str | None = None) -> dict[str, str | None]:
    if table_id is None:
        return {"table_id": None}
    normalized = str(table_id).strip()
    return {"table_id": normalized or None}


def _empty_admin_preview_candidate_state() -> dict[str, str | None]:
    return {"scenario_id": None, "candidate_key": None, "source": None}


def _seed_admin_preview_candidate_state(active) -> dict[str, str | None]:
    if active is None:
        return _empty_admin_preview_candidate_state()
    scenario_id = str(active.scenario_id)
    if active.scan_result is None or not active.scan_result.candidate_details:
        return {"scenario_id": scenario_id, "candidate_key": None, "source": None}
    if active.selected_candidate_key in active.scan_result.candidate_details:
        return {
            "scenario_id": scenario_id,
            "candidate_key": str(active.selected_candidate_key),
            "source": ADMIN_PREVIEW_SOURCE_WORKBENCH,
        }
    best_candidate_key = active.scan_result.best_candidate_key
    if best_candidate_key in active.scan_result.candidate_details:
        return {
            "scenario_id": scenario_id,
            "candidate_key": str(best_candidate_key),
            "source": ADMIN_PREVIEW_SOURCE_WORKBENCH,
        }
    return {"scenario_id": scenario_id, "candidate_key": None, "source": None}


def _admin_preview_candidate_exists(active, candidate_key: str | None) -> bool:
    return bool(
        active is not None
        and active.scan_result is not None
        and candidate_key is not None
        and candidate_key in active.scan_result.candidate_details
    )


def _resolve_admin_preview_candidate_state(active, current_state: dict[str, object] | None = None) -> dict[str, str | None]:
    if active is None:
        return _empty_admin_preview_candidate_state()

    stored = current_state or {}
    scenario_id = str(active.scenario_id)
    stored_scenario_id = str(stored.get("scenario_id") or "").strip() or None
    stored_candidate_key = str(stored.get("candidate_key") or "").strip() or None
    stored_source = str(stored.get("source") or "").strip() or None

    if stored_scenario_id == scenario_id and stored_source == ADMIN_PREVIEW_SOURCE_LOCAL:
        return {
            "scenario_id": scenario_id,
            "candidate_key": stored_candidate_key,
            "source": ADMIN_PREVIEW_SOURCE_LOCAL,
        }

    if active.scan_result is None or not active.scan_result.candidate_details:
        return {"scenario_id": scenario_id, "candidate_key": None, "source": None}

    return _seed_admin_preview_candidate_state(active)


def _requested_admin_preview_candidate_key(active, current_state: dict[str, object] | None = None) -> str | None:
    resolved_state = _resolve_admin_preview_candidate_state(active, current_state)
    candidate_key = str(resolved_state.get("candidate_key") or "").strip()
    return candidate_key or None


def _resolve_admin_preview_candidate_key(active, current_state: dict[str, object] | None = None) -> str | None:
    candidate_key = _requested_admin_preview_candidate_key(active, current_state)
    return candidate_key if _admin_preview_candidate_exists(active, candidate_key) else None


def _admin_preview_selector_state_key(active) -> str:
    if active is None:
        return PREVIEW_STATE_NO_SCAN
    if active.dirty:
        return PREVIEW_STATE_RERUN_REQUIRED
    if active.scan_result is None:
        return PREVIEW_STATE_NO_SCAN
    if not active.scan_result.candidate_details:
        return PREVIEW_STATE_CANDIDATE_MISSING
    return PREVIEW_STATE_READY


def _admin_preview_candidate_option_label(candidate_key: str, detail: dict[str, object], *, lang: str) -> str:
    k_wp = _format_number(detail.get("kWp"), decimals=3)
    battery_name = str(detail.get("battery_name") or "").strip() or tr("common.no_battery", lang)
    return tr(
        "workspace.admin.economics.preview.selector.option",
        lang,
        candidate_key=candidate_key,
        kWp=k_wp,
        battery_name=battery_name,
    )


def _admin_preview_candidate_meta(active, candidate_key: str | None, *, lang: str):
    if (
        active is None
        or active.scan_result is None
        or candidate_key not in active.scan_result.candidate_details
    ):
        return ""
    detail = active.scan_result.candidate_details[candidate_key]
    battery_name = str(detail.get("battery_name") or "").strip() or tr("common.no_battery", lang)
    inverter_name = str((((detail.get("inv_sel") or {}).get("inverter") or {}).get("name")) or "").strip()
    panel_name = str(detail.get("panel_name") or active.config_bundle.config.get("panel_name") or "").strip()
    if panel_name.startswith("__"):
        panel_name = ""
    return html.Div(
        id="admin-preview-candidate-identity",
        className="economics-candidate-identity-strip",
        children=[
            _economics_quantity_card(
                tr("workspace.admin.economics.preview.selector.meta.candidate", lang),
                candidate_key,
                component_id="admin-preview-candidate-meta-key",
            ),
            _economics_quantity_card(
                tr("workspace.admin.economics.preview.selector.meta.kwp", lang),
                f"{_format_number(detail.get('kWp'), decimals=3)} kWp",
                component_id="admin-preview-candidate-meta-kwp",
            ),
            _economics_quantity_card(
                tr("workspace.admin.economics.preview.selector.meta.battery", lang),
                battery_name,
                component_id="admin-preview-candidate-meta-battery",
            ),
            _economics_quantity_card(
                tr("workspace.admin.economics.preview.quantity.panel_name", lang),
                _economics_equipment_name(panel_name, kind="panel", lang=lang),
                component_id="admin-preview-candidate-meta-panel",
            ),
            _economics_quantity_card(
                tr("workspace.admin.economics.preview.quantity.inverter_name", lang),
                _economics_equipment_name(inverter_name, kind="inverter", lang=lang),
                component_id="admin-preview-candidate-meta-inverter",
            ),
        ],
    )


def _assumption_note_style(message: str) -> dict[str, str]:
    return {"display": "block"} if str(message or "").strip() else {"display": "none"}


def _assumption_card_class(field_key: str, *, disabled: bool = False, emphasize: bool = False) -> str:
    classes = ["field-card"]
    if disabled:
        classes.append("field-card-disabled")
    if emphasize and not disabled:
        classes.append("field-card-highlight")
    return " ".join(dict.fromkeys(classes))


def _profile_card_class_names(active_table_id: str | None) -> tuple[str, ...]:
    classes: list[str] = []
    for table_id in PROFILE_TABLE_IDS:
        is_active = table_id == active_table_id
        classes.append(PROFILE_CARD_ACTIVE_CLASS if is_active else PROFILE_CARD_BASE_CLASS)
    return tuple(classes)


def _blank_table_row(table_columns, table_rows=None) -> dict[str, str]:
    column_ids = [
        str(column.get("id", "")).strip()
        for column in (table_columns or [])
        if str(column.get("id", "")).strip()
    ]
    if not column_ids and table_rows:
        column_ids = [str(column).strip() for column in table_rows[0].keys() if str(column).strip()]
    return {column_id: "" for column_id in column_ids}


def _normalize_compare_value(value):
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
        try:
            number = float(stripped.replace(",", ""))
        except ValueError:
            return stripped
        return int(number) if number.is_integer() else round(number, 10)
    return value


def _format_cop(value: float | None, lang: str) -> str:
    if value is None:
        return "-"
    return format_metric("NPV", value, lang)


def _format_cop_per_kwp(value: float | None, lang: str) -> str:
    if value is None:
        return "-"
    return f"{_format_cop(value, lang)} / kWp"


def _format_number(value: float | int | None, *, decimals: int = 3) -> str:
    if value is None:
        return "-"
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.{decimals}f}".rstrip("0").rstrip(".")


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    formatted = f"{float(value) * 100:.1f}".rstrip("0").rstrip(".")
    return f"{formatted}%"


def _economics_summary_card(
    label: str,
    value: str,
    *,
    component_id: str | None = None,
    emphasized: bool = False,
    secondary_label: str | None = None,
    secondary_value: str | None = None,
) -> html.Div:
    secondary_children: list[object] = []
    if secondary_label and secondary_value:
        secondary_children.append(
            html.Div(
                className="economics-summary-secondary",
                children=[
                    html.Span(secondary_label, className="economics-summary-secondary-label"),
                    html.Strong(secondary_value, className="economics-summary-secondary-value"),
                ],
            )
        )
    return html.Div(
        id=component_id,
        className="scan-summary-card economics-summary-card" + (" economics-summary-card-key" if emphasized else ""),
        children=[
            html.Span(label, className="scan-summary-label"),
            html.Span(value, className="scan-summary-value"),
            *secondary_children,
        ],
    )


def _economics_breakdown_formula(row: dict[str, object], *, lang: str) -> str:
    rule = str(row.get("rule") or "")
    value_source = str(row.get("value_source") or "")
    hardware_binding = str(row.get("hardware_binding") or "")
    multiplier = float(row.get("multiplier", 0.0) or 0.0)
    unit_rate = float(row.get("unit_rate_COP", 0.0) or 0.0)
    base_amount = row.get("base_amount_COP")
    quantity_labels = {
        "en": {
            "per_kwp": "kWp",
            "per_panel": "panels",
            "per_inverter": "inverter(s)",
            "per_battery_kwh": "battery kWh",
            "selected_battery_catalog": "battery",
            "unavailable_battery": "battery",
        },
        "es": {
            "per_kwp": "kWp",
            "per_panel": "paneles",
            "per_inverter": "inversor(es)",
            "per_battery_kwh": "kWh batería",
            "selected_battery_catalog": "batería",
            "unavailable_battery": "batería",
        },
    }
    if rule in {"markup_pct", "tax_pct"}:
        return f"{_format_percent(unit_rate)} x {_format_cop(None if base_amount is None else float(base_amount), lang)}"
    if rule == "fixed_project":
        return f"1 x {_format_cop(unit_rate, lang)}"
    if hardware_binding == "battery" and value_source in {"selected_battery_catalog", "unavailable"}:
        unit = quantity_labels.get(lang, quantity_labels["es"]).get(
            "selected_battery_catalog" if value_source == "selected_battery_catalog" else "unavailable_battery",
            "",
        )
    else:
        unit = quantity_labels.get(lang, quantity_labels["es"]).get(rule, "")
    quantity = _format_number(multiplier, decimals=3)
    unit_suffix = f" {unit}" if unit else ""
    return f"{quantity}{unit_suffix} x {_format_cop(unit_rate, lang)}"


def _economics_breakdown_rows(rows, *, lang: str) -> list[dict[str, object]]:
    def _hardware_name_cell(row) -> str:
        hardware_name = str(row.hardware_name or "").strip()
        if hardware_name:
            return hardware_name
        if str(row.hardware_binding or "").strip() or str(row.value_source or "").strip() == "unavailable":
            return tr("workspace.admin.economics.preview.placeholder.not_available", lang)
        return ""

    return [
        {
            "source_table": economics_ui_label("source_table", row.source_table, lang=lang),
            "source_row": row.source_row,
            "stage_or_layer": economics_ui_label("stage" if row.group == "cost" else "layer", row.stage_or_layer, lang=lang),
            "name": row.name,
            "rule": economics_ui_label("basis" if row.group == "cost" else "method", row.rule, lang=lang),
            "value_source": economics_ui_label("value_source", row.value_source, lang=lang),
            "hardware_binding": economics_ui_label("hardware_binding", row.hardware_binding, lang=lang),
            "hardware_name": _hardware_name_cell(row),
            "calculation": _economics_breakdown_formula(
                {
                    "rule": row.rule,
                    "value_source": row.value_source,
                    "hardware_binding": row.hardware_binding,
                    "multiplier": row.multiplier,
                    "unit_rate_COP": row.unit_rate_COP,
                    "base_amount_COP": row.base_amount_COP,
                },
                lang=lang,
            ),
            "multiplier": row.multiplier,
            "unit_rate_COP": row.unit_rate_COP,
            "base_amount_COP": row.base_amount_COP,
            "line_amount_COP": row.line_amount_COP,
            "notes": row.notes,
        }
        for row in rows
    ]


def _economics_breakdown_table(
    table_id: str,
    rows: list[dict[str, object]],
    *,
    lang: str,
    advanced: bool = False,
    show_stage: bool = False,
):
    column_keys = ["name", "rule", "calculation", "line_amount_COP"]
    if show_stage:
        column_keys.insert(0, "stage_or_layer")
    if advanced:
        column_keys = [
            "stage_or_layer",
            "name",
            "rule",
            "value_source",
            "hardware_binding",
            "hardware_name",
            "calculation",
            "multiplier",
            "unit_rate_COP",
            "line_amount_COP",
            "notes",
        ]
        if any(row.get("base_amount_COP") is not None for row in rows):
            column_keys.insert(column_keys.index("line_amount_COP"), "base_amount_COP")
    columns, tooltip_header = build_table_display_columns("economics_breakdown", column_keys, lang)
    return dash_table.DataTable(
        id=table_id,
        data=rows,
        columns=columns,
        tooltip_header=tooltip_header,
        editable=False,
        row_deletable=False,
        sort_action="none",
        page_size=12,
        style_table={"overflowX": "auto"},
        style_cell={
            "padding": "0.4rem",
            "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif",
            "fontSize": 12,
            "color": "var(--color-text-primary)",
            "whiteSpace": "normal",
            "height": "auto",
            "minWidth": 110,
            "maxWidth": 240 if not advanced else 280,
        },
        style_header={
            "backgroundColor": "var(--color-primary-soft)",
            "color": "var(--color-text-primary)",
            "fontWeight": "bold",
        },
        style_cell_conditional=[
            {"if": {"column_id": "source_row"}, "textAlign": "right"},
            {"if": {"column_id": "multiplier"}, "textAlign": "right"},
            {"if": {"column_id": "unit_rate_COP"}, "textAlign": "right"},
            {"if": {"column_id": "base_amount_COP"}, "textAlign": "right"},
            {"if": {"column_id": "line_amount_COP"}, "textAlign": "right"},
        ],
        tooltip_delay=0,
        tooltip_duration=None,
    )


def _economics_preview_state_block(preview: EconomicsPreviewResult, *, lang: str) -> html.Div:
    state_key = preview.state or PREVIEW_STATE_NO_SCAN
    title = tr(f"workspace.admin.economics.preview.state.{state_key}.title", lang)
    detail = tr(f"workspace.admin.economics.preview.state.{state_key}.detail", lang)
    body = tr(preview.message_key or "workspace.admin.economics.preview.state.no_scan", lang)
    return html.Div(
        id="economics-preview-state-shell",
        className=(
            f"subpanel economics-preview-state-shell economics-preview-status-strip economics-preview-state-{state_key}"
            + (" economics-preview-state-empty" if preview.result is None else "")
        ),
        children=[
            html.Div(
                className="economics-preview-state-head",
                children=[
                    html.Span(title, id="economics-preview-state-title", className="economics-preview-state-chip"),
                    html.Div(body, id="economics-preview-status", className="status-line economics-preview-status"),
                ],
            ),
            html.P(detail, id="economics-preview-state-detail", className="section-copy economics-preview-state-detail"),
        ],
    )


def _economics_quantity_card(label: str, value: str, *, component_id: str | None = None) -> html.Div:
    return html.Div(
        id=component_id,
        className="field-card economics-preview-quantity-card",
        children=[
            html.Span(label, className="scan-summary-label"),
            html.Strong(value, className="scan-summary-value"),
        ],
    )


def _economics_candidate_source_text(candidate_source: str | None, *, lang: str) -> str:
    if candidate_source == "selected":
        return tr("workspace.admin.economics.preview.candidate_source.selected", lang)
    if candidate_source == "best_fallback":
        return tr("workspace.admin.economics.preview.candidate_source.best_fallback", lang)
    return tr("workspace.admin.economics.preview.placeholder.not_available", lang)


def _economics_equipment_name(name: str | None, *, kind: str, lang: str) -> str:
    stripped = str(name or "").strip()
    if stripped:
        return stripped
    if kind == "battery":
        placeholder_key = "workspace.admin.economics.preview.placeholder.no_battery"
    elif kind == "panel":
        placeholder_key = "workspace.admin.economics.preview.placeholder.no_panel"
    else:
        placeholder_key = "workspace.admin.economics.preview.placeholder.no_inverter"
    return tr(placeholder_key, lang)


def _economics_preview_quantities(preview: EconomicsPreviewResult, result, *, lang: str) -> html.Div:
    quantities = result.quantities
    return html.Div(
        id="economics-preview-quantities-shell",
        className="subpanel economics-preview-quantities-shell",
        children=[
            html.Div(
                className="section-head",
                children=[html.H5(tr("workspace.admin.economics.preview.quantities.title", lang), id="economics-preview-quantities-title")],
            ),
            html.Div(
                tr(
                    "workspace.admin.economics.preview.meta",
                    lang,
                    candidate_key=quantities.candidate_key,
                    kWp=quantities.kWp,
                    panel_count=quantities.panel_count,
                    inverter_count=quantities.inverter_count,
                    battery_kwh=quantities.battery_kwh,
                ),
                id="economics-preview-meta",
                className="status-line economics-preview-meta",
            ),
            html.Div(
                id="economics-preview-quantities-grid",
                className="economics-preview-quantities-grid",
                children=[
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.candidate", lang),
                        quantities.candidate_key,
                        component_id="economics-preview-quantity-candidate",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.candidate_source", lang),
                        _economics_candidate_source_text(preview.candidate_source, lang=lang),
                        component_id="economics-preview-quantity-candidate-source",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.kwp", lang),
                        f"{_format_number(quantities.kWp, decimals=3)} kWp",
                        component_id="economics-preview-quantity-kwp",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.panel_count", lang),
                        _format_number(quantities.panel_count, decimals=0),
                        component_id="economics-preview-quantity-panel-count",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.panel_name", lang),
                        _economics_equipment_name(quantities.panel_name, kind="panel", lang=lang),
                        component_id="economics-preview-quantity-panel-name",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.inverter_count", lang),
                        _format_number(quantities.inverter_count, decimals=0),
                        component_id="economics-preview-quantity-inverter-count",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.battery_kwh", lang),
                        f"{_format_number(quantities.battery_kwh, decimals=1)} kWh",
                        component_id="economics-preview-quantity-battery-kwh",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.inverter_name", lang),
                        _economics_equipment_name(quantities.inverter_name, kind="inverter", lang=lang),
                        component_id="economics-preview-quantity-inverter-name",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.battery_name", lang),
                        _economics_equipment_name(quantities.battery_name, kind="battery", lang=lang),
                        component_id="economics-preview-quantity-battery-name",
                    ),
                ],
            ),
        ],
    )


def _economics_preview_warning_block(messages: tuple[str, ...], *, lang: str) -> html.Div | None:
    if not messages:
        return None
    return html.Div(
        id="economics-preview-warnings-shell",
        className="subpanel economics-preview-warnings-shell economics-preview-status-strip",
        children=[
            html.Span(
                tr("workspace.admin.economics.preview.warnings.title", lang),
                id="economics-preview-warnings-title",
                className="economics-preview-state-chip",
            ),
            html.Div(
                id="economics-preview-warnings-list",
                className="economics-preview-warning-chips",
                children=[
                    html.Span(
                        localize_validation_message(ValidationIssue("warning", "economics_cost_items", message), lang=lang),
                        className="status-line economics-preview-warning-chip",
                    )
                    for message in messages
                ],
            ),
        ],
    )


def _economics_flow_card(*, component_id: str, title: str, formula: str, value: str) -> html.Div:
    return html.Div(
        id=component_id,
        className="field-card economics-preview-flow-card",
        children=[
            html.Span(title, className="scan-summary-label"),
            html.Strong(value, className="scan-summary-value"),
            html.Span(formula, className="section-copy"),
        ],
    )


def _economics_preview_flow(result, *, lang: str) -> html.Div:
    steps = [
        (
            "economics-preview-flow-technical",
            tr("workspace.admin.economics.preview.summary.technical", lang),
            tr("workspace.admin.economics.preview.flow.formula.technical", lang),
            _format_cop(result.technical_subtotal_COP, lang),
        ),
        (
            "economics-preview-flow-installed",
            tr("workspace.admin.economics.preview.summary.installed", lang),
            tr("workspace.admin.economics.preview.flow.formula.installed", lang),
            _format_cop(result.installed_subtotal_COP, lang),
        ),
        (
            "economics-preview-flow-cost-total",
            tr("workspace.admin.economics.preview.summary.cost_total", lang),
            tr("workspace.admin.economics.preview.flow.formula.cost_total", lang),
            _format_cop(result.cost_total_COP, lang),
        ),
        (
            "economics-preview-flow-tax-total",
            tr("workspace.admin.economics.preview.summary.tax_total", lang),
            tr("workspace.admin.economics.preview.flow.formula.tax_total", lang),
            _format_cop(result.tax_total_COP, lang),
        ),
        (
            "economics-preview-flow-subtotal-with-tax",
            tr("workspace.admin.economics.preview.summary.subtotal_with_tax", lang),
            tr("workspace.admin.economics.preview.flow.formula.subtotal_with_tax", lang),
            _format_cop(result.subtotal_with_tax_COP, lang),
        ),
        (
            "economics-preview-flow-post-tax-adjustments-total",
            tr("workspace.admin.economics.preview.summary.post_tax_adjustments_total", lang),
            tr("workspace.admin.economics.preview.flow.formula.post_tax_adjustments_total", lang),
            _format_cop(result.post_tax_adjustments_total_COP, lang),
        ),
        (
            "economics-preview-flow-final-price",
            tr("workspace.admin.economics.preview.summary.final_price", lang),
            tr("workspace.admin.economics.preview.flow.formula.final_price", lang),
            _format_cop(result.final_price_COP, lang),
        ),
        (
            "economics-preview-flow-final-price-per-kwp",
            tr("workspace.admin.economics.preview.summary.final_price_per_kwp", lang),
            tr("workspace.admin.economics.preview.flow.formula.final_price_per_kwp", lang),
            _format_cop_per_kwp(result.final_price_per_kwp_COP, lang),
        ),
    ]
    return html.Div(
        id="economics-preview-flow-shell",
        className="subpanel economics-preview-flow-shell",
        children=[
            html.Div(
                className="section-head",
                children=[html.H5(tr("workspace.admin.economics.preview.flow_live.title", lang), id="economics-preview-flow-title")],
            ),
            html.P(tr("workspace.admin.economics.preview.flow_live.copy", lang), className="section-copy"),
            html.Div(
                id="economics-preview-flow-grid",
                className="economics-preview-flow-grid",
                children=[
                    _economics_flow_card(component_id=component_id, title=title, formula=formula, value=value)
                    for component_id, title, formula, value in steps
                ],
            ),
            html.Div(tr("workspace.admin.economics.preview.flow.note_markup", lang), className="status-line economics-preview-note"),
            html.Div(tr("workspace.admin.economics.preview.flow.note_derived", lang), className="status-line economics-preview-note"),
        ],
    )


def _economics_preview_summary_shell(result, *, lang: str) -> html.Div:
    summary_cards = html.Div(
        id="economics-summary-cards",
        className="kpi-grid",
        children=[
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.cost_total", lang),
                _format_cop(result.cost_total_COP, lang),
                component_id="economics-summary-card-cost-total",
                emphasized=True,
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.tax_total", lang),
                _format_cop(result.tax_total_COP, lang),
                component_id="economics-summary-card-tax-total",
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.subtotal_with_tax", lang),
                _format_cop(result.subtotal_with_tax_COP, lang),
                component_id="economics-summary-card-subtotal-with-tax",
                emphasized=True,
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.post_tax_adjustments_total", lang),
                _format_cop(result.post_tax_adjustments_total_COP, lang),
                component_id="economics-summary-card-post-tax-adjustments",
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.final_price", lang),
                _format_cop(result.final_price_COP, lang),
                component_id="economics-summary-card-final-price",
                emphasized=True,
                secondary_label=tr("workspace.admin.economics.preview.summary.final_price_per_kwp", lang),
                secondary_value=_format_cop_per_kwp(result.final_price_per_kwp_COP, lang),
            ),
        ],
    )
    return html.Div(
        id="economics-summary-shell",
        className="subpanel economics-summary-shell",
        children=[
            html.Div(
                className="section-head",
                children=[html.H5(tr("workspace.admin.economics.preview.summary_block.title", lang), id="economics-summary-title")],
            ),
            html.P(tr("workspace.admin.economics.preview.summary_block.copy", lang), id="economics-summary-copy", className="section-copy"),
            summary_cards,
        ],
    )


def _economics_closing_rows(result, *, lang: str) -> list[dict[str, object]]:
    rows = [
        {
            "metric": tr("workspace.admin.economics.preview.summary.technical", lang),
            "value": _format_cop(result.technical_subtotal_COP, lang),
        },
        {
            "metric": tr("workspace.admin.economics.preview.summary.installed", lang),
            "value": _format_cop(result.installed_subtotal_COP, lang),
        },
        {
            "metric": tr("workspace.admin.economics.preview.summary.cost_total", lang),
            "value": _format_cop(result.cost_total_COP, lang),
        },
        {
            "metric": tr("workspace.admin.economics.preview.summary.tax_total", lang),
            "value": _format_cop(result.tax_total_COP, lang),
        },
        {
            "metric": tr("workspace.admin.economics.preview.summary.subtotal_with_tax", lang),
            "value": _format_cop(result.subtotal_with_tax_COP, lang),
        },
        {
            "metric": tr("workspace.admin.economics.preview.summary.post_tax_adjustments_total", lang),
            "value": _format_cop(result.post_tax_adjustments_total_COP, lang),
        },
        {
            "metric": tr("workspace.admin.economics.preview.summary.final_price", lang),
            "value": _format_cop(result.final_price_COP, lang),
        },
    ]
    return rows


def _economics_closing_shell(result, *, lang: str) -> html.Div:
    return html.Div(
        id="economics-closing-shell",
        className="subpanel economics-closing-shell",
        children=[
            html.Div(
                className="section-head",
                children=[html.H5(tr("workspace.admin.economics.preview.closing.title", lang), id="economics-closing-title")],
            ),
            html.P(tr("workspace.admin.economics.preview.closing.copy", lang), id="economics-closing-copy", className="section-copy"),
            html.Div(
                className="economics-table-wrap economics-table-wrap-dense",
                children=[
                    dash_table.DataTable(
                        id="economics-closing-table",
                        data=_economics_closing_rows(result, lang=lang),
                        columns=[
                            {"name": tr("workspace.admin.economics.preview.closing.metric", lang), "id": "metric"},
                            {"name": tr("workspace.admin.economics.preview.closing.value", lang), "id": "value"},
                        ],
                        editable=False,
                        row_deletable=False,
                        sort_action="none",
                        style_table={"overflowX": "auto"},
                        style_cell={
                            "padding": "0.45rem 0.55rem",
                            "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif",
                            "fontSize": 12,
                            "color": "var(--color-text-primary)",
                            "whiteSpace": "normal",
                            "height": "auto",
                        },
                        style_header={
                            "backgroundColor": "var(--color-primary-soft)",
                            "color": "var(--color-text-primary)",
                            "fontWeight": "bold",
                        },
                        style_cell_conditional=[
                            {"if": {"column_id": "value"}, "textAlign": "right"},
                        ],
                    )
                ],
            ),
        ],
    )


def _economics_breakdown_group(
    *,
    group_id: str,
    title: str,
    description: str,
    subtotal_label: str,
    subtotal_value: float | None,
    rows,
    lang: str,
    advanced: bool = False,
    show_stage: bool = False,
) -> html.Div:
    table_rows = _economics_breakdown_rows(rows, lang=lang)
    children = [html.Div(className="section-head", children=[html.H5(title, id=f"{group_id}-title")])]
    children.append(html.P(description, id=f"{group_id}-copy", className="section-copy"))
    if table_rows:
        children.append(
            html.Div(
                className="economics-table-wrap economics-table-wrap-dense",
                children=[
                    _economics_breakdown_table(
                        f"{group_id}-table",
                        table_rows,
                        lang=lang,
                        advanced=advanced,
                        show_stage=show_stage,
                    )
                ],
            )
        )
    else:
        children.append(html.Div(tr("workspace.admin.economics.preview.breakdown.empty", lang), className="status-line"))
    children.append(
        html.Div(
            id=f"{group_id}-subtotal",
            className="economics-breakdown-subtotal",
            children=[
                html.Span(subtotal_label, className="economics-breakdown-subtotal-label"),
                html.Strong(_format_cop(subtotal_value, lang), className="economics-breakdown-subtotal-value"),
            ],
        )
    )
    return html.Div(id=f"{group_id}-shell", className="profile-table-subsection economics-breakdown-group-shell", children=children)


def _economics_breakdown_advanced_details(result, *, lang: str) -> html.Details:
    return html.Details(
        id="economics-breakdown-advanced-details",
        className="subpanel economics-breakdown-advanced-details economics-collapsible-section",
        open=False,
        children=[
            html.Summary(
                id="economics-breakdown-advanced-summary",
                className="economics-collapsible-summary",
                children=[
                    html.Div(
                        className="economics-collapsible-summary-copy",
                        children=[
                            html.H5(tr("workspace.admin.economics.preview.breakdown.advanced.title", lang)),
                            html.P(
                                tr("workspace.admin.economics.preview.breakdown.advanced.copy", lang),
                                className="section-copy",
                            ),
                        ],
                    )
                ],
            ),
            html.Div(
                id="economics-breakdown-advanced-body",
                className="economics-collapsible-body economics-breakdown-advanced-body",
                children=[
                    _economics_breakdown_group(
                        group_id="economics-breakdown-advanced-technical",
                        title=tr("workspace.admin.economics.preview.breakdown.group.technical", lang),
                        description=tr("workspace.admin.economics.preview.breakdown.group.technical.copy", lang),
                        subtotal_label=tr("workspace.admin.economics.preview.summary.technical", lang),
                        subtotal_value=result.technical_subtotal_COP,
                        rows=[row for row in result.cost_rows if row.stage_or_layer == "technical"],
                        lang=lang,
                        advanced=True,
                        show_stage=True,
                    ),
                    _economics_breakdown_group(
                        group_id="economics-breakdown-advanced-installed",
                        title=tr("workspace.admin.economics.preview.breakdown.group.installed", lang),
                        description=tr("workspace.admin.economics.preview.breakdown.group.installed.copy", lang),
                        subtotal_label=tr("workspace.admin.economics.preview.summary.installed", lang),
                        subtotal_value=result.installed_subtotal_COP,
                        rows=[row for row in result.cost_rows if row.stage_or_layer == "installed"],
                        lang=lang,
                        advanced=True,
                        show_stage=True,
                    ),
                    _economics_breakdown_group(
                        group_id="economics-breakdown-advanced-tax",
                        title=tr("workspace.admin.economics.preview.breakdown.group.tax", lang),
                        description=tr("workspace.admin.economics.preview.breakdown.group.tax.copy", lang),
                        subtotal_label=tr("workspace.admin.economics.preview.summary.tax_total", lang),
                        subtotal_value=result.tax_total_COP,
                        rows=[row for row in result.price_rows if row.stage_or_layer == "tax"],
                        lang=lang,
                        advanced=True,
                        show_stage=True,
                    ),
                    _economics_breakdown_group(
                        group_id="economics-breakdown-advanced-adjustments",
                        title=tr("workspace.admin.economics.preview.breakdown.group.adjustments", lang),
                        description=tr("workspace.admin.economics.preview.breakdown.group.adjustments.copy", lang),
                        subtotal_label=tr("workspace.admin.economics.preview.summary.post_tax_adjustments_total", lang),
                        subtotal_value=result.post_tax_adjustments_total_COP,
                        rows=[row for row in result.price_rows if row.stage_or_layer in {"commercial", "sale"}],
                        lang=lang,
                        advanced=True,
                        show_stage=True,
                    ),
                ],
            ),
        ],
    )


def _economics_preview_advanced_details(preview: EconomicsPreviewResult, result, *, lang: str) -> html.Details:
    return html.Details(
        id="economics-preview-advanced-details",
        className="subpanel economics-preview-advanced-details economics-collapsible-section",
        open=False,
        children=[
            html.Summary(
                id="economics-preview-advanced-summary",
                className="economics-collapsible-summary",
                children=[
                    html.Div(
                        className="economics-collapsible-summary-copy",
                        children=[
                            html.H5(tr("workspace.admin.economics.preview.advanced.title", lang)),
                            html.P(tr("workspace.admin.economics.preview.advanced.copy", lang), className="section-copy"),
                        ],
                    )
                ],
            ),
            html.Div(
                id="economics-preview-advanced-body",
                className="economics-collapsible-body economics-preview-advanced-body",
                children=[
                    _economics_preview_quantities(preview, result, lang=lang),
                    _economics_preview_flow(result, lang=lang),
                ],
            ),
        ],
    )


def _render_economics_preview(preview: EconomicsPreviewResult, *, live_warnings: tuple[str, ...] = (), lang: str):
    state_block = _economics_preview_state_block(preview, lang=lang)
    if preview.state != PREVIEW_STATE_READY or preview.result is None:
        return [state_block]

    result = preview.result
    warnings_block = _economics_preview_warning_block(live_warnings, lang=lang)
    breakdown_shell = html.Div(
        id="economics-breakdown-shell",
        className="subpanel economics-breakdown-shell",
        children=[
            html.Div(
                className="section-head",
                children=[html.H5(tr("workspace.admin.economics.preview.breakdown.title", lang), id="economics-breakdown-title")],
            ),
            html.P(tr("workspace.admin.economics.preview.breakdown.copy", lang), id="economics-breakdown-copy", className="section-copy"),
            _economics_breakdown_group(
                group_id="economics-breakdown-technical",
                title=tr("workspace.admin.economics.preview.breakdown.group.technical", lang),
                description=tr("workspace.admin.economics.preview.breakdown.group.technical.copy", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.technical", lang),
                subtotal_value=result.technical_subtotal_COP,
                rows=[row for row in result.cost_rows if row.stage_or_layer == "technical"],
                lang=lang,
                show_stage=False,
            ),
            _economics_breakdown_group(
                group_id="economics-breakdown-installed",
                title=tr("workspace.admin.economics.preview.breakdown.group.installed", lang),
                description=tr("workspace.admin.economics.preview.breakdown.group.installed.copy", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.installed", lang),
                subtotal_value=result.installed_subtotal_COP,
                rows=[row for row in result.cost_rows if row.stage_or_layer == "installed"],
                lang=lang,
                show_stage=False,
            ),
            _economics_breakdown_group(
                group_id="economics-breakdown-tax",
                title=tr("workspace.admin.economics.preview.breakdown.group.tax", lang),
                description=tr("workspace.admin.economics.preview.breakdown.group.tax.copy", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.tax_total", lang),
                subtotal_value=result.tax_total_COP,
                rows=[row for row in result.price_rows if row.stage_or_layer == "tax"],
                lang=lang,
                show_stage=False,
            ),
            _economics_breakdown_group(
                group_id="economics-breakdown-adjustments",
                title=tr("workspace.admin.economics.preview.breakdown.group.adjustments", lang),
                description=tr("workspace.admin.economics.preview.breakdown.group.adjustments.copy", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.post_tax_adjustments_total", lang),
                subtotal_value=result.post_tax_adjustments_total_COP,
                rows=[row for row in result.price_rows if row.stage_or_layer in {"commercial", "sale"}],
                lang=lang,
                show_stage=True,
            ),
            _economics_breakdown_advanced_details(result, lang=lang),
        ],
    )
    return [
        state_block,
        *( [warnings_block] if warnings_block is not None else [] ),
        _economics_preview_summary_shell(result, lang=lang),
        _economics_closing_shell(result, lang=lang),
        breakdown_shell,
        _economics_preview_advanced_details(preview, result, lang=lang),
    ]


def _render_runtime_price_bridge_status(scenario, *, lang: str):
    state_key = resolve_runtime_price_bridge_state(scenario)
    record = scenario.runtime_price_bridge
    if state_key == "none" or record is None:
        return []
    applied_at = _format_timestamp_text(record.applied_at)
    final_price = _format_cop(record.applied_price_total_COP, lang)
    body = tr(
        f"workspace.admin.economics.bridge.status.{state_key}",
        lang,
        candidate_key=record.candidate_key,
        final_price=final_price,
        applied_at=applied_at,
    )
    detail_key = (
        "workspace.admin.economics.bridge.status.active.detail_rerun"
        if state_key == "active" and scenario.dirty
        else f"workspace.admin.economics.bridge.status.{state_key}.detail"
    )
    return html.Div(
        id="economics-bridge-status-card",
        className=f"subpanel economics-bridge-status-card economics-bridge-status-{state_key}",
        children=[
            html.H5(tr(f"workspace.admin.economics.bridge.status.{state_key}.title", lang), id="economics-bridge-status-title"),
            html.Div(body, id="economics-bridge-status-body", className="status-line"),
            html.P(tr(detail_key, lang), id="economics-bridge-status-detail", className="section-copy"),
        ],
    )
ADMIN_EXCLUDED_FIELDS = {
    "use_excel_profile",
    "alpha_mix",
    "E_month_kWh",
    "pricing_mode",
    "price_total_COP",
    "include_hw_in_price",
    "include_var_others",
    "price_others_total",
}


@callback(
    Output("admin-access-meta", "data", allow_duplicate=True),
    Input("admin-setup-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("admin-setup-pin-input", "value"),
    State("admin-setup-confirm-input", "value"),
    prevent_initial_call=True,
)
def setup_admin_session(_setup_clicks, session_payload, pin_value, confirm_value):
    client_state, _state, _unlocked = _admin_session(session_payload, None)
    if admin_pin_configured():
        return _admin_locked_meta("workspace.advanced.setup.already_configured", tone="info")
    try:
        pin = _validate_admin_setup_pin(pin_value, confirm_value)
    except ValueError as exc:
        return _admin_locked_meta(str(exc), tone="error")
    set_admin_pin(pin)
    grant_admin_session_access(client_state.session_id)
    return _admin_locked_meta("workspace.advanced.setup.success", tone="success")


@callback(
    Output("admin-access-meta", "data", allow_duplicate=True),
    Input("admin-unlock-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("admin-pin-input", "value"),
    prevent_initial_call=True,
)
def unlock_admin_session(_unlock_clicks, session_payload, pin_value):
    client_state, _state, _unlocked = _admin_session(session_payload, None)
    if not admin_pin_configured():
        return _admin_locked_meta("workspace.advanced.setup.ready", tone="info")
    if not verify_admin_pin(pin_value):
        return _admin_locked_meta("workspace.advanced.locked.invalid", tone="error")
    grant_admin_session_access(client_state.session_id)
    return _admin_locked_meta("workspace.advanced.locked.unlocked", tone="success")


@callback(
    Output("assumptions-advanced-tools-shell", "children"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
    Input("admin-access-meta", "data"),
)
def render_admin_access_shell(session_payload, language_value, access_meta):
    lang = _lang(language_value)
    _client_state, _state, unlocked = _admin_session(session_payload, lang)
    configured = admin_pin_configured()
    meta = access_meta or {}
    return build_admin_access_shell(
        lang=lang,
        configured=configured,
        unlocked=unlocked,
        status_key=meta.get("message_key"),
        tone=str(meta.get("tone") or "neutral"),
    )


@callback(
    Output("admin-show-all", "options"),
    Output("apply-admin-btn", "children"),
    Output("add-economics-cost-row-btn", "children"),
    Output("add-economics-tax-row-btn", "children"),
    Output("add-economics-adjustment-row-btn", "children"),
    Output("add-inverter-row-btn", "children"),
    Output("add-battery-row-btn", "children"),
    Output("add-panel-row-btn", "children"),
    Input("language-selector", "value"),
)
def translate_admin_secure_content(language_value):
    lang = _lang(language_value)
    return (
        [{"label": tr("workbench.assumptions.show_all", lang), "value": "all"}],
        tr("workbench.assumptions.apply", lang),
        tr("workbench.profiles.add_row", lang),
        tr("workbench.profiles.add_row", lang),
        tr("workbench.profiles.add_row", lang),
        tr("workbench.add_row", lang),
        tr("workbench.add_row", lang),
        tr("workbench.add_row", lang),
    )


@callback(
    Output({"type": "profile-table-activate", "table": ALL}, "children"),
    Input("language-selector", "value"),
    State({"type": "profile-table-activate", "table": ALL}, "id"),
)
def translate_profile_table_activators(language_value, activator_ids=None):
    lang = _lang(language_value)
    count = len(activator_ids or PROFILE_ACTIVATOR_TABLE_IDS)
    return [tr("workbench.profiles.preview_chart", lang)] * count


@callback(
    Output("admin-assumption-sections", "children"),
    Output("apply-admin-btn", "disabled"),
    Output("inverter-table-editor", "data"),
    Output("inverter-table-editor", "columns"),
    Output("inverter-table-editor", "tooltip_header"),
    Output("battery-table-editor", "data"),
    Output("battery-table-editor", "columns"),
    Output("battery-table-editor", "tooltip_header"),
    Output("panel-table-editor", "data"),
    Output("panel-table-editor", "columns"),
    Output("panel-table-editor", "tooltip_header"),
    Output("month-profile-editor", "data"),
    Output("month-profile-editor", "columns"),
    Output("month-profile-editor", "tooltip_header"),
    Output("sun-profile-editor", "data"),
    Output("sun-profile-editor", "columns"),
    Output("sun-profile-editor", "tooltip_header"),
    Output("economics-cost-items-editor", "data"),
    Output("economics-cost-items-editor", "columns"),
    Output("economics-cost-items-editor", "tooltip_header"),
    Output("economics-tax-items-editor", "data"),
    Output("economics-tax-items-editor", "columns"),
    Output("economics-tax-items-editor", "tooltip_header"),
    Output("economics-adjustment-items-editor", "data"),
    Output("economics-adjustment-items-editor", "columns"),
    Output("economics-adjustment-items-editor", "tooltip_header"),
    Input("scenario-session-store", "data"),
    Input("admin-show-all", "value", allow_optional=True),
    Input("language-selector", "value"),
    Input("admin-access-meta", "data"),
)
def populate_admin_page(session_payload, show_all_values, language_value, access_meta=None):
    lang = _lang(language_value)
    _access_meta = access_meta or {}
    empty = ([], [], {})
    if _access_meta.get("revision") is None:
        _access_meta = {}
    client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        return (
            render_assumption_sections(
                [],
                show_all=False,
                empty_message=tr("workbench.assumptions.none", lang),
                advanced_label=tr("workbench.assumptions.advanced", lang),
                input_id_type="admin-assumption-input",
                field_card_type="admin-assumption-field-card",
                context_note_type="admin-assumption-context-note",
            ),
            True,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
        )
    active = state.get_scenario()
    if active is None:
        return (
            render_assumption_sections(
                [],
                show_all=False,
                empty_message=tr("workbench.assumptions.none", lang),
                advanced_label=tr("workbench.assumptions.advanced", lang),
                input_id_type="admin-assumption-input",
                field_card_type="admin-assumption-field-card",
                context_note_type="admin-assumption-context-note",
            ),
            True,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
            *empty,
        )

    display_bundle = resolve_workspace_bundle_for_display(client_state.session_id, active.scenario_id, active.config_bundle)
    all_sections = build_assumption_sections(
        display_bundle,
        lang=lang,
        show_all="all" in (show_all_values or []),
        exclude_fields=ADMIN_EXCLUDED_FIELDS,
    )
    partition = partition_assumption_sections(all_sections)
    inverter_columns, inverter_tooltips = build_table_display_columns("inverter_catalog", list(display_bundle.inverter_catalog.columns), lang)
    battery_columns, battery_tooltips = build_table_display_columns("battery_catalog", list(display_bundle.battery_catalog.columns), lang)
    panel_columns, panel_tooltips = build_table_display_columns("panel_catalog", list(display_bundle.panel_catalog.columns), lang)
    month_columns, month_tooltips = build_table_display_columns("month_profile", list(display_bundle.month_profile_table.columns), lang)
    sun_columns, sun_tooltips = build_table_display_columns("sun_profile", list(display_bundle.sun_profile_table.columns), lang)
    economics_cost_columns, economics_cost_tooltips = build_table_display_columns(
        "economics_cost_items",
        list(display_bundle.economics_cost_items_table.columns),
        lang,
    )
    economics_price_columns, economics_price_tooltips = build_table_display_columns(
        "economics_price_items",
        list(display_bundle.economics_price_items_table.columns),
        lang,
    )
    return (
        render_assumption_sections(
            partition.admin_sections,
            show_all="all" in (show_all_values or []),
            empty_message=tr("workbench.assumptions.none", lang),
            advanced_label=tr("workbench.assumptions.advanced", lang),
            input_id_type="admin-assumption-input",
            field_card_type="admin-assumption-field-card",
            context_note_type="admin-assumption-context-note",
        ),
        False,
        display_bundle.inverter_catalog.to_dict("records"),
        inverter_columns,
        inverter_tooltips,
        display_bundle.battery_catalog.to_dict("records"),
        battery_columns,
        battery_tooltips,
        display_bundle.panel_catalog.to_dict("records"),
        panel_columns,
        panel_tooltips,
        display_bundle.month_profile_table.to_dict("records"),
        month_columns,
        month_tooltips,
        display_bundle.sun_profile_table.to_dict("records"),
        sun_columns,
        sun_tooltips,
        economics_cost_items_rows_to_editor(display_bundle.economics_cost_items_table, lang=lang),
        economics_cost_columns,
        economics_cost_tooltips,
        economics_price_items_rows_to_section_editor(
            display_bundle.economics_price_items_table,
            layers=("tax",),
            lang=lang,
        ),
        economics_price_columns,
        economics_price_tooltips,
        economics_price_items_rows_to_section_editor(
            display_bundle.economics_price_items_table,
            layers=("commercial", "sale"),
            lang=lang,
        ),
        economics_price_columns,
        economics_price_tooltips,
    )


@callback(
    Output("admin-preview-candidate-key", "data"),
    Input("scenario-session-store", "data"),
    State("admin-preview-candidate-key", "data"),
)
def sync_admin_preview_candidate_state(session_payload, current_state):
    _client_state, state, unlocked = _admin_session(session_payload, None)
    if not unlocked:
        return _empty_admin_preview_candidate_state()
    active = state.get_scenario()
    if active is None:
        return _empty_admin_preview_candidate_state()
    resolved_state = _resolve_admin_preview_candidate_state(active, current_state)
    return resolved_state


@callback(
    Output("admin-preview-candidate-key", "data", allow_duplicate=True),
    Input("admin-preview-candidate-dropdown", "value", allow_optional=True),
    State("scenario-session-store", "data"),
    State("admin-preview-candidate-key", "data"),
    prevent_initial_call=True,
)
def update_admin_preview_candidate_state(dropdown_value, session_payload, current_state):
    _client_state, state, unlocked = _admin_session(session_payload, None)
    if not unlocked:
        raise PreventUpdate
    active = state.get_scenario()
    if active is None or active.scan_result is None:
        raise PreventUpdate
    selected_candidate_key = str(dropdown_value or "").strip() or None
    if selected_candidate_key not in active.scan_result.candidate_details:
        raise PreventUpdate
    next_state = {
        "scenario_id": active.scenario_id,
        "candidate_key": selected_candidate_key,
        "source": ADMIN_PREVIEW_SOURCE_LOCAL,
    }
    if next_state == (current_state or {}):
        raise PreventUpdate
    return next_state


@callback(
    Output("admin-preview-candidate-dropdown", "options"),
    Output("admin-preview-candidate-dropdown", "value"),
    Output("admin-preview-candidate-dropdown", "disabled"),
    Output("admin-preview-candidate-helper", "children"),
    Output("admin-preview-candidate-meta", "children"),
    Input("scenario-session-store", "data"),
    Input("admin-preview-candidate-key", "data"),
    Input("language-selector", "value"),
)
def render_admin_preview_candidate_selector(session_payload, preview_candidate_state, language_value):
    lang = _lang(language_value)
    _client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        return [], None, True, "", ""
    active = state.get_scenario()
    if active is None:
        return [], None, True, "", ""

    resolved_state = _resolve_admin_preview_candidate_state(active, preview_candidate_state)
    requested_candidate_key = str(resolved_state.get("candidate_key") or "").strip() or None
    selected_candidate_key = _resolve_admin_preview_candidate_key(active, preview_candidate_state)
    state_key = _admin_preview_selector_state_key(active)
    local_candidate_missing = bool(
        resolved_state.get("source") == ADMIN_PREVIEW_SOURCE_LOCAL
        and requested_candidate_key is not None
        and selected_candidate_key is None
    )
    helper_key = {
        PREVIEW_STATE_READY: "workspace.admin.economics.preview.selector.state.ready",
        PREVIEW_STATE_RERUN_REQUIRED: "workspace.admin.economics.preview.selector.state.rerun_required",
        PREVIEW_STATE_CANDIDATE_MISSING: "workspace.admin.economics.preview.selector.state.candidate_missing",
        PREVIEW_STATE_NO_SCAN: "workspace.admin.economics.preview.selector.state.no_scan",
    }.get(state_key, "workspace.admin.economics.preview.selector.state.no_scan")
    if local_candidate_missing:
        helper_key = "workspace.admin.economics.preview.selector.state.candidate_missing"
    if active.scan_result is None:
        return [], None, True, tr(helper_key, lang), ""

    ordered_candidate_keys = [
        str(row["candidate_key"])
        for row in active.scan_result.candidates.to_dict("records")
        if str(row.get("candidate_key", "")).strip() in active.scan_result.candidate_details
    ]
    if not ordered_candidate_keys:
        ordered_candidate_keys = list(active.scan_result.candidate_details)
    options = [
        {
            "label": _admin_preview_candidate_option_label(
                candidate_key,
                active.scan_result.candidate_details[candidate_key],
                lang=lang,
            ),
            "value": candidate_key,
        }
        for candidate_key in ordered_candidate_keys
    ]
    return (
        options,
        selected_candidate_key,
        state_key != PREVIEW_STATE_READY,
        tr(helper_key, lang),
        _admin_preview_candidate_meta(active, selected_candidate_key, lang=lang),
    )


def _resolve_admin_economics_preview(
    active,
    *,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
    admin_preview_candidate_state,
):
    normalized_cost_rows = (
        active.config_bundle.economics_cost_items_table.to_dict("records")
        if economics_cost_rows is None
        else economics_cost_items_rows_from_editor(economics_cost_rows)
    )
    normalized_price_rows = (
        active.config_bundle.economics_price_items_table.to_dict("records")
        if economics_tax_rows is None or economics_adjustment_rows is None
        else economics_price_items_rows_from_split_editors(economics_tax_rows, economics_adjustment_rows)
    )
    preview_candidate_key = _requested_admin_preview_candidate_key(active, admin_preview_candidate_state)
    return resolve_economics_preview(
        active,
        economics_cost_items=normalized_cost_rows,
        economics_price_items=normalized_price_rows,
        candidate_key=preview_candidate_key,
        allow_best_fallback=False,
        candidate_source="selected" if preview_candidate_key is not None else None,
    )


@callback(
    Output("economics-preview-content", "children"),
    Input("scenario-session-store", "data"),
    Input("economics-cost-items-editor", "data", allow_optional=True),
    Input("economics-tax-items-editor", "data", allow_optional=True),
    Input("economics-adjustment-items-editor", "data", allow_optional=True),
    Input("language-selector", "value"),
    Input("admin-preview-candidate-key", "data"),
)
def render_economics_preview(
    session_payload,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
    language_value,
    admin_preview_candidate_state=None,
):
    lang = _lang(language_value)
    _client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        return []
    active = state.get_scenario()
    if active is None:
        return []
    preview = _resolve_admin_economics_preview(
        active,
        economics_cost_rows=economics_cost_rows,
        economics_tax_rows=economics_tax_rows,
        economics_adjustment_rows=economics_adjustment_rows,
        admin_preview_candidate_state=admin_preview_candidate_state,
    )
    return _render_economics_preview(preview, live_warnings=economics_preview_warning_messages(preview), lang=lang)


@callback(
    Output("economics-editors-shell", "className"),
    Output("economics-editors-gate-note", "children"),
    Output("economics-editors-gate-note", "style"),
    Output("economics-editors-panels", "style"),
    Input("scenario-session-store", "data"),
    Input("economics-cost-items-editor", "data", allow_optional=True),
    Input("economics-tax-items-editor", "data", allow_optional=True),
    Input("economics-adjustment-items-editor", "data", allow_optional=True),
    Input("language-selector", "value"),
    Input("admin-preview-candidate-key", "data"),
)
def sync_economics_editor_visibility(
    session_payload,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
    language_value,
    admin_preview_candidate_state=None,
):
    lang = _lang(language_value)
    _client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        return "economics-editors-shell economics-editors-shell-gated", "", {"display": "none"}, {"display": "none"}
    active = state.get_scenario()
    if active is None:
        return "economics-editors-shell economics-editors-shell-gated", "", {"display": "none"}, {"display": "none"}
    preview = _resolve_admin_economics_preview(
        active,
        economics_cost_rows=economics_cost_rows,
        economics_tax_rows=economics_tax_rows,
        economics_adjustment_rows=economics_adjustment_rows,
        admin_preview_candidate_state=admin_preview_candidate_state,
    )
    if preview.state == PREVIEW_STATE_READY and preview.result is not None:
        return "economics-editors-shell", "", {"display": "none"}, {}
    note_key = {
        PREVIEW_STATE_NO_SCAN: "workspace.admin.economics.editors.gated.no_scan",
        PREVIEW_STATE_RERUN_REQUIRED: "workspace.admin.economics.editors.gated.rerun_required",
        PREVIEW_STATE_CANDIDATE_MISSING: "workspace.admin.economics.editors.gated.candidate_missing",
    }.get(preview.state or PREVIEW_STATE_NO_SCAN, "workspace.admin.economics.editors.gated.no_scan")
    return (
        "economics-editors-shell economics-editors-shell-gated",
        tr(note_key, lang),
        {"display": "block"},
        {"display": "none"},
    )


@callback(
    Output("economics-bridge-btn", "disabled"),
    Output("economics-bridge-cta-note", "children"),
    Input("scenario-session-store", "data"),
    Input({"type": "admin-assumption-input", "field": ALL}, "id"),
    Input({"type": "admin-assumption-input", "field": ALL}, "value"),
    Input("inverter-table-editor", "data", allow_optional=True),
    Input("battery-table-editor", "data", allow_optional=True),
    Input("panel-table-editor", "data", allow_optional=True),
    Input("month-profile-editor", "data", allow_optional=True),
    Input("sun-profile-editor", "data", allow_optional=True),
    Input("economics-cost-items-editor", "data", allow_optional=True),
    Input("economics-tax-items-editor", "data", allow_optional=True),
    Input("economics-adjustment-items-editor", "data", allow_optional=True),
    Input("language-selector", "value"),
    Input("admin-preview-candidate-key", "data"),
)
def sync_economics_bridge_cta(
    session_payload,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
    language_value,
    admin_preview_candidate_state=None,
):
    lang = _lang(language_value)
    _client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        return True, ""
    active = state.get_scenario()
    if active is None:
        return True, ""
    preview_candidate_key = _requested_admin_preview_candidate_key(active, admin_preview_candidate_state)
    bridge_context = _resolve_economics_bridge_context(
        active,
        candidate_key=preview_candidate_key,
        assumption_input_ids=assumption_input_ids,
        assumption_values=assumption_values,
        inverter_rows=inverter_rows,
        battery_rows=battery_rows,
        panel_rows=panel_rows,
        month_profile_rows=month_profile_rows,
        sun_profile_rows=sun_profile_rows,
        economics_cost_rows=economics_cost_rows,
        economics_tax_rows=economics_tax_rows,
        economics_adjustment_rows=economics_adjustment_rows,
        applied_at=None,
    )
    return (not bool(bridge_context["eligible"])), _economics_bridge_cta_text(bridge_context, lang=lang)


@callback(
    Output("economics-bridge-status-shell", "children"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def render_runtime_price_bridge_ui(session_payload, language_value):
    lang = _lang(language_value)
    _client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        return []
    active = state.get_scenario()
    if active is None:
        return []
    return _render_runtime_price_bridge_status(active, lang=lang)


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("workbench-status", "children", allow_duplicate=True),
    Input("economics-bridge-btn", "n_clicks", allow_optional=True),
    State("scenario-session-store", "data"),
    State("project-name-input", "value"),
    State({"type": "admin-assumption-input", "field": ALL}, "id"),
    State({"type": "admin-assumption-input", "field": ALL}, "value"),
    State("inverter-table-editor", "data", allow_optional=True),
    State("battery-table-editor", "data", allow_optional=True),
    State("panel-table-editor", "data", allow_optional=True),
    State("month-profile-editor", "data", allow_optional=True),
    State("sun-profile-editor", "data", allow_optional=True),
    State("economics-cost-items-editor", "data", allow_optional=True),
    State("economics-tax-items-editor", "data", allow_optional=True),
    State("economics-adjustment-items-editor", "data", allow_optional=True),
    State("language-selector", "value"),
    State("admin-preview-candidate-key", "data"),
    prevent_initial_call=True,
)
def apply_economics_runtime_price_bridge(
    _bridge_clicks,
    session_payload,
    project_name_value,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
    language_value,
    admin_preview_candidate_state=None,
):
    lang = _lang(language_value)
    client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        raise PreventUpdate
    try:
        active = state.get_scenario()
        if active is None:
            raise PreventUpdate
        preview_candidate_key = _requested_admin_preview_candidate_key(active, admin_preview_candidate_state)
        bridge_context = _resolve_economics_bridge_context(
            active,
            candidate_key=preview_candidate_key,
            assumption_input_ids=assumption_input_ids,
            assumption_values=assumption_values,
            inverter_rows=inverter_rows,
            battery_rows=battery_rows,
            panel_rows=panel_rows,
            month_profile_rows=month_profile_rows,
            sun_profile_rows=sun_profile_rows,
            economics_cost_rows=economics_cost_rows,
            economics_tax_rows=economics_tax_rows,
            economics_adjustment_rows=economics_adjustment_rows,
            applied_at=datetime.now().isoformat(timespec="seconds"),
        )
        if not bridge_context["eligible"]:
            client_state = commit_client_session(client_state, state, bump_revision=False)
            return client_state.to_payload(), _economics_bridge_cta_text(bridge_context, lang=lang)
        prepared = bridge_context["prepared"]
        assert isinstance(prepared, PreparedEconomicsRuntimePriceBridge)
        state = apply_prepared_economics_runtime_price_bridge(
            state,
            active.scenario_id,
            prepared,
            mark_project_dirty=True,
        )
        updated_active = state.get_scenario(active.scenario_id)
        bridge_record = None if updated_active is None else updated_active.runtime_price_bridge
        assert bridge_record is not None
        saved = False
        if _project_is_bound(state):
            state = save_project(state, project_name=_resolved_project_name(project_name_value, state), language=lang)
            saved = True
        client_state = commit_client_session(client_state, state)
        status = _join_status_parts(
            tr(
                "workspace.admin.economics.bridge.applied",
                lang,
                final_price=_format_cop(bridge_record.applied_price_total_COP, lang),
                candidate_key=bridge_record.candidate_key,
            ),
            tr("workbench.run_flow.saved", lang) if saved else "",
            tr("workbench.run_flow.needs_rerun", lang),
        )
        return client_state.to_payload(), status
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc)


@callback(
    Output({"type": "admin-assumption-input", "field": ALL}, "disabled"),
    Output({"type": "admin-assumption-field-card", "field": ALL}, "className"),
    Output({"type": "admin-assumption-context-note", "group": ALL}, "children"),
    Output({"type": "admin-assumption-context-note", "group": ALL}, "style"),
    Input("scenario-session-store", "data"),
    Input({"type": "admin-assumption-input", "field": ALL}, "id"),
    Input({"type": "admin-assumption-input", "field": ALL}, "value"),
    Input("language-selector", "value"),
    State({"type": "admin-assumption-field-card", "field": ALL}, "id"),
    State({"type": "admin-assumption-context-note", "group": ALL}, "id"),
)
def sync_admin_assumption_context_ui(
    session_payload,
    assumption_input_ids,
    assumption_values,
    language_value,
    assumption_card_ids,
    note_ids,
):
    lang = _lang(language_value)
    _client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        raise PreventUpdate
    active = state.get_scenario()
    if active is None:
        return [], [], [], []

    current_config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
    context = assumption_context_map(current_config, panel_catalog=active.config_bundle.panel_catalog, lang=lang)
    disabled_map = dict(context.get("field_disabled") or {})
    emphasis_map = dict(context.get("field_emphasis") or {})
    notes_map = dict(context.get("notes") or {})

    disabled_values = [
        bool(disabled_map.get((component_id or {}).get("field", ""), False))
        for component_id in (assumption_input_ids or [])
    ]
    card_classes = [
        _assumption_card_class(
            str((component_id or {}).get("field", "")),
            disabled=bool(disabled_map.get((component_id or {}).get("field", ""), False)),
            emphasize=bool(emphasis_map.get((component_id or {}).get("field", ""), False)),
        )
        for component_id in (assumption_card_ids or [])
    ]
    note_children = [
        notes_map.get(str((component_id or {}).get("group", "")), "")
        for component_id in (note_ids or [])
    ]
    note_styles = [_assumption_note_style(message) for message in note_children]
    return disabled_values, card_classes, note_children, note_styles
@callback(
    Output("admin-draft-meta", "data"),
    Input("scenario-session-store", "data"),
    Input({"type": "admin-assumption-input", "field": ALL}, "id"),
    Input({"type": "admin-assumption-input", "field": ALL}, "value"),
    Input("inverter-table-editor", "data", allow_optional=True),
    Input("battery-table-editor", "data", allow_optional=True),
    Input("panel-table-editor", "data", allow_optional=True),
    Input("month-profile-editor", "data", allow_optional=True),
    Input("sun-profile-editor", "data", allow_optional=True),
    Input("economics-cost-items-editor", "data", allow_optional=True),
    Input("economics-tax-items-editor", "data", allow_optional=True),
    Input("economics-adjustment-items-editor", "data", allow_optional=True),
    prevent_initial_call=True,
)
def sync_admin_draft(
    session_payload,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
):
    client_state, state, unlocked = _admin_session(session_payload, None)
    if not unlocked:
        raise PreventUpdate
    active = state.get_scenario()
    if active is None:
        raise PreventUpdate
    table_rows = _admin_table_rows_payload(
        inverter_rows,
        battery_rows,
        panel_rows,
        month_profile_rows,
        sun_profile_rows,
        None if economics_cost_rows is None else economics_cost_items_rows_from_editor(economics_cost_rows),
        _combined_price_editor_rows_or_none(economics_tax_rows, economics_adjustment_rows),
    )
    unhydrated_tables = _unhydrated_admin_tables(table_rows)
    if unhydrated_tables:
        logger.debug("sync_admin_draft skipped until hydrated tables=%s", list(unhydrated_tables))
        raise PreventUpdate
    current_config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
    owned_fields = {
        str(component_id.get("field", "")).strip()
        for component_id in (assumption_input_ids or [])
        if str(component_id.get("field", "")).strip()
    }
    overrides = {
        field: current_config.get(field)
        for field in owned_fields
        if _normalize_compare_value(current_config.get(field)) != _normalize_compare_value(active.config_bundle.config.get(field))
    }
    rows_payload, owned_tables = table_draft_rows(
        base_bundle=active.config_bundle,
        table_rows=table_rows,
    )
    logger.debug(
        "sync_admin_draft scenario=%s owned_tables=%s draft_rows=%s",
        active.scenario_id,
        sorted(owned_tables),
        {table_key: len(rows) for table_key, rows in rows_payload.items()},
    )
    draft = upsert_workspace_draft(
        client_state.session_id,
        active.scenario_id,
        config_overrides=overrides,
        owned_config_fields=owned_fields,
        table_rows=rows_payload,
        owned_tables=owned_tables,
        project_slug=state.project_slug,
    )
    if draft is not None and state.project_slug:
        bind_workspace_draft_project(client_state.session_id, active.scenario_id, state.project_slug)
    return {"revision": 0 if draft is None else draft.revision}


@callback(
    Output("active-profile-table-state", "data"),
    Input({"type": "profile-table-activate", "table": ALL}, "n_clicks"),
    Input("month-profile-editor", "active_cell", allow_optional=True),
    Input("sun-profile-editor", "active_cell", allow_optional=True),
    State({"type": "profile-table-activate", "table": ALL}, "id"),
    State("active-profile-table-state", "data"),
    prevent_initial_call=True,
)
def sync_active_profile_table(
    _activator_clicks,
    month_active_cell,
    sun_active_cell,
    activator_ids,
    active_state,
):
    trigger = ctx.triggered_id
    current_table_id = str((active_state or {}).get("table_id") or "").strip() or None
    activator_clicks = {
        str((component_id or {}).get("table", "")).strip(): int(clicks or 0)
        for component_id, clicks in zip(activator_ids or [], _activator_clicks or [])
        if str((component_id or {}).get("table", "")).strip()
    }
    active_cells = {
        "month-profile-editor": month_active_cell,
        "sun-profile-editor": sun_active_cell,
    }
    if isinstance(trigger, dict) and trigger.get("type") == "profile-table-activate":
        table_id = str(trigger.get("table", "")).strip() or None
        if table_id is None:
            raise PreventUpdate
        if activator_clicks.get(table_id, 0) <= 0:
            raise PreventUpdate
        if table_id == current_table_id:
            return _active_profile_table_state()
        return _active_profile_table_state(table_id)
    if isinstance(trigger, str) and trigger in active_cells:
        if not active_cells.get(trigger) or trigger == current_table_id:
            raise PreventUpdate
        return _active_profile_table_state(trigger)
    raise PreventUpdate


@callback(
    Output("profile-main-chart-panel", "style"),
    Output("profile-main-chart-title", "children"),
    Output("profile-main-chart-subtitle", "children"),
    Output("profile-main-chart-graph", "figure"),
    Output("month-profile-card", "className"),
    Output("sun-profile-card", "className"),
    Input("active-profile-table-state", "data"),
    Input("month-profile-editor", "data", allow_optional=True),
    Input("month-profile-editor", "columns", allow_optional=True),
    Input("sun-profile-editor", "data", allow_optional=True),
    Input("sun-profile-editor", "columns", allow_optional=True),
    Input("language-selector", "value"),
)
def render_active_profile_chart(
    active_state,
    month_rows,
    month_columns,
    sun_rows,
    sun_columns,
    language_value,
):
    lang = _lang(language_value)
    active_table_id = str((active_state or {}).get("table_id") or "").strip() or None
    card_classes = _profile_card_class_names(active_table_id)
    hidden_style = {"display": "none"}
    empty_figure = go.Figure()
    if active_table_id is None:
        return (
            hidden_style,
            "",
            "",
            empty_figure,
            *card_classes,
        )
    table_rows = {
        "month-profile-editor": month_rows,
        "sun-profile-editor": sun_rows,
    }
    table_columns = {
        "month-profile-editor": month_columns,
        "sun-profile-editor": sun_columns,
    }
    render = build_profile_chart(active_table_id, table_rows.get(active_table_id), table_columns.get(active_table_id), lang)
    visible_style = {"display": "grid"}
    return (
        visible_style,
        render.title,
        render.subtitle,
        render.figure,
        *card_classes,
    )


@callback(
    Output("inverter-table-editor", "data", allow_duplicate=True),
    Input("add-inverter-row-btn", "n_clicks", allow_optional=True),
    State("inverter-table-editor", "data", allow_optional=True),
    prevent_initial_call=True,
)
def add_inverter_row(n_clicks, table_rows):
    if not n_clicks:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append({column: "" for column in INVERTER_REQUIRED_COLUMNS})
    return rows


@callback(
    Output("battery-table-editor", "data", allow_duplicate=True),
    Input("add-battery-row-btn", "n_clicks", allow_optional=True),
    State("battery-table-editor", "data", allow_optional=True),
    prevent_initial_call=True,
)
def add_battery_row(n_clicks, table_rows):
    if not n_clicks:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append({column: "" for column in BATTERY_REQUIRED_COLUMNS})
    return rows


@callback(
    Output("panel-table-editor", "data", allow_duplicate=True),
    Input("add-panel-row-btn", "n_clicks", allow_optional=True),
    State("panel-table-editor", "data", allow_optional=True),
    prevent_initial_call=True,
)
def add_panel_row(n_clicks, table_rows):
    if not n_clicks:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append({column: "" for column in PANEL_REQUIRED_COLUMNS})
    return rows


@callback(
    Output("economics-cost-items-editor", "data", allow_duplicate=True),
    Input("add-economics-cost-row-btn", "n_clicks", allow_optional=True),
    State("economics-cost-items-editor", "data", allow_optional=True),
    State("economics-cost-items-editor", "columns", allow_optional=True),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def add_economics_cost_row(n_clicks, table_rows, table_columns, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    blank_row["enabled"] = "Yes" if lang == "en" else "Sí"
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("economics-tax-items-editor", "data", allow_duplicate=True),
    Input("add-economics-tax-row-btn", "n_clicks", allow_optional=True),
    State("economics-tax-items-editor", "data", allow_optional=True),
    State("economics-tax-items-editor", "columns", allow_optional=True),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def add_economics_tax_row(n_clicks, table_rows, table_columns, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    blank_row["layer"] = economics_ui_label("layer", "tax", lang=lang)
    blank_row["method"] = economics_ui_label("method", "tax_pct", lang=lang)
    blank_row["enabled"] = "Yes" if lang == "en" else "Sí"
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("economics-adjustment-items-editor", "data", allow_duplicate=True),
    Input("add-economics-adjustment-row-btn", "n_clicks", allow_optional=True),
    State("economics-adjustment-items-editor", "data", allow_optional=True),
    State("economics-adjustment-items-editor", "columns", allow_optional=True),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def add_economics_adjustment_row(n_clicks, table_rows, table_columns, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    blank_row["layer"] = economics_ui_label("layer", "commercial", lang=lang)
    blank_row["method"] = economics_ui_label("method", "markup_pct", lang=lang)
    blank_row["enabled"] = "Yes" if lang == "en" else "Sí"
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("workbench-status", "children", allow_duplicate=True),
    Input("apply-admin-btn", "n_clicks", allow_optional=True),
    State("scenario-session-store", "data"),
    State("project-name-input", "value"),
    State({"type": "admin-assumption-input", "field": ALL}, "id"),
    State({"type": "admin-assumption-input", "field": ALL}, "value"),
    State("inverter-table-editor", "data", allow_optional=True),
    State("battery-table-editor", "data", allow_optional=True),
    State("panel-table-editor", "data", allow_optional=True),
    State("month-profile-editor", "data", allow_optional=True),
    State("sun-profile-editor", "data", allow_optional=True),
    State("economics-cost-items-editor", "data", allow_optional=True),
    State("economics-tax-items-editor", "data", allow_optional=True),
    State("economics-adjustment-items-editor", "data", allow_optional=True),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def apply_admin_edits(
    _apply_clicks,
    session_payload,
    project_name_value,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_tax_rows,
    economics_adjustment_rows,
    language_value,
):
    lang = _lang(language_value)
    client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        raise PreventUpdate
    try:
        active = state.get_scenario()
        if active is None:
            raise PreventUpdate
        table_rows = _admin_table_rows_payload(
            inverter_rows,
            battery_rows,
            panel_rows,
            month_profile_rows,
            sun_profile_rows,
            None if economics_cost_rows is None else economics_cost_items_rows_from_editor(economics_cost_rows),
            _combined_price_editor_rows_or_none(economics_tax_rows, economics_adjustment_rows),
        )
        unhydrated_tables = _unhydrated_admin_tables(table_rows)
        if unhydrated_tables:
            logger.debug("apply_admin_edits skipped until hydrated tables=%s", list(unhydrated_tables))
            raise PreventUpdate
        current_config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
        owned_fields = {
            str(component_id.get("field", "")).strip()
            for component_id in (assumption_input_ids or [])
            if str(component_id.get("field", "")).strip()
        }
        overrides = {
            field: current_config.get(field)
            for field in owned_fields
            if _normalize_compare_value(current_config.get(field)) != _normalize_compare_value(active.config_bundle.config.get(field))
        }
        rows_payload, owned_tables = table_draft_rows(
            base_bundle=active.config_bundle,
            table_rows=table_rows,
        )
        logger.debug(
            "apply_admin_edits scenario=%s owned_tables=%s draft_rows=%s",
            active.scenario_id,
            sorted(owned_tables),
            {table_key: len(rows) for table_key, rows in rows_payload.items()},
        )
        upsert_workspace_draft(
            client_state.session_id,
            active.scenario_id,
            config_overrides=overrides,
            owned_config_fields=owned_fields,
            table_rows=rows_payload,
            owned_tables=owned_tables,
            project_slug=state.project_slug,
        )
        state, updated = apply_workspace_draft_to_state(
            state,
            session_id=client_state.session_id,
            scenario_id=active.scenario_id,
        )
        saved = False
        if _project_is_bound(state):
            state = save_project(state, project_name=_resolved_project_name(project_name_value, state), language=lang)
            saved = True
        client_state = commit_client_session(client_state, state)
        status = _join_status_parts(
            tr("workbench.run_flow.applied", lang),
            tr("workbench.run_flow.saved", lang) if saved else "",
            tr("workbench.run_flow.needs_rerun", lang) if updated.dirty else "",
        )
        return client_state.to_payload(), status
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc)
