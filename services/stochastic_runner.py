from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
import math
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import time

import numpy as np
import pandas as pd

from pv_product.hardware import select_inverter_and_strings
from pv_product.utils import simulate_monthly_series_dow

from . import execution_parallel
from .i18n import tr
from .result_views import battery_name_from_candidate, candidate_key_for, summarize_energy_metrics
from .risk_views import build_risk_views_from_samples
from .scenario_runner import run_scan
from .types import (
    LoadedConfigBundle,
    MetricDistributionSummary,
    MonteCarloRunRequest,
    MonteCarloRunResult,
    MonteCarloSummary,
    PercentileSummary,
    RiskMetricSummary,
    ScanRunResult,
)

logger = logging.getLogger(__name__)

MC_SUPPORTED_MODE = "fixed_candidate"
MONTE_CARLO_WARNING_THRESHOLD = 5000
MC_UNCERTAINTY_FIELDS = ("mc_PR_std", "mc_buy_std", "mc_sell_std", "mc_demand_std")
MC_PARALLEL_MIN_SIMULATIONS = 32
MC_MIN_CHUNK_SIZE = 8
MC_CHUNKS_PER_WORKER = 4


@dataclass(frozen=True)
class MonteCarloWorkerContext:
    simulation_cfg: dict[str, object]
    design_scalars: dict[str, object]
    selected_inverter: dict[str, float]
    selected_battery: dict[str, object]
    demand_profile_7x24: np.ndarray
    day_weights: np.ndarray
    solar_profile: np.ndarray
    hsp_month: np.ndarray
    demand_month_factor: np.ndarray


@dataclass(frozen=True)
class MonteCarloExecutionReport:
    requested_workers: int
    effective_workers: int
    worker_source: str
    serial_reason: str | None
    execution_mode: str
    frozen_runtime: bool
    frozen_parallel_opt_in: bool
    chunk_count: int
    chunk_size: int
    fallback_to_serial: bool = False
    fallback_reason: str | None = None


_MC_WORKER_CONTEXT: MonteCarloWorkerContext | None = None


def _format_log_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    if not text:
        return "-"
    if any(char.isspace() for char in text) or "=" in text:
        return repr(text)
    return text


def _structured_log_message(**fields) -> str:
    return " ".join(f"{key}={_format_log_value(value)}" for key, value in fields.items())


def _validate_non_negative_int(value, field: str, *, lang: str = "es") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if field == "seed":
            raise ValueError(tr("risk.error.invalid_seed", lang))
        raise ValueError(f"{field} must be a non-negative integer." if lang == "en" else f"{field} debe ser un entero no negativo.")
    if value < 0:
        if field == "seed":
            raise ValueError(tr("risk.error.invalid_seed", lang))
        raise ValueError(f"{field} must be a non-negative integer." if lang == "en" else f"{field} debe ser un entero no negativo.")
    return value


def _validate_positive_int(value, field: str, *, lang: str = "es") -> int:
    if isinstance(value, bool):
        if field == "n_simulations":
            raise ValueError(tr("risk.error.invalid_n_simulations", lang))
        raise ValueError(f"{field} must be a positive integer." if lang == "en" else f"{field} debe ser un entero positivo.")
    if isinstance(value, float):
        if not value.is_integer():
            if field == "n_simulations":
                raise ValueError(tr("risk.error.invalid_n_simulations", lang))
            raise ValueError(f"{field} must be a positive integer." if lang == "en" else f"{field} debe ser un entero positivo.")
        value = int(value)
    if not isinstance(value, int) or value <= 0:
        if field == "n_simulations":
            raise ValueError(tr("risk.error.invalid_n_simulations", lang))
        raise ValueError(f"{field} must be a positive integer." if lang == "en" else f"{field} debe ser un entero positivo.")
    return value


def _lookup_price_per_kwp(table: pd.DataFrame, k_wp: float, table_name: str, *, lang: str = "es") -> float:
    mask = (table["MIN"] < k_wp) & (table["MAX"] >= k_wp)
    matches = table.loc[mask, "PRECIO_POR_KWP"].values
    if len(matches) == 0:
        raise ValueError(tr("risk.error.price_band_missing", lang, kwp=float(k_wp), table_name=table_name))
    return float(matches[0])


