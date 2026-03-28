from __future__ import annotations

import base64

from dash import Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.graph_objects as go

from pv_product.panel_catalog import MANUAL_PANEL_TOKEN, manual_panel_label, normalize_panel_name
from pv_product.panel_technology import panel_technology_field_label, panel_technology_mode_label

from .export_access import open_export_folder, publish_export_artifacts
from .export_artifacts import export_deterministic_artifacts
from .export_excel import export_scenario_workbook
from .i18n import tr
from .result_views import (
    build_annual_coverage_figure,
    build_battery_load_figure,
    build_cash_flow,
    build_cash_flow_figure,
    build_kpis,
    build_monthly_balance,
    build_monthly_balance_figure,
    build_npv_figure,
    build_typical_day_figure,
    build_visible_horizon_candidate_summary,
    format_horizon_year_value,
    resolve_selected_candidate_key_for_scenario,
    summarize_candidates_for_horizon,
)
from .runtime_paths import internal_results_root, project_exports_root
from .schematic import (
    build_schematic_legend,
    build_unifilar_model,
    default_schematic_inspector,
    resolve_schematic_focus,
    resolve_schematic_inspector,
    to_cytoscape_elements,
)
from .session_state import commit_client_session, resolve_scenario_session
from .workspace_status import resolve_results_status_digest
from .scenario_session import update_selected_candidate
from components import render_kpi_cards, render_schematic_inspector, render_schematic_legend
from .ui_schema import build_display_columns, format_metric


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _session_with_scan(payload, language_value: str | None):
    client_state, session_state = resolve_scenario_session(payload, ensure_scan=True, language=_lang(language_value))
    return client_state, session_state, session_state.get_scenario()


def _download_payload(content: bytes, filename: str) -> dict:
    return {"content": base64.b64encode(content).decode("ascii"), "filename": filename, "base64": True}


def _empty_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def _candidate_table_styles(selected_key: str, best_key: str) -> list[dict]:
    styles = [
        {
            "if": {"filter_query": "{best_battery_for_kwp} = true"},
            "backgroundColor": "#eff6ff",
        }
    ]
    if best_key:
        styles.insert(
            0,
            {
                "if": {"filter_query": f'{{candidate_key}} = "{best_key}"'},
                "backgroundColor": "#dcfce7",
                "fontWeight": "bold",
            },
        )
    if selected_key:
        styles.append(
            {
                "if": {"filter_query": f'{{candidate_key}} = "{selected_key}"'},
                "backgroundColor": "#fee2e2",
                "borderTop": "2px solid #b91c1c",
                "borderBottom": "2px solid #b91c1c",
                "fontWeight": "bold",
            }
        )
    return styles


def _selected_candidate_banner(detail: dict | None, *, lang: str = "es") -> list[html.Div]:
    fallback = "—"
    if not detail:
        return [
            html.Div(
                className="selected-candidate-banner-item",
                children=[
                    html.Span(tr("workbench.selected_design.banner.label", lang), className="selected-candidate-banner-label"),
                    html.Span(fallback, className="selected-candidate-banner-value"),
                ],
            )
        ]
    inverter_name = (((detail.get("inv_sel") or {}).get("inverter") or {}).get("name")) or fallback
    battery_name = format_metric("selected_battery", detail.get("battery_name", "None"), lang) if detail.get("battery_name") is not None else fallback
    visible_summary = detail.get("visible_horizon_summary") or {}
    project_summary = detail.get("project_summary") or detail.get("summary") or {}
    npv_value = visible_summary.get("NPV_COP")
    if npv_value is None:
        npv_value = project_summary.get("cum_disc_final")
    kwp_value = detail.get("kWp")
    banner_values = [
        (tr("workbench.selected_design.banner.kwp", lang), f"{float(kwp_value):.3f} kWp" if kwp_value is not None else fallback),
        (tr("workbench.selected_design.banner.battery", lang), battery_name or fallback),
        (tr("workbench.selected_design.banner.inverter", lang), str(inverter_name)),
        (tr("workbench.selected_design.banner.npv", lang), format_metric("NPV_COP", npv_value, lang) if npv_value is not None else fallback),
    ]
    return [
        html.Div(
            className="selected-candidate-banner-item",
            children=[
                html.Span(label, className="selected-candidate-banner-label"),
                html.Span(value, className="selected-candidate-banner-value"),
            ],
        )
        for label, value in banner_values
    ]


