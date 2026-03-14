from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from typing import Any

import pandas as pd

from pv_product.hardware import generate_kwp_candidates, peak_ratio_ok, select_inverter_and_strings
from pv_product.models import Battery, DispatchConfig, PVSystem
from pv_product.simulator import Simulator

from .types import LoadedConfigBundle

DEFAULT_PARALLEL_WORKERS = 4


@dataclass(frozen=True)
class DeterministicScanTask:
    task_index: int
    k_wp: float
    cfg: dict[str, Any]
    inv_catalog: pd.DataFrame
    battery_options: tuple[dict[str, Any], ...]
    demand_profile_7x24: Any
    day_weights: Any
    solar_profile: Any
    hsp_month: Any
    demand_month_factor: Any
    cop_kwp_table: pd.DataFrame
    cop_kwp_table_others: pd.DataFrame


@dataclass(frozen=True)
class DeterministicScanTaskResult:
    task_index: int
    detail_rows: tuple[dict[str, Any], ...]


def _build_battery(batt: dict[str, Any] | None, cfg: dict[str, Any]) -> Battery | None:
    if batt is None or float(batt.get("nom_kWh", 0) or 0) <= 0:
        return None
    usable = float(batt["nom_kWh"]) * float(cfg["bat_DoD"])
    coupling = str(cfg.get("bat_coupling", "ac")).strip().lower()
    eta_rt = float(cfg["bat_eta_rt"])
    eta = eta_rt ** 0.5
    return Battery(
        name=str(batt.get("name", "BAT")),
        usable_kwh=usable,
        max_ch_kw=float(batt.get("max_ch_kW", batt.get("max_kW", 0.0))),
        max_dis_kw=float(batt.get("max_dis_kW", batt.get("max_kW", 0.0))),
        eta_ch=eta,
        eta_dis=eta,
        coupling=coupling,
        soc_init=0.5,
        price_cop=float(batt.get("price_COP", 0.0)),
    )


def _lookup_price_per_kwp(table: pd.DataFrame, k_wp: float, table_name: str) -> float:
    mask = (table["MIN"] < k_wp) & (table["MAX"] >= k_wp)
    matches = table.loc[mask, "PRECIO_POR_KWP"].values
    if len(matches) == 0:
        raise ValueError(f"No hay banda de precio en '{table_name}' para {k_wp:.3f} kWp.")
    return float(matches[0])


def _build_battery_options(config_bundle: LoadedConfigBundle) -> tuple[dict[str, Any], ...]:
    cfg = config_bundle.config
    bat0 = {"name": "BAT-0", "nom_kWh": 0.0, "max_kW": 0.0, "max_ch_kW": 0.0, "max_dis_kW": 0.0, "price_COP": 0.0}
    if cfg["optimize_battery"] and cfg["include_battery"]:
        return tuple([bat0, *[row.to_dict() for _, row in config_bundle.battery_catalog.iterrows()]])
    if cfg["include_battery"] and cfg.get("battery_name"):
        row = config_bundle.battery_catalog[
            config_bundle.battery_catalog["name"].astype(str) == str(cfg["battery_name"])
        ]
        if not row.empty:
            return (row.iloc[0].to_dict(),)
    return (bat0,)


def _determine_max_workers(max_workers: int | None) -> int:
    if max_workers is not None:
        return max(1, int(max_workers))
    env_value = os.getenv("PV_SCAN_MAX_WORKERS")
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            return 1
    cpu_count = os.cpu_count() or 1
    return min(max(cpu_count - 1, 1), DEFAULT_PARALLEL_WORKERS)


def _build_tasks(config_bundle: LoadedConfigBundle) -> tuple[float, tuple[DeterministicScanTask, ...]]:
    cfg = dict(config_bundle.config)
    kwp_list, seed = generate_kwp_candidates(cfg)
    battery_options = _build_battery_options(config_bundle)
    tasks = tuple(
        DeterministicScanTask(
            task_index=index,
            k_wp=float(k_wp),
            cfg=cfg,
            inv_catalog=config_bundle.inverter_catalog,
            battery_options=battery_options,
            demand_profile_7x24=config_bundle.demand_profile_7x24,
            day_weights=config_bundle.day_weights,
            solar_profile=config_bundle.solar_profile,
            hsp_month=config_bundle.hsp_month,
            demand_month_factor=config_bundle.demand_month_factor,
            cop_kwp_table=config_bundle.cop_kwp_table,
            cop_kwp_table_others=config_bundle.cop_kwp_table_others,
        )
        for index, k_wp in enumerate(kwp_list)
    )
    return float(seed), tasks