def _validate_manual_k_wp(value, *, lang: str = "es") -> float:
    try:
        manual_k_wp = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(tr("risk.error.invalid_manual_kWp", lang)) from exc
    if not np.isfinite(manual_k_wp) or manual_k_wp <= 0:
        raise ValueError(tr("risk.error.invalid_manual_kWp", lang))
    return manual_k_wp


def _resolve_request(
    config_bundle: LoadedConfigBundle,
    selected_candidate_key: str | None,
    seed: int,
    n_simulations: int | None,
    return_samples: bool,
    mode: str,
    lang: str,
) -> tuple[MonteCarloRunRequest, int]:
    if mode != MC_SUPPORTED_MODE:
        raise ValueError(tr("risk.error.unsupported_mode", lang, mode=MC_SUPPORTED_MODE))
    if not selected_candidate_key:
        raise ValueError(tr("risk.error.no_candidate", lang))
    seed_value = _validate_non_negative_int(seed, "seed", lang=lang)
    if n_simulations is None:
        resolved_n = _validate_positive_int(config_bundle.config.get("mc_n_simulations", 0), "n_simulations", lang=lang)
    else:
        resolved_n = _validate_positive_int(n_simulations, "n_simulations", lang=lang)
    return (
        MonteCarloRunRequest(
            mode=mode,
            selected_candidate_key=selected_candidate_key,
            seed=seed_value,
            n_simulations=resolved_n,
            return_samples=bool(return_samples),
        ),
        resolved_n,
    )


def _resolve_baseline_scan(
    config_bundle: LoadedConfigBundle,
    baseline_scan: ScanRunResult | None,
) -> ScanRunResult:
    return baseline_scan if baseline_scan is not None else run_scan(config_bundle)


def _metric_summary(values) -> MetricDistributionSummary:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    n_total = int(array.size)
    n_finite = int(finite.size)
    n_missing = int(n_total - n_finite)

    if n_finite == 0:
        percentiles = PercentileSummary()
        return MetricDistributionSummary(
            n_total=n_total,
            n_finite=n_finite,
            n_missing=n_missing,
            mean=None,
            std=None,
            min=None,
            max=None,
            percentiles=percentiles,
            percentiles_over_finite_values=True,
        )

    pct = np.percentile(finite, [5, 10, 25, 50, 75, 90, 95])
    return MetricDistributionSummary(
        n_total=n_total,
        n_finite=n_finite,
        n_missing=n_missing,
        mean=float(np.mean(finite)),
        std=float(np.std(finite, ddof=0)),
        min=float(np.min(finite)),
        max=float(np.max(finite)),
        percentiles=PercentileSummary(
            p5=float(pct[0]),
            p10=float(pct[1]),
            p25=float(pct[2]),
            p50=float(pct[3]),
            p75=float(pct[4]),
            p90=float(pct[5]),
            p95=float(pct[6]),
        ),
        percentiles_over_finite_values=True,
    )


def _summarize_samples(sample_frame: pd.DataFrame) -> tuple[MonteCarloSummary, RiskMetricSummary]:
    npv = _metric_summary(sample_frame["NPV_COP"])
    payback = _metric_summary(sample_frame["payback_years"])
    self_consumption = _metric_summary(sample_frame["self_consumption_ratio"])
    self_sufficiency = _metric_summary(sample_frame["self_sufficiency_ratio"])
    annual_import = _metric_summary(sample_frame["annual_import_kwh"])
    annual_export = _metric_summary(sample_frame["annual_export_kwh"])

    risk_metrics = RiskMetricSummary(
        probability_negative_npv=float((pd.to_numeric(sample_frame["NPV_COP"], errors="coerce") < 0).fillna(False).mean()),
        probability_payback_within_horizon=float(pd.to_numeric(sample_frame["payback_years"], errors="coerce").notna().mean()),
    )
    summary = MonteCarloSummary(
        npv=npv,
        payback_years=payback,
        self_consumption_ratio=self_consumption,
        self_sufficiency_ratio=self_sufficiency,
        annual_import_kwh=annual_import,
        annual_export_kwh=annual_export,
    )
    return summary, risk_metrics


