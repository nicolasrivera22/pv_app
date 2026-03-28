from __future__ import annotations

import logging
import time

from dash import ALL, Input, Output, State, callback, ctx, dash_table, html
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.graph_objects as go

from components.admin_view import build_admin_access_shell
from components.assumption_editor import render_assumption_sections
from components.ui_mode_gate import render_ui_mode_gate
from .admin_access import (
    admin_pin_configured,
    grant_admin_session_access,
    is_admin_session_unlocked,
    set_admin_pin,
    verify_admin_pin,
)
from .economics_tables import (
    economics_cost_items_rows_from_editor,
    economics_cost_items_rows_to_editor,
    economics_price_items_rows_from_editor,
    economics_price_items_rows_to_editor,
)
from .economics_engine import (
    PREVIEW_STATE_NO_SCAN,
    PREVIEW_STATE_READY,
    EconomicsPreviewResult,
    resolve_economics_preview,
)
from .i18n import tr
from .profile_charts import build_profile_chart
from .project_io import save_project
from .session_state import commit_client_session, resolve_client_session
from .ui_schema import assumption_context_map, build_assumption_sections, build_table_display_columns, format_metric
from .validation import (
    BATTERY_REQUIRED_COLUMNS,
    INVERTER_REQUIRED_COLUMNS,
    PANEL_REQUIRED_COLUMNS,
)
from .workbench_ui import collect_config_updates, workbench_status_message
from .workspace_actions import (
    apply_workspace_draft_to_state,
    resolve_workspace_bundle_for_display,
    table_draft_rows,
)
from .workspace_drafts import bind_workspace_draft_project, upsert_workspace_draft
from .workspace_partitions import partition_assumption_sections
from .ui_mode import PAGE_ADMIN, resolve_page_access, resolve_ui_mode_from_payload

logger = logging.getLogger(__name__)


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


def _admin_session(payload, language_value: str | None):
    client_state, state = _session(payload, language_value)
    return client_state, state, is_admin_session_unlocked(client_state.session_id)


def _admin_page_access(payload) -> object:
    return resolve_page_access(PAGE_ADMIN, resolve_ui_mode_from_payload(payload))


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
        raise ValueError("workspace.admin.setup.empty")
    if not pin.isdigit():
        raise ValueError("workspace.admin.setup.digits_only")
    if len(pin) < 4:
        raise ValueError("workspace.admin.setup.too_short")
    if pin != confirm:
        raise ValueError("workspace.admin.setup.mismatch")
    return pin


PROFILE_MAIN_TABLE_IDS = (
    "month-profile-editor",
    "sun-profile-editor",
)
PROFILE_SECONDARY_TABLE_IDS = (
    "price-kwp-editor",
    "price-kwp-others-editor",
)
PROFILE_TABLE_IDS = (*PROFILE_MAIN_TABLE_IDS, *PROFILE_SECONDARY_TABLE_IDS)
PROFILE_ACTIVATOR_TABLE_IDS = (
    "month-profile-editor",
    "sun-profile-editor",
    "price-kwp-editor",
    "price-kwp-others-editor",
)
PROFILE_TABLE_VISIBILITY_PANELS = {
    "price-kwp-editor": "price-kwp-panel",
    "price-kwp-others-editor": "price-kwp-others-panel",
}
PROFILE_CARD_BASE_CLASS = "profile-table-card-shell"
PROFILE_CARD_ACTIVE_CLASS = f"{PROFILE_CARD_BASE_CLASS} profile-table-card-active"
ADMIN_REQUIRED_TABLE_KEYS = (
    "inverter_catalog",
    "battery_catalog",
    "panel_catalog",
    "month_profile",
    "sun_profile",
    "economics_cost_items",
    "economics_price_items",
    "cop_kwp_table",
    "cop_kwp_table_others",
)


def _project_is_bound(state) -> bool:
    return bool(str(state.project_slug or "").strip())


def _resolved_project_name(project_name_value, state) -> str:
    return (project_name_value or state.project_name or state.project_slug or "").strip()


