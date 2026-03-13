from __future__ import annotations

import pandas as pd


def candidate_key_for(k_wp: float, battery_name: str) -> str:
    return f"{k_wp:.3f}::{battery_name}"


def battery_name_from_candidate(battery: dict | None) -> str:
    if battery is None or float(battery.get("nom_kWh", 0) or 0) <= 0:
        return "None"
    return str(battery.get("name", "Battery"))


def build_candidate_table(detail_map: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for detail in detail_map.values():
        rows.append(
            {
                "candidate_key": detail["candidate_key"],
                "kWp": round(float(detail["kWp"]), 3),
                "battery": detail["battery_name"],
                "NPV_COP": float(detail["summary"]["cum_disc_final"]),
                "payback_years": detail["summary"]["payback_years"],
                "capex_client": float(detail["summary"]["capex_client"]),
                "self_consumption_ratio": detail["self_consumption_ratio"],
                "peak_ratio": float(detail["peak_ratio"]),
                "best_battery_for_kwp": bool(detail["best_battery"]),
            }
        )
    return pd.DataFrame(rows).sort_values(by=["kWp", "NPV_COP"], ascending=[True, False]).reset_index(drop=True)


def build_kpis(detail: dict) -> dict[str, float | str | None]:
    summary = detail["summary"]
    return {
        "best_kWp": round(float(detail["kWp"]), 3),
        "selected_battery": detail["battery_name"],
        "NPV": float(summary["cum_disc_final"]),
        "payback_years": summary["payback_years"],
        "self_consumption_ratio": float(detail.get("self_consumption_ratio", 0.0)),
    }


def build_monthly_balance(monthly: pd.DataFrame) -> pd.DataFrame:
    first_year = monthly.iloc[:12].copy()
    columns = [
        ("PV_a_Carga_kWh", "PV to load"),
        ("Bateria_a_Carga_kWh", "Battery to load"),
        ("Importacion_Red_kWh", "Grid import"),
    ]
    if "Exportacion_kWh" in first_year.columns:
        columns.append(("Exportacion_kWh", "Export"))
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
        candidate_table.sort_values("NPV_COP", ascending=False)
        .groupby("kWp", as_index=False)
        .first()[["kWp", "NPV_COP", "battery", "candidate_key"]]
    )
    return grouped.sort_values("kWp").reset_index(drop=True)


def calculate_self_consumption_ratio(monthly: pd.DataFrame) -> float:
    first_year = monthly.iloc[:12]
    consumed = first_year.get("PV_a_Carga_kWh", 0).sum() + first_year.get("Bateria_a_Carga_kWh", 0).sum()
    demand = first_year.get("Demanda_kWh", 0).sum()
    return float(consumed / demand) if demand else 0.0
