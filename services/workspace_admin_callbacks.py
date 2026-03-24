from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from components import render_assumption_sections
from .i18n import tr
from .profile_charts import build_profile_chart
from .project_io import save_project
from .session_state import commit_client_session, resolve_client_session
from .ui_schema import assumption_context_map, build_assumption_sections, build_table_display_columns
from .validation import BATTERY_REQUIRED_COLUMNS, INVERTER_REQUIRED_COLUMNS
from .workbench_ui import collect_config_updates, demand_profile_visibility, workbench_status_message
from .workspace_actions import (
    apply_workspace_draft_to_state,
    config_overrides_for_fields,
    resolve_workspace_bundle_for_display,
    table_draft_rows,
)
from .workspace_drafts import bind_workspace_draft_project, upsert_workspace_draft
from .workspace_partitions import partition_assumption_sections


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


PROFILE_MAIN_TABLE_IDS = (
    "month-profile-editor",
    "sun-profile-editor",
    "demand-profile-weights-editor",
)
PROFILE_SECONDARY_TABLE_IDS = (
    "price-kwp-editor",
    "price-kwp-others-editor",
    "demand-profile-editor",
    "demand-profile-general-editor",
)
PROFILE_TABLE_IDS = (*PROFILE_MAIN_TABLE_IDS, *PROFILE_SECONDARY_TABLE_IDS)
PROFILE_TABLE_VISIBILITY_PANELS = {
    "price-kwp-editor": "price-kwp-panel",
    "price-kwp-others-editor": "price-kwp-others-panel",
    "demand-profile-editor": "demand-profile-panel",
    "demand-profile-general-editor": "demand-profile-general-panel",
    "demand-profile-weights-editor": "demand-profile-weights-panel",
}
PROFILE_CARD_BASE_CLASS = "profile-table-card-shell"
PROFILE_CARD_ACTIVE_CLASS = f"{PROFILE_CARD_BASE_CLASS} profile-table-card-active"


def _project_is_bound(state) -> bool:
    return bool(str(state.project_slug or "").strip())


def _resolved_project_name(project_name_value, state) -> str:
    return (project_name_value or state.project_name or state.project_slug or "").strip()