def summarize_monte_carlo(result: MonteCarloRunResult) -> MonteCarloSummary:
    return result.summary


def _resolve_effective_design(
    config_bundle: LoadedConfigBundle,
    detail: dict,
    *,
    lang: str = "es",
) -> dict[str, object]:
    cfg = deepcopy(config_bundle.config)
    k_wp = float(detail["kWp"])
    inv_sel = deepcopy(detail["inv_sel"])
    if bool(cfg.get("mc_use_manual_kWp")):
        manual_k_wp = _validate_manual_k_wp(cfg.get("mc_manual_kWp"), lang=lang)
        n_mod = max(1, int(round(manual_k_wp * 1000.0 / float(cfg["P_mod_W"]))))
        k_wp = n_mod * float(cfg["P_mod_W"]) / 1000.0
        manual_inv_sel = select_inverter_and_strings(
            kWp=k_wp,
            module={
                "P_mod_W": cfg["P_mod_W"],
                "Voc25": cfg["Voc25"],
                "Vmp25": cfg["Vmp25"],
                "Isc": cfg["Isc"],
            },
            Tmin_C=cfg["Tmin_C"],
            a_Voc_pct=cfg["a_Voc_pct"],
            inv_catalog=config_bundle.inverter_catalog,
            ILR_target=(cfg["ILR_min"], cfg["ILR_max"]),
        )
        if manual_inv_sel is not None:
            inv_sel = deepcopy(manual_inv_sel)

    battery = deepcopy(detail["battery"])
    manual_battery_name = str(cfg.get("mc_battery_name", "") or "").strip()
    if manual_battery_name:
        battery_names = config_bundle.battery_catalog.get("name", pd.Series(dtype=object)).astype(str)
        matches = config_bundle.battery_catalog.loc[battery_names == manual_battery_name]
        if not matches.empty:
            battery = matches.iloc[0].to_dict()

    battery_name = battery_name_from_candidate(battery)
    return {
        "candidate_key": candidate_key_for(k_wp, battery_name),
        "kWp": k_wp,
        "inv_sel": inv_sel,
        "battery": battery,
        "battery_name": battery_name,
    }


def _compact_selected_inverter(inv_sel: dict) -> dict[str, float]:
    inverter = dict(inv_sel.get("inverter", {}) if isinstance(inv_sel, dict) else {})
    return {
        "AC_kW": float(inverter.get("AC_kW", 0.0) or 0.0),
        "price_COP": float(inverter.get("price_COP", 0.0) or 0.0),
    }


def _compact_selected_battery(battery: dict | None) -> dict[str, object]:
    source = dict(battery or {})
    max_kw = float(source.get("max_kW", 0.0) or 0.0)
    return {
        "name": str(source.get("name", "BAT-0")),
        "nom_kWh": float(source.get("nom_kWh", 0.0) or 0.0),
        "max_ch_kW": float(source.get("max_ch_kW", max_kw) or 0.0),
        "max_dis_kW": float(source.get("max_dis_kW", max_kw) or 0.0),
        "max_kW": max_kw,
        "price_COP": float(source.get("price_COP", 0.0) or 0.0),
    }


