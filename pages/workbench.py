from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

import pandas as pd
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, register_page
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from components import (
    ASSUMPTION_FIELDS,
    assumption_editor_section,
    assumption_values_from_config,
    candidate_explorer_section,
    catalog_editor_section,
    render_kpi_cards,
    render_validation_panel,
    scenario_sidebar,
)
from services import (
    ScenarioSessionState,
    create_scenario_record,
    default_scenario_name,
    delete_scenario,
    duplicate_scenario,
    export_scenario_workbook,
    load_config_from_excel,
    load_example_config,
    normalize_battery_catalog_rows,
    normalize_inverter_catalog_rows,
    rename_scenario,
    resolve_selected_candidate_key_for_scenario,
    run_scenario_scan,
    set_active_scenario,
    update_scenario_bundle,
    update_selected_candidate,
)
from services.result_views import (
    build_cash_flow,
    build_cash_flow_figure,
    build_kpis,
    build_monthly_balance,
    build_monthly_balance_figure,
    build_npv_figure,
)
from services.validation import BATTERY_REQUIRED_COLUMNS, INVERTER_REQUIRED_COLUMNS

register_page(__name__, path="/", name="Workbench")


def _empty_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def _state(payload) -> ScenarioSessionState:
    return ScenarioSessionState.from_payload(payload)


def _download_payload(content: bytes, filename: str) -> dict:
    return {"content": base64.b64encode(content).decode("ascii"), "filename": filename, "base64": True}


def _table_columns(frame: pd.DataFrame) -> list[dict]:
    return [{"name": column, "id": column} for column in frame.columns]


def _scenario_name_from_filename(filename: str | None, fallback: str) -> str:
    if filename:
        stem = Path(filename).stem.strip()
        if stem:
            return stem
    return fallback


layout = html.Div(
    className="page",
    children=[
        dcc.Download(id="scenario-download"),
        html.Div(
            className="workbench-grid",
            children=[
                scenario_sidebar(),
                html.Div(
                    className="main-stack",
                    children=[
                        html.Div(
                            className="panel",
                            children=[
                                html.Div(
                                    className="section-head",
                                    children=[
                                        html.H2("Active scenario"),
                                        html.Div(
                                            className="controls",
                                            children=[html.Button("Run deterministic scan", id="run-active-scan-btn", n_clicks=0, className="action-btn")],
                                        ),
                                    ],
                                ),
                                html.Div(id="active-source-status", className="status-line"),
                                html.Div(id="active-run-status", className="status-line"),
                                html.H3("Validation"),
                                html.Div(id="active-validation"),
                            ],
                        ),
                        assumption_editor_section(),
                        catalog_editor_section(),
                        candidate_explorer_section(),
                    ],
                ),
            ],
        ),
    ],
)


@callback(
    Output("scenario-dropdown", "options"),
    Output("scenario-dropdown", "value"),
    Output("rename-scenario-input", "value"),
    Output("scenario-overview-list", "children"),
    Output("active-source-status", "children"),
    Output("active-run-status", "children"),
    Output("active-validation", "children"),
    Output("run-active-scan-btn", "disabled"),
    Output("scenario-export-btn", "disabled"),
    Input("scenario-session-store", "data"),
)
def populate_scenario_shell(session_payload):
    state = _state(session_payload)
    options = [{"label": scenario.name, "value": scenario.scenario_id} for scenario in state.scenarios]
    active = state.get_scenario()
    pills = []
    for scenario in state.scenarios:
        css = "scenario-pill active" if scenario.scenario_id == state.active_scenario_id else "scenario-pill"
        status = "dirty" if scenario.dirty else "ready"
        pills.append(
            html.Div(
                className=css,
                children=[
                    html.Div(scenario.name),
                    html.Div(f"{scenario.source_name} · {status}", className="scenario-meta"),
                ],
            )
        )

    if active is None:
        return options, None, "", pills, "No active scenario.", "Run status: pending.", render_validation_panel([]), True, True

    run_status = "Run status: not executed yet."
    if active.last_run_at:
        run_status = f"Last deterministic run: {active.last_run_at}."
    validation_children = render_validation_panel(active.config_bundle.issues)
    has_errors = any(issue.level == "error" for issue in active.config_bundle.issues)
    export_disabled = active.scan_result is None or active.dirty
    return (
        options,
        active.scenario_id,
        active.name,
        pills,
        f"Source: {active.source_name}.",
        run_status,
        validation_children,
        has_errors,
        export_disabled,
    )


