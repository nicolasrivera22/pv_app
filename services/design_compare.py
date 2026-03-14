from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .i18n import tr
from .result_views import build_project_timeline
from .types import ScenarioRecord, ScenarioSessionState
from .ui_schema import format_metric

MAX_COMPARE_DESIGNS = 10

ANNUAL_COVERAGE_METRICS = ("PV_a_Carga_kWh", "Bateria_a_Carga_kWh", "Importacion_Red_kWh")
MONTHLY_DESTINATION_METRICS = ("PV_a_Carga_kWh", "PV_a_Bateria_kWh", "Exportacion_kWh", "Curtailment_kWh")


@dataclass(frozen=True)
class DesignComparePageState:
    code: str
    status_message: str
    empty_message: str
    export_message: str
    can_select: bool
    can_export: bool


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _empty_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def _apply_project_time_axes(
    figure: go.Figure,
    timeline: pd.DataFrame,
    *,
    lang: str = "es",
) -> go.Figure:
    if timeline.empty:
        return figure
    tick_frame = timeline.loc[timeline["is_year_start"], ["month_index", "calendar_year", "project_year"]].copy()
    tickvals = tick_frame["month_index"].tolist()
    calendar_ticktext = tick_frame["calendar_year"].astype(str).tolist()
    project_ticktext = [tr("timeline.project_year", lang, year=int(year)) for year in tick_frame["project_year"]]
    figure.update_xaxes(
        title_text=tr("timeline.axis.calendar_year", lang),
        tickmode="array",
        tickvals=tickvals,
        ticktext=calendar_ticktext,
        range=[0.5, float(timeline["month_index"].max()) + 0.5],
    )
    figure.update_layout(
        xaxis2={
            "overlaying": "x",
            "side": "top",
            "title": tr("timeline.axis.project_horizon", lang),
            "tickmode": "array",
            "tickvals": tickvals,
            "ticktext": project_ticktext,
            "showgrid": False,
        }
    )
    return figure


def _month_labels(monthly: pd.DataFrame) -> list[str]:
    if monthly.empty or "Año_mes" not in monthly.columns:
        return [str(index + 1) for index in range(12)]
    labels = monthly.iloc[:12]["Año_mes"].astype(str).tolist()
    return labels or [str(index + 1) for index in range(12)]


def _inverter_name(detail: dict[str, Any]) -> str:
    inverter = (detail.get("inv_sel") or {}).get("inverter") or {}
    return str(inverter.get("name", "-"))


def derive_panel_count(detail: dict[str, Any], scenario_record: ScenarioRecord) -> int:
    inv_sel = detail.get("inv_sel") or {}
    raw_modules = inv_sel.get("N_mod")
    if raw_modules not in (None, ""):
        rounded = int(round(float(raw_modules)))
        if rounded > 0:
            return rounded

    module_power_w = float(scenario_record.config_bundle.config.get("P_mod_W", 0.0) or 0.0)
    if module_power_w <= 0:
        return 0
    estimated = float(detail.get("kWp", 0.0) or 0.0) / (module_power_w / 1000.0)
    rounded = int(round(estimated))
    return rounded if rounded > 0 else 0


def _default_design_selection(scenario_record: ScenarioRecord) -> tuple[str, ...]:
    if scenario_record.scan_result is None or scenario_record.dirty:
        return ()
    if scenario_record.selected_candidate_key in scenario_record.scan_result.candidate_details:
        return (str(scenario_record.selected_candidate_key),)
    if scenario_record.scan_result.best_candidate_key in scenario_record.scan_result.candidate_details:
        return (str(scenario_record.scan_result.best_candidate_key),)
    if scenario_record.scan_result.candidate_details:
        return (next(iter(scenario_record.scan_result.candidate_details)),)
    return ()


def sanitize_design_selection(
    scenario_record: ScenarioRecord | None,
    candidate_keys: list[str] | tuple[str, ...],
    *,
    max_designs: int = MAX_COMPARE_DESIGNS,
) -> tuple[str, ...]:
    if scenario_record is None or scenario_record.scan_result is None or scenario_record.dirty:
        return ()
    valid_keys = set(scenario_record.scan_result.candidate_details)
    cleaned: list[str] = []
    seen: set[str] = set()
    for candidate_key in candidate_keys:
        key = str(candidate_key)
        if key in valid_keys and key not in seen:
            cleaned.append(key)
            seen.add(key)
        if len(cleaned) >= max_designs:
            break
    return tuple(cleaned)