def _build_monte_carlo_worker_context(
    config_bundle: LoadedConfigBundle,
    effective_detail: dict[str, object],
    *,
    lang: str = "es",
) -> MonteCarloWorkerContext:
    cfg = deepcopy(config_bundle.config)
    k_wp = float(effective_detail["kWp"])
    price_per_kwp_cop = _lookup_price_per_kwp(
        config_bundle.cop_kwp_table,
        k_wp,
        "Precios_kWp_relativos",
        lang=lang,
    )
    if cfg.get("include_var_others"):
        price_per_kwp_cop += _lookup_price_per_kwp(
            config_bundle.cop_kwp_table_others,
            k_wp,
            "Precios_kWp_relativos_Otros",
            lang=lang,
        )

    return MonteCarloWorkerContext(
        simulation_cfg={
            "PR": float(cfg["PR"]),
            "deg_rate": float(cfg.get("deg_rate", 0.0) or 0.0),
            "bat_DoD": float(cfg["bat_DoD"]),
            "bat_eta_rt": float(cfg["bat_eta_rt"]),
            "bat_coupling": str(cfg.get("bat_coupling", "ac")),
            "island_mode": bool(cfg.get("island_mode", False)),
            "g_tar_buy": float(cfg["g_tar_buy"]),
            "g_tar_sell": float(cfg["g_tar_sell"]),
            "discount_rate": float(cfg["discount_rate"]),
            "buy_tariff_COP_kWh": float(cfg["buy_tariff_COP_kWh"]),
            "sell_tariff_COP_kWh": float(cfg["sell_tariff_COP_kWh"]),
            "pricing_mode": str(cfg["pricing_mode"]),
            "price_total_COP": float(cfg["price_total_COP"]),
            "include_hw_in_price": bool(cfg["include_hw_in_price"]),
            "price_others_total": float(cfg["price_others_total"]),
            "soc_week_steady": bool(cfg.get("soc_week_steady", True)),
            "soc_iter_tol_kWh": float(cfg.get("soc_iter_tol_kWh", 1e-3) or 1e-3),
            "soc_iter_max": int(cfg.get("soc_iter_max", 10) or 10),
            "mc_PR_std": float(cfg.get("mc_PR_std", 0.0) or 0.0),
            "mc_buy_std": float(cfg.get("mc_buy_std", 0.0) or 0.0),
            "mc_sell_std": float(cfg.get("mc_sell_std", 0.0) or 0.0),
            "mc_demand_std": float(cfg.get("mc_demand_std", 0.0) or 0.0),
            "E_month_kWh": float(cfg["E_month_kWh"]),
            "years": int(cfg["years"]),
        },
        design_scalars={
            "candidate_key": str(effective_detail["candidate_key"]),
            "battery_name": str(effective_detail["battery_name"]),
            "kWp": k_wp,
            "export_allowed": bool(cfg["export_allowed"]),
            "price_per_kwp_cop": float(price_per_kwp_cop),
        },
        selected_inverter=_compact_selected_inverter(dict(effective_detail["inv_sel"])),
        selected_battery=_compact_selected_battery(
            effective_detail["battery"] if isinstance(effective_detail.get("battery"), dict) else None
        ),
        demand_profile_7x24=np.asarray(config_bundle.demand_profile_7x24, dtype=float),
        day_weights=np.asarray(config_bundle.day_weights, dtype=float),
        solar_profile=np.asarray(config_bundle.solar_profile, dtype=float),
        hsp_month=np.asarray(config_bundle.hsp_month, dtype=float),
        demand_month_factor=np.asarray(config_bundle.demand_month_factor, dtype=float),
    )


def _resolve_monte_carlo_execution_report(
    *,
    n_simulations: int,
    max_workers: int | None,
) -> MonteCarloExecutionReport:
    decision = execution_parallel.resolve_parallel_worker_decision(
        allow_parallel=True,
        task_count=n_simulations,
        max_workers=max_workers,
        primary_env_var="PV_MC_MAX_WORKERS",
        fallback_env_var="PV_SCAN_MAX_WORKERS",
    )
    serial_reason = decision.serial_reason
    execution_mode = decision.execution_mode
    effective_workers = decision.effective_workers
    chunk_count = 1
    chunk_size = n_simulations

    if serial_reason is None and n_simulations < MC_PARALLEL_MIN_SIMULATIONS:
        serial_reason = "below_parallel_threshold"
        execution_mode = "serial"
        effective_workers = 1
    elif serial_reason is None:
        effective_workers = min(decision.effective_workers, n_simulations)
        chunk_count = max(
            1,
            min(
                effective_workers * MC_CHUNKS_PER_WORKER,
                math.ceil(n_simulations / MC_MIN_CHUNK_SIZE),
            ),
        )
        chunk_size = max(1, math.ceil(n_simulations / chunk_count))

    return MonteCarloExecutionReport(
        requested_workers=decision.requested_workers,
        effective_workers=effective_workers,
        worker_source=decision.worker_source,
        serial_reason=serial_reason,
        execution_mode=execution_mode,
        frozen_runtime=decision.frozen_runtime,
        frozen_parallel_opt_in=decision.frozen_parallel_opt_in,
        chunk_count=chunk_count,
        chunk_size=chunk_size,
    )