def _join_status_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


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
    demand_profile_style: dict | None,
    demand_profile_general_style: dict | None,
    demand_profile_weights_style: dict | None,
) -> set[str]:
    panel_styles = {
        "price-kwp-panel": price_kwp_style,
        "price-kwp-others-panel": price_kwp_others_style,
        "demand-profile-panel": demand_profile_style,
        "demand-profile-general-panel": demand_profile_general_style,
        "demand-profile-weights-panel": demand_profile_weights_style,
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


@callback(
    Output("admin-page-title", "children"),
    Output("admin-page-copy", "children"),
    Output("admin-show-all", "options"),
    Output("apply-admin-btn", "children"),
    Output("admin-gating-note", "children"),
    Output("profile-editor-title", "children"),
    Output("profile-editor-note", "children"),
    Output("month-profile-title", "children"),
    Output("month-profile-tooltip", "children"),
    Output("sun-profile-title", "children"),
    Output("sun-profile-tooltip", "children"),
    Output("price-kwp-title", "children"),
    Output("price-kwp-tooltip", "children"),
    Output("price-kwp-others-title", "children"),
    Output("price-kwp-others-tooltip", "children"),
    Output("demand-profile-title", "children"),
    Output("demand-profile-tooltip", "children"),
    Output("demand-profile-general-title", "children"),
    Output("demand-profile-general-tooltip", "children"),
    Output("demand-profile-weights-title", "children"),
    Output("demand-profile-weights-tooltip", "children"),
    Output("add-price-kwp-row-btn", "children"),
    Output("add-price-kwp-others-row-btn", "children"),
    Output("catalog-editor-title", "children"),
    Output("inverter-editor-title", "children"),
    Output("battery-editor-title", "children"),
    Output("add-inverter-row-btn", "children"),
    Output("add-battery-row-btn", "children"),
    Input("language-selector", "value"),
)
def translate_admin_page(language_value):
    lang = _lang(language_value)
    return (
        tr("workspace.admin.title", lang),
        tr("workspace.admin.copy", lang),
        [{"label": tr("workbench.assumptions.show_all", lang), "value": "all"}],
        tr("workbench.assumptions.apply", lang),
        tr("workspace.admin.note", lang),
        tr("workbench.profiles", lang),
        tr("workbench.profiles.note", lang),
        tr("workbench.profiles.month", lang),
        tr("workbench.profiles.tooltip.month", lang),
        tr("workbench.profiles.sun", lang),
        tr("workbench.profiles.tooltip.sun", lang),
        tr("workbench.profiles.price", lang),
        tr("workbench.profiles.tooltip.price", lang),
        tr("workbench.profiles.price_others", lang),
        tr("workbench.profiles.tooltip.price_others", lang),
        tr("workbench.profiles.demand_weekday", lang),
        tr("workbench.profiles.tooltip.demand_weekday", lang),
        tr("workbench.profiles.demand_general", lang),
        tr("workbench.profiles.tooltip.demand_general", lang),
        tr("workbench.profiles.demand_weights", lang),
        tr("workbench.profiles.tooltip.demand_weights", lang),
        tr("workbench.profiles.add_row", lang),
        tr("workbench.profiles.add_row", lang),
        tr("workbench.catalogs", lang),
        tr("workbench.catalogs.inverters", lang),
        tr("workbench.catalogs.batteries", lang),
        tr("workbench.add_row", lang),
        tr("workbench.add_row", lang),
    )


@callback(
    Output({"type": "profile-table-activate", "table": ALL}, "children"),
    Input("language-selector", "value"),
)
def translate_profile_table_activators(language_value):
    lang = _lang(language_value)
    return [tr("workbench.profiles.preview_chart", lang)] * len(PROFILE_TABLE_IDS)


@callback(
    Output("admin-assumption-sections", "children"),
    Output("apply-admin-btn", "disabled"),
    Output("inverter-table-editor", "data"),
    Output("inverter-table-editor", "columns"),
    Output("inverter-table-editor", "tooltip_header"),
    Output("battery-table-editor", "data"),
    Output("battery-table-editor", "columns"),
    Output("battery-table-editor", "tooltip_header"),
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
    Output("demand-profile-editor", "data"),
    Output("demand-profile-editor", "columns"),
    Output("demand-profile-editor", "tooltip_header"),
    Output("demand-profile-general-editor", "data"),
    Output("demand-profile-general-editor", "columns"),
    Output("demand-profile-general-editor", "tooltip_header"),
    Output("demand-profile-weights-editor", "data"),
    Output("demand-profile-weights-editor", "columns"),
    Output("demand-profile-weights-editor", "tooltip_header"),
    Output("demand-profile-panel", "style"),
    Output("demand-profile-general-panel", "style"),
    Output("demand-profile-weights-panel", "style"),
    Input("scenario-session-store", "data"),
    Input("admin-show-all", "value"),
    Input("language-selector", "value"),
)
def populate_admin_page(session_payload, show_all_values, language_value):
    lang = _lang(language_value)
    client_state, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        empty = ([], [], {})
        hidden = {"display": "none"}
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
            hidden,
            hidden,
            hidden,
        )

    display_bundle = resolve_workspace_bundle_for_display(client_state.session_id, active.scenario_id, active.config_bundle)
    all_sections = build_assumption_sections(
        display_bundle,
        lang=lang,
        show_all="all" in (show_all_values or []),
    )
    partition = partition_assumption_sections(all_sections)
    visibility = demand_profile_visibility(str(display_bundle.config.get("use_excel_profile", "")))
    inverter_columns, inverter_tooltips = build_table_display_columns("inverter_catalog", list(display_bundle.inverter_catalog.columns), lang)
    battery_columns, battery_tooltips = build_table_display_columns("battery_catalog", list(display_bundle.battery_catalog.columns), lang)
    month_columns, month_tooltips = build_table_display_columns("month_profile", list(display_bundle.month_profile_table.columns), lang)
    sun_columns, sun_tooltips = build_table_display_columns("sun_profile", list(display_bundle.sun_profile_table.columns), lang)
    kwp_columns, kwp_tooltips = build_table_display_columns("cop_kwp", list(display_bundle.cop_kwp_table.columns), lang)
    kwp_other_columns, kwp_other_tooltips = build_table_display_columns("cop_kwp_others", list(display_bundle.cop_kwp_table_others.columns), lang)
    demand_columns, demand_tooltips = build_table_display_columns("demand_profile", list(display_bundle.demand_profile_table.columns), lang)
    demand_general_columns, demand_general_tooltips = build_table_display_columns("demand_profile_general", list(display_bundle.demand_profile_general_table.columns), lang)
    demand_weight_columns, demand_weight_tooltips = build_table_display_columns("demand_profile_weights", list(display_bundle.demand_profile_weights_table.columns), lang)
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
        display_bundle.demand_profile_table.to_dict("records"),
        demand_columns,
        demand_tooltips,
        display_bundle.demand_profile_general_table.to_dict("records"),
        demand_general_columns,
        demand_general_tooltips,
        display_bundle.demand_profile_weights_table.to_dict("records"),
        demand_weight_columns,
        demand_weight_tooltips,
        visibility["demand-profile-panel"],
        visibility["demand-profile-general-panel"],
        visibility["demand-profile-weights-panel"],
    )


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
    _, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        return [], [], [], []

    current_config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
    context = assumption_context_map(current_config, lang=lang)
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
    client_state, state = _session(session_payload, lang)
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
    Input("inverter-table-editor", "data"),
    Input("battery-table-editor", "data"),
    Input("month-profile-editor", "data"),
    Input("sun-profile-editor", "data"),
    Input("price-kwp-editor", "data"),
    Input("price-kwp-others-editor", "data"),
    Input("demand-profile-editor", "data"),
    Input("demand-profile-general-editor", "data"),
    Input("demand-profile-weights-editor", "data"),
    prevent_initial_call=True,
)
def sync_admin_draft(
    session_payload,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    month_profile_rows,
    sun_profile_rows,
    price_kwp_rows,
    price_kwp_others_rows,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
):
    client_state, state = _session(session_payload, None)
    active = state.get_scenario()
    if active is None:
        raise PreventUpdate
    overrides, owned_fields = config_overrides_for_fields(
        base_config=active.config_bundle.config,
        input_ids=assumption_input_ids,
        input_values=assumption_values,
    )
    rows_payload, owned_tables = table_draft_rows(
        base_bundle=active.config_bundle,
        table_rows={
            "inverter_catalog": inverter_rows,
            "battery_catalog": battery_rows,
            "month_profile": month_profile_rows,
            "sun_profile": sun_profile_rows,
            "cop_kwp_table": price_kwp_rows,
            "cop_kwp_table_others": price_kwp_others_rows,
            "demand_profile": demand_profile_rows,
            "demand_profile_general": demand_profile_general_rows,
            "demand_profile_weights": demand_profile_weights_rows,
        },
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
    Input("month-profile-editor", "active_cell"),
    Input("sun-profile-editor", "active_cell"),
    Input("demand-profile-weights-editor", "active_cell"),
    Input("price-kwp-editor", "active_cell"),
    Input("price-kwp-others-editor", "active_cell"),
    Input("demand-profile-editor", "active_cell"),
    Input("demand-profile-general-editor", "active_cell"),
    State("active-profile-table-state", "data"),
    prevent_initial_call=True,
)
def sync_active_profile_table(
    _activator_clicks,
    month_active_cell,
    sun_active_cell,
    demand_weights_active_cell,
    price_active_cell,
    price_others_active_cell,
    demand_weekday_active_cell,
    demand_general_active_cell,
    active_state,
):
    trigger = ctx.triggered_id
    current_table_id = str((active_state or {}).get("table_id") or "").strip() or None
    active_cells = {
        "month-profile-editor": month_active_cell,
        "sun-profile-editor": sun_active_cell,
        "demand-profile-weights-editor": demand_weights_active_cell,
        "price-kwp-editor": price_active_cell,
        "price-kwp-others-editor": price_others_active_cell,
        "demand-profile-editor": demand_weekday_active_cell,
        "demand-profile-general-editor": demand_general_active_cell,
    }
    if isinstance(trigger, dict) and trigger.get("type") == "profile-table-activate":
        table_id = str(trigger.get("table", "")).strip() or None
        if table_id is None:
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
    Input("price-kwp-panel", "style"),
    Input("price-kwp-others-panel", "style"),
    Input("demand-profile-panel", "style"),
    Input("demand-profile-general-panel", "style"),
    Input("demand-profile-weights-panel", "style"),
    prevent_initial_call=True,
)
def sanitize_active_profile_table(
    active_state,
    price_kwp_style,
    price_kwp_others_style,
    demand_profile_style,
    demand_profile_general_style,
    demand_profile_weights_style,
):
    active_table_id = str((active_state or {}).get("table_id") or "").strip() or None
    if active_table_id is None:
        raise PreventUpdate
    hidden_tables = _hidden_profile_tables(
        price_kwp_style,
        price_kwp_others_style,
        demand_profile_style,
        demand_profile_general_style,
        demand_profile_weights_style,
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
    Output("demand-profile-weights-card", "className"),
    Output("price-kwp-card", "className"),
    Output("price-kwp-others-card", "className"),
    Output("demand-profile-card", "className"),
    Output("demand-profile-general-card", "className"),
    Input("active-profile-table-state", "data"),
    Input("month-profile-editor", "data"),
    Input("month-profile-editor", "columns"),
    Input("sun-profile-editor", "data"),
    Input("sun-profile-editor", "columns"),
    Input("demand-profile-weights-editor", "data"),
    Input("demand-profile-weights-editor", "columns"),
    Input("price-kwp-editor", "data"),
    Input("price-kwp-editor", "columns"),
    Input("price-kwp-others-editor", "data"),
    Input("price-kwp-others-editor", "columns"),
    Input("demand-profile-editor", "data"),
    Input("demand-profile-editor", "columns"),
    Input("demand-profile-general-editor", "data"),
    Input("demand-profile-general-editor", "columns"),
    Input("language-selector", "value"),
    Input("price-kwp-panel", "style"),
    Input("price-kwp-others-panel", "style"),
    Input("demand-profile-panel", "style"),
    Input("demand-profile-general-panel", "style"),
    Input("demand-profile-weights-panel", "style"),
)
def render_active_profile_chart(
    active_state,
    month_rows,
    month_columns,
    sun_rows,
    sun_columns,
    demand_weights_rows,
    demand_weights_columns,
    price_rows,
    price_columns,
    price_others_rows,
    price_others_columns,
    demand_weekday_rows,
    demand_weekday_columns,
    demand_general_rows,
    demand_general_columns,
    language_value,
    price_kwp_style,
    price_kwp_others_style,
    demand_profile_style,
    demand_profile_general_style,
    demand_profile_weights_style,
):
    lang = _lang(language_value)
    hidden_tables = _hidden_profile_tables(
        price_kwp_style,
        price_kwp_others_style,
        demand_profile_style,
        demand_profile_general_style,
        demand_profile_weights_style,
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
        "demand-profile-weights-editor": demand_weights_rows,
        "price-kwp-editor": price_rows,
        "price-kwp-others-editor": price_others_rows,
        "demand-profile-editor": demand_weekday_rows,
        "demand-profile-general-editor": demand_general_rows,
    }
    table_columns = {
        "month-profile-editor": month_columns,
        "sun-profile-editor": sun_columns,
        "demand-profile-weights-editor": demand_weights_columns,
        "price-kwp-editor": price_columns,
        "price-kwp-others-editor": price_others_columns,
        "demand-profile-editor": demand_weekday_columns,
        "demand-profile-general-editor": demand_general_columns,
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
    Input("add-inverter-row-btn", "n_clicks"),
    State("inverter-table-editor", "data"),
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
    Input("add-battery-row-btn", "n_clicks"),
    State("battery-table-editor", "data"),
    prevent_initial_call=True,
)
def add_battery_row(n_clicks, table_rows):
    if not n_clicks:
        raise PreventUpdate
    rows = list(table_rows or [])
    rows.append({column: "" for column in BATTERY_REQUIRED_COLUMNS})
    return rows