def evaluate_deterministic_scan_task(task: DeterministicScanTask) -> DeterministicScanTaskResult:
    cfg = task.cfg
    simulator = Simulator(
        dow24=task.demand_profile_7x24,
        day_w=task.day_weights,
        solar_shape=task.solar_profile,
        hsp_month=task.hsp_month,
        demand_month_factor=task.demand_month_factor,
    )
    module = {
        "P_mod_W": cfg["P_mod_W"],
        "Voc25": cfg["Voc25"],
        "Vmp25": cfg["Vmp25"],
        "Isc": cfg["Isc"],
    }
    k_wp = task.k_wp
    inv_sel = select_inverter_and_strings(
        kWp=k_wp,
        module=module,
        Tmin_C=cfg["Tmin_C"],
        a_Voc_pct=cfg["a_Voc_pct"],
        inv_catalog=task.inv_catalog,
        ILR_target=(cfg["ILR_min"], cfg["ILR_max"]),
    )
    if inv_sel is None:
        return DeterministicScanTaskResult(task_index=task.task_index, detail_rows=())

    ok_peak, ratio = peak_ratio_ok(
        cfg,
        k_wp,
        inv_sel,
        task.solar_profile,
        task.hsp_month,
        task.demand_month_factor,
        dow24=task.demand_profile_7x24,
        day_w=task.day_weights,
    )
    if not ok_peak:
        return DeterministicScanTaskResult(task_index=task.task_index, detail_rows=())

    price_per_kwp_cop = _lookup_price_per_kwp(task.cop_kwp_table, k_wp, "Precios_kWp_relativos")
    if cfg["include_var_others"]:
        price_per_kwp_cop += _lookup_price_per_kwp(
            task.cop_kwp_table_others,
            k_wp,
            "Precios_kWp_relativos_Otros",
        )

    detail_rows: list[dict[str, Any]] = []
    island_mode = bool(cfg.get("island_mode", False))
    export_allowed_eff = bool(cfg["export_allowed"]) and not island_mode
    for batt in task.battery_options:
        battery = _build_battery(batt, cfg)
        system = PVSystem(
            kwp=k_wp,
            pr=cfg["PR"],
            hsp_month=task.hsp_month,
            solar_shape=task.solar_profile,
            inverter_ac_kw=inv_sel["inverter"]["AC_kW"],
            deg_rate=cfg.get("deg_rate", 0.0),
        )
        dispatch_cfg = DispatchConfig(
            inverter_ac_kw=inv_sel["inverter"]["AC_kW"],
            allow_import=not island_mode,
            allow_export=export_allowed_eff,
            export_limit_kw=(0.0 if not cfg["export_allowed"] else None),
            mode=("island" if island_mode else ("zero_export" if not cfg["export_allowed"] else "grid")),
        )
        sim_res = simulator.run(
            cfg=cfg,
            system=system,
            dispatch_cfg=dispatch_cfg,
            inv_sel=inv_sel,
            battery_sel=batt,
            battery=battery,
            years=cfg["years"],
            price_per_kwp_cop=price_per_kwp_cop,
            stochastic=False,
        )
        detail_rows.append(
            {
                "kWp": k_wp,
                "inv_sel": inv_sel,
                "battery": batt,
                "df": sim_res.monthly,
                "summary": sim_res.summary,
                "value": sim_res.summary["cum_disc_final"],
                "peak_ratio": ratio,
                "best_battery": False,
            }
        )
    return DeterministicScanTaskResult(task_index=task.task_index, detail_rows=tuple(detail_rows))


def _run_tasks_serial(tasks: tuple[DeterministicScanTask, ...]) -> tuple[dict[str, Any], ...]:
    results = [evaluate_deterministic_scan_task(task) for task in tasks]
    ordered = sorted(results, key=lambda item: item.task_index)
    return tuple(detail for result in ordered for detail in result.detail_rows)


def _run_tasks_parallel(tasks: tuple[DeterministicScanTask, ...], max_workers: int) -> tuple[dict[str, Any], ...]:
    mp_context = get_context("spawn")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=mp_context) as executor:
        results = list(executor.map(evaluate_deterministic_scan_task, tasks))
    ordered = sorted(results, key=lambda item: item.task_index)
    return tuple(detail for result in ordered for detail in result.detail_rows)


def run_deterministic_scan_tasks(
    config_bundle: LoadedConfigBundle,
    *,
    allow_parallel: bool = True,
    max_workers: int | None = None,
) -> tuple[float, tuple[dict[str, Any], ...]]:
    seed_kwp, tasks = _build_tasks(config_bundle)
    worker_count = _determine_max_workers(max_workers)
    if (
        not allow_parallel
        or worker_count <= 1
        or len(tasks) <= 1
        or bool(getattr(sys, "frozen", False))
    ):
        return seed_kwp, _run_tasks_serial(tasks)
    try:
        return seed_kwp, _run_tasks_parallel(tasks, max_workers=worker_count)
    except Exception:
        return seed_kwp, _run_tasks_serial(tasks)