def _chunk_tasks(n_simulations: int, chunk_size: int, base_seed: int) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (start_index, min(start_index + chunk_size, n_simulations), base_seed)
        for start_index in range(0, n_simulations, chunk_size)
    )


def _initialize_monte_carlo_worker(worker_context: MonteCarloWorkerContext) -> None:
    global _MC_WORKER_CONTEXT
    _MC_WORKER_CONTEXT = worker_context


def _rng_for_simulation(base_seed: int, simulation_index: int):
    """Return a per-simulation RNG.

    The serial and parallel paths both use independent deterministic substreams
    keyed by `simulation_index`. This keeps the new implementation invariant to
    scheduling and worker count, but it may not match the legacy serial stream
    bit by bit because the legacy code consumed one shared RNG sequentially.
    """

    child_seed = np.random.SeedSequence(int(base_seed), spawn_key=(int(simulation_index),))
    return np.random.default_rng(child_seed)


def _simulate_monte_carlo_row(
    worker_context: MonteCarloWorkerContext,
    *,
    simulation_index: int,
    base_seed: int,
) -> tuple[int, float, object, float, float, float, float]:
    rng = _rng_for_simulation(base_seed, simulation_index)
    monthly, summary = simulate_monthly_series_dow(
        cfg=worker_context.simulation_cfg,
        kWp=float(worker_context.design_scalars["kWp"]),
        inv_sel={"inverter": worker_context.selected_inverter},
        battery_sel=worker_context.selected_battery,
        export_allowed=bool(worker_context.design_scalars["export_allowed"]),
        years=int(worker_context.simulation_cfg["years"]),
        dow24=worker_context.demand_profile_7x24,
        day_w=worker_context.day_weights,
        s24=worker_context.solar_profile,
        hsp_month=worker_context.hsp_month,
        PR_month_std=float(worker_context.simulation_cfg["mc_PR_std"]),
        buy_month_offset_std=float(worker_context.simulation_cfg["mc_buy_std"]),
        sell_month_offset_std=float(worker_context.simulation_cfg["mc_sell_std"]),
        demand_month_offset_std=float(worker_context.simulation_cfg["mc_demand_std"]),
        rng=rng,
        demand_month_factor=worker_context.demand_month_factor,
        price_per_kwp_cop=float(worker_context.design_scalars["price_per_kwp_cop"]),
    )
    energy = summarize_energy_metrics(monthly)
    return (
        int(simulation_index),
        float(summary["cum_disc_final"]),
        summary["payback_years"],
        float(energy["self_consumption_ratio"]),
        float(energy["self_sufficiency_ratio"]),
        float(energy["annual_import_kwh"]),
        float(energy["annual_export_kwh"]),
    )


def _simulate_chunk_rows(
    worker_context: MonteCarloWorkerContext,
    *,
    start_index: int,
    stop_index: int,
    base_seed: int,
) -> tuple[tuple[int, float, object, float, float, float, float], ...]:
    return tuple(
        _simulate_monte_carlo_row(
            worker_context,
            simulation_index=simulation_index,
            base_seed=base_seed,
        )
        for simulation_index in range(start_index, stop_index)
    )


def _run_monte_carlo_chunk(task: tuple[int, int, int]) -> tuple[tuple[int, float, object, float, float, float, float], ...]:
    worker_context = _MC_WORKER_CONTEXT
    if worker_context is None:
        raise RuntimeError("Monte Carlo worker context has not been initialized.")
    start_index, stop_index, base_seed = task
    return _simulate_chunk_rows(
        worker_context,
        start_index=start_index,
        stop_index=stop_index,
        base_seed=base_seed,
    )