def _join_status_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _admin_table_rows_payload(
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_price_rows,
    price_kwp_rows,
    price_kwp_others_rows,
) -> dict[str, list[dict[str, object]] | None]:
    return {
        "inverter_catalog": inverter_rows,
        "battery_catalog": battery_rows,
        "panel_catalog": panel_rows,
        "month_profile": month_profile_rows,
        "sun_profile": sun_profile_rows,
        "economics_cost_items": economics_cost_rows,
        "economics_price_items": economics_price_rows,
        "cop_kwp_table": price_kwp_rows,
        "cop_kwp_table_others": price_kwp_others_rows,
    }


def _unhydrated_admin_tables(table_rows: dict[str, list[dict[str, object]] | None]) -> tuple[str, ...]:
    return tuple(table_key for table_key in ADMIN_REQUIRED_TABLE_KEYS if table_rows.get(table_key) is None)


def _active_profile_table_state(table_id: str | None = None) -> dict[str, str | None]:
    if table_id is None:
        return {"table_id": None}
    normalized = str(table_id).strip()
    return {"table_id": normalized or None}


def _assumption_note_style(message: str) -> dict[str, str]:
    return {"display": "block"} if str(message or "").strip() else {"display": "none"}


def _assumption_card_class(field_key: str, *, disabled: bool = False, emphasize: bool = False) -> str:
    classes = ["field-card"]
    if field_key in {"pricing_mode", "include_hw_in_price", "include_var_others", "price_total_COP", "price_others_total"}:
        classes.append("precios-card")
    if disabled:
        classes.append("field-card-disabled")
    if emphasize and not disabled:
        classes.append("field-card-highlight")
    return " ".join(dict.fromkeys(classes))


def _is_hidden_style(style: dict | None) -> bool:
    return str((style or {}).get("display", "block")).strip().lower() == "none"


def _hidden_profile_tables(
    price_kwp_style: dict | None,
    price_kwp_others_style: dict | None,
) -> set[str]:
    panel_styles = {
        "price-kwp-panel": price_kwp_style,
        "price-kwp-others-panel": price_kwp_others_style,
    }
    return {
        table_id
        for table_id, panel_id in PROFILE_TABLE_VISIBILITY_PANELS.items()
        if _is_hidden_style(panel_styles.get(panel_id))
    }


def _profile_card_class_names(active_table_id: str | None, hidden_tables: set[str] | None = None) -> tuple[str, ...]:
    hidden = hidden_tables or set()
    classes: list[str] = []
    for table_id in PROFILE_TABLE_IDS:
        is_active = table_id == active_table_id and table_id not in hidden
        classes.append(PROFILE_CARD_ACTIVE_CLASS if is_active else PROFILE_CARD_BASE_CLASS)
    return tuple(classes)


def _resolve_pricing_inputs(assumption_input_ids, assumption_values, cfg):
    pricing_mode = str(cfg.get("pricing_mode", "variable")).strip().lower()
    include_others = cfg.get("include_var_others", False)
    for input_id, value in zip(assumption_input_ids or [], assumption_values or []):
        field = (input_id or {}).get("field", "") if isinstance(input_id, dict) else ""
        if field == "pricing_mode" and value is not None:
            pricing_mode = str(value).strip().lower()
        elif field == "include_var_others" and value is not None:
            include_others = value
    return pricing_mode, include_others


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


def _economics_summary_card(label: str, value: str) -> html.Div:
    return html.Div(
        className="scan-summary-card",
        children=[
            html.Span(label, className="scan-summary-label"),
            html.Span(value, className="scan-summary-value"),
        ],
    )