def _has_viable_scan_result(scan_result) -> bool:
    return scan_result is not None and not scan_result.candidates.empty and bool(scan_result.candidate_details)


def _scenario_horizon_years(active) -> int:
    if active is None:
        return 1
    configured_years = (active.config_bundle.config or {}).get("years", 1)
    try:
        return max(1, int(float(configured_years)))
    except (TypeError, ValueError):
        return 1


def _resolved_candidate_horizon(active, slider_value) -> int:
    max_years = _scenario_horizon_years(active)
    try:
        requested_years = int(float(slider_value))
    except (TypeError, ValueError):
        requested_years = max_years
    return max(1, min(requested_years, max_years))


def _candidate_horizon_marks(max_years: int) -> dict[int, str]:
    if max_years <= 6:
        marks = list(range(1, max_years + 1))
    elif max_years <= 10:
        marks = sorted({1, *range(2, max_years, 2), max_years})
    else:
        marks = sorted({1, max(2, round(max_years / 2)), max_years})
    return {int(year): str(int(year)) for year in marks}


def _visible_horizon_candidate_presentation(detail: dict | None, horizon_years: int) -> dict | None:
    if not detail:
        return detail
    return build_visible_horizon_candidate_summary(detail, horizon_years)


def _payback_note_for_presentation(detail: dict | None, *, lang: str = "es") -> dict[str, str]:
    if not detail:
        return {}
    payback_state = detail.get("payback_display_state") or {}
    message_key = payback_state.get("message_key")
    if not message_key:
        return {}
    return {"payback_years": tr(str(message_key), lang)}


def _apply_workbench_table_text(columns: list[dict], tooltip_header: dict[str, str], *, lang: str = "es") -> tuple[list[dict], dict[str, str]]:
    next_columns = [dict(column) for column in columns]
    next_tooltips = dict(tooltip_header)
    next_tooltips["payback_years"] = tr("workbench.horizon.helper", lang)
    for column in next_columns:
        if column.get("id") == "payback_years":
            column["name"] = tr("workbench.payback.project_axis_label", lang)
            break
    return next_columns, next_tooltips


def _scan_max_evaluated_kwp(scan_result) -> float | None:
    values: list[float] = []
    if scan_result is None:
        return None
    if not scan_result.candidates.empty and "kWp" in scan_result.candidates.columns:
        values.extend(float(value) for value in scan_result.candidates["kWp"].dropna().tolist())
    values.extend(
        float(point["kWp"])
        for point in scan_result.discarded_points
        if point.get("kWp") not in (None, "")
    )
    return max(values) if values else None


def _dominant_discard_reasons(scan_result) -> list[str]:
    counts = dict(scan_result.discard_counts or {})
    ordered = ["peak_ratio", "inverter_string"]
    highest = max((int(counts.get(reason, 0)) for reason in ordered), default=0)
    if highest <= 0:
        return []
    return [reason for reason in ordered if int(counts.get(reason, 0)) == highest]


def _join_reason_labels(reason_labels: list[str], lang: str) -> str:
    if not reason_labels:
        return ""
    if len(reason_labels) == 1:
        return reason_labels[0]
    conjunction = " y " if lang == "es" else " and "
    if len(reason_labels) == 2:
        return conjunction.join(reason_labels)
    return ", ".join(reason_labels[:-1]) + f"{conjunction}{reason_labels[-1]}"


def _panel_model_summary_label(panel_name: str | None, *, lang: str = "es") -> str:
    normalized = normalize_panel_name(panel_name)
    if normalized == MANUAL_PANEL_TOKEN:
        return manual_panel_label(lang)
    return normalized


def _scan_summary_strip(
    scan_result,
    *,
    panel_technology_mode: str | None = None,
    panel_name: str | None = None,
    lang: str = "es",
) -> list[html.Div]:
    if scan_result is None:
        return []
    cards = [
        ("workbench.scan_summary.evaluated", int(scan_result.evaluated_kwp_count)),
        ("workbench.scan_summary.viable", int(scan_result.viable_kwp_count)),
        ("workbench.scan_summary.discard_peak_ratio", int((scan_result.discard_counts or {}).get("peak_ratio", 0))),
        ("workbench.scan_summary.discard_inverter_string", int((scan_result.discard_counts or {}).get("inverter_string", 0))),
        ("Modelo de panel" if lang == "es" else "Panel model", _panel_model_summary_label(panel_name, lang=lang)),
        (panel_technology_field_label(lang), panel_technology_mode_label(panel_technology_mode, lang)),
    ]
    return [
        html.Div(
            className="scan-summary-card",
            children=[
                html.Span(tr(label_key, lang) if label_key.startswith("workbench.") else label_key, className="scan-summary-label"),
                html.Span(f"{value:,}" if isinstance(value, int) else str(value), className="scan-summary-value"),
            ],
        )
        for label_key, value in cards
    ]


