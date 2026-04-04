from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx, no_update
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.graph_objects as go

from pv_product.panel_catalog import PANEL_DERIVED_CONFIG_FIELDS, PANEL_SELECTION_CATALOG, apply_panel_selection

from components import render_assumption_sections, render_validation_panel
from .i18n import tr
from .project_io import list_projects, save_project, slugify_project_name
from .scenario_session import run_scenario_scan
from .session_state import commit_client_session, resolve_client_session
from .ui_schema import assumption_context_map, build_assumption_sections, display_assumption_value
from .workbench_ui import collect_config_updates, workbench_status_message
from .workspace_actions import apply_workspace_draft_to_state, resolve_workspace_bundle_for_display, table_draft_rows
from .workspace_demand import (
    DEMAND_PROFILE_CONFIG_FIELDS,
    build_active_demand_chart,
    build_demand_profile_ui_state,
    demand_mode_options,
    demand_profile_control_updates,
    relative_profile_type_options,
)
from .workspace_drafts import bind_workspace_draft_project, upsert_workspace_draft
from .workspace_partitions import partition_assumption_sections
from .ui_mode import admin_surface_style, internal_entry_style, resolve_ui_mode_from_payload


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session(payload, language_value: str | None):
    return resolve_client_session(payload, language=_lang(language_value))


def _project_is_bound(state) -> bool:
    return bool(str(state.project_slug or "").strip())


def _clean_project_name_seed(value) -> str:
    cleaned = str(value or "").strip().replace("_", " ").replace("-", " ")
    normalized = " ".join(cleaned.split())
    return "" if normalized.casefold() in {"", "none", "nan", "null"} else normalized


def _resolved_project_name(project_name_value, state, *, suggested_name: str | None = None) -> str:
    typed_name = str(project_name_value or "").strip()
    return typed_name or (suggested_name or state.project_name or state.project_slug or "").strip()


def _join_status_parts(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _run_choice_state(*, open_dialog: bool = False, suggested_project_name: str | None = None) -> dict[str, object]:
    return {
        "open": open_dialog,
        "suggested_project_name": str(suggested_project_name or "").strip(),
    }


def _suggest_run_project_name(state, active, *, lang: str) -> str:
    preferred_name = _clean_project_name_seed(getattr(active, "name", ""))
    existing_slugs = {manifest.slug for manifest in list_projects()}
    if preferred_name:
        if slugify_project_name(preferred_name) not in existing_slugs:
            return preferred_name
        suffix = 2
        while True:
            candidate = f"{preferred_name} {suffix}"
            if slugify_project_name(candidate) not in existing_slugs:
                return candidate
            suffix += 1

    base_name = tr("workbench.run_dialog.default_project_base", lang)
    index = 1
    while True:
        candidate = f"{base_name} {index}"
        if slugify_project_name(candidate) not in existing_slugs:
            return candidate
        index += 1


def _bundle_has_errors(bundle) -> bool:
    return any(issue.level == "error" for issue in bundle.issues)


def _assumption_note_style(message: str) -> dict[str, str]:
    return {"display": "block"} if str(message or "").strip() else {"display": "none"}


def _assumption_card_class(field_key: str, *, disabled: bool = False, emphasize: bool = False) -> str:
    classes = ["field-card"]
    if disabled:
        classes.append("field-card-disabled")
    if emphasize and not disabled:
        classes.append("field-card-highlight")
    return " ".join(dict.fromkeys(classes))


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
        numeric_text = stripped.replace(",", "")
        try:
            number = float(numeric_text)
        except ValueError:
            return stripped
        return int(number) if number.is_integer() else round(number, 10)
    return value


def _assumptions_draft_payload(
    active,
    *,
    assumption_input_ids,
    assumption_values,
    demand_profile_mode_value,
    demand_profile_alpha_value,
    demand_profile_energy_value,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
):
    base_bundle = active.config_bundle
    current_config = demand_profile_control_updates(
        base_bundle.config,
        assumption_input_ids=assumption_input_ids,
        assumption_values=assumption_values,
        mode_value=demand_profile_mode_value,
        alpha_mix_value=demand_profile_alpha_value,
        e_month_value=demand_profile_energy_value,
    )
    owned_fields = {
        str(component_id.get("field", "")).strip()
        for component_id in (assumption_input_ids or [])
        if str(component_id.get("field", "")).strip()
    } | DEMAND_PROFILE_CONFIG_FIELDS
    overrides = {
        field: current_config.get(field)
        for field in owned_fields
        if _normalize_compare_value(current_config.get(field)) != _normalize_compare_value(base_bundle.config.get(field))
    }
    rows_payload, owned_tables = table_draft_rows(
        base_bundle=base_bundle,
        table_rows={
            "demand_profile": demand_profile_rows if demand_profile_rows is not None else base_bundle.demand_profile_table.to_dict("records"),
            "demand_profile_general": (
                demand_profile_general_rows
                if demand_profile_general_rows is not None
                else base_bundle.demand_profile_general_table.to_dict("records")
            ),
            "demand_profile_weights": (
                demand_profile_weights_rows
                if demand_profile_weights_rows is not None
                else base_bundle.demand_profile_weights_table.to_dict("records")
            ),
        },
    )
    return overrides, owned_fields, rows_payload, owned_tables


ASSUMPTIONS_PAGE_RESPONSE_KEYS = (
    "sections",
    "validation",
    "apply_disabled",
    "scan_disabled",
    "mode_options",
    "mode_value",
    "type_options",
    "type_value",
    "alpha_value",
    "energy_value",
    "alpha_disabled",
    "energy_disabled",
    "mode_note",
    "weekday_rows",
    "weekday_columns",
    "weekday_tooltips",
    "total_rows",
    "total_columns",
    "total_tooltips",
    "total_preview_rows",
    "total_preview_columns",
    "total_preview_tooltips",
    "relative_rows",
    "relative_columns",
    "relative_tooltips",
    "relative_preview_rows",
    "relative_preview_columns",
    "relative_preview_tooltips",
    "panel_style",
    "general_panel_style",
    "general_preview_panel_style",
    "weights_panel_style",
    "weights_preview_panel_style",
    "energy_shell_style",
    "alpha_shell_style",
    "type_shell_style",
    "relative_grid_style",
    "secondary_grid_style",
    "chart_panel_style",
    "chart_title",
    "chart_subtitle",
    "chart_figure",
)


def _build_empty_assumptions_chart(lang: str, *, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        template="plotly_white",
        margin={"l": 44, "r": 18, "t": 20, "b": 36},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 13, "color": "#475569"},
            }
        ],
    )
    return figure


