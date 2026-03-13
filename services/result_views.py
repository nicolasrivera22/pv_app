from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .i18n import tr
from .types import ScenarioRecord, ScenarioSessionState
from .ui_schema import metric_label


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
        return frame
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


def build_cash_flow(monthly: pd.DataFrame) -> pd.DataFrame:
    frame = monthly[["Año_mes", "NPV_COP", "Ahorro_COP"]].copy()
    frame.rename(columns={"NPV_COP": "cumulative_npv", "Ahorro_COP": "monthly_savings"}, inplace=True)
    return frame


def build_npv_curve(candidate_table: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        candidate_table.sort_values(["kWp", "NPV_COP", "scan_order"], ascending=[True, False, True], kind="mergesort")
        .groupby("kWp", as_index=False, sort=True)
        .first()[["kWp", "NPV_COP", "battery", "candidate_key", "payback_years", "self_consumption_ratio", "peak_ratio"]]
    )
    return grouped.sort_values("kWp").reset_index(drop=True)


def build_npv_figure(
    candidate_table: pd.DataFrame,
    selected_key: str | None = None,
    *,
    lang: str = "es",
    title: str | None = None,
) -> go.Figure:
    curve = build_npv_curve(candidate_table)
    figure_title = title or ("VPN vs kWp" if lang == "es" else "NPV vs kWp")
    figure = px.line(
        curve,
        x="kWp",
        y="NPV_COP",
        markers=True,
        template="plotly_white",
        title=figure_title,
        hover_data={
            "candidate_key": True,
            "battery": True,
            "NPV_COP": ":,.0f",
            "payback_years": ":.2f",
            "self_consumption_ratio": ":.2%",
            "peak_ratio": ":.3f",
        },
        custom_data=["candidate_key"],
    )
    if selected_key:
        selected_row = curve[curve["candidate_key"] == selected_key]
        if not selected_row.empty:
            figure.add_scatter(
                x=selected_row["kWp"],
                y=selected_row["NPV_COP"],
                mode="markers",
                marker={"size": 14, "color": "#b91c1c"},
                name="Candidato seleccionado" if lang == "es" else "Selected candidate",
                customdata=selected_row[["candidate_key"]],
                hovertemplate=("Seleccionado" if lang == "es" else "Selected") + ": %{customdata[0]}<extra></extra>",
            )
    figure.update_yaxes(title=metric_label("NPV_COP", lang))
    figure.update_xaxes(title="kWp instalado" if lang == "es" else "Installed kWp")
    return figure


def build_monthly_balance_figure(
    monthly_balance: pd.DataFrame,
    *,
    lang: str = "es",
    title: str | None = None,
) -> go.Figure:
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
    figure.update_xaxes(title="Mes" if lang == "es" else "Month")
    figure.update_yaxes(title="kWh")
    return figure


def build_cash_flow_figure(
    cash_flow: pd.DataFrame,
    *,
    lang: str = "es",
    title: str | None = None,
) -> go.Figure:
    figure_title = title or ("Flujo acumulado descontado" if lang == "es" else "Cumulative cash flow")
    figure = px.line(
        cash_flow,
        x="Año_mes",
        y="cumulative_npv",
        template="plotly_white",
        title=figure_title,
    )
    figure.add_hline(y=0, line_dash="dash", line_color="#334155")
    figure.update_xaxes(title="Mes" if lang == "es" else "Month")
    figure.update_yaxes(title="Flujo acumulado descontado [COP]" if lang == "es" else "Discounted cumulative cash flow (COP)")
    return figure


def resolve_selected_candidate_key(scan_result, selected_rows=None, table_rows=None) -> str:
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
) -> str:
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
    rows = [build_scenario_summary_row(scenario) for scenario in scenarios if scenario.scan_result is not None and not scenario.dirty]
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
    clean_scenarios = [scenario for scenario in scenarios if scenario.scan_result is not None and not scenario.dirty]
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
        npv_overlay.add_trace(
            go.Scatter(
                x=curve["kWp"],
                y=curve["NPV_COP"],
                mode="lines+markers",
                name=scenario.name,
                customdata=curve[["candidate_key", "battery"]],
                hovertemplate=(
                    "%{fullData.name}<br>"
                    + f"{tr('compare.axis.kwp', lang)}=%{{x:.3f}}<br>"
                    + f"{metric_label('NPV_COP', lang)}=%{{y:,.0f}}<br>"
                    + ("Candidato" if lang == "es" else "Candidate")
                    + "=%{customdata[0]}<br>"
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