def _economics_breakdown_formula(row: dict[str, object], *, lang: str) -> str:
    rule = str(row.get("rule") or "")
    multiplier = float(row.get("multiplier", 0.0) or 0.0)
    unit_rate = float(row.get("unit_rate_COP", 0.0) or 0.0)
    base_amount = row.get("base_amount_COP")
    quantity_labels = {
        "en": {
            "per_kwp": "kWp",
            "per_panel": "panels",
            "per_inverter": "inverter(s)",
            "per_battery_kwh": "battery kWh",
        },
        "es": {
            "per_kwp": "kWp",
            "per_panel": "paneles",
            "per_inverter": "inversor(es)",
            "per_battery_kwh": "kWh batería",
        },
    }
    if rule == "markup_pct":
        return f"{_format_percent(unit_rate)} x {_format_cop(None if base_amount is None else float(base_amount), lang)}"
    if rule == "fixed_project":
        return f"1 x {_format_cop(unit_rate, lang)}"
    unit = quantity_labels.get(lang, quantity_labels["es"]).get(rule, "")
    quantity = _format_number(multiplier, decimals=3)
    unit_suffix = f" {unit}" if unit else ""
    return f"{quantity}{unit_suffix} x {_format_cop(unit_rate, lang)}"


def _economics_breakdown_rows(rows, *, lang: str) -> list[dict[str, object]]:
    return [
        {
            "source_table": row.source_table,
            "source_row": row.source_row,
            "stage_or_layer": row.stage_or_layer,
            "name": row.name,
            "rule": row.rule,
            "calculation": _economics_breakdown_formula(
                {
                    "rule": row.rule,
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


def _economics_breakdown_table(table_id: str, rows: list[dict[str, object]], *, lang: str):
    columns, tooltip_header = build_table_display_columns(
        "economics_breakdown",
        [
            "source_table",
            "source_row",
            "stage_or_layer",
            "name",
            "rule",
            "calculation",
            "multiplier",
            "unit_rate_COP",
            "base_amount_COP",
            "line_amount_COP",
            "notes",
        ],
        lang,
    )
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
        },
        style_header={
            "backgroundColor": "var(--color-primary-soft)",
            "color": "var(--color-text-primary)",
            "fontWeight": "bold",
        },
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
        className="subpanel economics-preview-state-shell",
        children=[
            html.H5(title, id="economics-preview-state-title"),
            html.Div(body, id="economics-preview-status", className="status-line economics-preview-status"),
            html.P(detail, id="economics-preview-state-detail", className="section-copy"),
        ],
    )


def _economics_quantity_card(label: str, value: str) -> html.Div:
    return html.Div(
        className="field-card economics-preview-quantity-card",
        children=[
            html.Span(label, className="scan-summary-label"),
            html.Strong(value, className="scan-summary-value"),
        ],
    )


def _economics_preview_quantities(result, *, lang: str) -> html.Div:
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
                    _economics_quantity_card(tr("workspace.admin.economics.preview.quantity.candidate", lang), quantities.candidate_key),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.kwp", lang),
                        f"{_format_number(quantities.kWp, decimals=3)} kWp",
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.panel_count", lang),
                        _format_number(quantities.panel_count, decimals=0),
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.inverter_count", lang),
                        _format_number(quantities.inverter_count, decimals=0),
                    ),
                    _economics_quantity_card(
                        tr("workspace.admin.economics.preview.quantity.battery_kwh", lang),
                        f"{_format_number(quantities.battery_kwh, decimals=1)} kWh",
                    ),
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
            "economics-preview-flow-commercial-adjustment",
            tr("workspace.admin.economics.preview.summary.commercial_adjustment", lang),
            tr("workspace.admin.economics.preview.flow.formula.commercial_adjustment", lang),
            _format_cop(result.commercial_adjustment_COP, lang),
        ),
        (
            "economics-preview-flow-commercial-offer",
            tr("workspace.admin.economics.preview.summary.commercial_offer", lang),
            tr("workspace.admin.economics.preview.flow.formula.commercial_offer", lang),
            _format_cop(result.commercial_offer_COP, lang),
        ),
        (
            "economics-preview-flow-sale-adjustment",
            tr("workspace.admin.economics.preview.summary.sale_adjustment", lang),
            tr("workspace.admin.economics.preview.flow.formula.sale_adjustment", lang),
            _format_cop(result.sale_adjustment_COP, lang),
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


def _economics_breakdown_group(
    *,
    group_id: str,
    title: str,
    subtotal_label: str,
    subtotal_value: float | None,
    rows,
    lang: str,
) -> html.Div:
    table_rows = _economics_breakdown_rows(rows, lang=lang)
    children = [
        html.Div(
            className="section-head",
            children=[
                html.H5(title, id=f"{group_id}-title"),
                html.Div(f"{subtotal_label}: {_format_cop(subtotal_value, lang)}", id=f"{group_id}-total", className="status-line"),
            ],
        )
    ]
    if table_rows:
        children.append(_economics_breakdown_table(f"{group_id}-table", table_rows, lang=lang))
    else:
        children.append(html.Div(tr("workspace.admin.economics.preview.breakdown.empty", lang), className="status-line"))
    return html.Div(id=f"{group_id}-shell", className="profile-table-subsection economics-breakdown-group-shell", children=children)


def _render_economics_preview(preview: EconomicsPreviewResult, *, lang: str):
    state_block = _economics_preview_state_block(preview, lang=lang)
    if preview.state != PREVIEW_STATE_READY or preview.result is None:
        return [state_block]

    result = preview.result
    summary_cards = html.Div(
        id="economics-summary-cards",
        className="kpi-grid",
        children=[
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.technical", lang),
                _format_cop(result.technical_subtotal_COP, lang),
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.installed", lang),
                _format_cop(result.installed_subtotal_COP, lang),
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.cost_total", lang),
                _format_cop(result.cost_total_COP, lang),
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.commercial_adjustment", lang),
                _format_cop(result.commercial_adjustment_COP, lang),
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.commercial_offer", lang),
                _format_cop(result.commercial_offer_COP, lang),
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.sale_adjustment", lang),
                _format_cop(result.sale_adjustment_COP, lang),
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.final_price", lang),
                _format_cop(result.final_price_COP, lang),
            ),
            _economics_summary_card(
                tr("workspace.admin.economics.preview.summary.final_price_per_kwp", lang),
                _format_cop_per_kwp(result.final_price_per_kwp_COP, lang),
            ),
        ],
    )
    breakdown_shell = html.Div(
        id="economics-breakdown-shell",
        className="subpanel economics-breakdown-shell",
        children=[
            html.H5(tr("workspace.admin.economics.preview.breakdown.title", lang), id="economics-breakdown-title"),
            _economics_breakdown_group(
                group_id="economics-breakdown-technical",
                title=tr("workspace.admin.economics.preview.breakdown.group.technical", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.technical", lang),
                subtotal_value=result.technical_subtotal_COP,
                rows=[row for row in result.cost_rows if row.stage_or_layer == "technical"],
                lang=lang,
            ),
            _economics_breakdown_group(
                group_id="economics-breakdown-installed",
                title=tr("workspace.admin.economics.preview.breakdown.group.installed", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.installed", lang),
                subtotal_value=result.installed_subtotal_COP,
                rows=[row for row in result.cost_rows if row.stage_or_layer == "installed"],
                lang=lang,
            ),
            _economics_breakdown_group(
                group_id="economics-breakdown-commercial",
                title=tr("workspace.admin.economics.preview.breakdown.group.commercial", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.commercial_adjustment", lang),
                subtotal_value=result.commercial_adjustment_COP,
                rows=[row for row in result.price_rows if row.stage_or_layer == "commercial"],
                lang=lang,
            ),
            _economics_breakdown_group(
                group_id="economics-breakdown-sale",
                title=tr("workspace.admin.economics.preview.breakdown.group.sale", lang),
                subtotal_label=tr("workspace.admin.economics.preview.summary.sale_adjustment", lang),
                subtotal_value=result.sale_adjustment_COP,
                rows=[row for row in result.price_rows if row.stage_or_layer == "sale"],
                lang=lang,
            ),
        ],
    )
    return [
        state_block,
        _economics_preview_quantities(result, lang=lang),
        _economics_preview_flow(result, lang=lang),
        summary_cards,
        breakdown_shell,
    ]


ADMIN_EXCLUDED_FIELDS = {"use_excel_profile", "alpha_mix", "E_month_kWh"}


@callback(
    Output("admin-access-meta", "data", allow_duplicate=True),
    Input("admin-setup-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("admin-setup-pin-input", "value"),
    State("admin-setup-confirm-input", "value"),
    prevent_initial_call=True,
)
def setup_admin_session(_setup_clicks, session_payload, pin_value, confirm_value):
    if not _admin_page_access(session_payload).allowed:
        raise PreventUpdate
    client_state, _state, _unlocked = _admin_session(session_payload, None)
    if admin_pin_configured():
        return _admin_locked_meta("workspace.admin.setup.already_configured", tone="info")
    try:
        pin = _validate_admin_setup_pin(pin_value, confirm_value)
    except ValueError as exc:
        return _admin_locked_meta(str(exc), tone="error")
    set_admin_pin(pin)
    grant_admin_session_access(client_state.session_id)
    return _admin_locked_meta("workspace.admin.setup.success", tone="success")


@callback(
    Output("admin-access-meta", "data", allow_duplicate=True),
    Input("admin-unlock-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("admin-pin-input", "value"),
    prevent_initial_call=True,
)
def unlock_admin_session(_unlock_clicks, session_payload, pin_value):
    if not _admin_page_access(session_payload).allowed:
        raise PreventUpdate
    client_state, _state, _unlocked = _admin_session(session_payload, None)
    if not admin_pin_configured():
        return _admin_locked_meta("workspace.admin.setup.ready", tone="info")
    if not verify_admin_pin(pin_value):
        return _admin_locked_meta("workspace.admin.locked.invalid", tone="error")
    grant_admin_session_access(client_state.session_id)
    return _admin_locked_meta("workspace.admin.locked.unlocked", tone="success")


@callback(
    Output("admin-access-shell", "children"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
    Input("admin-access-meta", "data"),
)
def render_admin_access_shell(session_payload, language_value, access_meta):
    lang = _lang(language_value)
    access = _admin_page_access(session_payload)
    if access.is_gated:
        return render_ui_mode_gate(access, lang=lang, component_id="admin-mode-gate")
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
    Output("admin-page-title", "children"),
    Output("admin-page-copy", "children"),
    Output("admin-gating-note", "children"),
    Input("language-selector", "value"),
)
def translate_admin_page_header(language_value):
    lang = _lang(language_value)
    return (
        tr("workspace.admin.title", lang),
        tr("workspace.admin.copy", lang),
        tr("workspace.admin.note", lang),
    )


@callback(
    Output("admin-show-all", "options"),
    Output("apply-admin-btn", "children"),
    Output("add-price-kwp-row-btn", "children"),
    Output("add-price-kwp-others-row-btn", "children"),
    Output("add-economics-cost-row-btn", "children"),
    Output("add-economics-price-row-btn", "children"),
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
    Output("price-kwp-editor", "data"),
    Output("price-kwp-editor", "columns"),
    Output("price-kwp-editor", "tooltip_header"),
    Output("price-kwp-others-editor", "data"),
    Output("price-kwp-others-editor", "columns"),
    Output("price-kwp-others-editor", "tooltip_header"),
    Output("economics-cost-items-editor", "data"),
    Output("economics-cost-items-editor", "columns"),
    Output("economics-cost-items-editor", "tooltip_header"),
    Output("economics-price-items-editor", "data"),
    Output("economics-price-items-editor", "columns"),
    Output("economics-price-items-editor", "tooltip_header"),
    Input("scenario-session-store", "data"),
    Input("admin-show-all", "value", allow_optional=True),
    Input("language-selector", "value"),
    Input("admin-access-meta", "data"),
)
def populate_admin_page(session_payload, show_all_values, language_value, access_meta=None):
    lang = _lang(language_value)
    _access_meta = access_meta or {}
    if not _admin_page_access(session_payload).allowed:
        empty = ([], [], {})
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
            *empty,
        )
    client_state, state, unlocked = _admin_session(session_payload, lang)
    empty = ([], [], {})
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
    kwp_columns, kwp_tooltips = build_table_display_columns("cop_kwp", list(display_bundle.cop_kwp_table.columns), lang)
    kwp_other_columns, kwp_other_tooltips = build_table_display_columns("cop_kwp_others", list(display_bundle.cop_kwp_table_others.columns), lang)
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
        display_bundle.cop_kwp_table.to_dict("records"),
        kwp_columns,
        kwp_tooltips,
        display_bundle.cop_kwp_table_others.to_dict("records"),
        kwp_other_columns,
        kwp_other_tooltips,
        economics_cost_items_rows_to_editor(display_bundle.economics_cost_items_table),
        economics_cost_columns,
        economics_cost_tooltips,
        economics_price_items_rows_to_editor(display_bundle.economics_price_items_table),
        economics_price_columns,
        economics_price_tooltips,
    )


@callback(
    Output("economics-preview-content", "children"),
    Input("scenario-session-store", "data"),
    Input("economics-cost-items-editor", "data", allow_optional=True),
    Input("economics-price-items-editor", "data", allow_optional=True),
    Input("language-selector", "value"),
)
def render_economics_preview(session_payload, economics_cost_rows, economics_price_rows, language_value):
    lang = _lang(language_value)
    if not _admin_page_access(session_payload).allowed:
        return []
    _client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        return []
    active = state.get_scenario()
    if active is None:
        return []
    normalized_cost_rows = (
        active.config_bundle.economics_cost_items_table.to_dict("records")
        if economics_cost_rows is None
        else economics_cost_items_rows_from_editor(economics_cost_rows)
    )
    normalized_price_rows = (
        active.config_bundle.economics_price_items_table.to_dict("records")
        if economics_price_rows is None
        else economics_price_items_rows_from_editor(economics_price_rows)
    )
    preview = resolve_economics_preview(
        active,
        economics_cost_items=normalized_cost_rows,
        economics_price_items=normalized_price_rows,
    )
    return _render_economics_preview(preview, lang=lang)


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
    if not _admin_page_access(session_payload).allowed:
        raise PreventUpdate
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
    Output("price-kwp-panel", "style"),
    Output("price-kwp-others-panel", "style"),
    Output("price-kwp-placeholder", "children"),
    Output("price-kwp-placeholder", "style"),
    Output("price-kwp-others-placeholder", "children"),
    Output("price-kwp-others-placeholder", "style"),
    Input("scenario-session-store", "data"),
    Input({"type": "admin-assumption-input", "field": ALL}, "id"),
    Input({"type": "admin-assumption-input", "field": ALL}, "value"),
    Input("language-selector", "value"),
)
def toggle_pricing_table_visibility(session_payload, assumption_input_ids, assumption_values, language_value):
    lang = _lang(language_value)
    if not _admin_page_access(session_payload).allowed:
        hidden = {"display": "none"}
        placeholder_hidden = {"display": "none"}
        return hidden, hidden, "", placeholder_hidden, "", placeholder_hidden
    client_state, state, unlocked = _admin_session(session_payload, lang)
    if not unlocked:
        hidden = {"display": "none"}
        placeholder_hidden = {"display": "none"}
        return hidden, hidden, "", placeholder_hidden, "", placeholder_hidden
    active = state.get_scenario()
    if active is None:
        hidden = {"display": "none"}
        placeholder_hidden = {"display": "none"}
        return hidden, hidden, "", placeholder_hidden, "", placeholder_hidden

    display_bundle = resolve_workspace_bundle_for_display(client_state.session_id, active.scenario_id, active.config_bundle)
    pricing_mode, include_others = _resolve_pricing_inputs(assumption_input_ids, assumption_values, display_bundle.config)

    price_kwp_style = {"display": "block"}
    kwp_placeholder_children = ""
    kwp_placeholder_style = {"display": "none"}
    if pricing_mode == "total":
        price_kwp_style = {"display": "none"}
        kwp_placeholder_children = tr("workbench.profiles.placeholder.price_hidden", lang)
        kwp_placeholder_style = {"display": "block"}

    price_others_style = {"display": "block"}
    others_placeholder_children = ""
    others_placeholder_style = {"display": "none"}
    if not include_others:
        price_others_style = {"display": "none"}
        others_placeholder_children = tr("workbench.profiles.placeholder.price_others_hidden", lang)
        others_placeholder_style = {"display": "block"}

    return (
        price_kwp_style,
        price_others_style,
        kwp_placeholder_children,
        kwp_placeholder_style,
        others_placeholder_children,
        others_placeholder_style,
    )


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
    Input("price-kwp-editor", "data", allow_optional=True),
    Input("price-kwp-others-editor", "data", allow_optional=True),
    Input("economics-cost-items-editor", "data", allow_optional=True),
    Input("economics-price-items-editor", "data", allow_optional=True),
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
    price_kwp_rows,
    price_kwp_others_rows,
    economics_cost_rows,
    economics_price_rows,
):
    if not _admin_page_access(session_payload).allowed:
        raise PreventUpdate
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
        None if economics_price_rows is None else economics_price_items_rows_from_editor(economics_price_rows),
        price_kwp_rows,
        price_kwp_others_rows,
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
    Input("price-kwp-editor", "active_cell", allow_optional=True),
    Input("price-kwp-others-editor", "active_cell", allow_optional=True),
    State({"type": "profile-table-activate", "table": ALL}, "id"),
    State("active-profile-table-state", "data"),
    prevent_initial_call=True,
)
def sync_active_profile_table(
    _activator_clicks,
    month_active_cell,
    sun_active_cell,
    price_active_cell,
    price_others_active_cell,
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
        "price-kwp-editor": price_active_cell,
        "price-kwp-others-editor": price_others_active_cell,
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
    Output("active-profile-table-state", "data", allow_duplicate=True),
    Input("active-profile-table-state", "data"),
    Input("price-kwp-panel", "style", allow_optional=True),
    Input("price-kwp-others-panel", "style", allow_optional=True),
    prevent_initial_call=True,
)
def sanitize_active_profile_table(
    active_state,
    price_kwp_style,
    price_kwp_others_style,
):
    active_table_id = str((active_state or {}).get("table_id") or "").strip() or None
    if active_table_id is None:
        raise PreventUpdate
    hidden_tables = _hidden_profile_tables(
        price_kwp_style,
        price_kwp_others_style,
    )
    if active_table_id in hidden_tables:
        return _active_profile_table_state()
    raise PreventUpdate