def _build_assumptions_response(
    *,
    lang: str,
    sections: list[dict],
    validation_issues,
    apply_disabled: bool,
    scan_disabled: bool,
    show_all: bool,
    empty_message: str,
    demand_state: dict[str, object] | None = None,
    demand_chart: dict[str, object] | None = None,
    empty_chart_title: str = "",
):
    hidden = {"display": "none"}
    mode_options = demand_mode_options(lang)
    type_options = relative_profile_type_options(lang)
    fallback_mode = mode_options[1]["value"] if len(mode_options) > 1 else "perfil general"
    fallback_type = type_options[-1]["value"] if type_options else "mixta"
    resolved_demand_state = demand_state or {
        "profile_mode": fallback_mode,
        "profile_type": fallback_type,
        "alpha_mix": 0.5,
        "e_month_kwh": 0,
        "alpha_disabled": True,
        "energy_disabled": True,
        "mode_note": tr("workbench.profiles.mode.note.total", lang),
        "weekday_source_rows": [],
        "weekday_columns": [],
        "weekday_tooltips": {},
        "total_source_rows": [],
        "total_columns": [],
        "total_tooltips": {},
        "total_preview_rows": [],
        "total_preview_columns": [],
        "total_preview_tooltips": {},
        "relative_source_rows": [],
        "relative_columns": [],
        "relative_tooltips": {},
        "relative_preview_rows": [],
        "relative_preview_columns": [],
        "relative_preview_tooltips": {},
        "visibility": {
            "demand-profile-panel": hidden,
            "demand-profile-general-panel": hidden,
            "demand-profile-general-preview-panel": hidden,
            "demand-profile-weights-panel": hidden,
        },
        "weights_preview_style": hidden,
        "energy_shell_style": hidden,
        "alpha_shell_style": hidden,
        "type_shell_style": hidden,
        "relative_grid_style": hidden,
        "secondary_grid_style": hidden,
    }
    resolved_chart = demand_chart or {
        "style": {"display": "grid"},
        "title": empty_chart_title,
        "copy": empty_message,
        "figure": _build_empty_assumptions_chart(lang, message=empty_message),
    }
    response = {
        "sections": render_assumption_sections(
            sections,
            show_all=show_all,
            empty_message=empty_message,
            advanced_label=tr("workbench.assumptions.advanced", lang),
            input_id_type="assumptions-input",
            field_card_type="assumptions-field-card",
            context_note_type="assumptions-context-note",
        ),
        "validation": render_validation_panel(validation_issues, lang=lang),
        "apply_disabled": apply_disabled,
        "scan_disabled": scan_disabled,
        "mode_options": mode_options,
        "mode_value": resolved_demand_state["profile_mode"],
        "type_options": type_options,
        "type_value": resolved_demand_state["profile_type"],
        "alpha_value": resolved_demand_state["alpha_mix"],
        "energy_value": resolved_demand_state["e_month_kwh"],
        "alpha_disabled": resolved_demand_state["alpha_disabled"],
        "energy_disabled": resolved_demand_state["energy_disabled"],
        "mode_note": resolved_demand_state["mode_note"],
        "weekday_rows": resolved_demand_state["weekday_source_rows"],
        "weekday_columns": resolved_demand_state["weekday_columns"],
        "weekday_tooltips": resolved_demand_state["weekday_tooltips"],
        "total_rows": resolved_demand_state["total_source_rows"],
        "total_columns": resolved_demand_state["total_columns"],
        "total_tooltips": resolved_demand_state["total_tooltips"],
        "total_preview_rows": resolved_demand_state["total_preview_rows"],
        "total_preview_columns": resolved_demand_state["total_preview_columns"],
        "total_preview_tooltips": resolved_demand_state["total_preview_tooltips"],
        "relative_rows": resolved_demand_state["relative_source_rows"],
        "relative_columns": resolved_demand_state["relative_columns"],
        "relative_tooltips": resolved_demand_state["relative_tooltips"],
        "relative_preview_rows": resolved_demand_state["relative_preview_rows"],
        "relative_preview_columns": resolved_demand_state["relative_preview_columns"],
        "relative_preview_tooltips": resolved_demand_state["relative_preview_tooltips"],
        "panel_style": resolved_demand_state["visibility"]["demand-profile-panel"],
        "general_panel_style": resolved_demand_state["visibility"]["demand-profile-general-panel"],
        "general_preview_panel_style": resolved_demand_state["visibility"]["demand-profile-general-preview-panel"],
        "weights_panel_style": resolved_demand_state["visibility"]["demand-profile-weights-panel"],
        "weights_preview_panel_style": resolved_demand_state["weights_preview_style"],
        "energy_shell_style": resolved_demand_state["energy_shell_style"],
        "alpha_shell_style": resolved_demand_state["alpha_shell_style"],
        "type_shell_style": resolved_demand_state["type_shell_style"],
        "relative_grid_style": resolved_demand_state["relative_grid_style"],
        "secondary_grid_style": resolved_demand_state["secondary_grid_style"],
        "chart_panel_style": resolved_chart["style"],
        "chart_title": resolved_chart["title"],
        "chart_subtitle": resolved_chart["copy"],
        "chart_figure": resolved_chart["figure"],
    }
    missing = [key for key in ASSUMPTIONS_PAGE_RESPONSE_KEYS if key not in response]
    if missing:
        raise ValueError(f"Missing assumptions response keys: {missing}")
    return tuple(response[key] for key in ASSUMPTIONS_PAGE_RESPONSE_KEYS)


