from __future__ import annotations

from copy import deepcopy

from pv_product.optimizer import Optimizer

from .result_views import (
    battery_name_from_candidate,
    build_candidate_table,
    build_cash_flow,
    build_kpis,
    build_monthly_balance,
    build_npv_curve,
    calculate_self_consumption_ratio,
    candidate_key_for,
)
from .types import LoadedConfigBundle, ScanRunResult, ScenarioRunResult
from .validation import validate_config


def _deterministic_config(config: dict) -> dict:
    cfg = deepcopy(config)
    cfg["mc_PR_std"] = 0.0
    cfg["mc_buy_std"] = 0.0
    cfg["mc_sell_std"] = 0.0
    cfg["mc_demand_std"] = 0.0
    return cfg


def run_scan(config_bundle: LoadedConfigBundle) -> ScanRunResult:
    combined_issues = {}
    for issue in [*config_bundle.issues, *validate_config(config_bundle)]:
        combined_issues[(issue.level, issue.field, issue.message)] = issue
    issues = tuple(combined_issues.values())
    error_issues = [issue for issue in issues if issue.level == "error"]
    if error_issues:
        joined = "; ".join(f"{issue.field}: {issue.message}" for issue in error_issues)
        raise ValueError(f"La configuración no es ejecutable: {joined}")

    cfg = _deterministic_config(config_bundle.config)
    optimizer = Optimizer(
        cfg=cfg,
        inv_catalog=config_bundle.inverter_catalog,
        bat_catalog=config_bundle.battery_catalog,
        dow24=config_bundle.demand_profile_7x24,
        day_w=config_bundle.day_weights,
        s24=config_bundle.solar_profile,
        hsp_month=config_bundle.hsp_month,
        demand_month_factor=config_bundle.demand_month_factor,
        export_allowed=bool(cfg["export_allowed"]),
        cop_kwp_table=config_bundle.cop_kwp_table,
        cop_kwp_table_others=config_bundle.cop_kwp_table_others,
    )
    _, _, seed_kwp, detail_rows = optimizer.run()
    detail_map: dict[str, dict] = {}
    for scan_order, detail in enumerate(detail_rows):
        battery_name = battery_name_from_candidate(detail["battery"])
        candidate_key = candidate_key_for(detail["kWp"], battery_name)
        monthly = detail["df"].copy()
        detail_map[candidate_key] = {
            "scan_order": scan_order,
            "candidate_key": candidate_key,
            "kWp": float(detail["kWp"]),
            "battery_name": battery_name,
            "battery": deepcopy(detail["battery"]),
            "inv_sel": deepcopy(detail["inv_sel"]),
            "summary": deepcopy(detail["summary"]),
            "value": float(detail["value"]),
            "peak_ratio": float(detail["peak_ratio"]),
            "best_battery": False,
            "monthly": monthly,
            "self_consumption_ratio": calculate_self_consumption_ratio(monthly),
        }

    candidate_table = build_candidate_table(detail_map)
    if candidate_table.empty:
        raise ValueError("No se encontraron candidatos viables para el escenario determinístico.")

    best_for_kwp = set(candidate_table.loc[candidate_table["best_battery_for_kwp"], "candidate_key"])
    for candidate_key, detail in detail_map.items():
        detail["best_battery"] = candidate_key in best_for_kwp

    best_candidate_key = candidate_table.sort_values(
        by=["NPV_COP", "scan_order"],
        ascending=[False, True],
        kind="mergesort",
    ).iloc[0]["candidate_key"]
    return ScanRunResult(
        candidates=candidate_table,
        best_candidate_key=best_candidate_key,
        candidate_details=detail_map,
        seed_kwp=seed_kwp,
        issues=issues,
    )


def run_scenario(config_bundle: LoadedConfigBundle, candidate_key: str | None = None) -> ScenarioRunResult:
    scan_result = run_scan(config_bundle)
    selected_key = candidate_key or scan_result.best_candidate_key
    if selected_key not in scan_result.candidate_details:
        raise KeyError(f"No existe el candidato '{selected_key}' en el escaneo.")

    detail = scan_result.candidate_details[selected_key]
    monthly = detail["monthly"].copy()
    return ScenarioRunResult(
        candidate_key=selected_key,
        candidate=detail,
        monthly=monthly,
        kpis=build_kpis(detail),
        cash_flow=build_cash_flow(monthly),
        monthly_balance=build_monthly_balance(monthly),
        npv_curve=build_npv_curve(scan_result.candidates),
        issues=scan_result.issues,
    )