def resolve_design_selection(
    state: ScenarioSessionState,
    scenario_record: ScenarioRecord | None,
    *,
    max_designs: int = MAX_COMPARE_DESIGNS,
) -> tuple[str, ...]:
    if scenario_record is None or scenario_record.scan_result is None or scenario_record.dirty:
        return ()
    if scenario_record.scenario_id in state.design_comparison_candidate_keys:
        return sanitize_design_selection(
            scenario_record,
            state.design_comparison_candidate_keys.get(scenario_record.scenario_id, ()),
            max_designs=max_designs,
        )
    return sanitize_design_selection(scenario_record, _default_design_selection(scenario_record), max_designs=max_designs)


def append_design_selection(
    scenario_record: ScenarioRecord,
    current_keys: list[str] | tuple[str, ...],
    keys_to_add: list[str] | tuple[str, ...],
    *,
    max_designs: int = MAX_COMPARE_DESIGNS,
) -> tuple[str, ...]:
    return sanitize_design_selection(scenario_record, [*current_keys, *keys_to_add], max_designs=max_designs)


def remove_design_selection(
    scenario_record: ScenarioRecord,
    current_keys: list[str] | tuple[str, ...],
    candidate_key: str,
) -> tuple[str, ...]:
    return sanitize_design_selection(
        scenario_record,
        [key for key in current_keys if str(key) != str(candidate_key)],
    )