def _build_empty_assumptions_response(*, state, lang: str):
    if _project_is_bound(state):
        empty_title = tr("workspace.results_digest.no_active.title", lang)
        empty_message = tr("workspace.results_digest.no_active.body", lang)
    else:
        empty_title = tr("workspace.assumptions.empty.no_project_title", lang)
        empty_message = tr("workspace.assumptions.empty.no_project_body", lang)
    return _build_assumptions_response(
        lang=lang,
        sections=[],
        validation_issues=[],
        apply_disabled=True,
        scan_disabled=True,
        show_all=False,
        empty_message=empty_message,
        empty_chart_title=empty_title,
    )


@callback(
    Output("assumptions-page-title", "children"),
    Output("assumptions-page-copy", "children"),
    Output("assumptions-validation-title", "children"),
    Output("assumptions-show-all", "options"),
    Output("apply-assumptions-btn", "children"),
    Output("run-assumptions-scan-btn", "children"),
    Output("assumptions-run-progress", "children"),
    Output("assumptions-general-tab", "label"),
    Output("assumptions-demand-tab", "label"),
    Output("assumptions-demand-title", "children"),
    Output("assumptions-demand-copy", "children"),
    Output("assumptions-demand-profile-mode-title", "children"),
    Output("assumptions-demand-profile-mode-copy", "children"),
    Output("assumptions-demand-profile-title", "children"),
    Output("assumptions-demand-profile-tooltip", "children"),
    Output("assumptions-demand-profile-general-title", "children"),
    Output("assumptions-demand-profile-general-tooltip", "children"),
    Output("assumptions-demand-profile-general-preview-title", "children"),
    Output("assumptions-demand-profile-weights-title", "children"),
    Output("assumptions-demand-profile-weights-tooltip", "children"),
    Output("assumptions-demand-profile-type-label", "children"),
    Output("assumptions-demand-profile-alpha-label", "children"),
    Output("assumptions-demand-profile-energy-label", "children"),
    Output("assumptions-demand-profile-weights-preview-title", "children"),
    Output("assumptions-demand-profile-weights-preview-copy", "children"),
    Output("assumptions-advanced-tools-title", "children"),
    Output("assumptions-advanced-tools-copy", "children"),
    Input("language-selector", "value"),
)
def translate_assumptions_page(language_value):
    lang = _lang(language_value)
    return (
        tr("workspace.assumptions.title", lang),
        tr("workspace.assumptions.copy", lang),
        tr("common.validation", lang),
        [{"label": tr("workbench.assumptions.show_all", lang), "value": "all"}],
        tr("workbench.assumptions.apply", lang),
        tr("workbench.run_scan", lang),
        tr("workbench.run_running", lang),
        tr("workspace.assumptions.tab.general", lang),
        tr("workspace.assumptions.tab.demand", lang),
        tr("workspace.assumptions.demand.title", lang),
        tr("workspace.assumptions.demand.copy", lang),
        tr("workbench.profiles.mode.title", lang),
        tr("workbench.profiles.mode.copy", lang),
        tr("workbench.profiles.demand_weekday", lang),
        tr("workbench.profiles.tooltip.demand_weekday", lang),
        tr("workbench.profiles.demand_general", lang),
        tr("workbench.profiles.tooltip.demand_general", lang),
        tr("workbench.profiles.demand_general_preview", lang),
        tr("workbench.profiles.demand_weights", lang),
        tr("workbench.profiles.tooltip.demand_weights", lang),
        tr("workbench.profiles.relative.type", lang),
        tr("workbench.profiles.relative.alpha", lang),
        tr("workbench.profiles.relative.energy", lang),
        tr("workbench.profiles.relative.preview", lang),
        tr("workbench.profiles.relative.preview.copy", lang),
        tr("workspace.advanced.title", lang),
        tr("workspace.advanced.copy", lang),
    )


