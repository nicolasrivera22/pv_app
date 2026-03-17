from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Input, Output, State, callback, dcc, html, register_page, ctx
from dash.exceptions import PreventUpdate

from components import (
    build_ecdf_figure,
    build_histogram_figure,
    empty_risk_figure,
    render_message_list,
    render_metadata_table,
    render_risk_summary_cards,
    risk_charts_section,
    risk_controls_section,
    risk_tables_section,
)
from services import (
    clear_missing_risk_result_payload,
    export_risk_artifacts,
    get_risk_result,
    internal_results_root,
    open_export_folder,
    publish_export_artifacts,
    project_exports_root,
    resolve_client_session,
    resolve_scenario_session,
    run_monte_carlo,
    store_risk_result,
)
from services.i18n import tr
from services.risk_ui import (
    build_risk_candidate_options,
    build_risk_metadata_rows,
    build_risk_result_store_payload,
    prepare_percentile_table_for_display,
    ready_risk_scenarios,
    resolve_default_risk_candidate,
    resolve_default_risk_scenario,
    validate_risk_run_inputs,
)

register_page(__name__, path="/risk", name="Risk")

def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _retain_samples(values: list[str] | None) -> bool:
    return "retain" in (values or [])


def _safe_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


layout = html.Div(
    className="page",
    children=[
        dcc.Store(id="risk-latest-export-folder", storage_type="memory", data=""),
        dcc.Store(id="risk-result-store", storage_type="memory"),
        html.Div(
            className="main-stack",
            children=[
                risk_controls_section(),
                dcc.Loading(
                    type="default",
                    children=html.Div(
                        className="main-stack",
                        children=[
                            risk_charts_section(),
                            risk_tables_section(),
                        ],
                    ),
                ),
            ],
        ),
    ],
)


@callback(
    Output("risk-page-title", "children"),
    Output("risk-page-intro", "children"),
    Output("risk-mode-note", "children"),
    Output("risk-scenario-label", "children"),
    Output("risk-candidate-label", "children"),
    Output("risk-n-simulations-label", "children"),
    Output("risk-seed-label", "children"),
    Output("risk-seed-help", "children"),
    Output("risk-retain-samples-label", "children"),
    Output("risk-retain-samples", "options"),
    Output("risk-retain-samples-help", "children"),
    Output("risk-run-btn", "children"),
    Output("risk-export-artifacts-btn", "children"),
    Output("risk-open-exports-btn", "children"),
    Output("risk-export-progress", "children"),
    Output("risk-summary-title", "children"),
    Output("risk-distributions-title", "children"),
    Output("risk-metadata-title", "children"),
    Output("risk-percentiles-title", "children"),
    Output("risk-payback-histogram-description", "children"),
    Output("risk-npv-histogram-description", "children"),
    Output("risk-payback-ecdf-description", "children"),
    Output("risk-npv-ecdf-description", "children"),
    Input("language-selector", "value"),
)
def translate_risk_page(language_value):
    lang = _lang(language_value)
    return (
        tr("risk.page_title", lang),
        tr("risk.page_intro", lang),
        tr("risk.mode_note", lang),
        tr("risk.scenario.label", lang),
        tr("risk.candidate.label", lang),
        tr("risk.n_simulations.label", lang),
        tr("risk.seed.label", lang),
        tr("risk.seed.help", lang),
        tr("risk.retain_samples.label", lang),
        [{"label": tr("risk.retain_samples.option", lang), "value": "retain"}],
        tr("risk.retain_samples.help", lang),
        tr("risk.run", lang),
        tr("risk.export_artifacts", lang),
        tr("common.open_exports_folder", lang),
        tr("risk.export_artifacts_running", lang),
        tr("risk.summary.title", lang),
        tr("risk.distributions.title", lang),
        tr("risk.metadata.title", lang),
        tr("risk.percentiles.title", lang),
        tr("risk.chart.payback_hist.description", lang),
        tr("risk.chart.npv_hist.description", lang),
        tr("risk.chart.payback_ecdf.description", lang),
        tr("risk.chart.npv_ecdf.description", lang),
    )


@callback(
    Output("risk-scenario-dropdown", "options"),
    Output("risk-scenario-dropdown", "value"),
    Input("scenario-session-store", "data"),
    State("risk-scenario-dropdown", "value"),
)
def populate_risk_scenarios(session_payload, current_value):
    _, state = resolve_client_session(session_payload, language="es")
    scenarios = ready_risk_scenarios(state)
    options = [{"label": scenario.name, "value": scenario.scenario_id} for scenario in scenarios]
    selected = resolve_default_risk_scenario(state, current_value)
    return options, selected


