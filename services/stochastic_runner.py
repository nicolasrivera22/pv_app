from __future__ import annotations

from copy import deepcopy

import numpy as np
import pandas as pd

from pv_product.utils import simulate_monthly_series_dow

from .result_views import summarize_energy_metrics
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

MC_SUPPORTED_MODE = "fixed_candidate"
MONTE_CARLO_WARNING_THRESHOLD = 5000
MC_UNCERTAINTY_FIELDS = ("mc_PR_std", "mc_buy_std", "mc_sell_std", "mc_demand_std")


def _validate_non_negative_int(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} debe ser un entero no negativo.")
    if value < 0:
        raise ValueError(f"{field} debe ser un entero no negativo.")
    return value


def _validate_positive_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} debe ser un entero positivo.")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field} debe ser un entero positivo.")
        value = int(value)
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} debe ser un entero positivo.")
    return value


def _lookup_price_per_kwp(table: pd.DataFrame, k_wp: float, table_name: str) -> float:
    mask = (table["MIN"] < k_wp) & (table["MAX"] >= k_wp)
    matches = table.loc[mask, "PRECIO_POR_KWP"].values
    if len(matches) == 0:
        raise ValueError(f"No hay banda de precio en '{table_name}' para {k_wp:.3f} kWp.")
    return float(matches[0])


def _resolve_request(
    config_bundle: LoadedConfigBundle,
    selected_candidate_key: str | None,
    seed: int,
    n_simulations: int | None,
    return_samples: bool,
    mode: str,
) -> tuple[MonteCarloRunRequest, int]:
    if mode != MC_SUPPORTED_MODE:
        raise ValueError(f"El modo '{mode}' aún no está soportado en 2B.1. Usa '{MC_SUPPORTED_MODE}'.")
    if not selected_candidate_key:
        raise ValueError("selected_candidate_key es obligatorio para Monte Carlo de candidato fijo.")
    seed_value = _validate_non_negative_int(seed, "seed")
    if n_simulations is None:
        resolved_n = _validate_positive_int(config_bundle.config.get("mc_n_simulations", 0), "n_simulations")
    else:
        resolved_n = _validate_positive_int(n_simulations, "n_simulations")
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


def _simulate_fixed_candidate_draws(
    config_bundle: LoadedConfigBundle,
    detail: dict,
    request: MonteCarloRunRequest,
) -> pd.DataFrame:
    cfg = deepcopy(config_bundle.config)
    k_wp = float(detail["kWp"])
    price_per_kwp_cop = _lookup_price_per_kwp(
        config_bundle.cop_kwp_table,
        k_wp,
        "Precios_kWp_relativos",
    )
    if cfg.get("include_var_others"):
        price_per_kwp_cop += _lookup_price_per_kwp(
            config_bundle.cop_kwp_table_others,
            k_wp,
            "Precios_kWp_relativos_Otros",
        )

    rng = np.random.default_rng(request.seed)
    rows = []
    for simulation_index in range(request.n_simulations or 0):
        monthly, summary = simulate_monthly_series_dow(
            cfg=cfg,
            kWp=k_wp,
            inv_sel=detail["inv_sel"],
            battery_sel=detail["battery"],
            export_allowed=bool(cfg["export_allowed"]),
            years=int(cfg["years"]),
            dow24=config_bundle.demand_profile_7x24,
            day_w=config_bundle.day_weights,
            s24=config_bundle.solar_profile,
            hsp_month=config_bundle.hsp_month,
            PR_month_std=float(cfg.get("mc_PR_std", 0.0) or 0.0),
            buy_month_offset_std=float(cfg.get("mc_buy_std", 0.0) or 0.0),
            sell_month_offset_std=float(cfg.get("mc_sell_std", 0.0) or 0.0),
            demand_month_offset_std=float(cfg.get("mc_demand_std", 0.0) or 0.0),
            rng=rng,
            demand_month_factor=config_bundle.demand_month_factor,
            price_per_kwp_cop=price_per_kwp_cop,
        )
        energy = summarize_energy_metrics(monthly)
        rows.append(
            {
                "simulation_index": simulation_index,
                "candidate_key": detail["candidate_key"],
                "kWp": k_wp,
                "battery": detail["battery_name"],
                "NPV_COP": float(summary["cum_disc_final"]),
                "payback_years": summary["payback_years"],
                "self_consumption_ratio": float(energy["self_consumption_ratio"]),
                "self_sufficiency_ratio": float(energy["self_sufficiency_ratio"]),
                "annual_import_kwh": float(energy["annual_import_kwh"]),
                "annual_export_kwh": float(energy["annual_export_kwh"]),
            }
        )
    return pd.DataFrame(rows)


def run_monte_carlo(
    config_bundle: LoadedConfigBundle,
    *,
    selected_candidate_key: str | None = None,
    seed: int = 0,
    n_simulations: int | None = None,
    return_samples: bool = False,
    baseline_scan: ScanRunResult | None = None,
    mode: str = MC_SUPPORTED_MODE,
) -> MonteCarloRunResult:
    request, resolved_n = _resolve_request(
        config_bundle,
        selected_candidate_key=selected_candidate_key,
        seed=seed,
        n_simulations=n_simulations,
        return_samples=return_samples,
        mode=mode,
    )
    baseline = _resolve_baseline_scan(config_bundle, baseline_scan)
    if request.selected_candidate_key not in baseline.candidate_details:
        raise ValueError(f"No existe el candidato '{request.selected_candidate_key}' en el escaneo determinístico.")

    detail = baseline.candidate_details[request.selected_candidate_key]
    sample_frame = _simulate_fixed_candidate_draws(config_bundle, detail, request)
    summary, risk_metrics = _summarize_samples(sample_frame)

    warnings: list[str] = []
    if resolved_n > MONTE_CARLO_WARNING_THRESHOLD:
        warnings.append(
            f"n_simulations={resolved_n} supera el umbral recomendado de {MONTE_CARLO_WARNING_THRESHOLD}; conserva solo vistas compactas si no necesitas muestras crudas."
        )
    if summary.payback_years.n_finite == 0:
        warnings.append("Ninguna simulación alcanzó payback dentro del horizonte del proyecto.")

    labels = {
        "candidate_key": detail["candidate_key"],
        "battery": detail["battery_name"],
        "kWp": f"{float(detail['kWp']):.3f}",
        "mode": request.mode,
    }
    views = build_risk_views_from_samples(sample_frame, summary, labels=labels)
    active_uncertainty = {field: float(config_bundle.config.get(field, 0.0) or 0.0) for field in MC_UNCERTAINTY_FIELDS}
    samples = sample_frame if request.return_samples else None
    return MonteCarloRunResult(
        request=request,
        seed=request.seed,
        n_simulations=resolved_n,
        selected_candidate_key=detail["candidate_key"],
        baseline_best_candidate_key=baseline.best_candidate_key,
        selected_kWp=float(detail["kWp"]),
        selected_battery=str(detail["battery_name"]),
        active_uncertainty=active_uncertainty,
        warnings=tuple(warnings),
        summary=summary,
        risk_metrics=risk_metrics,
        views=views,
        samples=samples,
    )