def sync_workspace_internal_entry(session_payload):
    return internal_entry_style(resolve_ui_mode_from_payload(session_payload))


@callback(
    Output("assumptions-advanced-tools-entry-shell", "style"),
    Output("advanced-tools", "style"),
    Input("scenario-session-store", "data"),
)
def sync_assumptions_admin_surface_visibility(session_payload):
    style = admin_surface_style(resolve_ui_mode_from_payload(session_payload))
    return style, style


@callback(
    Output("assumptions-sections", "children"),
    Output("assumptions-validation", "children"),
    Output("apply-assumptions-btn", "disabled"),
    Output("run-assumptions-scan-btn", "disabled"),
    Output("assumptions-demand-profile-mode-selector", "options"),
    Output("assumptions-demand-profile-mode-selector", "value"),
    Output("assumptions-demand-profile-type-selector", "options"),
    Output("assumptions-demand-profile-type-selector", "value"),
    Output("assumptions-demand-profile-alpha-slider", "value"),
    Output("assumptions-demand-profile-energy-input", "value"),
    Output("assumptions-demand-profile-alpha-slider", "disabled"),
    Output("assumptions-demand-profile-energy-input", "disabled"),
    Output("assumptions-demand-profile-mode-note", "children"),
    Output("assumptions-demand-profile-editor", "data"),
    Output("assumptions-demand-profile-editor", "columns"),
    Output("assumptions-demand-profile-editor", "tooltip_header"),
    Output("assumptions-demand-profile-general-editor", "data"),
    Output("assumptions-demand-profile-general-editor", "columns"),
    Output("assumptions-demand-profile-general-editor", "tooltip_header"),
    Output("assumptions-demand-profile-general-preview-editor", "data"),
    Output("assumptions-demand-profile-general-preview-editor", "columns"),
    Output("assumptions-demand-profile-general-preview-editor", "tooltip_header"),
    Output("assumptions-demand-profile-weights-editor", "data"),
    Output("assumptions-demand-profile-weights-editor", "columns"),
    Output("assumptions-demand-profile-weights-editor", "tooltip_header"),
    Output("assumptions-demand-profile-weights-preview-editor", "data"),
    Output("assumptions-demand-profile-weights-preview-editor", "columns"),
    Output("assumptions-demand-profile-weights-preview-editor", "tooltip_header"),
    Output("assumptions-demand-profile-panel", "style"),
    Output("assumptions-demand-profile-general-panel", "style"),
    Output("assumptions-demand-profile-general-preview-panel", "style"),
    Output("assumptions-demand-profile-weights-panel", "style"),
    Output("assumptions-demand-profile-weights-preview-panel", "style"),
    Output("assumptions-demand-profile-energy-shell", "style"),
    Output("assumptions-demand-profile-alpha-shell", "style"),
    Output("assumptions-demand-profile-type-shell", "style"),
    Output("assumptions-demand-profile-relative-grid", "style"),
    Output("assumptions-demand-profile-secondary-grid", "style"),
    Output("assumptions-demand-profile-chart-panel", "style"),
    Output("assumptions-demand-profile-chart-title", "children"),
    Output("assumptions-demand-profile-chart-subtitle", "children"),
    Output("assumptions-demand-profile-chart-graph", "figure"),
    Input("scenario-session-store", "data"),
    Input("assumptions-show-all", "value"),
    Input("language-selector", "value"),
)
def populate_assumptions_page(session_payload, show_all_values, language_value):
    lang = _lang(language_value)
    client_state, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        return _build_empty_assumptions_response(state=state, lang=lang)

    display_bundle = resolve_workspace_bundle_for_display(client_state.session_id, active.scenario_id, active.config_bundle)
    all_sections = build_assumption_sections(
        display_bundle,
        lang=lang,
        show_all="all" in (show_all_values or []),
        exclude_fields=DEMAND_PROFILE_CONFIG_FIELDS,
    )
    partition = partition_assumption_sections(all_sections)
    demand_state = build_demand_profile_ui_state(bundle=display_bundle, lang=lang)
    demand_chart = build_active_demand_chart(lang=lang, demand_state=demand_state)
    return _build_assumptions_response(
        lang=lang,
        sections=partition.client_safe_sections,
        validation_issues=active.config_bundle.issues,
        apply_disabled=False,
        scan_disabled=_bundle_has_errors(active.config_bundle),
        show_all="all" in (show_all_values or []),
        empty_message=tr("workbench.assumptions.none", lang),
        demand_state=demand_state,
        demand_chart=demand_chart,
    )


