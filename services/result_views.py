from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from pv_product.utils import (
    prepare_autoconsumo_anual_series,
    prepare_battery_monthly_series,
    prepare_cumulative_npv_series,
    prepare_typical_day_series,
)

from .i18n import tr
from .types import ScenarioRecord, ScenarioSessionState
from .ui_schema import format_metric, metric_label


MONTH_ABBREVIATIONS = {
    "es": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}

CANDIDATE_TABLE_COLUMNS = [
    "scan_order",
    "candidate_key",
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
    "best_battery_for_kwp",
]
NPV_CURVE_COLUMNS = ["kWp", "NPV_COP", "battery", "candidate_key", "payback_years", "self_consumption_ratio", "peak_ratio"]


def candidate_key_for(k_wp: float, battery_name: str) -> str:
    return f"{k_wp:.3f}::{battery_name}"


def battery_name_from_candidate(battery: dict | None) -> str:
    if battery is None or float(battery.get("nom_kWh", 0) or 0) <= 0:
        return "None"
    return str(battery.get("name", "Battery"))


def calculate_self_consumption_ratio(monthly: pd.DataFrame) -> float:
    first_year = monthly.iloc[:12]
    consumed = first_year.get("PV_a_Carga_kWh", 0).sum() + first_year.get("Bateria_a_Carga_kWh", 0).sum()
    demand = first_year.get("Demanda_kWh", 0).sum()
    return float(consumed / demand) if demand else 0.0


def calculate_self_sufficiency_ratio(monthly: pd.DataFrame) -> float:
    first_year = monthly.iloc[:12]
    demand = first_year.get("Demanda_kWh", 0).sum()
    imports = first_year.get("Importacion_Red_kWh", 0).sum()
    return float(1.0 - (imports / demand)) if demand else 0.0


def summarize_energy_metrics(monthly: pd.DataFrame) -> dict[str, float]:
    first_year = monthly.iloc[:12]
    demand = float(first_year.get("Demanda_kWh", 0).sum())
    imports = float(first_year.get("Importacion_Red_kWh", 0).sum())
    exports = float(first_year.get("Exportacion_kWh", 0).sum())
    return {
        "annual_demand_kwh": demand,
        "annual_import_kwh": imports,
        "annual_export_kwh": exports,
        "self_consumption_ratio": calculate_self_consumption_ratio(first_year),
        "self_sufficiency_ratio": calculate_self_sufficiency_ratio(first_year),
    }