def _run_monte_carlo_chunks_serial(
    chunk_tasks: tuple[tuple[int, int, int], ...],
    worker_context: MonteCarloWorkerContext,
) -> tuple[tuple[tuple[int, float, object, float, float, float, float], ...], ...]:
    return tuple(
        _simulate_chunk_rows(
            worker_context,
            start_index=start_index,
            stop_index=stop_index,
            base_seed=base_seed,
        )
        for start_index, stop_index, base_seed in chunk_tasks
    )


def _run_monte_carlo_chunks_parallel(
    chunk_tasks: tuple[tuple[int, int, int], ...],
    worker_context: MonteCarloWorkerContext,
    *,
    max_workers: int,
) -> tuple[tuple[tuple[int, float, object, float, float, float, float], ...], ...]:
    mp_context = get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=mp_context,
        initializer=_initialize_monte_carlo_worker,
        initargs=(worker_context,),
    ) as executor:
        chunk_rows = list(executor.map(_run_monte_carlo_chunk, chunk_tasks))
    return tuple(chunk_rows)


def _rows_to_sample_frame(
    chunk_rows: tuple[tuple[tuple[int, float, object, float, float, float, float], ...], ...],
    effective_detail: dict[str, object],
) -> pd.DataFrame:
    columns = [
        "simulation_index",
        "NPV_COP",
        "payback_years",
        "self_consumption_ratio",
        "self_sufficiency_ratio",
        "annual_import_kwh",
        "annual_export_kwh",
    ]
    flattened_rows = sorted((row for chunk in chunk_rows for row in chunk), key=lambda item: item[0])
    frame = pd.DataFrame(flattened_rows, columns=columns)
    frame.insert(1, "candidate_key", str(effective_detail["candidate_key"]))
    frame.insert(2, "kWp", float(effective_detail["kWp"]))
    frame.insert(3, "battery", str(effective_detail["battery_name"]))
    return frame


def _simulate_fixed_candidate_draws(
    config_bundle: LoadedConfigBundle,
    detail: dict,
    request: MonteCarloRunRequest,
    *,
    lang: str = "es",
) -> tuple[pd.DataFrame, dict[str, object], MonteCarloExecutionReport]:
    effective_detail = _resolve_effective_design(config_bundle, detail, lang=lang)
    worker_context = _build_monte_carlo_worker_context(config_bundle, effective_detail, lang=lang)
    execution_report = _resolve_monte_carlo_execution_report(
        n_simulations=int(request.n_simulations or 0),
        max_workers=None,
    )
    chunk_tasks = _chunk_tasks(
        int(request.n_simulations or 0),
        int(execution_report.chunk_size or 1),
        int(request.seed),
    )

    if execution_report.execution_mode == "serial":
        chunk_rows = _run_monte_carlo_chunks_serial(chunk_tasks, worker_context)
        return _rows_to_sample_frame(chunk_rows, effective_detail), effective_detail, execution_report

    try:
        chunk_rows = _run_monte_carlo_chunks_parallel(
            chunk_tasks,
            worker_context,
            max_workers=execution_report.effective_workers,
        )
    except Exception as exc:
        logger.exception(
            _structured_log_message(
                event="monte_carlo_parallel_fallback",
                n_simulations=request.n_simulations,
                requested_workers=execution_report.requested_workers,
                effective_workers=1,
                worker_source=execution_report.worker_source,
                chunk_count=execution_report.chunk_count,
                chunk_size=execution_report.chunk_size,
                frozen_runtime=execution_report.frozen_runtime,
                frozen_parallel_opt_in=execution_report.frozen_parallel_opt_in,
                fallback_reason="parallel_exception",
                exc_class=type(exc).__name__,
                exc_message=str(exc),
            )
        )
        fallback_report = MonteCarloExecutionReport(
            requested_workers=execution_report.requested_workers,
            effective_workers=1,
            worker_source=execution_report.worker_source,
            serial_reason="parallel_exception",
            execution_mode="serial",
            frozen_runtime=execution_report.frozen_runtime,
            frozen_parallel_opt_in=execution_report.frozen_parallel_opt_in,
            chunk_count=execution_report.chunk_count,
            chunk_size=execution_report.chunk_size,
            fallback_to_serial=True,
            fallback_reason="parallel_exception",
        )
        chunk_rows = _run_monte_carlo_chunks_serial(chunk_tasks, worker_context)
        return _rows_to_sample_frame(chunk_rows, effective_detail), effective_detail, fallback_report

    return _rows_to_sample_frame(chunk_rows, effective_detail), effective_detail, execution_report


