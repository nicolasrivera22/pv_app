from __future__ import annotations

from copy import deepcopy

import numpy as np
import pandas as pd

from pv_product.hardware import select_inverter_and_strings
from pv_product.utils import simulate_monthly_series_dow

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

MC_SUPPORTED_MODE = "fixed_candidate"
MONTE_CARLO_WARNING_THRESHOLD = 5000
MC_UNCERTAINTY_FIELDS = ("mc_PR_std", "mc_buy_std", "mc_sell_std", "mc_demand_std")


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


def _simulate_fixed_candidate_draws(
    config_bundle: LoadedConfigBundle,
    detail: dict,
    request: MonteCarloRunRequest,
    *,
    lang: str = "es",
) -> tuple[pd.DataFrame, dict[str, object]]:
    cfg = deepcopy(config_bundle.config)
    effective_detail = _resolve_effective_design(config_bundle, detail, lang=lang)
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

    rng = np.random.default_rng(request.seed)
    rows = []
    for simulation_index in range(request.n_simulations or 0):
        monthly, summary = simulate_monthly_series_dow(
            cfg=cfg,
            kWp=k_wp,
            inv_sel=effective_detail["inv_sel"],
            battery_sel=effective_detail["battery"],
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
                "candidate_key": effective_detail["candidate_key"],
                "kWp": k_wp,
                "battery": effective_detail["battery_name"],
                "NPV_COP": float(summary["cum_disc_final"]),
                "payback_years": summary["payback_years"],
                "self_consumption_ratio": float(energy["self_consumption_ratio"]),
                "self_sufficiency_ratio": float(energy["self_sufficiency_ratio"]),
                "annual_import_kwh": float(energy["annual_import_kwh"]),
                "annual_export_kwh": float(energy["annual_export_kwh"]),
            }
        )
    return pd.DataFrame(rows), effective_detail


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
    sample_frame, effective_detail = _simulate_fixed_candidate_draws(config_bundle, detail, request, lang=lang)
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
    return MonteCarloRunResult(
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