def build_candidate_table(detail_map: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for detail in detail_map.values():
        energy = summarize_energy_metrics(detail["monthly"])
        rows.append(
            {
                "scan_order": int(detail["scan_order"]),
                "candidate_key": detail["candidate_key"],
                "kWp": round(float(detail["kWp"]), 3),
                "battery": detail["battery_name"],
                "NPV_COP": float(detail["summary"]["cum_disc_final"]),
                "payback_years": detail["summary"]["payback_years"],
                "capex_client": float(detail["summary"]["capex_client"]),
                "self_consumption_ratio": energy["self_consumption_ratio"],
                "self_sufficiency_ratio": energy["self_sufficiency_ratio"],
                "annual_import_kwh": energy["annual_import_kwh"],
                "annual_export_kwh": energy["annual_export_kwh"],
                "peak_ratio": float(detail["peak_ratio"]),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=CANDIDATE_TABLE_COLUMNS)
    frame = frame.sort_values(
        by=["kWp", "NPV_COP", "scan_order"],
        ascending=[True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    frame["best_battery_for_kwp"] = False
    best_idx = frame.groupby("kWp", sort=False).head(1).index
    frame.loc[best_idx, "best_battery_for_kwp"] = True
    return frame


def build_kpis(detail: dict) -> dict[str, float | str | None]:
    summary = detail["summary"]
    metrics = summarize_energy_metrics(detail["monthly"])
    return {
        "best_kWp": round(float(detail["kWp"]), 3),
        "selected_battery": detail["battery_name"],
        "NPV": float(summary["cum_disc_final"]),
        "payback_years": summary["payback_years"],
        "self_consumption_ratio": float(detail.get("self_consumption_ratio", metrics["self_consumption_ratio"])),
        "self_sufficiency_ratio": float(detail.get("self_sufficiency_ratio", metrics["self_sufficiency_ratio"])),
        "annual_import_kwh": metrics["annual_import_kwh"],
        "annual_export_kwh": metrics["annual_export_kwh"],
    }


def build_monthly_balance(monthly: pd.DataFrame, lang: str = "en") -> pd.DataFrame:
    first_year = monthly.iloc[:12].copy()
    if lang == "es":
        columns = [
            ("PV_a_Carga_kWh", "FV a carga"),
            ("Bateria_a_Carga_kWh", "Batería a carga"),
            ("Importacion_Red_kWh", "Importación de red"),
        ]
    else:
        columns = [
            ("PV_a_Carga_kWh", "PV to load"),
            ("Bateria_a_Carga_kWh", "Battery to load"),
            ("Importacion_Red_kWh", "Grid import"),
        ]
    if "Exportacion_kWh" in first_year.columns:
        columns.append(("Exportacion_kWh", "Exportación" if lang == "es" else "Export"))
    frame = pd.DataFrame({"Año_mes": first_year["Año_mes"].tolist()})
    for source_column, label in columns:
        frame[label] = first_year.get(source_column, 0.0)
    return frame


def _empty_result_figure(title: str, message: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title=title,
        template="plotly_white",
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
    )
    return figure


def _module_count(k_wp: float | None, module_power_w: float | None) -> int | None:
    if k_wp is None or module_power_w is None:
        return None
    if float(module_power_w) <= 0:
        return None
    return max(1, int(round((1000.0 * float(k_wp)) / float(module_power_w))))


def _module_annotation(k_wp: float | None, module_power_w: float | None, *, lang: str = "es") -> dict[str, Any] | None:
    panel_count = _module_count(k_wp, module_power_w)
    if panel_count is None:
        return None
    label = f"# {tr('common.chart.panels', lang).lower()}"
    return {
        "text": f"{label}={panel_count}",
        "xref": "paper",
        "yref": "paper",
        "x": 0.01,
        "y": 0.99,
        "xanchor": "left",
        "yanchor": "top",
        "showarrow": False,
        "font": {"size": 11},
        "bgcolor": "whitesmoke",
        "bordercolor": "gray",
        "borderwidth": 1,
        "borderpad": 4,
    }


def _deep_dive_empty(title: str, *, lang: str = "es") -> go.Figure:
    return _empty_result_figure(title, tr("workbench.deep_dive.no_data", lang))


def _infer_month_number(value: Any) -> int | None:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        month = int(value.month)
        return month if 1 <= month <= 12 else None
    if isinstance(value, (int, float)) and not pd.isna(value):
        month = int(value)
        return month if 1 <= month <= 12 else None
    if value is None:
        return None
    parts = [int(part) for part in re.findall(r"\d+", str(value))]
    for part in reversed(parts):
        if 1 <= part <= 12:
            return part
    return None


def abbreviated_month_labels(values: pd.Series | list[Any] | tuple[Any, ...], *, lang: str = "es") -> list[str]:
    locale = lang if lang in MONTH_ABBREVIATIONS else "es"
    source = list(values)
    labels: list[str] = []
    for index, value in enumerate(source):
        month_number = _infer_month_number(value)
        if month_number is None:
            month_number = (index % 12) + 1
        labels.append(MONTH_ABBREVIATIONS[locale][month_number - 1])
    return labels


def build_project_timeline(month_count: int, *, base_year: int | None = None) -> pd.DataFrame:
    if month_count <= 0:
        return pd.DataFrame(columns=["month_index", "calendar_year", "project_year", "is_year_start"])
    current_year = int(base_year) if base_year is not None else date.today().year
    month_index = pd.Series(range(1, month_count + 1), dtype=int)
    project_year = ((month_index - 1) // 12) + 1
    calendar_year = (current_year + project_year).astype(int)
    return pd.DataFrame(
        {
            "month_index": month_index.astype(int),
            "calendar_year": calendar_year.astype(int),
            "project_year": project_year.astype(int),
            "is_year_start": ((month_index - 1) % 12 == 0),
        }
    )


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


def build_cash_flow(monthly: pd.DataFrame, *, base_year: int | None = None) -> pd.DataFrame:
    frame = monthly[["Año_mes", "NPV_COP", "Ahorro_COP"]].copy()
    frame.rename(columns={"NPV_COP": "cumulative_npv", "Ahorro_COP": "monthly_savings"}, inplace=True)
    timeline = build_project_timeline(len(frame), base_year=base_year)
    if not timeline.empty:
        frame = frame.reset_index(drop=True).join(timeline)
    return frame


def build_npv_curve(candidate_table: pd.DataFrame) -> pd.DataFrame:
    if candidate_table.empty:
        return pd.DataFrame(columns=NPV_CURVE_COLUMNS)
    grouped = (
        candidate_table.sort_values(["kWp", "NPV_COP", "scan_order"], ascending=[True, False, True], kind="mergesort")
        .groupby("kWp", as_index=False, sort=True)
        .first()[NPV_CURVE_COLUMNS]
    )
    return grouped.sort_values("kWp").reset_index(drop=True)


def _build_panel_count_axis(curve: pd.DataFrame, module_power_w: float | None, *, max_ticks: int = 6) -> tuple[list[float], list[str]] | None:
    if not module_power_w or float(module_power_w) <= 0 or curve.empty or "panel_count" not in curve.columns:
        return None
    module_kw = float(module_power_w) / 1000.0
    if module_kw <= 0:
        return None
    panel_counts = sorted({int(value) for value in curve["panel_count"].dropna().tolist()})
    if not panel_counts:
        return None
    if len(panel_counts) <= max_ticks:
        selected_counts = panel_counts
    else:
        selected_counts = []
        last_index = len(panel_counts) - 1
        for step in range(max_ticks):
            index = round((last_index * step) / (max_ticks - 1))
            selected_counts.append(panel_counts[index])
        selected_counts = list(dict.fromkeys(selected_counts))
        if selected_counts[0] != panel_counts[0]:
            selected_counts.insert(0, panel_counts[0])
        if selected_counts[-1] != panel_counts[-1]:
            selected_counts.append(panel_counts[-1])
    tickvals = [float(panel_count) * module_kw for panel_count in selected_counts]
    ticktext = [f"{panel_count:,}" for panel_count in selected_counts]
    return tickvals, ticktext


def _discard_reason_label(reason: str, lang: str) -> str:
    return tr(f"workbench.scan_discard.reason.{reason}", lang)


def _discard_hover_text(point: dict[str, Any], lang: str) -> str:
    reason = str(point.get("reason", "")).strip()
    base = (
        f"{tr('workbench.scan_discard.discarded_prefix', lang)}: {_discard_reason_label(reason, lang)}"
        f"<br>kWp: {float(point.get('kWp', 0.0)):.3f}"
    )
    if reason != "peak_ratio":
        return f"{base}<extra></extra>"
    details = []
    peak_ratio = point.get("peak_ratio")
    limit = point.get("limit_peak_ratio")
    if peak_ratio not in (None, ""):
        details.append(f"{metric_label('peak_ratio', lang)}: {float(peak_ratio):.1%}")
    if limit not in (None, ""):
        details.append(f"{tr('workbench.scan_discard.limit_label', lang)}: {float(limit):.1f}")
    suffix = f"<br>{'<br>'.join(details)}" if details else ""
    return f"{base}{suffix}<extra></extra>"


def _add_viable_npv_traces(
    figure: go.Figure,
    curve: pd.DataFrame,
    *,
    lang: str,
    figure_title: str,
    selected_key: str | None,
    row: int | None = None,
) -> None:
    hover_template = (
        f"kWp: %{{x:.3f}}<br>"
        f"{tr('common.chart.panels', lang)}: %{{customdata[1]}}<br>"
        f"{'Batería' if lang == 'es' else 'Battery'}: %{{customdata[2]}}<br>"
        f"{metric_label('NPV_COP', lang)}: %{{y:,.0f}}<br>"
        f"{metric_label('payback_years', lang)}: %{{customdata[3]:.2f}}<br>"
        f"{metric_label('self_consumption_ratio', lang)}: %{{customdata[4]:.1%}}<br>"
        f"{metric_label('peak_ratio', lang)}: %{{customdata[5]:.1%}}<extra></extra>"
    )
    add_trace_kwargs = {"row": row, "col": 1} if row is not None else {}
    figure.add_trace(
        go.Scatter(
            x=curve["kWp"],
            y=curve["NPV_COP"],
            mode="lines+markers",
            name=figure_title,
            line={"color": "#2563eb", "width": 3},
            marker={"size": 9, "color": "#2563eb"},
            customdata=curve[["candidate_key", "panel_count", "battery_display", "payback_years", "self_consumption_ratio", "peak_ratio"]],
            hovertemplate=hover_template,
        ),
        **add_trace_kwargs,
    )
    if not selected_key:
        return
    selected_row = curve[curve["candidate_key"] == selected_key]
    if selected_row.empty:
        return
    figure.add_trace(
        go.Scatter(
            x=selected_row["kWp"],
            y=selected_row["NPV_COP"],
            mode="markers",
            marker={"size": 14, "color": "#b91c1c"},
            name=tr("common.chart.selected_design", lang),
            customdata=selected_row[["candidate_key", "panel_count"]],
            hovertemplate=(
                tr("common.chart.selected_design", lang)
                + "<br>"
                + tr("common.chart.panels", lang)
                + ": %{customdata[1]}<extra></extra>"
            ),
        ),
        **add_trace_kwargs,
    )


def _apply_panel_count_axis(
    figure: go.Figure,
    curve: pd.DataFrame,
    module_power_w: float | None,
    *,
    lang: str,
    axis_name: str,
    overlay_axis: str,
) -> None:
    panel_axis = _build_panel_count_axis(curve, module_power_w)
    if panel_axis is None:
        return
    tickvals, ticktext = panel_axis
    figure.update_layout(
        {
            axis_name: {
                "overlaying": overlay_axis,
                "side": "top",
                "title": {"text": tr("common.chart.panel_count", lang), "standoff": 8},
                "tickvals": tickvals,
                "ticktext": ticktext,
                "showgrid": False,
            }
        }
    )


def build_npv_figure(
    candidate_table: pd.DataFrame,
    selected_key: str | None = None,
    *,
    lang: str = "es",
    title: str | None = None,
    module_power_w: float | None = None,
    discarded_points: tuple[dict[str, Any], ...] | list[dict[str, Any]] | None = None,
) -> go.Figure:
    curve = build_npv_curve(candidate_table)
    curve = curve.copy()
    curve["battery_display"] = curve["battery"].map(lambda value: format_metric("selected_battery", value, lang))
    if module_power_w and float(module_power_w) > 0:
        curve["panel_count"] = curve["kWp"].map(lambda value: int(round(float(value) / (float(module_power_w) / 1000.0))))
    else:
        curve["panel_count"] = None
    figure_title = title or ("VPN vs kWp" if lang == "es" else "NPV vs kWp")
    discarded = [dict(point) for point in (discarded_points or [])]
    if not discarded:
        figure = make_subplots(specs=[[{"secondary_y": True}]])
        if curve.empty:
            figure.add_annotation(
                text=tr("workbench.scan_discard.no_viable_detail", lang),
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
        else:
            _add_viable_npv_traces(figure, curve, lang=lang, figure_title=figure_title, selected_key=selected_key)
            figure.add_trace(
                go.Scatter(
                    x=curve["kWp"],
                    y=curve["payback_years"],
                    mode="lines+markers",
                    name=metric_label("payback_years", lang),
                    line={"color": "#0f766e", "width": 2, "dash": "dash"},
                    marker={"size": 6, "color": "#0f766e"},
                    hovertemplate=(
                        f"kWp: %{{x:.3f}}<br>{metric_label('payback_years', lang)}: %{{y:.2f}}<extra></extra>"
                    ),
                ),
                secondary_y=True,
            )
        figure.update_layout(template="plotly_white", title=figure_title, hovermode="x unified", margin={"t": 88})
        figure.update_yaxes(title=metric_label("NPV_COP", lang), tickformat=",.0f", secondary_y=False)
        figure.update_yaxes(title=metric_label("payback_years", lang), secondary_y=True)
        figure.update_xaxes(title=tr("common.chart.installed_kwp", lang))
        _apply_panel_count_axis(figure, curve, module_power_w, lang=lang, axis_name="xaxis2", overlay_axis="x")
        return figure

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.82, 0.18],
        vertical_spacing=0.05,
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )
    if curve.empty:
        figure.add_annotation(
            text=tr("workbench.scan_discard.all_discarded_chart", lang),
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.88,
            showarrow=False,
        )
    else:
        _add_viable_npv_traces(figure, curve, lang=lang, figure_title=figure_title, selected_key=selected_key, row=1)
        figure.add_trace(
            go.Scatter(
                x=curve["kWp"],
                y=curve["payback_years"],
                mode="lines+markers",
                name=metric_label("payback_years", lang),
                line={"color": "#0f766e", "width": 2, "dash": "dash"},
                marker={"size": 6, "color": "#0f766e"},
                hovertemplate=(
                    f"kWp: %{{x:.3f}}<br>{metric_label('payback_years', lang)}: %{{y:.2f}}<extra></extra>"
                ),
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    discard_frame = pd.DataFrame(discarded).sort_values(["scan_order", "kWp"], kind="mergesort").reset_index(drop=True)
    for reason, color in (("peak_ratio", "#d97706"), ("inverter_string", "#64748b")):
        subset = discard_frame[discard_frame["reason"] == reason]
        if subset.empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=subset["kWp"],
                y=[0.5] * len(subset),
                mode="markers",
                name=_discard_reason_label(reason, lang),
                marker={"size": 11, "symbol": "x", "color": color, "line": {"width": 2, "color": color}},
                hovertemplate=[_discard_hover_text(point, lang) for point in subset.to_dict("records")],
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    figure.update_layout(template="plotly_white", title=figure_title, hovermode="x unified", margin={"t": 88})
    figure.update_yaxes(title=metric_label("NPV_COP", lang), tickformat=",.0f", row=1, col=1, secondary_y=False)
    figure.update_yaxes(title=metric_label("payback_years", lang), row=1, col=1, secondary_y=True)
    figure.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, range=[0, 1], row=2, col=1)
    figure.update_xaxes(title=tr("common.chart.installed_kwp", lang), row=2, col=1)
    _apply_panel_count_axis(figure, curve, module_power_w, lang=lang, axis_name="xaxis3", overlay_axis="x")
    return figure


def build_monthly_balance_figure(
    monthly_balance: pd.DataFrame,
    *,
    lang: str = "es",
    title: str | None = None,
) -> go.Figure:
    month_values = monthly_balance["Año_mes"].tolist()
    month_labels = abbreviated_month_labels(month_values, lang=lang)
    melted = monthly_balance.melt(id_vars="Año_mes", var_name="series", value_name="kWh")
    figure_title = title or ("Balance mensual de energía (año 1)" if lang == "es" else "Monthly energy balance (year 1)")
    figure = px.bar(
        melted,
        x="Año_mes",
        y="kWh",
        color="series",
        barmode="stack",
        template="plotly_white",
        title=figure_title,
    )
    figure.update_xaxes(
        title=tr("common.chart.month", lang),
        tickmode="array",
        tickvals=month_values,
        ticktext=month_labels,
        categoryorder="array",
        categoryarray=month_values,
    )
    figure.update_yaxes(title="kWh", tickformat=",.0f")
    return figure


def build_annual_coverage_figure(
    detail: dict[str, Any],
    config: dict[str, Any],
    *,
    lang: str = "es",
) -> go.Figure:
    export_allowed = bool(config.get("export_allowed", True))
    title = (
        "Autoconsumo, Importación y Exportación (Año 1)"
        if lang == "es" and export_allowed
        else "Cobertura mensual de demanda (Año 1)"
        if lang == "es"
        else "Self-consumption, import, and export (Year 1)"
        if export_allowed
        else "Monthly demand coverage (Year 1)"
    )
    monthly = detail.get("monthly")
    if not isinstance(monthly, pd.DataFrame) or monthly.empty:
        return _deep_dive_empty(title, lang=lang)
    prepared = prepare_autoconsumo_anual_series(monthly, export_allowed=export_allowed, lang=lang)
    month_values = prepared["xlabels"]
    month_labels = abbreviated_month_labels(month_values, lang=lang)
    figure = go.Figure()
    for series in prepared["series"]:
        figure.add_bar(
            x=month_values,
            y=series["values"],
            name=series["label"],
            marker_color=series["color"],
        )
    figure.update_layout(
        template="plotly_white",
        title=title,
        barmode="stack",
        annotations=[annotation] if (annotation := _module_annotation(detail.get("kWp"), config.get("P_mod_W"), lang=lang)) else [],
    )
    figure.update_xaxes(
        title=tr("common.chart.month", lang),
        tickmode="array",
        tickvals=month_values,
        ticktext=month_labels,
        categoryorder="array",
        categoryarray=month_values,
    )
    figure.update_yaxes(title="kWh", tickformat=",.0f")
    return figure


def build_battery_load_figure(
    detail: dict[str, Any],
    config: dict[str, Any],
    *,
    lang: str = "es",
) -> go.Figure:
    title = "Cobertura de la Demanda (mensual)" if lang == "es" else "Demand coverage (monthly)"
    monthly = detail.get("monthly")
    required = {"PV_a_Carga_kWh", "Bateria_a_Carga_kWh", "Importacion_Red_kWh"}
    if not isinstance(monthly, pd.DataFrame) or monthly.empty or not required.issubset(monthly.columns):
        return _deep_dive_empty(title, lang=lang)
    prepared = prepare_battery_monthly_series(monthly.iloc[:12].copy(), lang=lang)
    month_values = prepared["xlabels"]
    month_labels = abbreviated_month_labels(month_values, lang=lang)
    color_map = (
        {
            "PV → Carga": "#57eb36",
            "Batería → Carga": "#6fa8dc",
            "Importación Red": "#f26c4f",
        }
        if lang == "es"
        else {
            "PV to load": "#57eb36",
            "Battery to load": "#6fa8dc",
            "Grid import": "#f26c4f",
        }
    )
    figure = go.Figure()
    for series in prepared["coverage_series"]:
        figure.add_bar(
            x=month_values,
            y=series["values"],
            name=series["label"],
            marker_color=color_map.get(series["label"], "#94a3b8"),
        )
    figure.update_layout(
        template="plotly_white",
        title=title,
        barmode="stack",
        annotations=[annotation] if (annotation := _module_annotation(detail.get("kWp"), config.get("P_mod_W"), lang=lang)) else [],
    )
    figure.update_xaxes(
        title=tr("common.chart.month", lang),
        tickmode="array",
        tickvals=month_values,
        ticktext=month_labels,
        categoryorder="array",
        categoryarray=month_values,
    )
    figure.update_yaxes(title=tr("common.chart.energy_kwh", lang), tickformat=",.0f")
    return figure


def build_pv_destination_figure(
    detail: dict[str, Any],
    config: dict[str, Any],
    *,
    lang: str = "es",
) -> go.Figure:
    title = "Destino de la Generación FV (mensual)" if lang == "es" else "PV generation destination (monthly)"
    monthly = detail.get("monthly")
    required = {"PV_a_Carga_kWh", "PV_a_Bateria_kWh", "Exportacion_kWh"}
    if not isinstance(monthly, pd.DataFrame) or monthly.empty or not required.issubset(monthly.columns):
        return _deep_dive_empty(title, lang=lang)
    prepared = prepare_battery_monthly_series(monthly.iloc[:12].copy(), lang=lang)
    color_map = (
        {
            "PV → Carga": "#57eb36",
            "PV → Batería": "#6fa8dc",
            "Exportación": "#f7b32b",
            "Recorte": "#94a3b8",
        }
        if lang == "es"
        else {
            "PV to load": "#57eb36",
            "PV to battery": "#6fa8dc",
            "Export": "#f7b32b",
            "Curtailment": "#94a3b8",
        }
    )
    figure = go.Figure()
    for series in prepared["destination_series"]:
        values = list(series["values"])
        if series["label"] == "Curtailment" and not any(abs(float(value)) > 1e-6 for value in values):
            continue
        figure.add_bar(
            x=prepared["xlabels"],
            y=values,
            name=series["label"],
            marker_color=color_map.get(series["label"], "#94a3b8"),
        )
    figure.update_layout(
        template="plotly_white",
        title=title,
        barmode="stack",
        annotations=[annotation] if (annotation := _module_annotation(detail.get("kWp"), config.get("P_mod_W"), lang=lang)) else [],
    )
    figure.update_xaxes(title=tr("common.chart.month", lang))
    figure.update_yaxes(title=tr("common.chart.energy_kwh", lang), tickformat=",.0f")
    return figure


def build_typical_day_figure(
    detail: dict[str, Any],
    scenario: ScenarioRecord,
    *,
    lang: str = "es",
) -> go.Figure:
    export_allowed = bool(scenario.config_bundle.config.get("export_allowed", True))
    title = "Día Típico" if lang == "es" else "Typical day"
    if not scenario.config_bundle.demand_profile_7x24.size or not scenario.config_bundle.solar_profile.size:
        return _deep_dive_empty(title, lang=lang)
    prepared = prepare_typical_day_series(
        detail.get("kWp", 0.0),
        detail.get("inv_sel") or {"inverter": {"AC_kW": 0.0}},
        scenario.config_bundle.config,
        scenario.config_bundle.demand_profile_7x24[0],
        scenario.config_bundle.solar_profile,
        scenario.config_bundle.hsp_month,
        scenario.config_bundle.demand_month_factor,
        battery=detail.get("battery"),
        export_allowed=export_allowed,
    )
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_bar(
        x=prepared["hours"],
        y=prepared["demand_kw"],
        name=tr("common.chart.demand", lang),
        marker_color="red",
        offsetgroup="demand",
    )
    figure.add_bar(
        x=prepared["hours"],
        y=prepared["pv_ac_kw"],
        name=tr("common.chart.pv", lang),
        marker_color="#57eb36",
        offsetgroup="pv",
    )
    if prepared.get("has_battery"):
        figure.add_trace(
            go.Scatter(
                x=prepared["hours"],
                y=prepared["battery_to_load_kw"],
                mode="lines+markers",
                name=tr("common.chart.battery_to_load", lang),
                line={"color": "#2563eb", "width": 3},
                marker={"size": 6, "color": "#2563eb"},
            ),
            secondary_y=False,
        )
        figure.add_trace(
            go.Scatter(
                x=prepared["hours"],
                y=prepared["pv_to_battery_kw"],
                mode="lines+markers",
                name=tr("common.chart.pv_to_battery", lang),
                line={"color": "#f59e0b", "width": 2.5, "dash": "dash"},
                marker={"size": 5, "color": "#f59e0b"},
            ),
            secondary_y=False,
        )
        if any(abs(float(value)) > 1e-6 for value in prepared["grid_import_kw"]):
            figure.add_trace(
                go.Scatter(
                    x=prepared["hours"],
                    y=prepared["grid_import_kw"],
                    mode="lines",
                    name=tr("common.chart.grid_import", lang),
                    line={"color": "#6b7280", "width": 2, "dash": "dot"},
                ),
                secondary_y=False,
            )
    figure.add_trace(
        go.Scatter(
            x=prepared["hours"],
            y=prepared["solar_factor_pct"],
            mode="lines",
            name=tr("common.chart.solar_factor", lang),
            line={"color": "#f2bb4b", "width": 2.5},
        ),
        secondary_y=True,
    )
    figure.update_layout(
        template="plotly_white",
        title=title + (f" ({tr('common.chart.zero_export_suffix', lang)})" if export_allowed is False else ""),
        barmode="group",
        annotations=[annotation] if (annotation := _module_annotation(detail.get("kWp"), scenario.config_bundle.config.get("P_mod_W"), lang=lang)) else [],
    )
    figure.update_xaxes(title=tr("common.chart.hour", lang), tickmode="linear", dtick=1, range=[-0.5, 23.5])
    figure.update_yaxes(title=tr("common.chart.power_kw", lang), secondary_y=False)
    figure.update_yaxes(title=f"{tr('common.chart.solar_factor', lang)} [%]", secondary_y=True)
    return figure


def build_cash_flow_figure(
    cash_flow: pd.DataFrame,
    *,
    lang: str = "es",
    title: str | None = None,
    base_year: int | None = None,
    k_wp: float | None = None,
    module_power_w: float | None = None,
) -> go.Figure:
    figure_title = title or ("Flujo acumulado descontado" if lang == "es" else "Cumulative discounted cash flow")
    frame = cash_flow.copy()
    if "month_index" not in frame.columns or "calendar_year" not in frame.columns or "project_year" not in frame.columns:
        timeline = build_project_timeline(len(frame), base_year=base_year)
        if not timeline.empty:
            frame = frame.reset_index(drop=True).join(timeline)
    figure = go.Figure()
    if not frame.empty:
        prepared = prepare_cumulative_npv_series(
            frame.rename(
                columns={
                    "cumulative_npv": "NPV_COP",
                    "monthly_savings": "Ahorro_COP",
                }
            )
        )
        figure.add_trace(
            go.Bar(
                x=frame["month_index"],
                y=frame["cumulative_npv"],
                name=figure_title,
                marker={"color": prepared["colors"]},
                customdata=frame[["month_index", "calendar_year", "project_year", "monthly_savings"]],
                hovertemplate=(
                    tr("timeline.hover.project_month", lang)
                    + ": %{customdata[0]:.0f}<br>"
                    + tr("timeline.hover.calendar_year", lang)
                    + ": %{customdata[1]:.0f}<br>"
                    + tr("timeline.hover.project_year", lang)
                    + ": "
                    + tr("timeline.project_year", lang, year="%{customdata[2]:.0f}")
                    + "<br>"
                    + tr("common.chart.cumulative_npv", lang)
                    + ": %{y:,.0f}<br>"
                    + tr("timeline.hover.monthly_savings", lang)
                    + ": %{customdata[3]:,.0f}<extra></extra>"
                ),
            )
        )
        if prepared["crossing_x"] is not None and "Año_mes" in frame.columns:
            crossing_match = frame.loc[frame["Año_mes"] == prepared["crossing_x"], "month_index"]
            if not crossing_match.empty:
                figure.add_vline(x=float(crossing_match.iloc[0]), line_dash="dash", line_color="blue")
        _apply_project_time_axes(figure, frame[["month_index", "calendar_year", "project_year", "is_year_start"]], lang=lang)
    figure.update_layout(
        template="plotly_white",
        title=figure_title,
        hovermode="x unified",
        annotations=[annotation] if (annotation := _module_annotation(k_wp, module_power_w, lang=lang)) else [],
    )
    figure.add_hline(y=0, line_dash="dash", line_color="#334155")
    figure.update_yaxes(
        title="Flujo acumulado descontado [COP]" if lang == "es" else "Discounted cumulative cash flow (COP)",
        tickformat=",.0f",
    )
    return figure


def resolve_selected_candidate_key(scan_result, selected_rows=None, table_rows=None) -> str | None:
    selected_key = scan_result.best_candidate_key
    if selected_rows and table_rows:
        selected_index = selected_rows[0]
        if 0 <= selected_index < len(table_rows):
            candidate_key = table_rows[selected_index].get("candidate_key")
            if candidate_key in scan_result.candidate_details:
                selected_key = candidate_key
    return selected_key


def resolve_selected_candidate_key_for_scenario(
    scan_result,
    scenario_selected_key: str | None,
    table_rows: list[dict] | None = None,
    selected_rows: list[int] | None = None,
    click_data: dict | None = None,
) -> str | None:
    if click_data and click_data.get("points"):
        point = click_data["points"][0]
        customdata = point.get("customdata")
        if isinstance(customdata, (list, tuple)) and customdata:
            candidate_key = customdata[0]
            if candidate_key in scan_result.candidate_details:
                return candidate_key
    if selected_rows and table_rows:
        selected_key = resolve_selected_candidate_key(scan_result, selected_rows, table_rows)
        if selected_key in scan_result.candidate_details:
            return selected_key
    if scenario_selected_key in scan_result.candidate_details:
        return str(scenario_selected_key)
    return scan_result.best_candidate_key


def build_scenario_summary_row(scenario: ScenarioRecord) -> dict[str, Any]:
    if scenario.scan_result is None:
        raise ValueError(f"El escenario '{scenario.name}' no tiene un escaneo determinístico.")
    candidate_key = scenario.selected_candidate_key or scenario.scan_result.best_candidate_key
    if not candidate_key:
        raise ValueError(f"El escenario '{scenario.name}' no tiene diseños viables en el escaneo determinístico.")
    detail = scenario.scan_result.candidate_details[candidate_key]
    kpis = build_kpis(detail)
    return {
        "scenario_id": scenario.scenario_id,
        "scenario": scenario.name,
        "candidate_key": candidate_key,
        "best_kWp": kpis["best_kWp"],
        "battery": kpis["selected_battery"],
        "NPV_COP": kpis["NPV"],
        "payback_years": kpis["payback_years"],
        "self_consumption_ratio": kpis["self_consumption_ratio"],
        "self_sufficiency_ratio": kpis["self_sufficiency_ratio"],
        "annual_import_kwh": kpis["annual_import_kwh"],
        "annual_export_kwh": kpis["annual_export_kwh"],
    }


def build_comparison_table(scenarios: list[ScenarioRecord]) -> pd.DataFrame:
    rows = [
        build_scenario_summary_row(scenario)
        for scenario in scenarios
        if scenario.scan_result is not None and not scenario.dirty and scenario.scan_result.best_candidate_key
    ]
    if not rows:
        return pd.DataFrame(
            columns=[
                "scenario_id",
                "scenario",
                "candidate_key",
                "best_kWp",
                "battery",
                "NPV_COP",
                "payback_years",
                "self_consumption_ratio",
                "self_sufficiency_ratio",
                "annual_import_kwh",
                "annual_export_kwh",
            ]
        )
    return pd.DataFrame(rows).sort_values("scenario").reset_index(drop=True)


def build_comparison_figures(scenarios: list[ScenarioRecord], lang: str = "es") -> dict[str, go.Figure]:
    clean_scenarios = [
        scenario
        for scenario in scenarios
        if scenario.scan_result is not None and not scenario.dirty and scenario.scan_result.best_candidate_key
    ]
    summary = build_comparison_table(clean_scenarios)

    if summary.empty:
        empty = go.Figure()
        empty.update_layout(
            template="plotly_white",
            title=tr("compare.figure.empty_title", lang),
            annotations=[{"text": tr("compare.figure.empty_message", lang), "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False}],
        )
        return {"kpi_bar": empty, "npv_overlay": empty}

    metrics = summary.melt(
        id_vars=["scenario"],
        value_vars=["NPV_COP", "payback_years", "self_consumption_ratio"],
        var_name="metric",
        value_name="value",
    )
    metrics["metric_label"] = metrics["metric"].map(
        {
            "NPV_COP": metric_label("NPV_COP", lang),
            "payback_years": metric_label("payback_years", lang),
            "self_consumption_ratio": metric_label("self_consumption_ratio", lang),
        }
    )
    metrics["display_value"] = metrics.apply(
        lambda row: row["value"] * 100 if row["metric"] == "self_consumption_ratio" else row["value"],
        axis=1,
    )
    kpi_bar = px.bar(
        metrics,
        x="scenario",
        y="display_value",
        color="metric_label",
        barmode="group",
        template="plotly_white",
        title=tr("compare.figure.kpi_title", lang),
    )
    kpi_bar.update_yaxes(title=tr("compare.axis.metric", lang))
    kpi_bar.update_xaxes(title=tr("compare.axis.scenario", lang))

    npv_overlay = go.Figure()
    for scenario in clean_scenarios:
        assert scenario.scan_result is not None
        curve = build_npv_curve(scenario.scan_result.candidates)
        curve = curve.copy()
        curve["battery_display"] = curve["battery"].map(lambda value: format_metric("selected_battery", value, lang))
        npv_overlay.add_trace(
            go.Scatter(
                x=curve["kWp"],
                y=curve["NPV_COP"],
                mode="lines+markers",
                name=scenario.name,
                customdata=curve[["candidate_key", "battery_display"]],
                hovertemplate=(
                    "%{fullData.name}<br>"
                    + f"{tr('compare.axis.kwp', lang)}=%{{x:.3f}}<br>"
                    + f"{metric_label('NPV_COP', lang)}=%{{y:,.0f}}<br>"
                    + metric_label("battery", lang)
                    + "=%{customdata[1]}<extra></extra>"
                ),
            )
        )
    npv_overlay.update_layout(template="plotly_white", title=tr("compare.figure.npv_title", lang))
    npv_overlay.update_xaxes(title=tr("compare.axis.kwp", lang))
    npv_overlay.update_yaxes(title=metric_label("NPV_COP", lang))
    return {"kpi_bar": kpi_bar, "npv_overlay": npv_overlay}


def build_session_comparison_rows(state: ScenarioSessionState) -> list[ScenarioRecord]:
    selected_ids = set(state.comparison_scenario_ids)
    return [scenario for scenario in state.scenarios if scenario.scenario_id in selected_ids]