def build_design_compare_state(
    scenario_record: ScenarioRecord | None,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> DesignComparePageState:
    lang = _lang(lang)
    selected_count = len(selected_candidate_keys)
    if scenario_record is None:
        message = tr("compare.state.no_active", lang)
        return DesignComparePageState("no_active", message, message, "", False, False)
    if scenario_record.dirty and scenario_record.last_run_at:
        message = tr("compare.state.dirty", lang)
        return DesignComparePageState("dirty", message, message, "", False, False)
    if scenario_record.scan_result is None:
        message = tr("compare.state.no_scan", lang)
        return DesignComparePageState("no_scan", message, message, "", False, False)
    if selected_count == 0:
        message = tr("compare.state.no_selection", lang)
        return DesignComparePageState("no_selection", message, message, tr("compare.export.requires_two", lang), True, False)
    export_message = "" if selected_count >= 2 else tr("compare.export.requires_two", lang)
    return DesignComparePageState(
        "ready",
        tr("compare.state.selected", lang, count=selected_count),
        tr("compare.state.selected", lang, count=selected_count),
        export_message,
        True,
        selected_count >= 2,
    )


def _base_candidate_frame(scenario_record: ScenarioRecord, *, lang: str = "es") -> pd.DataFrame:
    assert scenario_record.scan_result is not None
    base = scenario_record.scan_result.candidates.copy()
    rows: list[dict[str, Any]] = []
    for row in base.to_dict("records"):
        candidate_key = str(row["candidate_key"])
        detail = scenario_record.scan_result.candidate_details[candidate_key]
        rows.append(
            {
                "candidate_key": candidate_key,
                "kWp": float(row["kWp"]),
                "panel_count": derive_panel_count(detail, scenario_record),
                "battery": format_metric("selected_battery", detail["battery_name"], lang),
                "inverter_name": _inverter_name(detail),
                "NPV_COP": float(row["NPV_COP"]),
                "payback_years": row["payback_years"],
                "capex_client": float(row["capex_client"]),
                "self_consumption_ratio": float(row["self_consumption_ratio"]),
                "self_sufficiency_ratio": float(row["self_sufficiency_ratio"]),
                "annual_import_kwh": float(row["annual_import_kwh"]),
                "annual_export_kwh": float(row["annual_export_kwh"]),
                "peak_ratio": float(row["peak_ratio"]),
                "is_workbench_selected": candidate_key == scenario_record.selected_candidate_key,
                "is_best_candidate": candidate_key == scenario_record.scan_result.best_candidate_key,
            }
        )
    return pd.DataFrame(rows)


def build_available_design_rows(scenario_record: ScenarioRecord, *, lang: str = "es") -> pd.DataFrame:
    if scenario_record.scan_result is None or scenario_record.dirty:
        return pd.DataFrame(
            columns=[
                "candidate_key",
                "kWp",
                "panel_count",
                "battery",
                "inverter_name",
                "NPV_COP",
                "payback_years",
                "capex_client",
                "self_consumption_ratio",
                "annual_import_kwh",
                "annual_export_kwh",
                "peak_ratio",
                "is_workbench_selected",
                "is_best_candidate",
            ]
        )
    return _base_candidate_frame(scenario_record, lang=lang)


def build_selected_design_rows(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> pd.DataFrame:
    rows = build_available_design_rows(scenario_record, lang=lang)
    if rows.empty:
        return pd.DataFrame(
            columns=[
                "design_label",
                "candidate_key",
                "kWp",
                "panel_count",
                "battery",
                "inverter_name",
                "NPV_COP",
                "payback_years",
                "capex_client",
                "self_consumption_ratio",
                "self_sufficiency_ratio",
                "annual_import_kwh",
                "annual_export_kwh",
                "peak_ratio",
            ]
        )
    indexed = rows.set_index("candidate_key")
    selected_rows: list[dict[str, Any]] = []
    for index, candidate_key in enumerate(selected_candidate_keys):
        if candidate_key not in indexed.index:
            continue
        row = indexed.loc[candidate_key].to_dict()
        row["design_label"] = f"#{index + 1}"
        selected_rows.append(
            {
                "design_label": row["design_label"],
                "candidate_key": candidate_key,
                "kWp": row["kWp"],
                "panel_count": row["panel_count"],
                "battery": row["battery"],
                "inverter_name": row["inverter_name"],
                "NPV_COP": row["NPV_COP"],
                "payback_years": row["payback_years"],
                "capex_client": row["capex_client"],
                "self_consumption_ratio": row["self_consumption_ratio"],
                "self_sufficiency_ratio": row["self_sufficiency_ratio"],
                "annual_import_kwh": row["annual_import_kwh"],
                "annual_export_kwh": row["annual_export_kwh"],
                "peak_ratio": row["peak_ratio"],
            }
        )
    return pd.DataFrame(selected_rows)


def build_design_comparison_rows(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> pd.DataFrame:
    return build_selected_design_rows(scenario_record, selected_candidate_keys, lang=lang)


def _metric_color(metric: str) -> str:
    palette = {
        "PV_a_Carga_kWh": "#16a34a",
        "Bateria_a_Carga_kWh": "#7c3aed",
        "Importacion_Red_kWh": "#dc2626",
        "PV_a_Bateria_kWh": "#a855f7",
        "Exportacion_kWh": "#2563eb",
        "Curtailment_kWh": "#94a3b8",
    }
    return palette.get(metric, "#475569")


def _metric_name(metric: str, lang: str) -> str:
    return tr(f"compare.metric.{metric}", lang)


def _selected_lookup_frame(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> pd.DataFrame:
    frame = build_selected_design_rows(scenario_record, selected_candidate_keys, lang=lang)
    if frame.empty:
        return frame
    return frame.set_index("candidate_key")


def build_annual_demand_coverage_frame(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
) -> pd.DataFrame:
    if scenario_record.scan_result is None or scenario_record.dirty:
        return pd.DataFrame(columns=["design_label", "candidate_key", "metric", "value_kwh"])
    selected_frame = _selected_lookup_frame(scenario_record, selected_candidate_keys)
    rows: list[dict[str, Any]] = []
    for candidate_key in selected_candidate_keys:
        if candidate_key not in selected_frame.index:
            continue
        detail = scenario_record.scan_result.candidate_details[candidate_key]
        monthly = detail["monthly"].iloc[:12]
        for metric in ANNUAL_COVERAGE_METRICS:
            rows.append(
                {
                    "design_label": selected_frame.loc[candidate_key, "design_label"],
                    "candidate_key": candidate_key,
                    "metric": metric,
                    "value_kwh": float(monthly.get(metric, 0.0).sum()),
                }
            )
    return pd.DataFrame(rows)


def build_monthly_pv_destination_frame(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
) -> pd.DataFrame:
    if scenario_record.scan_result is None or scenario_record.dirty:
        return pd.DataFrame(columns=["design_label", "candidate_key", "month", "metric", "value_kwh"])
    selected_frame = _selected_lookup_frame(scenario_record, selected_candidate_keys)
    rows: list[dict[str, Any]] = []
    for candidate_key in selected_candidate_keys:
        if candidate_key not in selected_frame.index:
            continue
        detail = scenario_record.scan_result.candidate_details[candidate_key]
        monthly = detail["monthly"].iloc[:12].copy()
        labels = _month_labels(monthly)
        for month_index, month_label in enumerate(labels):
            for metric in MONTHLY_DESTINATION_METRICS:
                value = 0.0
                if metric in monthly.columns and month_index < len(monthly):
                    value = float(monthly.iloc[month_index][metric] or 0.0)
                rows.append(
                    {
                        "design_label": selected_frame.loc[candidate_key, "design_label"],
                        "candidate_key": candidate_key,
                        "month": month_label,
                        "metric": metric,
                        "value_kwh": value,
                    }
                )
    return pd.DataFrame(rows)


def build_typical_day_frame(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> pd.DataFrame:
    if scenario_record.scan_result is None or scenario_record.dirty:
        return pd.DataFrame(
            columns=[
                "design_label",
                "candidate_key",
                "hour",
                "demand_kw",
                "pv_kw",
                "solar_factor_pct",
                "kWp",
                "panel_count",
                "battery",
                "inverter_name",
            ]
        )
    selected_frame = _selected_lookup_frame(scenario_record, selected_candidate_keys, lang=lang)
    cfg = scenario_record.config_bundle.config
    demand_month_factor = np.asarray(scenario_record.config_bundle.demand_month_factor, dtype=float)
    hsp_month = np.asarray(scenario_record.config_bundle.hsp_month, dtype=float)
    w24 = np.asarray(scenario_record.config_bundle.demand_profile_7x24[0], dtype=float)
    solar_factor = np.asarray(scenario_record.config_bundle.solar_profile, dtype=float)
    month_for_plot = int(np.argmax(demand_month_factor)) if demand_month_factor.size else 0
    demand_day = (float(demand_month_factor[month_for_plot]) if demand_month_factor.size else 1.0) * float(cfg.get("E_month_kWh", 0.0) or 0.0) / 30.0
    pr_eff = float(cfg.get("PR", 0.0) or 0.0)
    rows: list[dict[str, Any]] = []
    for candidate_key in selected_candidate_keys:
        if candidate_key not in selected_frame.index:
            continue
        detail = scenario_record.scan_result.candidate_details[candidate_key]
        inverter = (detail.get("inv_sel") or {}).get("inverter") or {}
        p_ac = float(inverter.get("AC_kW", 0.0) or 0.0)
        k_wp = float(detail.get("kWp", 0.0) or 0.0)
        e_pv_day = k_wp * pr_eff * (float(hsp_month[month_for_plot]) if hsp_month.size else 0.0)
        demand_profile = np.asarray(w24, dtype=float) * demand_day
        pv_profile = np.minimum(np.asarray(solar_factor, dtype=float) * e_pv_day, p_ac)
        for hour in range(24):
            rows.append(
                {
                    "design_label": selected_frame.loc[candidate_key, "design_label"],
                    "candidate_key": candidate_key,
                    "hour": hour,
                    "demand_kw": float(demand_profile[hour]),
                    "pv_kw": float(pv_profile[hour]),
                    "solar_factor_pct": float(solar_factor[hour] * 100.0),
                    "kWp": k_wp,
                    "panel_count": int(selected_frame.loc[candidate_key, "panel_count"]),
                    "battery": selected_frame.loc[candidate_key, "battery"],
                    "inverter_name": selected_frame.loc[candidate_key, "inverter_name"],
                }
            )
    return pd.DataFrame(rows)


def build_npv_projection_frame(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
    base_year: int | None = None,
) -> pd.DataFrame:
    if scenario_record.scan_result is None or scenario_record.dirty:
        return pd.DataFrame(columns=["design_label", "candidate_key", "Año_mes", "NPV_COP", "month_index", "calendar_year", "project_year"])
    selected_frame = _selected_lookup_frame(scenario_record, selected_candidate_keys, lang=lang)
    rows: list[dict[str, Any]] = []
    for candidate_key in selected_candidate_keys:
        if candidate_key not in selected_frame.index:
            continue
        detail = scenario_record.scan_result.candidate_details[candidate_key]
        monthly = detail["monthly"].reset_index(drop=True)
        timeline = build_project_timeline(len(monthly), base_year=base_year)
        for index, row in monthly.iterrows():
            timeline_row = timeline.iloc[index] if not timeline.empty else None
            rows.append(
                {
                    "design_label": selected_frame.loc[candidate_key, "design_label"],
                    "candidate_key": candidate_key,
                    "Año_mes": str(row["Año_mes"]),
                    "month_index": int(timeline_row["month_index"]) if timeline_row is not None else (index + 1),
                    "calendar_year": int(timeline_row["calendar_year"]) if timeline_row is not None else None,
                    "project_year": int(timeline_row["project_year"]) if timeline_row is not None else None,
                    "NPV_COP": float(row["NPV_COP"]),
                    "kWp": float(detail["kWp"]),
                    "panel_count": int(selected_frame.loc[candidate_key, "panel_count"]),
                    "battery": selected_frame.loc[candidate_key, "battery"],
                    "inverter_name": selected_frame.loc[candidate_key, "inverter_name"],
                }
            )
    return pd.DataFrame(rows)


def build_annual_demand_coverage_figure(
    frame: pd.DataFrame,
    *,
    lang: str = "es",
    empty_message: str,
) -> go.Figure:
    if frame.empty:
        return _empty_figure(tr("compare.figure.annual_coverage", lang), empty_message)
    figure = go.Figure()
    for metric in ANNUAL_COVERAGE_METRICS:
        subset = frame[frame["metric"] == metric]
        if subset.empty or float(subset["value_kwh"].abs().sum()) <= 0:
            continue
        figure.add_bar(
            x=subset["design_label"],
            y=subset["value_kwh"],
            name=_metric_name(metric, lang),
            marker_color=_metric_color(metric),
            customdata=subset[["candidate_key"]],
            hovertemplate=(
                ("Diseño" if lang == "es" else "Design")
                + ": %{x}<br>"
                + ("Candidato" if lang == "es" else "Candidate")
                + ": %{customdata[0]}<br>"
                + ("Energía" if lang == "es" else "Energy")
                + ": %{y:,.0f} kWh<extra></extra>"
            ),
        )
    figure.update_layout(template="plotly_white", title=tr("compare.figure.annual_coverage", lang), barmode="stack")
    figure.update_xaxes(title=tr("compare.axis.design", lang))
    figure.update_yaxes(title="kWh", tickformat=",.0f")
    return figure


def build_monthly_pv_destination_figure(
    frame: pd.DataFrame,
    *,
    lang: str = "es",
    empty_message: str,
) -> go.Figure:
    if frame.empty:
        return _empty_figure(tr("compare.figure.monthly_destination", lang), empty_message)
    selection_count = frame["design_label"].nunique()
    metrics = [metric for metric in MONTHLY_DESTINATION_METRICS if metric in set(frame["metric"]) and float(frame.loc[frame["metric"] == metric, "value_kwh"].abs().sum()) > 0]
    if not metrics:
        return _empty_figure(tr("compare.figure.monthly_destination", lang), empty_message)

    month_order = list(dict.fromkeys(frame["month"].tolist()))
    if selection_count <= 4:
        figure = go.Figure()
        for metric in metrics:
            subset = frame[frame["metric"] == metric]
            figure.add_bar(
                x=[subset["month"], subset["design_label"]],
                y=subset["value_kwh"],
                name=_metric_name(metric, lang),
                marker_color=_metric_color(metric),
                customdata=subset[["month", "design_label", "candidate_key"]],
                hovertemplate=(
                    ("Mes" if lang == "es" else "Month")
                    + ": %{customdata[0]}<br>"
                    + ("Diseño" if lang == "es" else "Design")
                    + ": %{customdata[1]}<br>"
                    + ("Candidato" if lang == "es" else "Candidate")
                    + ": %{customdata[2]}<br>"
                    + ("Energía" if lang == "es" else "Energy")
                    + ": %{y:,.0f} kWh<extra></extra>"
                ),
            )
        figure.update_layout(template="plotly_white", title=tr("compare.figure.monthly_destination", lang), barmode="stack")
        figure.update_yaxes(title="kWh", tickformat=",.0f")
        return figure

    display = frame[frame["metric"].isin(metrics)].copy()
    display["metric_label"] = display["metric"].map(lambda metric: _metric_name(metric, lang))
    columns = 3 if selection_count > 4 else 2
    rows = int(np.ceil(selection_count / columns))
    figure = px.bar(
        display,
        x="month",
        y="value_kwh",
        color="metric_label",
        facet_col="design_label",
        facet_col_wrap=columns,
        category_orders={"month": month_order},
        template="plotly_white",
        title=tr("compare.figure.monthly_destination", lang),
        height=max(360, 300 * rows),
    )
    figure.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    figure.update_yaxes(title="kWh", tickformat=",.0f")
    figure.update_xaxes(title=tr("compare.axis.month", lang))
    return figure


def build_typical_day_figure(
    frame: pd.DataFrame,
    *,
    lang: str = "es",
    empty_message: str,
) -> go.Figure:
    if frame.empty:
        return _empty_figure(tr("compare.figure.typical_day", lang), empty_message)
    labels = list(dict.fromkeys(frame["design_label"].tolist()))
    columns = 2 if len(labels) <= 4 else 3
    rows = int(np.ceil(len(labels) / columns))
    specs: list[list[dict[str, bool]]] = []
    for row_index in range(rows):
        spec_row: list[dict[str, bool]] = []
        for column_index in range(columns):
            spec_row.append({"secondary_y": True} if row_index * columns + column_index < len(labels) else None)  # type: ignore[arg-type]
        specs.append(spec_row)
    titles = []
    for label in labels:
        subset = frame[frame["design_label"] == label]
        first = subset.iloc[0]
        titles.append(
            tr(
                "compare.typical_day.subtitle",
                lang,
                label=label,
                kwp=float(first["kWp"]),
                panels=int(first["panel_count"]),
            )
        )
    figure = make_subplots(rows=rows, cols=columns, subplot_titles=titles, specs=specs, horizontal_spacing=0.08, vertical_spacing=0.14)
    for index, label in enumerate(labels):
        subset = frame[frame["design_label"] == label]
        row = (index // columns) + 1
        column = (index % columns) + 1
        show_legend = index == 0
        hours = subset["hour"]
        figure.add_bar(
            x=hours,
            y=subset["demand_kw"],
            name=tr("compare.metric.typical_demand", lang),
            marker_color="#dc2626",
            legendgroup="demand",
            showlegend=show_legend,
            row=row,
            col=column,
            secondary_y=False,
        )
        figure.add_bar(
            x=hours,
            y=subset["pv_kw"],
            name=tr("compare.metric.typical_pv", lang),
            marker_color="#16a34a",
            legendgroup="pv",
            showlegend=show_legend,
            row=row,
            col=column,
            secondary_y=False,
        )
        figure.add_scatter(
            x=hours,
            y=subset["solar_factor_pct"],
            mode="lines",
            name=tr("compare.metric.typical_solar_factor", lang),
            line={"color": "#f59e0b", "width": 2.2},
            legendgroup="solar",
            showlegend=show_legend,
            row=row,
            col=column,
            secondary_y=True,
        )
    figure.update_layout(
        template="plotly_white",
        title=tr("compare.figure.typical_day", lang),
        barmode="group",
        height=max(420, rows * 320),
    )
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            figure.update_xaxes(title_text=tr("compare.axis.hour", lang), dtick=4, row=row, col=column)
            figure.update_yaxes(title_text="kW", row=row, col=column, secondary_y=False)
            figure.update_yaxes(title_text=tr("compare.axis.solar_factor", lang), row=row, col=column, secondary_y=True)
    return figure


def build_npv_projection_figure(
    frame: pd.DataFrame,
    *,
    lang: str = "es",
    empty_message: str,
    base_year: int | None = None,
) -> go.Figure:
    if frame.empty:
        return _empty_figure(tr("compare.figure.npv_projection", lang), empty_message)
    display = frame.copy()
    if "month_index" not in display.columns or "calendar_year" not in display.columns or "project_year" not in display.columns:
        month_numbers = pd.to_numeric(display.get("Año_mes"), errors="coerce")
        horizon_months = int(month_numbers.max()) if month_numbers.notna().any() else 0
        timeline = build_project_timeline(horizon_months, base_year=base_year)
        if not timeline.empty and horizon_months > 0:
            display = display.copy()
            display["_month_number"] = month_numbers.astype("Int64")
            timeline = timeline.rename(columns={"month_index": "_month_number"})
            display = display.merge(timeline, on="_month_number", how="left").drop(columns="_month_number")
        elif "month_index" not in display.columns:
            display = display.copy()
            display["month_index"] = month_numbers.fillna(pd.Series(range(1, len(display) + 1), index=display.index))
    figure = px.line(
        display,
        x="month_index",
        y="NPV_COP",
        color="design_label",
        template="plotly_white",
        title=tr("compare.figure.npv_projection", lang),
        custom_data=["candidate_key", "kWp", "panel_count", "battery", "inverter_name", "calendar_year", "project_year", "month_index"],
    )
    figure.update_traces(
        hovertemplate=(
            ("Diseño" if lang == "es" else "Design")
            + ": %{fullData.name}<br>"
            + ("Candidato" if lang == "es" else "Candidate")
            + ": %{customdata[0]}<br>"
            + "kWp: %{customdata[1]:.3f}<br>"
            + ("Paneles" if lang == "es" else "Panels")
            + ": %{customdata[2]}<br>"
            + ("Batería" if lang == "es" else "Battery")
            + ": %{customdata[3]}<br>"
            + ("Inversor" if lang == "es" else "Inverter")
            + ": %{customdata[4]}<br>"
            + tr("timeline.hover.calendar_year", lang)
            + ": %{customdata[5]:.0f}<br>"
            + tr("timeline.hover.project_year", lang)
            + ": "
            + tr("timeline.project_year", lang, year="%{customdata[6]:.0f}")
            + "<br>"
            + tr("timeline.hover.project_month", lang)
            + ": %{customdata[7]:.0f}<br>"
            + "VPN: %{y:,.0f}<extra></extra>"
        )
    )
    if {"month_index", "calendar_year", "project_year"}.issubset(display.columns):
        timeline = display[["month_index", "calendar_year", "project_year"]].drop_duplicates().copy()
        timeline["is_year_start"] = ((timeline["month_index"] - 1) % 12 == 0)
        _apply_project_time_axes(figure, timeline, lang=lang)
    figure.update_yaxes(title_text="VPN [COP]" if lang == "es" else "NPV [COP]", tickformat=",.0f")
    figure.update_layout(hovermode="x unified")
    return figure


def build_design_comparison_figures(
    scenario_record: ScenarioRecord | None,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
    empty_message: str,
) -> dict[str, go.Figure]:
    lang = _lang(lang)
    if scenario_record is None or scenario_record.scan_result is None or scenario_record.dirty or not selected_candidate_keys:
        return {
            "annual_coverage": _empty_figure(tr("compare.figure.annual_coverage", lang), empty_message),
            "monthly_destination": _empty_figure(tr("compare.figure.monthly_destination", lang), empty_message),
            "typical_day": _empty_figure(tr("compare.figure.typical_day", lang), empty_message),
            "npv_projection": _empty_figure(tr("compare.figure.npv_projection", lang), empty_message),
        }
    annual_frame = build_annual_demand_coverage_frame(scenario_record, selected_candidate_keys)
    monthly_destination = build_monthly_pv_destination_frame(scenario_record, selected_candidate_keys)
    typical_day = build_typical_day_frame(scenario_record, selected_candidate_keys, lang=lang)
    npv_projection = build_npv_projection_frame(scenario_record, selected_candidate_keys, lang=lang)
    return {
        "annual_coverage": build_annual_demand_coverage_figure(annual_frame, lang=lang, empty_message=empty_message),
        "monthly_destination": build_monthly_pv_destination_figure(monthly_destination, lang=lang, empty_message=empty_message),
        "typical_day": build_typical_day_figure(typical_day, lang=lang, empty_message=empty_message),
        "npv_projection": build_npv_projection_figure(npv_projection, lang=lang, empty_message=empty_message),
    }


def build_design_comparison_export_frames(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> dict[str, pd.DataFrame]:
    summary = build_design_comparison_rows(scenario_record, selected_candidate_keys, lang=lang)
    metrics = summary[
        [
            "design_label",
            "kWp",
            "panel_count",
            "battery",
            "inverter_name",
            "NPV_COP",
            "payback_years",
            "capex_client",
            "self_consumption_ratio",
            "self_sufficiency_ratio",
            "annual_import_kwh",
            "annual_export_kwh",
            "peak_ratio",
        ]
    ].copy() if not summary.empty else summary.copy()
    return {
        "Design_Comparison_Summary": summary,
        "Design_Comparison_Metrics": metrics,
        "Annual_Demand_Coverage": build_annual_demand_coverage_frame(scenario_record, selected_candidate_keys),
        "Monthly_PV_Destination": build_monthly_pv_destination_frame(scenario_record, selected_candidate_keys),
        "Typical_Day": build_typical_day_frame(scenario_record, selected_candidate_keys, lang=lang),
        "NPV_Projection": build_npv_projection_frame(scenario_record, selected_candidate_keys, lang=lang),
    }