def _scan_discard_explainer(scan_result, *, lang: str = "es") -> tuple[str, dict[str, str]]:
    if scan_result is None:
        return "", {"display": "none"}
    discard_total = sum(int(value) for value in (scan_result.discard_counts or {}).values())
    if discard_total <= 0:
        return "", {"display": "none"}
    max_kwp = _scan_max_evaluated_kwp(scan_result) or 0.0
    reasons = _dominant_discard_reasons(scan_result)
    dominant = _join_reason_labels([tr(f"workbench.scan_discard.reason.{reason}", lang) for reason in reasons], lang)
    if int(scan_result.viable_kwp_count) <= 0:
        key = "workbench.scan_discard.explainer.all"
    else:
        key = "workbench.scan_discard.explainer.partial"
    return tr(key, lang, max_kwp=max_kwp, reason=dominant), {"display": "block"}


@callback(
    Output("results-page-title", "children"),
    Output("results-page-copy", "children"),
    Output("candidate-explorer-title", "children"),
    Output("candidate-export-note", "children"),
    Output("candidate-explorer-intro", "children"),
    Output("candidate-horizon-label", "children"),
    Output("candidate-horizon-helper", "children"),
    Output("selected-candidate-kpi-title", "children"),
    Output("candidate-selection-helper", "children"),
    Output("selected-candidate-deep-dive-title", "children"),
    Output("selected-candidate-deep-dive-note", "children"),
    Output("scenario-export-btn", "children"),
    Output("scenario-artifacts-btn", "children"),
    Output("scenario-open-exports-btn", "children"),
    Output("scenario-artifacts-progress", "children"),
    Input("language-selector", "value"),
)
def translate_results_page(language_value):
    lang = _lang(language_value)
    return (
        tr("workspace.results.title", lang),
        tr("workspace.results.copy", lang),
        tr("workbench.candidate_explorer", lang),
        tr("workbench.export.note", lang),
        tr("workbench.candidate_explorer.intro", lang),
        tr("workbench.horizon.label", lang),
        tr("workbench.horizon.helper", lang),
        tr("workbench.selected_design.summary", lang),
        tr("workbench.candidate_selection.helper", lang),
        tr("workbench.deep_dive.title", lang),
        tr("workbench.deep_dive.note", lang),
        tr("workbench.export_scenario", lang),
        tr("common.export_artifacts", lang),
        tr("common.open_exports_folder", lang),
        tr("workbench.export_artifacts_running", lang),
    )