@callback(
    Output("profile-main-chart-panel", "style"),
    Output("profile-main-chart-title", "children"),
    Output("profile-main-chart-subtitle", "children"),
    Output("profile-main-chart-graph", "figure"),
    Output("profile-secondary-chart-panel", "style"),
    Output("profile-secondary-chart-title", "children"),
    Output("profile-secondary-chart-subtitle", "children"),
    Output("profile-secondary-chart-graph", "figure"),
    Output("month-profile-card", "className"),
    Output("sun-profile-card", "className"),
    Output("price-kwp-card", "className"),
    Output("price-kwp-others-card", "className"),
    Input("active-profile-table-state", "data"),
    Input("month-profile-editor", "data", allow_optional=True),
    Input("month-profile-editor", "columns", allow_optional=True),
    Input("sun-profile-editor", "data", allow_optional=True),
    Input("sun-profile-editor", "columns", allow_optional=True),
    Input("price-kwp-editor", "data", allow_optional=True),
    Input("price-kwp-editor", "columns", allow_optional=True),
    Input("price-kwp-others-editor", "data", allow_optional=True),
    Input("price-kwp-others-editor", "columns", allow_optional=True),
    Input("language-selector", "value"),
    Input("price-kwp-panel", "style", allow_optional=True),
    Input("price-kwp-others-panel", "style", allow_optional=True),
)
def render_active_profile_chart(
    active_state,
    month_rows,
    month_columns,
    sun_rows,
    sun_columns,
    price_rows,
    price_columns,
    price_others_rows,
    price_others_columns,
    language_value,
    price_kwp_style,
    price_kwp_others_style,
):
    lang = _lang(language_value)
    hidden_tables = _hidden_profile_tables(
        price_kwp_style,
        price_kwp_others_style,
    )
    active_table_id = str((active_state or {}).get("table_id") or "").strip() or None
    if active_table_id in hidden_tables:
        active_table_id = None
    card_classes = _profile_card_class_names(active_table_id, hidden_tables)
    hidden_style = {"display": "none"}
    empty_figure = go.Figure()
    if active_table_id is None:
        return (
            hidden_style,
            "",
            "",
            empty_figure,
            hidden_style,
            "",
            "",
            empty_figure,
            *card_classes,
        )
    table_rows = {
        "month-profile-editor": month_rows,
        "sun-profile-editor": sun_rows,
        "price-kwp-editor": price_rows,
        "price-kwp-others-editor": price_others_rows,
    }
    table_columns = {
        "month-profile-editor": month_columns,
        "sun-profile-editor": sun_columns,
        "price-kwp-editor": price_columns,
        "price-kwp-others-editor": price_others_columns,
    }
    render = build_profile_chart(active_table_id, table_rows.get(active_table_id), table_columns.get(active_table_id), lang)
    visible_style = {"display": "grid"}
    if render.row_target == "main":
        return (
            visible_style,
            render.title,
            render.subtitle,
            render.figure,
            hidden_style,
            "",
            "",
            empty_figure,
            *card_classes,
        )
    return (
        hidden_style,
        "",
        "",
        empty_figure,
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
    Output("price-kwp-editor", "data", allow_duplicate=True),
    Input("add-price-kwp-row-btn", "n_clicks", allow_optional=True),
    State("price-kwp-editor", "data", allow_optional=True),
    State("price-kwp-editor", "columns", allow_optional=True),
    prevent_initial_call=True,
)
def add_price_kwp_row(n_clicks, table_rows, table_columns):
    if not n_clicks:
        raise PreventUpdate
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("price-kwp-others-editor", "data", allow_duplicate=True),
    Input("add-price-kwp-others-row-btn", "n_clicks", allow_optional=True),
    State("price-kwp-others-editor", "data", allow_optional=True),
    State("price-kwp-others-editor", "columns", allow_optional=True),
    prevent_initial_call=True,
)
def add_price_kwp_others_row(n_clicks, table_rows, table_columns):
    if not n_clicks:
        raise PreventUpdate
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("economics-cost-items-editor", "data", allow_duplicate=True),
    Input("add-economics-cost-row-btn", "n_clicks", allow_optional=True),
    State("economics-cost-items-editor", "data", allow_optional=True),
    State("economics-cost-items-editor", "columns", allow_optional=True),
    prevent_initial_call=True,
)
def add_economics_cost_row(n_clicks, table_rows, table_columns):
    if not n_clicks:
        raise PreventUpdate
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append(blank_row)
    return rows


@callback(
    Output("economics-price-items-editor", "data", allow_duplicate=True),
    Input("add-economics-price-row-btn", "n_clicks", allow_optional=True),
    State("economics-price-items-editor", "data", allow_optional=True),
    State("economics-price-items-editor", "columns", allow_optional=True),
    prevent_initial_call=True,
)
def add_economics_price_row(n_clicks, table_rows, table_columns):
    if not n_clicks:
        raise PreventUpdate
    blank_row = _blank_table_row(table_columns, table_rows)
    if not blank_row:
        raise PreventUpdate
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
    State("price-kwp-editor", "data", allow_optional=True),
    State("price-kwp-others-editor", "data", allow_optional=True),
    State("economics-cost-items-editor", "data", allow_optional=True),
    State("economics-price-items-editor", "data", allow_optional=True),
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
    price_kwp_rows,
    price_kwp_others_rows,
    economics_cost_rows,
    economics_price_rows,
    language_value,
):
    lang = _lang(language_value)
    if not _admin_page_access(session_payload).allowed:
        raise PreventUpdate
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
            None if economics_price_rows is None else economics_price_items_rows_from_editor(economics_price_rows),
            price_kwp_rows,
            price_kwp_others_rows,
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
