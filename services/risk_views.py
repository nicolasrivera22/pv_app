from __future__ import annotations

import numpy as np
import pandas as pd

from pv_product.utils import _kde_gauss, _silverman_bandwidth

from .types import MonteCarloRunResult, RiskViewBundle

HISTOGRAM_METRICS = ("NPV_COP", "payback_years")
KDE_METRICS = ("NPV_COP", "payback_years")
ECDF_METRICS = ("NPV_COP", "payback_years")
PERCENTILE_TABLE_METRICS = (
    ("npv", "NPV_COP"),
    ("payback_years", "payback_years"),
    ("self_consumption_ratio", "self_consumption_ratio"),
    ("self_sufficiency_ratio", "self_sufficiency_ratio"),
    ("annual_import_kwh", "annual_import_kwh"),
    ("annual_export_kwh", "annual_export_kwh"),
)


def _histogram_frame(samples: pd.DataFrame, metric: str, bins: int) -> pd.DataFrame:
    finite = pd.to_numeric(samples[metric], errors="coerce").dropna().to_numpy(dtype=float)
    if finite.size == 0:
        return pd.DataFrame(columns=["metric", "bin_left", "bin_right", "count", "probability"])

    bins = max(1, min(int(bins), finite.size))
    counts, edges = np.histogram(finite, bins=bins)
    total_count = max(len(samples), 1)
    return pd.DataFrame(
        {
            "metric": metric,
            "bin_left": edges[:-1],
            "bin_right": edges[1:],
            "count": counts.astype(int),
            "probability": counts / total_count,
        }
    )


def _ecdf_frame(samples: pd.DataFrame, metric: str, max_points: int) -> pd.DataFrame:
    finite = np.sort(pd.to_numeric(samples[metric], errors="coerce").dropna().to_numpy(dtype=float))
    if finite.size == 0:
        return pd.DataFrame(columns=["metric", "value", "cdf"])

    if finite.size <= max_points:
        probs = np.arange(1, finite.size + 1, dtype=float) / finite.size
        values = finite
    else:
        probs = np.linspace(1.0 / finite.size, 1.0, num=max_points, dtype=float)
        values = np.quantile(finite, probs, method="linear")

    return pd.DataFrame({"metric": metric, "value": values, "cdf": probs})


def _density_frame(samples: pd.DataFrame, metric: str, points: int = 240) -> pd.DataFrame:
    finite = np.sort(pd.to_numeric(samples[metric], errors="coerce").dropna().to_numpy(dtype=float))
    if finite.size < 2:
        return pd.DataFrame(columns=["metric", "value", "density"])

    vmin = float(np.min(finite))
    vmax = float(np.max(finite))
    pad = 0.1 * (vmax - vmin + 1e-12)
    x_grid = np.linspace(vmin - pad, vmax + pad, max(80, int(points)))
    bandwidth = _silverman_bandwidth(finite)
    density = _kde_gauss(x_grid, finite, bandwidth)
    return pd.DataFrame({"metric": metric, "value": x_grid, "density": density})


def _percentile_table(summary) -> pd.DataFrame:
    rows = []
    for attr_name, label in PERCENTILE_TABLE_METRICS:
        metric = getattr(summary, attr_name)
        rows.append(
            {
                "metric": label,
                "n_total": metric.n_total,
                "n_finite": metric.n_finite,
                "n_missing": metric.n_missing,
                "mean": metric.mean,
                "std": metric.std,
                "min": metric.min,
                "max": metric.max,
                "p5": metric.p5,
                "p10": metric.p10,
                "p25": metric.p25,
                "p50": metric.p50,
                "p75": metric.p75,
                "p90": metric.p90,
                "p95": metric.p95,
                "percentiles_over_finite_values": metric.percentiles_over_finite_values,
            }
        )
    return pd.DataFrame(rows)


def build_risk_views_from_samples(
    samples: pd.DataFrame,
    summary,
    *,
    histogram_bins: int = 40,
    ecdf_points: int = 201,
    labels: dict[str, str] | None = None,
) -> RiskViewBundle:
    histograms = {metric: _histogram_frame(samples, metric, histogram_bins) for metric in HISTOGRAM_METRICS}
    densities = {metric: _density_frame(samples, metric) for metric in KDE_METRICS}
    ecdfs = {metric: _ecdf_frame(samples, metric, ecdf_points) for metric in ECDF_METRICS}
    return RiskViewBundle(
        histogram_bins=int(histogram_bins),
        ecdf_points=int(ecdf_points),
        histograms=histograms,
        densities=densities,
        ecdfs=ecdfs,
        percentile_table=_percentile_table(summary),
        labels=dict(labels or {}),
    )


def prepare_risk_views(
    result: MonteCarloRunResult,
    *,
    histogram_bins: int = 40,
    ecdf_points: int = 201,
) -> RiskViewBundle:
    if result.samples is None:
        if result.views.histogram_bins == histogram_bins and result.views.ecdf_points == ecdf_points:
            return result.views
        raise ValueError(
            "El resultado no conserva muestras crudas. Ejecuta con return_samples=True para recalcular vistas con otros parámetros."
        )
    return build_risk_views_from_samples(
        result.samples,
        result.summary,
        histogram_bins=histogram_bins,
        ecdf_points=ecdf_points,
        labels=result.views.labels,
    )