@callback(
    Output({"type": "assumption-input", "field": ALL}, "value"),
    Output("inverter-table-editor", "data"),
    Output("inverter-table-editor", "columns"),
    Output("battery-table-editor", "data"),
    Output("battery-table-editor", "columns"),
    Input("scenario-session-store", "data"),
)
def populate_editors(session_payload):
    state = _state(session_payload)
    active = state.get_scenario()
    if active is None:
        return [None for _ in ASSUMPTION_FIELDS], [], [], [], []
    inverter_catalog = active.config_bundle.inverter_catalog.copy()
    battery_catalog = active.config_bundle.battery_catalog.copy()
    return (
        assumption_values_from_config(active.config_bundle.config),
        inverter_catalog.to_dict("records"),
        _table_columns(inverter_catalog),
        battery_catalog.to_dict("records"),
        _table_columns(battery_catalog),
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
    Output("scenario-session-store", "data"),
    Output("workbench-status", "children"),
    Input("scenario-upload", "contents"),
    Input("load-example-btn", "n_clicks"),
    Input("duplicate-scenario-btn", "n_clicks"),
    Input("rename-scenario-btn", "n_clicks"),
    Input("delete-scenario-btn", "n_clicks"),
    Input("apply-edits-btn", "n_clicks"),
    Input("run-active-scan-btn", "n_clicks"),
    Input("set-active-scenario-btn", "n_clicks"),
    State("scenario-upload", "filename"),
    State("rename-scenario-input", "value"),
    State("scenario-dropdown", "value"),
    State("scenario-session-store", "data"),
    State({"type": "assumption-input", "field": ALL}, "value"),
    State("inverter-table-editor", "data"),
    State("battery-table-editor", "data"),
    prevent_initial_call=True,
)
def mutate_session_state(
    upload_contents,
    _example_clicks,
    _duplicate_clicks,
    _rename_clicks,
    _delete_clicks,
    _apply_clicks,
    _run_clicks,
    _set_active_clicks,
    upload_filename,
    rename_value,
    scenario_dropdown_value,
    session_payload,
    assumption_values,
    inverter_rows,
    battery_rows,
):
    trigger = ctx.triggered_id
    state = _state(session_payload)

    try:
        if trigger == "scenario-upload":
            if not upload_contents:
                raise PreventUpdate
            _, encoded = upload_contents.split(",", 1)
            bundle = load_config_from_excel(base64.b64decode(encoded))
            scenario_name = _scenario_name_from_filename(upload_filename, default_scenario_name(state))
            record = create_scenario_record(scenario_name, bundle, source_name=upload_filename or bundle.source_name)
            state = replace(state, scenarios=(*state.scenarios, record), active_scenario_id=record.scenario_id)
            return state.to_payload(), f"Loaded workbook into scenario '{record.name}'."

        if trigger == "load-example-btn":
            bundle = load_example_config()
            name = default_scenario_name(state)
            record = create_scenario_record(name, bundle, source_name=bundle.source_name)
            state = replace(state, scenarios=(*state.scenarios, record), active_scenario_id=record.scenario_id)
            return state.to_payload(), f"Loaded bundled example as '{record.name}'."

        active = state.get_scenario()
        if active is None:
            raise PreventUpdate

        if trigger == "duplicate-scenario-btn":
            state = duplicate_scenario(state, active.scenario_id)
            return state.to_payload(), "Duplicated active scenario."

        if trigger == "rename-scenario-btn":
            state = rename_scenario(state, active.scenario_id, rename_value or active.name)
            return state.to_payload(), "Renamed active scenario."

        if trigger == "delete-scenario-btn":
            state = delete_scenario(state, active.scenario_id)
            return state.to_payload(), "Deleted active scenario."

        if trigger == "set-active-scenario-btn":
            if scenario_dropdown_value == state.active_scenario_id:
                raise PreventUpdate
            state = set_active_scenario(state, scenario_dropdown_value)
            selected = state.get_scenario()
            return state.to_payload(), f"Active scenario set to '{selected.name}'." if selected else "No active scenario."

        if trigger == "apply-edits-btn":
            config = dict(active.config_bundle.config)
            for definition, value in zip(ASSUMPTION_FIELDS, assumption_values):
                config[definition["field"]] = value
            inverter_catalog, inverter_issues = normalize_inverter_catalog_rows(inverter_rows)
            battery_catalog, battery_issues = normalize_battery_catalog_rows(battery_rows)
            updated_bundle = replace(
                active.config_bundle,
                config=config,
                inverter_catalog=inverter_catalog,
                battery_catalog=battery_catalog,
                issues=tuple([*inverter_issues, *battery_issues]),
            )
            state = update_scenario_bundle(state, active.scenario_id, updated_bundle)
            return state.to_payload(), "Applied scenario edits. Deterministic results marked dirty until rerun."

        if trigger == "run-active-scan-btn":
            state = run_scenario_scan(state, active.scenario_id)
            updated = state.get_scenario(active.scenario_id)
            return state.to_payload(), f"Deterministic scan completed for '{updated.name}'."

    except PreventUpdate:
        raise
    except Exception as exc:
        return state.to_payload(), f"Action failed: {exc}"

    raise PreventUpdate