@callback(
    Output({"type": "assumptions-input", "field": ALL}, "value"),
    Output({"type": "assumptions-input", "field": ALL}, "disabled"),
    Output({"type": "assumptions-field-card", "field": ALL}, "className"),
    Output({"type": "assumptions-context-note", "group": ALL}, "children"),
    Output({"type": "assumptions-context-note", "group": ALL}, "style"),
    Input("scenario-session-store", "data"),
    Input({"type": "assumptions-input", "field": ALL}, "id"),
    Input({"type": "assumptions-input", "field": ALL}, "value"),
    Input("language-selector", "value"),
    State({"type": "assumptions-field-card", "field": ALL}, "id"),
    State({"type": "assumptions-context-note", "group": ALL}, "id"),
)
def sync_assumption_context_ui(
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
        return [], [], [], [], []

    current_config = collect_config_updates(assumption_input_ids, assumption_values, active.config_bundle.config)
    effective_config, panel_resolution = apply_panel_selection(current_config, active.config_bundle.panel_catalog)
    context = assumption_context_map(current_config, panel_catalog=active.config_bundle.panel_catalog, lang=lang)
    disabled_map = dict(context.get("field_disabled") or {})
    emphasis_map = dict(context.get("field_emphasis") or {})
    notes_map = dict(context.get("notes") or {})

    next_values = list(assumption_values or [])
    if panel_resolution.selection_mode == PANEL_SELECTION_CATALOG:
        for index, component_id in enumerate(assumption_input_ids or []):
            field_key = str((component_id or {}).get("field", "")).strip()
            if field_key in PANEL_DERIVED_CONFIG_FIELDS:
                next_values[index] = display_assumption_value(field_key, effective_config.get(field_key))
    value_updates = [no_update for _ in (assumption_input_ids or [])]
    if len(next_values) == len(assumption_values or []) and any(
        _normalize_compare_value(updated) != _normalize_compare_value(current)
        for updated, current in zip(next_values, assumption_values or [])
    ):
        value_updates = next_values

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
    return value_updates, disabled_values, card_classes, note_children, note_styles


@callback(
    Output("assumptions-draft-meta", "data"),
    Input("scenario-session-store", "data"),
    Input({"type": "assumptions-input", "field": ALL}, "id"),
    Input({"type": "assumptions-input", "field": ALL}, "value"),
    Input("assumptions-demand-profile-mode-selector", "value", allow_optional=True),
    Input("assumptions-demand-profile-alpha-slider", "value", allow_optional=True),
    Input("assumptions-demand-profile-energy-input", "value", allow_optional=True),
    Input("assumptions-demand-profile-editor", "data", allow_optional=True),
    Input("assumptions-demand-profile-general-editor", "data", allow_optional=True),
    Input("assumptions-demand-profile-weights-editor", "data", allow_optional=True),
    prevent_initial_call=True,
)
def sync_assumptions_draft(
    session_payload,
    assumption_input_ids,
    assumption_values,
    demand_profile_mode_value,
    demand_profile_alpha_value,
    demand_profile_energy_value,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
):
    client_state, state = _session(session_payload, None)
    active = state.get_scenario()
    if active is None:
        raise PreventUpdate
    overrides, owned_fields, rows_payload, owned_tables = _assumptions_draft_payload(
        active,
        assumption_input_ids=assumption_input_ids,
        assumption_values=assumption_values,
        demand_profile_mode_value=demand_profile_mode_value,
        demand_profile_alpha_value=demand_profile_alpha_value,
        demand_profile_energy_value=demand_profile_energy_value,
        demand_profile_rows=demand_profile_rows,
        demand_profile_general_rows=demand_profile_general_rows,
        demand_profile_weights_rows=demand_profile_weights_rows,
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
    Output("assumptions-demand-profile-editor", "data", allow_duplicate=True),
    Output("assumptions-demand-profile-general-editor", "data", allow_duplicate=True),
    Output("assumptions-demand-profile-general-preview-editor", "data", allow_duplicate=True),
    Output("assumptions-demand-profile-weights-editor", "data", allow_duplicate=True),
    Output("assumptions-demand-profile-weights-preview-editor", "data", allow_duplicate=True),
    Output("assumptions-demand-profile-panel", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-general-panel", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-general-preview-panel", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-weights-panel", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-weights-preview-panel", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-energy-input", "value", allow_duplicate=True),
    Output("assumptions-demand-profile-alpha-slider", "disabled", allow_duplicate=True),
    Output("assumptions-demand-profile-energy-input", "disabled", allow_duplicate=True),
    Output("assumptions-demand-profile-energy-shell", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-mode-note", "children", allow_duplicate=True),
    Output("assumptions-demand-profile-alpha-shell", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-type-shell", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-relative-grid", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-secondary-grid", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-chart-panel", "style", allow_duplicate=True),
    Output("assumptions-demand-profile-chart-title", "children", allow_duplicate=True),
    Output("assumptions-demand-profile-chart-subtitle", "children", allow_duplicate=True),
    Output("assumptions-demand-profile-chart-graph", "figure", allow_duplicate=True),
    Input("assumptions-demand-profile-mode-selector", "value"),
    Input("assumptions-demand-profile-type-selector", "value"),
    Input("assumptions-demand-profile-alpha-slider", "value"),
    Input("assumptions-demand-profile-energy-input", "value"),
    Input("assumptions-demand-profile-editor", "data_timestamp"),
    Input("assumptions-demand-profile-general-editor", "data_timestamp"),
    Input("assumptions-demand-profile-weights-editor", "data_timestamp"),
    Input("assumptions-subtabs", "value"),
    Input("language-selector", "value"),
    State("scenario-session-store", "data"),
    State("assumptions-demand-profile-editor", "data"),
    State("assumptions-demand-profile-general-editor", "data"),
    State("assumptions-demand-profile-weights-editor", "data"),
    prevent_initial_call=True,
)
def sync_assumptions_demand_profile_views(
    profile_mode_value,
    profile_type_value,
    alpha_mix_value,
    e_month_value,
    _weekday_timestamp,
    _total_timestamp,
    _relative_timestamp,
    _subtab_value,
    language_value,
    session_payload,
    weekday_rows,
    total_rows,
    relative_rows,
):
    lang = _lang(language_value)
    client_state, state = _session(session_payload, lang)
    active = state.get_scenario()
    if active is None:
        raise PreventUpdate
    display_bundle = resolve_workspace_bundle_for_display(client_state.session_id, active.scenario_id, active.config_bundle)
    demand_state = build_demand_profile_ui_state(
        bundle=display_bundle,
        lang=lang,
        profile_mode_value=profile_mode_value,
        relative_profile_type_value=profile_type_value,
        alpha_mix_value=alpha_mix_value,
        e_month_value=e_month_value,
        weekday_rows=weekday_rows,
        total_rows=total_rows,
        relative_rows=relative_rows,
    )
    demand_chart = build_active_demand_chart(lang=lang, demand_state=demand_state)
    return (
        demand_state["weekday_source_rows"],
        demand_state["total_source_rows"],
        demand_state["total_preview_rows"],
        demand_state["relative_source_rows"],
        demand_state["relative_preview_rows"],
        demand_state["visibility"]["demand-profile-panel"],
        demand_state["visibility"]["demand-profile-general-panel"],
        demand_state["visibility"]["demand-profile-general-preview-panel"],
        demand_state["visibility"]["demand-profile-weights-panel"],
        demand_state["weights_preview_style"],
        demand_state["e_month_kwh"],
        demand_state["alpha_disabled"],
        demand_state["energy_disabled"],
        demand_state["energy_shell_style"],
        demand_state["mode_note"],
        demand_state["alpha_shell_style"],
        demand_state["type_shell_style"],
        demand_state["relative_grid_style"],
        demand_state["secondary_grid_style"],
        demand_chart["style"],
        demand_chart["title"],
        demand_chart["copy"],
        demand_chart["figure"],
    )


@callback(
    Output("run-scan-choice-dialog", "style"),
    Output("run-scan-choice-title", "children"),
    Output("run-scan-choice-copy", "children"),
    Output("run-scan-save-and-run-btn", "children"),
    Output("run-scan-save-and-run-btn", "disabled"),
    Output("run-scan-run-unsaved-btn", "children"),
    Output("run-scan-cancel-btn", "children"),
    Input("run-scan-choice-state", "data"),
    Input("project-name-input", "value"),
    Input("language-selector", "value"),
)
def sync_run_scan_choice_dialog(dialog_state, project_name_value, language_value):
    lang = _lang(language_value)
    suggested_name = str((dialog_state or {}).get("suggested_project_name") or "").strip()
    project_name = str(project_name_value or "").strip() or suggested_name
    copy = (
        tr("workbench.run_dialog.body_named", lang, name=project_name)
        if project_name
        else tr("workbench.run_dialog.body_unnamed", lang)
    )
    style = {"display": "flex"} if (dialog_state or {}).get("open") else {"display": "none"}
    return (
        style,
        tr("workbench.run_dialog.title", lang),
        copy,
        tr("workbench.run_dialog.save_and_run", lang),
        not bool(project_name),
        tr("workbench.run_dialog.run_without_saving", lang),
        tr("workbench.run_dialog.cancel", lang),
    )


@callback(
    Output("project-name-input", "value", allow_duplicate=True),
    Input("run-scan-choice-state", "data"),
    Input("scenario-session-store", "data"),
    State("project-name-input", "value"),
    prevent_initial_call=True,
)
def sync_run_scan_suggested_project_name(dialog_state, _session_payload, project_name_value):
    if not (dialog_state or {}).get("open"):
        raise PreventUpdate
    if _clean_project_name_seed(project_name_value):
        raise PreventUpdate
    suggested_name = str((dialog_state or {}).get("suggested_project_name") or "").strip()
    if not suggested_name:
        raise PreventUpdate
    return suggested_name


def _sync_current_assumptions_slice(
    client_state,
    state,
    active,
    assumption_input_ids,
    assumption_values,
    demand_profile_mode_value,
    demand_profile_alpha_value,
    demand_profile_energy_value,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
):
    overrides, owned_fields, rows_payload, owned_tables = _assumptions_draft_payload(
        active,
        assumption_input_ids=assumption_input_ids,
        assumption_values=assumption_values,
        demand_profile_mode_value=demand_profile_mode_value,
        demand_profile_alpha_value=demand_profile_alpha_value,
        demand_profile_energy_value=demand_profile_energy_value,
        demand_profile_rows=demand_profile_rows,
        demand_profile_general_rows=demand_profile_general_rows,
        demand_profile_weights_rows=demand_profile_weights_rows,
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


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("workbench-status", "children", allow_duplicate=True),
    Output("run-scan-choice-state", "data"),
    Input("apply-assumptions-btn", "n_clicks"),
    Input("run-assumptions-scan-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("project-name-input", "value"),
    State({"type": "assumptions-input", "field": ALL}, "id"),
    State({"type": "assumptions-input", "field": ALL}, "value"),
    State("assumptions-demand-profile-mode-selector", "value", allow_optional=True),
    State("assumptions-demand-profile-alpha-slider", "value", allow_optional=True),
    State("assumptions-demand-profile-energy-input", "value", allow_optional=True),
    State("assumptions-demand-profile-editor", "data", allow_optional=True),
    State("assumptions-demand-profile-general-editor", "data", allow_optional=True),
    State("assumptions-demand-profile-weights-editor", "data", allow_optional=True),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("run-assumptions-scan-btn", "disabled"), True, False),
        (Output("assumptions-run-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def mutate_assumptions_state(
    _apply_clicks,
    _run_clicks,
    session_payload,
    project_name_value,
    assumption_input_ids,
    assumption_values,
    demand_profile_mode_value,
    demand_profile_alpha_value,
    demand_profile_energy_value,
    demand_profile_rows,
    demand_profile_general_rows,
    demand_profile_weights_rows,
    language_value,
):
    lang = _lang(language_value)
    trigger = ctx.triggered_id
    client_state, state = _session(session_payload, lang)
    closed_dialog = _run_choice_state()
    try:
        active = state.get_scenario()
        if active is None:
            raise PreventUpdate

        _sync_current_assumptions_slice(
            client_state,
            state,
            active,
            assumption_input_ids,
            assumption_values,
            demand_profile_mode_value,
            demand_profile_alpha_value,
            demand_profile_energy_value,
            demand_profile_rows,
            demand_profile_general_rows,
            demand_profile_weights_rows,
        )
        state, updated_active = apply_workspace_draft_to_state(
            state,
            session_id=client_state.session_id,
            scenario_id=active.scenario_id,
        )

        if trigger == "apply-assumptions-btn":
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
            return client_state.to_payload(), status, closed_dialog

        if trigger == "run-assumptions-scan-btn":
            if _project_is_bound(state):
                saved = False
                if _project_is_bound(state):
                    state = save_project(state, project_name=_resolved_project_name(project_name_value, state), language=lang)
                    updated_active = state.get_scenario(updated_active.scenario_id) or updated_active
                    saved = True
                if _bundle_has_errors(updated_active.config_bundle):
                    client_state = commit_client_session(client_state, state)
                    status = _join_status_parts(
                        tr("workbench.run_flow.applied", lang),
                        tr("workbench.run_flow.saved", lang) if saved else "",
                        tr("workbench.run_flow.validation_blocked", lang),
                    )
                    return client_state.to_payload(), status, closed_dialog
                state = run_scenario_scan(state, updated_active.scenario_id)
                updated = state.get_scenario(updated_active.scenario_id) or updated_active
                client_state = commit_client_session(client_state, state)
                status = _join_status_parts(
                    tr("workbench.run_flow.applied", lang),
                    tr("workbench.run_flow.saved", lang) if saved else "",
                    tr("workbench.run_flow.ran", lang, name=updated.name),
                )
                return client_state.to_payload(), status, closed_dialog

            if _bundle_has_errors(updated_active.config_bundle):
                client_state = commit_client_session(client_state, state)
                status = _join_status_parts(
                    tr("workbench.run_flow.applied", lang),
                    tr("workbench.run_flow.validation_blocked", lang),
                )
                return client_state.to_payload(), status, closed_dialog

            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.choose_save", lang),
            )
            return (
                client_state.to_payload(),
                status,
                _run_choice_state(
                    open_dialog=True,
                    suggested_project_name=_suggest_run_project_name(state, updated_active, lang=lang),
                ),
            )
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc), closed_dialog
    raise PreventUpdate


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Output("workbench-status", "children", allow_duplicate=True),
    Output("run-scan-choice-state", "data", allow_duplicate=True),
    Input("run-scan-save-and-run-btn", "n_clicks"),
    Input("run-scan-run-unsaved-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("project-name-input", "value"),
    State("run-scan-choice-state", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("run-assumptions-scan-btn", "disabled"), True, False),
        (Output("assumptions-run-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def resolve_run_scan_choice(
    _save_and_run_clicks,
    _run_without_saving_clicks,
    session_payload,
    project_name_value,
    dialog_state,
    language_value,
):
    lang = _lang(language_value)
    trigger = ctx.triggered_id
    client_state, state = _session(session_payload, lang)
    closed_dialog = _run_choice_state()
    suggested_name = str((dialog_state or {}).get("suggested_project_name") or "").strip()

    if not (dialog_state or {}).get("open"):
        raise PreventUpdate

    try:
        active = state.get_scenario()
        if active is None:
            raise PreventUpdate

        if _bundle_has_errors(active.config_bundle):
            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.validation_blocked", lang),
            )
            return client_state.to_payload(), status, closed_dialog

        if trigger == "run-scan-save-and-run-btn":
            resolved_name = _resolved_project_name(project_name_value, state, suggested_name=suggested_name)
            if not resolved_name:
                return no_update, tr("workbench.run_dialog.name_required", lang), dialog_state
            state = save_project(state, project_name=resolved_name, language=lang)
            active = state.get_scenario(active.scenario_id) or active
            state = run_scenario_scan(state, active.scenario_id)
            updated = state.get_scenario(active.scenario_id) or active
            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.saved", lang),
                tr("workbench.run_flow.ran", lang, name=updated.name),
            )
            return client_state.to_payload(), status, closed_dialog

        if trigger == "run-scan-run-unsaved-btn":
            state = run_scenario_scan(state, active.scenario_id)
            updated = state.get_scenario(active.scenario_id) or active
            client_state = commit_client_session(client_state, state)
            status = _join_status_parts(
                tr("workbench.run_flow.applied", lang),
                tr("workbench.run_flow.ran_without_saving", lang, name=updated.name),
            )
            return client_state.to_payload(), status, closed_dialog
    except PreventUpdate:
        raise
    except Exception as exc:
        client_state = commit_client_session(client_state, state, bump_revision=False)
        return client_state.to_payload(), workbench_status_message("common.action_failed", lang, error=exc), closed_dialog
    raise PreventUpdate


@callback(
    Output("workbench-status", "children", allow_duplicate=True),
    Output("run-scan-choice-state", "data", allow_duplicate=True),
    Input("run-scan-cancel-btn", "n_clicks"),
    State("run-scan-choice-state", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def cancel_run_scan_choice(_cancel_clicks, dialog_state, language_value):
    if not (dialog_state or {}).get("open"):
        raise PreventUpdate
    lang = _lang(language_value)
    status = _join_status_parts(
        tr("workbench.run_flow.applied", lang),
        tr("workbench.run_flow.cancelled", lang),
    )
    return status, _run_choice_state()