def run_monte_carlo(
    config_bundle: LoadedConfigBundle,
    *,
    selected_candidate_key: str | None = None,
    seed: int = 0,
    n_simulations: int | None = None,
    return_samples: bool = False,
    baseline_scan: ScanRunResult | None = None,
    mode: str = MC_SUPPORTED_MODE,
    lang: str = "es",
) -> MonteCarloRunResult:
    started_at = time.perf_counter()
    request, resolved_n = _resolve_request(
        config_bundle,
        selected_candidate_key=selected_candidate_key,
        seed=seed,
        n_simulations=n_simulations,
        return_samples=return_samples,
        mode=mode,
        lang=lang,
    )
    baseline = _resolve_baseline_scan(config_bundle, baseline_scan)
    if request.selected_candidate_key not in baseline.candidate_details:
        raise ValueError(tr("risk.error.design_missing_in_scan", lang))

    detail = baseline.candidate_details[request.selected_candidate_key]
    sample_frame, effective_detail, execution_report = _simulate_fixed_candidate_draws(config_bundle, detail, request, lang=lang)
    summary, risk_metrics = _summarize_samples(sample_frame)

    warnings: list[str] = []
    if resolved_n > MONTE_CARLO_WARNING_THRESHOLD:
        warnings.append(
            tr("risk.warning.large_run", lang, count=resolved_n, threshold=MONTE_CARLO_WARNING_THRESHOLD)
        )
    if summary.payback_years.n_finite == 0:
        warnings.append(tr("risk.warning.no_payback", lang))

    labels = {
        "candidate_key": str(effective_detail["candidate_key"]),
        "battery": str(effective_detail["battery_name"]),
        "kWp": f"{float(effective_detail['kWp']):.3f}",
        "mode": request.mode,
    }
    views = build_risk_views_from_samples(sample_frame, summary, labels=labels)
    active_uncertainty = {field: float(config_bundle.config.get(field, 0.0) or 0.0) for field in MC_UNCERTAINTY_FIELDS}
    samples = sample_frame if request.return_samples else None
    result = MonteCarloRunResult(
        request=request,
        seed=request.seed,
        n_simulations=resolved_n,
        selected_candidate_key=detail["candidate_key"],
        baseline_best_candidate_key=baseline.best_candidate_key,
        selected_kWp=float(effective_detail["kWp"]),
        selected_battery=str(effective_detail["battery_name"]),
        active_uncertainty=active_uncertainty,
        warnings=tuple(warnings),
        summary=summary,
        risk_metrics=risk_metrics,
        views=views,
        samples=samples,
    )
    total_ms = (time.perf_counter() - started_at) * 1000.0
    logger.info(
        _structured_log_message(
            event="monte_carlo_run",
            total_ms=f"{total_ms:.1f}",
            n_simulations=resolved_n,
            execution_mode=execution_report.execution_mode,
            requested_workers=execution_report.requested_workers,
            effective_workers=execution_report.effective_workers,
            worker_source=execution_report.worker_source,
            chunk_count=execution_report.chunk_count,
            chunk_size=execution_report.chunk_size,
            frozen_runtime=execution_report.frozen_runtime,
            frozen_parallel_opt_in=execution_report.frozen_parallel_opt_in,
            serial_reason=execution_report.serial_reason,
            fallback_to_serial=execution_report.fallback_to_serial,
            fallback_reason=execution_report.fallback_reason,
        )
    )
    return result