@callback(
    Output("scenario-session-store", "data", allow_duplicate=True),
    Input("active-candidate-table", "selected_rows"),
    Input("active-npv-graph", "clickData"),
    State("active-candidate-table", "data"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def persist_selected_candidate(selected_rows, click_data, table_rows, session_payload):
    state = _state(session_payload)
    active = state.get_scenario()
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
    return state.to_payload()


@callback(
    Output("active-kpi-cards", "children"),
    Output("active-npv-graph", "figure"),
    Output("active-monthly-balance-graph", "figure"),
    Output("active-cash-flow-graph", "figure"),
    Output("active-candidate-table", "data"),
    Output("active-candidate-table", "columns"),
    Output("active-candidate-table", "selected_rows"),
    Output("active-candidate-table", "style_data_conditional"),
    Input("scenario-session-store", "data"),
)
def populate_results(session_payload):
    state = _state(session_payload)
    active = state.get_scenario()
    empty = _empty_figure("Results", "Run a deterministic scan to view results.")
    if active is None or active.scan_result is None:
        return [], empty, empty, empty, [], [], [], []

    scan = active.scan_result
    selected_key = resolve_selected_candidate_key_for_scenario(scan, active.selected_candidate_key)
    detail = scan.candidate_details[selected_key]
    kpis = build_kpis(detail)
    monthly_balance = build_monthly_balance(detail["monthly"])
    cash_flow = build_cash_flow(detail["monthly"])
    table = scan.candidates.copy()
    columns = _table_columns(table)
    selected_index = table.index[table["candidate_key"] == selected_key].tolist()
    best_key = scan.best_candidate_key
    styles = [
        {
            "if": {"filter_query": f'{{candidate_key}} = "{best_key}"'},
            "backgroundColor": "#dcfce7",
            "fontWeight": "bold",
        },
        {
            "if": {"filter_query": "{best_battery_for_kwp} = true"},
            "backgroundColor": "#eff6ff",
        },
    ]
    return (
        render_kpi_cards(kpis),
        build_npv_figure(table, selected_key=selected_key),
        build_monthly_balance_figure(monthly_balance),
        build_cash_flow_figure(cash_flow),
        table.to_dict("records"),
        columns,
        [selected_index[0]] if selected_index else [],
        styles,
    )


@callback(
    Output("scenario-download", "data"),
    Input("scenario-export-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    prevent_initial_call=True,
)
def export_active_scenario(n_clicks, session_payload):
    if not n_clicks:
        raise PreventUpdate
    state = _state(session_payload)
    active = state.get_scenario()
    if active is None or active.scan_result is None or active.dirty:
        raise PreventUpdate
    content = export_scenario_workbook(active)
    filename = f"{active.name.replace(' ', '_')}_deterministic.xlsx"
    return _download_payload(content, filename)