@callback(
    Output("results-status-digest", "children"),
    Output("results-status-digest", "className"),
    Output("results-status-digest", "style"),
    Output("results-main-content", "style"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_results_digest(session_payload, language_value):
    lang = _lang(language_value)
    _, _, active = _session_with_scan(session_payload, lang)
    digest = resolve_results_status_digest(active)
    if digest is None:
        return [], "panel results-status-digest", {"display": "none"}, {"display": "block"}
    cta = (
        dcc.Link(tr(digest.cta_label_key, lang), href=digest.cta_href, className="action-btn")
        if digest.cta_href and digest.cta_label_key
        else None
    )
    children = [
        html.H3(tr(digest.title_key, lang)),
        html.P(tr(digest.body_key, lang), className="section-copy"),
    ]
    if cta is not None:
        children.append(html.Div(className="controls", children=[cta]))
    return children, f"panel results-status-digest results-status-digest-{digest.tone}", {"display": "block"}, {"display": "none"}


@callback(
    Output("candidate-horizon-slider", "min"),
    Output("candidate-horizon-slider", "max"),
    Output("candidate-horizon-slider", "marks"),
    Output("candidate-horizon-slider", "value"),
    Output("candidate-horizon-slider", "disabled"),
    Output("candidate-horizon-toolbar", "style"),
    Output("candidate-horizon-value", "children"),
    Output("candidate-horizon-context", "data"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
    State("candidate-horizon-slider", "value"),
    State("candidate-horizon-context", "data"),
)
def sync_candidate_horizon_slider(session_payload, language_value, current_value, current_context):
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    hidden_style = {"display": "none"}
    if active is None or active.scan_result is None or not _has_viable_scan_result(active.scan_result):
        return 1, 1, {1: "1"}, 1, True, hidden_style, "", {}

    max_years = _scenario_horizon_years(active)
    next_context = {
        "scenario_id": active.scenario_id,
        "scan_fingerprint": active.scan_fingerprint,
        "max_years": max_years,
    }
    if next_context != (current_context or {}):
        value = max_years
    else:
        try:
            resolved_value = int(float(current_value))
        except (TypeError, ValueError):
            resolved_value = max_years
        value = max(1, min(resolved_value, max_years))
    return (
        1,
        max_years,
        _candidate_horizon_marks(max_years),
        value,
        False,
        {},
        format_horizon_year_value(value, lang=lang),
        next_context,
    )


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Input("active-candidate-table", "selected_rows"),
    Input("active-npv-graph", "clickData"),
    State("active-candidate-table", "data"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def persist_selected_candidate(selected_rows, click_data, table_rows, session_payload):
    client_state, state, active = _session_with_scan(session_payload, None)
    if active is None or active.scan_result is None:
        raise PreventUpdate
    selected_key = resolve_selected_candidate_key_for_scenario(
        active.scan_result,
        active.selected_candidate_key,
        table_rows=table_rows,
        selected_rows=selected_rows,
        click_data=click_data,
    )
    if selected_key == active.selected_candidate_key:
        raise PreventUpdate
    state = update_selected_candidate(state, active.scenario_id, selected_key)
    client_state = commit_client_session(client_state, state)
    return client_state.to_payload()


@callback(
    Output("scan-summary-strip", "children"),
    Output("scan-discard-explainer", "children"),
    Output("scan-discard-explainer", "style"),
    Output("active-kpi-cards", "children"),
    Output("active-npv-graph", "figure"),
    Output("selected-candidate-banner", "children"),
    Output("active-monthly-balance-graph", "figure"),
    Output("active-cash-flow-graph", "figure"),
    Output("active-annual-coverage-graph", "figure"),
    Output("active-battery-load-graph", "figure"),
    Output("active-typical-day-graph", "figure"),
    Output("active-candidate-table", "data"),
    Output("active-candidate-table", "columns"),
    Output("active-candidate-table", "selected_rows"),
    Output("active-candidate-table", "style_data_conditional"),
    Output("active-candidate-table", "tooltip_header"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
    Input("candidate-horizon-slider", "value"),
)
def populate_results(session_payload, language_value, horizon_slider_value):
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    empty = _empty_figure(tr("common.results", lang), tr("workbench.results.empty", lang))
    if active is None or active.scan_result is None:
        return [], "", {"display": "none"}, [], empty, [], empty, empty, empty, empty, empty, [], [], [], [], {}

    scan = active.scan_result
    horizon_years = _resolved_candidate_horizon(active, horizon_slider_value)
    summary_strip = _scan_summary_strip(
        scan,
        panel_technology_mode=active.config_bundle.config.get("panel_technology_mode"),
        panel_name=active.config_bundle.config.get("panel_name"),
        lang=lang,
    )
    discard_explainer, discard_explainer_style = _scan_discard_explainer(scan, lang=lang)
    selected_key = resolve_selected_candidate_key_for_scenario(scan, active.selected_candidate_key)
    table = summarize_candidates_for_horizon(scan.candidate_details, horizon_years)
    table["battery"] = table["battery"].replace({"None": tr("common.no_battery", lang)})
    visible_columns = [
        "kWp",
        "battery",
        "NPV_COP",
        "payback_years",
        "capex_client",
        "self_consumption_ratio",
        "self_sufficiency_ratio",
        "annual_import_kwh",
        "annual_export_kwh",
        "peak_ratio",
    ]
    columns, tooltip_header = build_display_columns(visible_columns, lang)
    columns, tooltip_header = _apply_workbench_table_text(columns, tooltip_header, lang=lang)
    columns.extend(
        [
            {"name": "candidate_key", "id": "candidate_key"},
            {"name": "scan_order", "id": "scan_order"},
            {"name": "best_battery_for_kwp", "id": "best_battery_for_kwp"},
        ]
    )
    selected_index = table.index[table["candidate_key"] == selected_key].tolist() if selected_key else []
    best_key = None if table.empty else str(
        table.sort_values(by=["NPV_COP", "scan_order"], ascending=[False, True], kind="mergesort").iloc[0]["candidate_key"]
    )
    styles = _candidate_table_styles(selected_key, best_key)
    module_power_w = float(active.config_bundle.config.get("P_mod_W", 0.0) or 0.0)
    npv_figure = build_npv_figure(
        table,
        selected_key=selected_key,
        lang=lang,
        horizon_years=horizon_years,
        payback_label=tr("workbench.payback.project_axis_label", lang),
        module_power_w=module_power_w,
        discarded_points=scan.discarded_points,
    )
    if not _has_viable_scan_result(scan) or not selected_key:
        detail_empty = _empty_figure(tr("common.results", lang), tr("workbench.scan_discard.no_viable_detail", lang))
        return (
            summary_strip,
            discard_explainer,
            discard_explainer_style,
            [],
            npv_figure,
            _selected_candidate_banner(None, lang=lang),
            detail_empty,
            detail_empty,
            detail_empty,
            detail_empty,
            detail_empty,
            table.to_dict("records"),
            columns,
            [],
            styles,
            tooltip_header,
        )

    detail = scan.candidate_details[selected_key]
    presentation_detail = _visible_horizon_candidate_presentation(detail, horizon_years)
    kpis = build_kpis(presentation_detail)
    monthly_balance = build_monthly_balance(detail["monthly"], lang=lang)
    cash_flow = build_cash_flow(detail["monthly"])
    return (
        summary_strip,
        discard_explainer,
        discard_explainer_style,
        render_kpi_cards(
            kpis,
            lang,
            label_overrides={"payback_years": tr("workbench.payback.project_label", lang)},
            notes=_payback_note_for_presentation(presentation_detail, lang=lang),
        ),
        npv_figure,
        _selected_candidate_banner(presentation_detail, lang=lang),
        build_monthly_balance_figure(monthly_balance, lang=lang),
        build_cash_flow_figure(cash_flow, lang=lang, k_wp=float(detail["kWp"]), module_power_w=module_power_w),
        build_annual_coverage_figure(detail, active.config_bundle.config, lang=lang),
        build_battery_load_figure(detail, active.config_bundle.config, lang=lang),
        build_typical_day_figure(detail, active, lang=lang),
        table.to_dict("records"),
        columns,
        [selected_index[0]] if selected_index else [],
        styles,
        tooltip_header,
    )


@callback(
    Output("unifilar-diagram-title", "children"),
    Output("unifilar-diagram-summary", "children"),
    Output("unifilar-diagram-empty", "children"),
    Output("unifilar-diagram-empty", "style"),
    Output("unifilar-diagram-note", "children"),
    Output("unifilar-diagram-shell", "style"),
    Output("active-unifilar-diagram", "elements"),
    Output("active-unifilar-diagram", "style"),
    Output("unifilar-legend-title", "children"),
    Output("unifilar-legend-items", "children"),
    Output("unifilar-inspector-title", "children"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_unifilar_diagram(session_payload, language_value):
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    title = tr("workbench.schematic.title", lang)
    empty_message = tr("workbench.schematic.empty", lang)
    legend_title = tr("workbench.schematic.legend.title", lang)
    inspector_title = tr("workbench.schematic.inspector.title", lang)
    legend_children = render_schematic_legend(build_schematic_legend(lang))
    if active is None or active.scan_result is None:
        return (
            title,
            "",
            empty_message,
            {"display": "block"},
            "",
            {"display": "none"},
            [],
            {"width": "100%", "height": "420px"},
            legend_title,
            legend_children,
            inspector_title,
        )

    selected_key = resolve_selected_candidate_key_for_scenario(active.scan_result, active.selected_candidate_key)
    if not selected_key:
        return (
            title,
            "",
            tr("workbench.schematic.no_viable", lang),
            {"display": "block"},
            "",
            {"display": "none"},
            [],
            {"width": "100%", "height": "420px"},
            legend_title,
            legend_children,
            inspector_title,
        )
    model = build_unifilar_model(active, selected_key, lang=lang)
    return (
        title,
        model.string_summary,
        "",
        {"display": "none"},
        model.note,
        {"display": "block"},
        to_cytoscape_elements(model),
        {"width": "100%", "height": f"{model.diagram_height}px"},
        legend_title,
        legend_children,
        inspector_title,
    )


@callback(
    Output("unifilar-inspector-lock", "data"),
    Input("active-unifilar-diagram", "tapNodeData"),
    Input("scenario-session-store", "data"),
)
def sync_unifilar_inspector_lock(tap_node, session_payload):
    trigger = ctx.triggered_id
    if trigger == "active-unifilar-diagram" and tap_node and tap_node.get("id"):
        return {"node_id": str(tap_node["id"])}
    return None


@callback(
    Output("unifilar-inspector-body", "children"),
    Input("unifilar-inspector-lock", "data"),
    Input("scenario-session-store", "data"),
    Input("language-selector", "value"),
)
def populate_unifilar_inspector(inspector_lock, session_payload, language_value):
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    if active is None or active.scan_result is None:
        return render_schematic_inspector(default_schematic_inspector(model=None, lang=lang))

    selected_key = resolve_selected_candidate_key_for_scenario(active.scan_result, active.selected_candidate_key)
    if not selected_key:
        return render_schematic_inspector(default_schematic_inspector(model=None, lang=lang))
    model = build_unifilar_model(active, selected_key, lang=lang)
    locked_node_id = str((inspector_lock or {}).get("node_id") or "") or None
    node_data, is_locked = resolve_schematic_focus(locked_node_id=locked_node_id, hover_node_data=None)
    inspector = resolve_schematic_inspector(node_data, model, lang=lang, locked=is_locked)
    return render_schematic_inspector(inspector)


@callback(
    Output("scenario-download", "data"),
    Input("scenario-export-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def export_active_scenario(n_clicks, session_payload):
    if not n_clicks:
        raise PreventUpdate
    _, state, active = _session_with_scan(session_payload, None)
    if active is None or active.scan_result is None or active.dirty or not _has_viable_scan_result(active.scan_result):
        raise PreventUpdate
    content = export_scenario_workbook(active)
    filename = f"{active.name.replace(' ', '_')}_deterministic.xlsx"
    return _download_payload(content, filename)


@callback(
    Output("workbench-status", "children", allow_duplicate=True),
    Output("workbench-latest-export-folder", "data"),
    Input("scenario-artifacts-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("scenario-artifacts-btn", "disabled"), True, False),
        (Output("scenario-artifacts-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def export_active_artifacts(n_clicks, session_payload, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    _, state, active = _session_with_scan(session_payload, lang)
    if active is None or active.scan_result is None or active.dirty or not _has_viable_scan_result(active.scan_result):
        raise PreventUpdate
    output_root = project_exports_root(state.project_slug) if state.project_slug else internal_results_root()
    paths = export_deterministic_artifacts(active, output_root=output_root)
    publish_result = publish_export_artifacts(
        paths,
        project_slug=state.project_slug,
        scenario_slug=active.name or active.scenario_id,
        export_kind="deterministic",
    )
    if publish_result.published_root is not None:
        published_path = str(publish_result.published_root.resolve())
        return tr("workbench.export_artifacts_done", lang, path=published_path), published_path
    if publish_result.publish_error:
        return (
            tr(
                "workbench.export_artifacts_partial",
                lang,
                path=str(publish_result.internal_root.resolve()),
                error=publish_result.publish_error,
            ),
            "",
        )
    return tr("workbench.export_artifacts_done", lang, path=str(publish_result.display_root.resolve())), ""


@callback(
    Output("scenario-open-exports-btn", "disabled"),
    Input("workbench-latest-export-folder", "data"),
)
def sync_workbench_export_folder_button(folder_path):
    return not bool(folder_path)


@callback(
    Output("workbench-status", "children", allow_duplicate=True),
    Input("scenario-open-exports-btn", "n_clicks"),
    State("workbench-latest-export-folder", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def open_workbench_exports_folder(n_clicks, folder_path, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    if not folder_path:
        return tr("common.exports_folder_unavailable", lang, error=tr("common.exports_folder_none", lang))
    try:
        open_export_folder(folder_path)
    except (FileNotFoundError, OSError, RuntimeError) as exc:
        return tr("common.exports_folder_unavailable", lang, error=str(exc))
    return tr("common.exports_folder_opened", lang, path=folder_path)