@callback(
    Output("risk-open-exports-btn", "disabled"),
    Input("risk-latest-export-folder", "data"),
)
def sync_risk_export_folder_button(folder_path):
    return not bool(folder_path)


@callback(
    Output("risk-candidate-dropdown", "options"),
    Output("risk-candidate-dropdown", "value"),
    Output("risk-n-simulations-input", "value"),
    Input("scenario-session-store", "data"),
    Input("risk-scenario-dropdown", "value"),
    Input("language-selector", "value"),
    State("risk-candidate-dropdown", "value"),
    State("risk-n-simulations-input", "value"),
)
def populate_risk_candidates(session_payload, scenario_id, language_value, current_candidate_key, current_n_simulations):
    lang = _lang(language_value)
    _, state = resolve_scenario_session(session_payload, scenario_id=scenario_id, ensure_scan=True, language=lang)
    scenario = state.get_scenario(scenario_id)
    if scenario is None or scenario.scan_result is None or scenario.dirty:
        return [], None, current_n_simulations

    options = build_risk_candidate_options(scenario, lang)
    option_values = {option["value"] for option in options}
    candidate_key = current_candidate_key if current_candidate_key in option_values else resolve_default_risk_candidate(scenario)

    default_n = int(scenario.config_bundle.config.get("mc_n_simulations", 1000) or 1000)
    n_simulations = current_n_simulations
    if ctx.triggered_id in {"risk-scenario-dropdown", "scenario-session-store"} or n_simulations in (None, ""):
        n_simulations = default_n

    return options, candidate_key, n_simulations