@callback(
    Output("price-kwp-editor", "data", allow_duplicate=True),
    Input("add-price-kwp-row-btn", "n_clicks"),
    State("price-kwp-editor", "data"),
    State("price-kwp-editor", "columns"),
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
    Input("add-price-kwp-others-row-btn", "n_clicks"),
    State("price-kwp-others-editor", "data"),
    State("price-kwp-others-editor", "columns"),
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
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("workbench-status", "children", allow_duplicate=True),
    Input("apply-admin-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("project-name-input", "value"),
    State({"type": "admin-assumption-input", "field": ALL}, "id"),
    State({"type": "admin-assumption-input", "field": ALL}, "value"),
    State("inverter-table-editor", "data"),
    State("battery-table-editor", "data"),
    State("month-profile-editor", "data"),
    State("sun-profile-editor", "data"),
    State("price-kwp-editor", "data"),
    State("price-kwp-others-editor", "data"),
    State("demand-profile-editor", "data"),
    State("demand-profile-general-editor", "data"),
    State("demand-profile-weights-editor", "data"),
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
    month_profile_rows,
    sun_profile_rows,
    price_kwp_rows,
    price_kwp_others_rows,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
    language_value,
):
    lang = _lang(language_value)
    client_state, state = _session(session_payload, lang)
    try:
        active = state.get_scenario()
        if active is None:
            raise PreventUpdate
        overrides, owned_fields = config_overrides_for_fields(
            base_config=active.config_bundle.config,
            input_ids=assumption_input_ids,
            input_values=assumption_values,
        )
        rows_payload, owned_tables = table_draft_rows(
            base_bundle=active.config_bundle,
            table_rows={
                "inverter_catalog": inverter_rows,
                "battery_catalog": battery_rows,
                "month_profile": month_profile_rows,
                "sun_profile": sun_profile_rows,
                "cop_kwp_table": price_kwp_rows,
                "cop_kwp_table_others": price_kwp_others_rows,
                "demand_profile": demand_profile_rows,
                "demand_profile_general": demand_profile_general_rows,
                "demand_profile_weights": demand_profile_weights_rows,
            },
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
        state, _ = apply_workspace_draft_to_state(
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
            tr("workbench.run_flow.needs_rerun", lang),
        )
        return client_state.to_payload(), status
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc)