@callback(
    Output("risk-result-store", "data", allow_duplicate=True),
    Input("risk-result-store", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def clear_missing_risk_result(result_payload, language_value):
    payload = result_payload or {}
    result_id = payload.get("result_id")
    if not result_id:
        raise PreventUpdate
    if get_risk_result(str(result_id)) is not None:
        raise PreventUpdate
    return clear_missing_risk_result_payload(payload, lang=_lang(language_value))


@callback(
    Output("risk-result-store", "data"),
    Input("risk-run-btn", "n_clicks"),
    State("scenario-session-store", "data"),
    State("risk-scenario-dropdown", "value"),
    State("risk-candidate-dropdown", "value"),
    State("risk-n-simulations-input", "value"),
    State("risk-seed-input", "value"),
    State("risk-retain-samples", "value"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[(Output("risk-run-btn", "disabled"), True, False)],
)
def run_risk_analysis(
    n_clicks,
    session_payload,
    scenario_id,
    candidate_key,
    n_simulations,
    seed,
    retain_samples_values,
    language_value,
):
    if not n_clicks:
        raise PreventUpdate

    lang = _lang(language_value)
    _, state = resolve_scenario_session(session_payload, scenario_id=scenario_id, ensure_scan=True, language=lang)
    scenario = state.get_scenario(scenario_id)
    retain_samples = _retain_samples(retain_samples_values)
    errors = validate_risk_run_inputs(scenario, candidate_key, n_simulations, seed, lang=lang)
    if errors:
        return build_risk_result_store_payload(
            result_id=None,
            scenario_id=scenario_id,
            candidate_key=candidate_key,
            n_simulations=_safe_int(n_simulations),
            seed=_safe_int(seed),
            retain_samples=retain_samples,
            status=tr("risk.status.failed", lang),
            errors=errors,
        )

    assert scenario is not None and scenario.scan_result is not None
    try:
        result = run_monte_carlo(
            scenario.config_bundle,
            selected_candidate_key=candidate_key,
            seed=int(seed),
            n_simulations=int(n_simulations),
            return_samples=retain_samples,
            baseline_scan=scenario.scan_result,
            lang=lang,
        )
        result_id = store_risk_result(result)
        return build_risk_result_store_payload(
            result_id=result_id,
            scenario_id=scenario_id,
            candidate_key=result.selected_candidate_key,
            n_simulations=result.n_simulations,
            seed=result.seed,
            retain_samples=retain_samples,
            status=tr("risk.status.completed", lang),
            warnings=list(result.warnings),
        )
    except Exception as exc:
        return build_risk_result_store_payload(
            result_id=None,
            scenario_id=scenario_id,
            candidate_key=candidate_key,
            n_simulations=_safe_int(n_simulations),
            seed=_safe_int(seed),
            retain_samples=retain_samples,
            status=tr("risk.status.failed", lang),
            errors=[str(exc)],
        )


@callback(
    Output("risk-result-store", "data", allow_duplicate=True),
    Input("risk-scenario-dropdown", "value"),
    Input("risk-candidate-dropdown", "value"),
    Input("risk-n-simulations-input", "value"),
    Input("risk-seed-input", "value"),
    Input("risk-retain-samples", "value"),
    State("risk-result-store", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def invalidate_risk_result(
    scenario_id,
    candidate_key,
    n_simulations,
    seed,
    retain_samples_values,
    result_payload,
    language_value,
):
    if not result_payload or not result_payload.get("result_id"):
        raise PreventUpdate

    current_n = _safe_int(n_simulations)
    current_seed = _safe_int(seed)
    current_retain = _retain_samples(retain_samples_values)
    if (
        scenario_id == result_payload.get("scenario_id")
        and candidate_key == result_payload.get("candidate_key")
        and current_n == result_payload.get("n_simulations")
        and current_seed == result_payload.get("seed")
        and current_retain == bool(result_payload.get("retain_samples"))
    ):
        raise PreventUpdate

    return build_risk_result_store_payload(
        result_id=None,
        scenario_id=scenario_id,
        candidate_key=candidate_key,
        n_simulations=current_n,
        seed=current_seed,
        retain_samples=current_retain,
        status=tr("risk.status.inputs_changed", _lang(language_value)),
    )


@callback(
    Output("risk-validation", "children"),
    Output("risk-status", "children"),
    Output("risk-summary-cards", "children"),
    Output("risk-payback-histogram", "figure"),
    Output("risk-npv-histogram", "figure"),
    Output("risk-payback-ecdf", "figure"),
    Output("risk-npv-ecdf", "figure"),
    Output("risk-percentile-table", "data"),
    Output("risk-percentile-table", "columns"),
    Output("risk-metadata-table", "children"),
    Output("risk-warnings", "children"),
    Output("risk-export-artifacts-btn", "disabled"),
    Input("scenario-session-store", "data"),
    Input("risk-result-store", "data"),
    Input("risk-scenario-dropdown", "value"),
    Input("language-selector", "value"),
)
def render_risk_results(session_payload, result_payload, scenario_id, language_value):
    lang = _lang(language_value)
    _, state = resolve_scenario_session(session_payload, scenario_id=scenario_id, ensure_scan=True, language=lang)
    ready = ready_risk_scenarios(state)
    if not ready:
        message = tr("risk.empty.no_scenarios", lang)
        empty = empty_risk_figure(tr("risk.chart.npv_hist", lang), message)
        return (
            render_message_list([message]),
            tr("risk.status.ready", lang),
            [],
            empty_risk_figure(tr("risk.chart.payback_hist", lang), message),
            empty,
            empty_risk_figure(tr("risk.chart.payback_ecdf", lang), message),
            empty_risk_figure(tr("risk.chart.npv_ecdf", lang), message),
            [],
            [],
            render_message_list([], empty_message=message),
            html.Div(),
            True,
        )

    result_payload = result_payload or {}
    errors = list(result_payload.get("errors", []))
    status = result_payload.get("status") or tr("risk.status.ready", lang)
    if not result_payload.get("result_id"):
        message = errors[0] if errors else tr("risk.empty.no_result", lang)
        return (
            render_message_list(errors, empty_message=tr("risk.validation.none", lang)),
            status,
            [],
            empty_risk_figure(tr("risk.chart.payback_hist", lang), message),
            empty_risk_figure(tr("risk.chart.npv_hist", lang), message),
            empty_risk_figure(tr("risk.chart.payback_ecdf", lang), message),
            empty_risk_figure(tr("risk.chart.npv_ecdf", lang), message),
            [],
            [],
            render_message_list([], empty_message=message),
            html.Div(),
            True,
        )

    result = get_risk_result(str(result_payload["result_id"]))
    if result is None:
        missing = tr("risk.error.result_missing", lang)
        return (
            render_message_list([missing]),
            tr("risk.status.rerun_needed", lang),
            [],
            empty_risk_figure(tr("risk.chart.payback_hist", lang), missing),
            empty_risk_figure(tr("risk.chart.npv_hist", lang), missing),
            empty_risk_figure(tr("risk.chart.payback_ecdf", lang), missing),
            empty_risk_figure(tr("risk.chart.npv_ecdf", lang), missing),
            [],
            [],
            render_message_list([], empty_message=missing),
            html.Div(),
            True,
        )

    scenario = state.get_scenario(result_payload.get("scenario_id") or scenario_id)
    if scenario is None:
        unavailable = tr("risk.error.scenario_unavailable", lang)
        return (
            render_message_list([unavailable]),
            tr("risk.status.failed", lang),
            [],
            empty_risk_figure(tr("risk.chart.payback_hist", lang), unavailable),
            empty_risk_figure(tr("risk.chart.npv_hist", lang), unavailable),
            empty_risk_figure(tr("risk.chart.payback_ecdf", lang), unavailable),
            empty_risk_figure(tr("risk.chart.npv_ecdf", lang), unavailable),
            [],
            [],
            render_message_list([], empty_message=unavailable),
            html.Div(),
            True,
        )

    percentile_table = prepare_percentile_table_for_display(result.views, lang=lang)
    columns = [
        {"name": tr(f"risk.table.{column}", lang), "id": column}
        if column != "metric"
        else {"name": tr("risk.table.metric", lang), "id": column}
        for column in percentile_table.columns
    ]
    warnings = list(result_payload.get("warnings", []))
    warning_children = html.Div()
    if warnings:
        warning_children = html.Div(
            [
                html.H4(tr("risk.warnings.title", lang)),
                render_message_list(warnings),
            ]
        )

    return (
        render_message_list(errors, empty_message=tr("risk.validation.none", lang)),
        status,
        render_risk_summary_cards(result, lang),
        build_histogram_figure(
            result.views.histograms["payback_years"],
            title=tr("risk.chart.payback_hist", lang),
            x_title=tr("risk.axis.payback", lang),
            lang=lang,
            empty_message=tr("risk.empty.no_payback", lang),
            highlight_range=(
                (result.summary.payback_years.p10, result.summary.payback_years.p90)
                if result.summary.payback_years.p10 is not None and result.summary.payback_years.p90 is not None
                else None
            ),
            density_frame=result.views.densities.get("payback_years"),
        ),
        build_histogram_figure(
            result.views.histograms["NPV_COP"],
            title=tr("risk.chart.npv_hist", lang),
            x_title=tr("risk.axis.npv", lang),
            lang=lang,
            density_frame=result.views.densities.get("NPV_COP"),
        ),
        build_ecdf_figure(
            result.views.ecdfs["payback_years"],
            title=tr("risk.chart.payback_ecdf", lang),
            x_title=tr("risk.axis.payback", lang),
            lang=lang,
            empty_message=tr("risk.empty.no_payback", lang),
        ),
        build_ecdf_figure(
            result.views.ecdfs["NPV_COP"],
            title=tr("risk.chart.npv_ecdf", lang),
            x_title=tr("risk.axis.npv", lang),
            lang=lang,
        ),
        percentile_table.to_dict("records"),
        columns,
        render_metadata_table(build_risk_metadata_rows(scenario, result, lang=lang)),
        warning_children,
        False,
    )


@callback(
    Output("risk-status", "children", allow_duplicate=True),
    Output("risk-latest-export-folder", "data"),
    Input("risk-export-artifacts-btn", "n_clicks"),
    State("risk-result-store", "data"),
    State("scenario-session-store", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
    running=[
        (Output("risk-export-artifacts-btn", "disabled"), True, False),
        (Output("risk-export-progress", "style"), {"display": "block"}, {"display": "none"}),
    ],
)
def export_risk_result_artifacts(n_clicks, result_payload, session_payload, language_value):
    if not n_clicks:
        raise PreventUpdate
    lang = _lang(language_value)
    payload = result_payload or {}
    result_id = payload.get("result_id")
    if not result_id:
        raise PreventUpdate
    result = get_risk_result(str(result_id))
    if result is None:
        return tr("risk.error.result_missing", lang), ""
    _, state = resolve_client_session(session_payload, language=lang)
    scenario = state.get_scenario(payload.get("scenario_id"))
    if scenario is None:
        return tr("risk.error.scenario_unavailable", lang), ""
    output_root = project_exports_root(state.project_slug) if state.project_slug else None
    paths = export_risk_artifacts(scenario, result, output_root=output_root or internal_results_root())
    publish_result = publish_export_artifacts(
        paths,
        project_slug=state.project_slug,
        scenario_slug=scenario.name or scenario.scenario_id,
        export_kind="risk",
    )
    if publish_result.published_root is not None:
        published_path = str(publish_result.published_root.resolve())
        return tr("risk.export_done", lang, path=published_path), published_path
    if publish_result.publish_error:
        return (
            tr(
                "risk.export_partial",
                lang,
                path=str(publish_result.internal_root.resolve()),
                error=publish_result.publish_error,
            ),
            "",
        )
    return tr("risk.export_done", lang, path=str(publish_result.display_root.resolve())), ""


@callback(
    Output("risk-status", "children", allow_duplicate=True),
    Input("risk-open-exports-btn", "n_clicks"),
    State("risk-latest-export-folder", "data"),
    State("language-selector", "value"),
    prevent_initial_call=True,
)
def open_risk_exports_folder(n_clicks, folder_path, language_value):
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
