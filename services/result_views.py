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

from .candidate_financials import (
    CandidateFinancialSnapshot,
    CandidateFinancialSnapshotUnavailableError,
    attach_candidate_financial_snapshot,
    attach_candidate_financial_snapshots,
    build_snapshot_monthly_frame,
    resolve_financial_candidate_key,
    snapshot_npv_at_horizon,
    snapshot_project_summary,
    validate_candidate_financial_snapshot,
)
from .i18n import tr
from .types import ScenarioRecord, ScenarioSessionState
from .ui_schema import format_metric, metric_label


MONTH_ABBREVIATIONS = {
    "es": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}
MONTHS_PER_YEAR = 12

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
CLICK_ROLE_NPV_CURVE = "npv_curve"
CLICK_ROLE_PAYBACK_CURVE = "payback_curve"
CLICK_ROLE_SELECTED_OVERLAY = "selected_overlay"
CLICK_ROLE_BEST_OVERLAY = "best_overlay"
EXPLORER_SUBSET_MODE_OPTIMAL = "optimal"
EXPLORER_SUBSET_MODE_BATTERY = "battery"
EXPLORER_SUBSET_KEY_OPTIMAL = "optimal"
EXPLORER_SUBSET_KEY_NO_BATTERY = "battery:none"
CLICK_POINT_ROLE_PRIORITY = {
    CLICK_ROLE_NPV_CURVE: 0,
    CLICK_ROLE_PAYBACK_CURVE: 1,
    CLICK_ROLE_BEST_OVERLAY: 2,
    CLICK_ROLE_SELECTED_OVERLAY: 3,
}


def candidate_key_for(k_wp: float, battery_name: str) -> str:
    return f"{k_wp:.3f}::{battery_name}"


def battery_name_from_candidate(battery: dict | None) -> str:
    if battery is None or float(battery.get("nom_kWh", 0) or 0) <= 0:
        return "None"
    return str(battery.get("name", "Battery"))


def calculate_self_consumption_ratio(monthly: pd.DataFrame) -> float:
    first_year = monthly.iloc[:MONTHS_PER_YEAR]
    consumed = first_year.get("PV_a_Carga_kWh", 0).sum() + first_year.get("Bateria_a_Carga_kWh", 0).sum()
    demand = first_year.get("Demanda_kWh", 0).sum()
    return float(consumed / demand) if demand else 0.0


def calculate_self_sufficiency_ratio(monthly: pd.DataFrame) -> float:
    first_year = monthly.iloc[:MONTHS_PER_YEAR]
    demand = first_year.get("Demanda_kWh", 0).sum()
    imports = first_year.get("Importacion_Red_kWh", 0).sum()
    return float(1.0 - (imports / demand)) if demand else 0.0


def summarize_energy_metrics(monthly: pd.DataFrame) -> dict[str, float]:
    first_year = monthly.iloc[:MONTHS_PER_YEAR]
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


def _available_horizon_years(monthly: pd.DataFrame) -> int:
    if not isinstance(monthly, pd.DataFrame) or monthly.empty:
        return 1
    return max(1, (len(monthly) + MONTHS_PER_YEAR - 1) // MONTHS_PER_YEAR)


def _normalize_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized if pd.notna(normalized) else None


def _normalize_optional_int(value: Any) -> int | None:
    normalized = _normalize_optional_float(value)
    if normalized is None:
        return None
    return int(normalized)


def _normalize_payback_years(value: Any) -> float | None:
    normalized = _normalize_optional_float(value)
    if normalized is None or normalized < 0:
        return None
    return normalized


def _normalize_payback_month(value: Any) -> int | None:
    normalized = _normalize_optional_int(value)
    if normalized is None or normalized <= 0:
        return None
    return normalized


def _snapshot_from_detail(detail: dict[str, Any]) -> CandidateFinancialSnapshot | None:
    snapshot = detail.get("financial_snapshot")
    return snapshot if isinstance(snapshot, CandidateFinancialSnapshot) else None


def build_candidate_project_summary(
    detail: dict[str, Any],
    *,
    require_financial_snapshot: bool = False,
) -> dict[str, Any]:
    snapshot = _snapshot_from_detail(detail)
    if snapshot is not None:
        return snapshot_project_summary(snapshot)
    if require_financial_snapshot:
        candidate_key = str(detail.get("candidate_key") or "<missing>")
        raise CandidateFinancialSnapshotUnavailableError(
            f"Candidato '{candidate_key}': se requiere CandidateFinancialSnapshot para construir project_summary."
        )
    # Compatibility-only fallback for snapshot-less helpers. Live scenario-backed paths must set require_financial_snapshot=True.
    summary = dict(detail.get("summary") or {})
    summary["cum_disc_final"] = _normalize_optional_float(summary.get("cum_disc_final"))
    summary["capex_client"] = _normalize_optional_float(summary.get("capex_client"))
    summary["payback_years"] = _normalize_payback_years(summary.get("payback_years"))
    summary["payback_month"] = _normalize_payback_month(summary.get("payback_month"))
    return summary


def _coerce_visible_horizon_years(value: Any, *, default: int = 1, max_years: int | None = None) -> int:
    try:
        resolved = int(float(value))
    except (TypeError, ValueError):
        resolved = default
    resolved = max(0, resolved)
    if max_years is not None:
        resolved = min(resolved, max_years)
    return resolved


def visible_financial_metric_key(horizon_years: Any) -> str:
    return "capex_client" if _coerce_visible_horizon_years(horizon_years, default=1) == 0 else "NPV_COP"


def _display_metric_prefers_lower_value(metric_key: str) -> bool:
    return metric_key == "capex_client"


def summarize_candidate_for_horizon(
    detail: dict[str, Any],
    horizon_years: int,
    *,
    require_financial_snapshot: bool = False,
) -> dict[str, Any]:
    snapshot = _snapshot_from_detail(detail)
    monthly = detail.get("monthly")
    project_summary = build_candidate_project_summary(detail, require_financial_snapshot=require_financial_snapshot)
    display_metric_key = visible_financial_metric_key(horizon_years)
    if display_metric_key == "capex_client":
        return {
            "horizon_years": 0,
            "horizon_months": 0,
            "NPV_COP": None,
            "display_metric_key": display_metric_key,
            "display_value_COP": project_summary.get("capex_client"),
        }
    if snapshot is not None:
        effective_years, horizon_months, npv_value = snapshot_npv_at_horizon(snapshot, horizon_years)
        return {
            "horizon_years": effective_years,
            "horizon_months": horizon_months,
            "NPV_COP": npv_value,
            "display_metric_key": "NPV_COP",
            "display_value_COP": npv_value,
        }
    if require_financial_snapshot:
        candidate_key = str(detail.get("candidate_key") or "<missing>")
        raise CandidateFinancialSnapshotUnavailableError(
            f"Candidato '{candidate_key}': se requiere CandidateFinancialSnapshot para resumir el horizonte visible."
        )
    # Compatibility-only fallback for snapshot-less helpers. Live scenario-backed paths must set require_financial_snapshot=True.
    if not isinstance(monthly, pd.DataFrame) or monthly.empty or "NPV_COP" not in monthly.columns:
        effective_years = _coerce_visible_horizon_years(horizon_years, default=1)
        return {
            "horizon_years": effective_years,
            "horizon_months": 0,
            "NPV_COP": project_summary.get("cum_disc_final"),
            "display_metric_key": "NPV_COP",
            "display_value_COP": project_summary.get("cum_disc_final"),
        }

    max_years = _available_horizon_years(monthly)
    effective_years = _coerce_visible_horizon_years(horizon_years, default=max_years, max_years=max_years)
    horizon_months = min(len(monthly), effective_years * MONTHS_PER_YEAR)
    truncated = monthly.iloc[:horizon_months].reset_index(drop=True)
    npv_series = pd.to_numeric(truncated["NPV_COP"], errors="coerce")
    finite_npv = npv_series.dropna()
    npv_value = float(finite_npv.iloc[-1]) if not finite_npv.empty else None

    return {
        "horizon_years": effective_years,
        "horizon_months": horizon_months,
        "NPV_COP": npv_value,
        "display_metric_key": "NPV_COP",
        "display_value_COP": npv_value,
    }


def resolve_payback_display_state(
    payback_years: Any,
    visible_horizon_years: int | float | None,
    *,
    payback_month: Any = None,
) -> dict[str, Any]:
    resolved_visible_horizon = _coerce_visible_horizon_years(visible_horizon_years, default=1)
    resolved_payback_years = _normalize_payback_years(payback_years)
    resolved_payback_month = _normalize_payback_month(payback_month)
    if resolved_payback_years is None:
        return {
            "visible_horizon_years": resolved_visible_horizon,
            "project_payback_years": None,
            "project_payback_month": resolved_payback_month,
            "reaches_payback": False,
            "within_visible_horizon": False,
            "message_key": "workbench.payback.note.project_horizon",
            "trace_payback_years": None,
        }
    if resolved_payback_month is not None:
        within_visible_horizon = resolved_payback_month <= (resolved_visible_horizon * MONTHS_PER_YEAR)
    else:
        within_visible_horizon = resolved_payback_years <= float(resolved_visible_horizon)
    return {
        "visible_horizon_years": resolved_visible_horizon,
        "project_payback_years": resolved_payback_years,
        "project_payback_month": resolved_payback_month,
        "reaches_payback": True,
        "within_visible_horizon": within_visible_horizon,
        "message_key": None if within_visible_horizon else "workbench.payback.note.visible_horizon",
        "trace_payback_years": resolved_payback_years,
    }


def build_visible_horizon_candidate_summary(
    detail: dict[str, Any],
    horizon_years: int,
    *,
    require_financial_snapshot: bool = False,
) -> dict[str, Any]:
    snapshot = _snapshot_from_detail(detail)
    project_summary = build_candidate_project_summary(detail, require_financial_snapshot=require_financial_snapshot)
    visible_horizon_summary = summarize_candidate_for_horizon(
        detail,
        horizon_years,
        require_financial_snapshot=require_financial_snapshot,
    )
    payback_display_state = resolve_payback_display_state(
        project_summary.get("payback_years"),
        visible_horizon_summary["horizon_years"],
        payback_month=project_summary.get("payback_month"),
    )
    return {
        **detail,
        "financial_snapshot": snapshot,
        "project_summary": project_summary,
        "visible_horizon_summary": visible_horizon_summary,
        "payback_display_state": payback_display_state,
    }


def _candidate_summary_row(
    detail: dict[str, Any],
    *,
    npv_cop: float | None = None,
    display_value_cop: float | None = None,
    payback_years: float | None = None,
    require_financial_snapshot: bool = False,
) -> dict[str, Any]:
    energy = summarize_energy_metrics(detail["monthly"])
    project_summary = build_candidate_project_summary(detail, require_financial_snapshot=require_financial_snapshot)
    resolved_display_value = display_value_cop if display_value_cop is not None else npv_cop
    if resolved_display_value is None:
        resolved_display_value = project_summary.get("cum_disc_final")
    capex_client = project_summary.get("capex_client")
    return {
        "scan_order": int(detail["scan_order"]),
        "candidate_key": detail["candidate_key"],
        "kWp": round(float(detail["kWp"]), 3),
        "battery": detail["battery_name"],
        "NPV_COP": float(resolved_display_value) if resolved_display_value is not None else None,
        "payback_years": payback_years if payback_years is not None else project_summary.get("payback_years"),
        "capex_client": float(capex_client) if capex_client is not None else None,
        "self_consumption_ratio": energy["self_consumption_ratio"],
        "self_sufficiency_ratio": energy["self_sufficiency_ratio"],
        "annual_import_kwh": energy["annual_import_kwh"],
        "annual_export_kwh": energy["annual_export_kwh"],
        "peak_ratio": float(detail["peak_ratio"]),
    }


def _finalize_candidate_table(frame: pd.DataFrame, *, display_metric_key: str = "NPV_COP") -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=CANDIDATE_TABLE_COLUMNS)
    value_ascending = _display_metric_prefers_lower_value(display_metric_key)
    frame = frame.sort_values(
        by=["kWp", "NPV_COP", "scan_order"],
        ascending=[True, value_ascending, True],
        kind="mergesort",
    ).reset_index(drop=True)
    frame["best_battery_for_kwp"] = False
    best_idx = frame.groupby("kWp", sort=False).head(1).index
    frame.loc[best_idx, "best_battery_for_kwp"] = True
    return frame


def build_candidate_table(
    detail_map: dict[str, dict],
    *,
    require_financial_snapshot: bool = False,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            _candidate_summary_row(detail, require_financial_snapshot=require_financial_snapshot)
            for detail in detail_map.values()
        ]
    )
    return _finalize_candidate_table(frame)


def _safe_battery_kwh(detail: dict[str, Any]) -> float | None:
    battery = detail.get("battery") if isinstance(detail.get("battery"), dict) else {}
    normalized = _normalize_optional_float((battery or {}).get("nom_kWh"))
    if normalized is None or normalized <= 0:
        return None
    return float(normalized)


def _safe_battery_name(detail: dict[str, Any]) -> str:
    battery = detail.get("battery") if isinstance(detail.get("battery"), dict) else {}
    return str(detail.get("battery_name") or (battery or {}).get("name") or "").strip()


def battery_family_key_from_detail(detail: dict[str, Any]) -> str:
    battery_name = _safe_battery_name(detail)
    battery_kwh = _safe_battery_kwh(detail)
    lowered_name = battery_name.casefold()
    if battery_kwh is None and lowered_name in {"", "none", "bat-0"}:
        return EXPLORER_SUBSET_KEY_NO_BATTERY
    if battery_kwh is not None:
        return f"battery:kwh:{battery_kwh:.3f}"
    fallback_name = lowered_name or "unknown"
    return f"battery:name:{fallback_name}"


def battery_family_label_from_detail(detail: dict[str, Any], *, lang: str = "es") -> str:
    battery_name = _safe_battery_name(detail)
    battery_kwh = _safe_battery_kwh(detail)
    lowered_name = battery_name.casefold()
    if battery_kwh is None and lowered_name in {"", "none", "bat-0"}:
        return tr("common.no_battery", lang)
    if battery_kwh is not None:
        suffix = "batería" if lang == "es" else "battery"
        return f"{battery_kwh:.1f} kWh {suffix}"
    return battery_name or tr("common.no_battery", lang)


def enrich_results_candidate_table(
    candidate_table: pd.DataFrame,
    detail_map: dict[str, dict[str, Any]],
    *,
    lang: str = "es",
) -> pd.DataFrame:
    frame = candidate_table.copy()
    if frame.empty:
        for column in ("battery_family_key", "battery_family_label", "battery_kwh"):
            frame[column] = pd.Series(dtype=object)
        return frame
    family_keys: list[str] = []
    family_labels: list[str] = []
    battery_kwh_values: list[float | None] = []
    for candidate_key in frame["candidate_key"].tolist():
        detail = detail_map.get(str(candidate_key), {})
        family_keys.append(battery_family_key_from_detail(detail))
        family_labels.append(battery_family_label_from_detail(detail, lang=lang))
        battery_kwh_values.append(_safe_battery_kwh(detail))
    frame["battery_family_key"] = family_keys
    frame["battery_family_label"] = family_labels
    frame["battery_kwh"] = battery_kwh_values
    return frame


def subset_mode_for_key(subset_key: str | None) -> str:
    return EXPLORER_SUBSET_MODE_OPTIMAL if subset_key == EXPLORER_SUBSET_KEY_OPTIMAL else EXPLORER_SUBSET_MODE_BATTERY


def candidate_key_in_subset(candidate_table: pd.DataFrame, candidate_key: str | None, subset_key: str | None) -> bool:
    if candidate_table.empty or candidate_key in (None, "") or subset_key in (None, ""):
        return False
    if subset_key == EXPLORER_SUBSET_KEY_OPTIMAL:
        if "best_battery_for_kwp" not in candidate_table.columns:
            return False
        subset = candidate_table[candidate_table["best_battery_for_kwp"] == True]  # noqa: E712
    else:
        if "battery_family_key" not in candidate_table.columns:
            return False
        subset = candidate_table[candidate_table["battery_family_key"] == subset_key]
    return bool(not subset.empty and candidate_key in subset["candidate_key"].astype(str).tolist())


def filter_results_subset(candidate_table: pd.DataFrame, subset_key: str | None) -> pd.DataFrame:
    if candidate_table.empty or subset_key in (None, ""):
        return candidate_table.iloc[0:0].copy()
    if subset_key == EXPLORER_SUBSET_KEY_OPTIMAL:
        if "best_battery_for_kwp" not in candidate_table.columns:
            return candidate_table.iloc[0:0].copy()
        return candidate_table[candidate_table["best_battery_for_kwp"] == True].copy()  # noqa: E712
    if "battery_family_key" not in candidate_table.columns:
        return candidate_table.iloc[0:0].copy()
    return candidate_table[candidate_table["battery_family_key"] == subset_key].copy()


def subset_label_for_key(candidate_table: pd.DataFrame, subset_key: str | None, *, lang: str = "es") -> str:
    if subset_key == EXPLORER_SUBSET_KEY_OPTIMAL:
        return tr("workbench.explorer.family.optimal", lang)
    subset = filter_results_subset(candidate_table, subset_key)
    if subset.empty:
        return ""
    return str(subset.iloc[0].get("battery_family_label") or "")


def build_results_explorer_options(candidate_table: pd.DataFrame, *, lang: str = "es") -> list[dict[str, str]]:
    if candidate_table.empty:
        return []
    options = [{"label": tr("workbench.explorer.family.optimal", lang), "value": EXPLORER_SUBSET_KEY_OPTIMAL}]
    family_frame = (
        candidate_table[["battery_family_key", "battery_family_label", "battery_kwh"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    if family_frame.empty:
        return options
    family_frame["sort_bucket"] = family_frame["battery_family_key"].map(
        lambda value: 0 if value == EXPLORER_SUBSET_KEY_NO_BATTERY else 1
    )
    family_frame["sort_kwh"] = family_frame["battery_kwh"].map(lambda value: float(value) if value is not None and pd.notna(value) else float("inf"))
    family_frame = family_frame.sort_values(
        ["sort_bucket", "sort_kwh", "battery_family_label", "battery_family_key"],
        kind="mergesort",
    ).reset_index(drop=True)
    options.extend(
        {
            "label": str(row["battery_family_label"]),
            "value": str(row["battery_family_key"]),
        }
        for row in family_frame.to_dict("records")
    )
    return options


def _first_available_subset_key(candidate_table: pd.DataFrame, *, lang: str = "es") -> str | None:
    options = build_results_explorer_options(candidate_table, lang=lang)
    if not options:
        return None
    for option in options:
        if option["value"] != EXPLORER_SUBSET_KEY_OPTIMAL:
            return str(option["value"])
    return str(options[0]["value"])


def _best_candidate_key_from_subset(
    subset: pd.DataFrame,
    *,
    display_metric_key: str = "NPV_COP",
) -> str | None:
    if subset.empty:
        return None
    value_ascending = _display_metric_prefers_lower_value(display_metric_key)
    ordered = subset.sort_values(
        ["NPV_COP", "scan_order", "candidate_key"],
        ascending=[value_ascending, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return str(ordered.iloc[0]["candidate_key"])


def resolve_nearest_candidate_key_in_subset(
    candidate_table: pd.DataFrame,
    reference_candidate_key: str | None,
    subset_key: str | None,
    *,
    display_metric_key: str = "NPV_COP",
) -> str | None:
    subset = filter_results_subset(candidate_table, subset_key)
    if subset.empty:
        return None
    if reference_candidate_key not in candidate_table["candidate_key"].astype(str).tolist():
        return _best_candidate_key_from_subset(subset, display_metric_key=display_metric_key)
    reference_row = candidate_table[candidate_table["candidate_key"] == reference_candidate_key].head(1)
    if reference_row.empty:
        return _best_candidate_key_from_subset(subset, display_metric_key=display_metric_key)
    reference_kwp = float(reference_row.iloc[0]["kWp"])
    nearest = (
        subset.assign(
            kwp_delta=subset["kWp"].map(lambda value: abs(float(value) - reference_kwp)),
            candidate_key_sort=subset["candidate_key"].astype(str),
        )
        .sort_values(["kwp_delta", "scan_order", "candidate_key_sort"], kind="mergesort")
        .reset_index(drop=True)
    )
    return str(nearest.iloc[0]["candidate_key"])


def resolve_results_explorer_state(
    candidate_table: pd.DataFrame,
    *,
    scenario_id: str | None,
    scan_fingerprint: str | None,
    selected_candidate_key: str | None,
    current_state: dict[str, Any] | None = None,
    lang: str = "es",
) -> dict[str, Any]:
    if candidate_table.empty:
        return {
            "scenario_id": scenario_id,
            "scan_fingerprint": scan_fingerprint,
            "subset_mode": EXPLORER_SUBSET_MODE_OPTIMAL,
            "subset_key": None,
            "subset_label": "",
        }
    current = current_state or {}
    current_subset_key = str(current.get("subset_key") or "").strip() or None
    same_scan = (
        str(current.get("scenario_id") or "") == str(scenario_id or "")
        and str(current.get("scan_fingerprint") or "") == str(scan_fingerprint or "")
    )
    explorer_options = build_results_explorer_options(candidate_table, lang=lang)
    if same_scan and selected_candidate_key and candidate_key_in_subset(candidate_table, selected_candidate_key, current_subset_key):
        preserved_key = current_subset_key
    else:
        preserved_key = None
    if preserved_key is None and selected_candidate_key and selected_candidate_key in candidate_table["candidate_key"].astype(str).tolist():
        selected_row = candidate_table[candidate_table["candidate_key"] == selected_candidate_key].head(1)
        resolved_key = str(selected_row.iloc[0]["battery_family_key"])
    elif EXPLORER_SUBSET_KEY_OPTIMAL in [option["value"] for option in explorer_options]:
        optimal_subset = filter_results_subset(candidate_table, EXPLORER_SUBSET_KEY_OPTIMAL)
        resolved_key = EXPLORER_SUBSET_KEY_OPTIMAL if not optimal_subset.empty else _first_available_subset_key(candidate_table, lang=lang)
    else:
        resolved_key = _first_available_subset_key(candidate_table, lang=lang)
    final_key = preserved_key or resolved_key
    return {
        "scenario_id": scenario_id,
        "scan_fingerprint": scan_fingerprint,
        "subset_mode": subset_mode_for_key(final_key),
        "subset_key": final_key,
        "subset_label": subset_label_for_key(candidate_table, final_key, lang=lang),
    }


def canonical_results_explorer_view(
    candidate_table: pd.DataFrame,
    *,
    selected_candidate_key: str | None,
    subset_key: str | None,
    display_metric_key: str = "NPV_COP",
) -> dict[str, Any]:
    if candidate_table.empty:
        return {
            "subset_key": None,
            "subset_rows": candidate_table.iloc[0:0].copy(),
            "highlight_keys": tuple(),
            "selected_candidate_key": None,
        }
    active_subset_key = subset_key if subset_key not in (None, "") else EXPLORER_SUBSET_KEY_OPTIMAL
    subset = filter_results_subset(candidate_table, active_subset_key)
    if subset.empty:
        fallback_key = EXPLORER_SUBSET_KEY_OPTIMAL if not filter_results_subset(candidate_table, EXPLORER_SUBSET_KEY_OPTIMAL).empty else _first_available_subset_key(candidate_table)
        active_subset_key = fallback_key
        subset = filter_results_subset(candidate_table, active_subset_key)
    if candidate_key_in_subset(candidate_table, selected_candidate_key, active_subset_key):
        final_selected_key = selected_candidate_key
    elif selected_candidate_key and selected_candidate_key in candidate_table["candidate_key"].astype(str).tolist():
        final_selected_key = resolve_nearest_candidate_key_in_subset(
            candidate_table,
            selected_candidate_key,
            active_subset_key,
            display_metric_key=display_metric_key,
        )
    else:
        final_selected_key = _best_candidate_key_from_subset(subset, display_metric_key=display_metric_key)
    return {
        "subset_key": active_subset_key,
        "subset_rows": subset.copy(),
        "highlight_keys": tuple(str(candidate_key) for candidate_key in subset["candidate_key"].astype(str).tolist()),
        "selected_candidate_key": final_selected_key,
    }


def summarize_candidates_for_horizon(
    detail_map: dict[str, dict],
    horizon_years: int,
    *,
    require_financial_snapshot: bool = False,
) -> pd.DataFrame:
    display_metric_key = visible_financial_metric_key(horizon_years)
    rows = []
    for detail in detail_map.values():
        presentation = build_visible_horizon_candidate_summary(
            detail,
            horizon_years,
            require_financial_snapshot=require_financial_snapshot,
        )
        rows.append(
            _candidate_summary_row(
                detail,
                display_value_cop=presentation["visible_horizon_summary"].get("display_value_COP"),
                payback_years=presentation["payback_display_state"]["trace_payback_years"],
                require_financial_snapshot=require_financial_snapshot,
            )
        )
    return _finalize_candidate_table(pd.DataFrame(rows), display_metric_key=display_metric_key)


def build_kpis(detail: dict, *, require_financial_snapshot: bool = False) -> dict[str, float | str | None]:
    project_summary = (
        build_candidate_project_summary(detail, require_financial_snapshot=True)
        if require_financial_snapshot
        else (detail.get("project_summary") or build_candidate_project_summary(detail))
    )
    visible_horizon_summary = detail.get("visible_horizon_summary") or {}
    payback_display_state = detail.get("payback_display_state") or {}
    metrics = summarize_energy_metrics(detail["monthly"])
    display_metric_key = str(visible_horizon_summary.get("display_metric_key") or "NPV_COP")
    npv_value = visible_horizon_summary.get("display_value_COP")
    if npv_value is None:
        npv_value = project_summary.get("capex_client") if display_metric_key == "capex_client" else project_summary.get("cum_disc_final")
    payback_value = payback_display_state.get("project_payback_years")
    if payback_value is None:
        payback_value = project_summary.get("payback_years")
    return {
        "best_kWp": round(float(detail["kWp"]), 3),
        "selected_battery": detail["battery_name"],
        "NPV": float(npv_value) if npv_value is not None else None,
        "financial_metric_key": display_metric_key,
        "payback_years": payback_value,
        "self_consumption_ratio": float(detail.get("self_consumption_ratio", metrics["self_consumption_ratio"])),
        "self_sufficiency_ratio": float(detail.get("self_sufficiency_ratio", metrics["self_sufficiency_ratio"])),
        "annual_import_kwh": metrics["annual_import_kwh"],
        "annual_export_kwh": metrics["annual_export_kwh"],
    }


def build_monthly_balance(monthly: pd.DataFrame, lang: str = "en") -> pd.DataFrame:
    first_year = monthly.iloc[:MONTHS_PER_YEAR].copy()
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


def build_cash_flow(
    monthly: pd.DataFrame,
    *,
    base_year: int | None = None,
    financial_snapshot: CandidateFinancialSnapshot | None = None,
    require_financial_snapshot: bool = False,
) -> pd.DataFrame:
    if financial_snapshot is not None:
        snapshot_frame = build_snapshot_monthly_frame(monthly, financial_snapshot)
        frame = snapshot_frame[
            [
                "Año_mes",
                "NPV_COP",
                "Ahorro_COP",
                "Cumulative_Cash_Flow_COP",
                "Cash_Flow_Discounted_COP",
            ]
        ].copy()
        frame.rename(
            columns={
                "NPV_COP": "cumulative_npv",
                "Ahorro_COP": "monthly_savings",
                "Cumulative_Cash_Flow_COP": "cumulative_cash_flow",
                "Cash_Flow_Discounted_COP": "monthly_discounted_cash_flow",
            },
            inplace=True,
        )
    elif require_financial_snapshot:
        raise CandidateFinancialSnapshotUnavailableError(
            "Se requiere CandidateFinancialSnapshot para construir el cash flow de una ruta viva."
        )
    else:
        # Compatibility-only fallback for tests/helpers that operate on legacy snapshot-less monthly frames.
        frame = monthly[["Año_mes", "NPV_COP", "Ahorro_COP"]].copy()
        frame.rename(columns={"NPV_COP": "cumulative_npv", "Ahorro_COP": "monthly_savings"}, inplace=True)
    timeline = build_project_timeline(len(frame), base_year=base_year)
    if not timeline.empty:
        frame = frame.reset_index(drop=True).join(timeline)
    return frame


def build_npv_curve(candidate_table: pd.DataFrame, *, display_metric_key: str = "NPV_COP") -> pd.DataFrame:
    if candidate_table.empty:
        return pd.DataFrame(columns=NPV_CURVE_COLUMNS)
    value_ascending = _display_metric_prefers_lower_value(display_metric_key)
    grouped = (
        candidate_table.sort_values(["kWp", "NPV_COP", "scan_order"], ascending=[True, value_ascending, True], kind="mergesort")
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


def format_horizon_year_value(years: int, *, lang: str = "es") -> str:
    resolved_years = max(0, int(years))
    if lang == "es":
        unit = "año" if resolved_years == 1 else "años"
    else:
        unit = "year" if resolved_years == 1 else "years"
    return f"{resolved_years} {unit}"


def _npv_figure_title(base_title: str, *, horizon_years: int | None, lang: str) -> str:
    if horizon_years is None:
        return base_title
    return f"{base_title}<br><sup>{tr('workbench.horizon.label', lang)}: {format_horizon_year_value(horizon_years, lang=lang)}</sup>"


def _format_payback_hover_value(value: Any, *, lang: str = "es") -> str:
    normalized = _normalize_payback_years(value)
    if normalized is None:
        return "-"
    return format_metric("payback_years", normalized, lang)


def _financial_axis_label(metric_key: str, *, lang: str) -> str:
    if metric_key == "capex_client":
        return tr("workbench.project_price.axis_label", lang)
    return metric_label("NPV_COP", lang)


def _financial_chart_title(metric_key: str, *, lang: str) -> str:
    if metric_key == "capex_client":
        return tr("workbench.project_price.chart_title", lang)
    return "VPN vs kWp" if lang == "es" else "NPV vs kWp"


def _curve_hover_lines(curve: pd.DataFrame, *, lang: str, display_metric_key: str, payback_label: str) -> list[str]:
    lines: list[str] = []
    for row in curve.to_dict("records"):
        panel_count = row.get("panel_count")
        panel_value = str(int(panel_count)) if panel_count is not None and pd.notna(panel_count) else "-"
        lines.append(
            "<br>".join(
                [
                    f"kWp: {float(row['kWp']):.3f}",
                    f"{tr('common.chart.panels', lang)}: {panel_value}",
                    f"{'Batería' if lang == 'es' else 'Battery'}: {row['battery_display']}",
                    f"{_financial_axis_label(display_metric_key, lang=lang)}: {format_metric(display_metric_key, row['NPV_COP'], lang)}",
                    f"{payback_label}: {_format_payback_hover_value(row.get('payback_years'), lang=lang)}",
                    f"{metric_label('self_consumption_ratio', lang)}: {100 * float(row['self_consumption_ratio']):.1f}%",
                    f"{metric_label('peak_ratio', lang)}: {100 * float(row['peak_ratio']):.1f}%",
                ]
            )
        )
    return lines


def _payback_trace_hover_lines(curve: pd.DataFrame, *, label: str, lang: str) -> list[str]:
    return [
        f"kWp: {float(k_wp):.3f}<br>{label}: {_format_payback_hover_value(payback_years, lang=lang)}"
        for k_wp, payback_years in zip(curve["kWp"], curve["payback_years"], strict=False)
    ]


def _candidate_overlay_row(candidate_table: pd.DataFrame, candidate_key: str | None) -> pd.DataFrame:
    if candidate_table.empty or not candidate_key:
        return pd.DataFrame()
    selected = candidate_table[candidate_table["candidate_key"] == candidate_key]
    if selected.empty:
        return selected
    return selected.sort_values(["scan_order", "kWp"], kind="mergesort").head(1).reset_index(drop=True)


def _best_candidate_overlay_row(
    candidate_table: pd.DataFrame,
    *,
    display_metric_key: str = "NPV_COP",
    exclude_candidate_key: str | None = None,
) -> pd.DataFrame:
    if candidate_table.empty:
        return candidate_table.iloc[0:0].copy()
    value_ascending = _display_metric_prefers_lower_value(display_metric_key)
    best_row = candidate_table.sort_values(
        ["NPV_COP", "scan_order", "kWp"],
        ascending=[value_ascending, True, True],
        kind="mergesort",
    ).head(1)
    if exclude_candidate_key and str(best_row.iloc[0]["candidate_key"]) == str(exclude_candidate_key):
        return candidate_table.iloc[0:0].copy()
    return best_row.reset_index(drop=True)


def _chart_point_customdata(frame: pd.DataFrame, *, point_role: str) -> pd.DataFrame:
    return frame.assign(point_role=point_role)[["candidate_key", "panel_count", "point_role"]]


def _add_viable_npv_traces(
    figure: go.Figure,
    curve: pd.DataFrame,
    *,
    lang: str,
    figure_title: str,
    display_metric_key: str,
    payback_label: str,
    selected_row: pd.DataFrame,
    row: int | None = None,
) -> None:
    add_trace_kwargs = {"row": row, "col": 1} if row is not None else {}
    figure.add_trace(
        go.Scatter(
            x=curve["kWp"],
            y=curve["NPV_COP"],
            mode="lines+markers",
            name=figure_title,
            line={"color": "#2563eb", "width": 3},
            marker={"size": 9, "color": "#2563eb"},
            ids=curve["candidate_key"],
            customdata=_chart_point_customdata(curve, point_role=CLICK_ROLE_NPV_CURVE),
            hovertext=_curve_hover_lines(curve, lang=lang, display_metric_key=display_metric_key, payback_label=payback_label),
            hovertemplate="%{hovertext}<extra></extra>",
        ),
        **add_trace_kwargs,
    )
    if selected_row.empty:
        return
    figure.add_trace(
        go.Scatter(
            x=selected_row["kWp"],
            y=selected_row["NPV_COP"],
            mode="markers",
            marker={"size": 18, "color": "#dc2626", "line": {"width": 3, "color": "#7f1d1d"}},
            name=tr("common.chart.selected_design", lang),
            ids=selected_row["candidate_key"],
            customdata=_chart_point_customdata(selected_row, point_role=CLICK_ROLE_SELECTED_OVERLAY),
            hovertext=_curve_hover_lines(selected_row, lang=lang, display_metric_key=display_metric_key, payback_label=payback_label),
            hovertemplate=tr("common.chart.selected_design", lang) + "<br>%{hovertext}<extra></extra>",
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
    horizon_years: int | None = None,
    display_metric_key: str | None = None,
    payback_label: str | None = None,
    module_power_w: float | None = None,
    discarded_points: tuple[dict[str, Any], ...] | list[dict[str, Any]] | None = None,
) -> go.Figure:
    resolved_display_metric = display_metric_key or visible_financial_metric_key(horizon_years)
    display_table = candidate_table.copy()
    display_table["battery_display"] = display_table["battery"].map(lambda value: format_metric("selected_battery", value, lang))
    if module_power_w and float(module_power_w) > 0:
        display_table["panel_count"] = display_table["kWp"].map(lambda value: int(round(float(value) / (float(module_power_w) / 1000.0))))
    else:
        display_table["panel_count"] = None
    curve = build_npv_curve(candidate_table, display_metric_key=resolved_display_metric)
    curve = curve.copy()
    curve["battery_display"] = curve["battery"].map(lambda value: format_metric("selected_battery", value, lang))
    if module_power_w and float(module_power_w) > 0:
        curve["panel_count"] = curve["kWp"].map(lambda value: int(round(float(value) / (float(module_power_w) / 1000.0))))
    else:
        curve["panel_count"] = None
    selected_row = _candidate_overlay_row(display_table, selected_key)
    figure_title = title or _financial_chart_title(resolved_display_metric, lang=lang)
    full_title = _npv_figure_title(figure_title, horizon_years=horizon_years, lang=lang)
    resolved_payback_label = payback_label or metric_label("payback_years", lang)
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
            _add_viable_npv_traces(
                figure,
                curve,
                lang=lang,
                figure_title=figure_title,
                display_metric_key=resolved_display_metric,
                payback_label=resolved_payback_label,
                selected_row=selected_row,
            )
            figure.add_trace(
                go.Scatter(
                    x=curve["kWp"],
                    y=curve["payback_years"],
                    mode="lines+markers",
                    name=resolved_payback_label,
                    line={"color": "#0f766e", "width": 2, "dash": "dash"},
                    marker={"size": 6, "color": "#0f766e"},
                    ids=curve["candidate_key"],
                    customdata=_chart_point_customdata(curve, point_role=CLICK_ROLE_PAYBACK_CURVE),
                    hovertext=_payback_trace_hover_lines(curve, label=resolved_payback_label, lang=lang),
                    hovertemplate="%{hovertext}<extra></extra>",
                ),
                secondary_y=True,
            )
        figure.update_layout(
            template="plotly_white",
            title=full_title,
            hovermode="x unified",
            margin={"t": 108 if horizon_years is not None else 88},
        )
        figure.update_yaxes(title=_financial_axis_label(resolved_display_metric, lang=lang), tickformat=",.0f", secondary_y=False)
        figure.update_yaxes(title=resolved_payback_label, secondary_y=True)
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
        _add_viable_npv_traces(
            figure,
            curve,
            lang=lang,
            figure_title=figure_title,
            display_metric_key=resolved_display_metric,
            payback_label=resolved_payback_label,
            selected_row=selected_row,
            row=1,
        )
        figure.add_trace(
            go.Scatter(
                x=curve["kWp"],
                y=curve["payback_years"],
                mode="lines+markers",
                name=resolved_payback_label,
                line={"color": "#0f766e", "width": 2, "dash": "dash"},
                marker={"size": 6, "color": "#0f766e"},
                ids=curve["candidate_key"],
                customdata=_chart_point_customdata(curve, point_role=CLICK_ROLE_PAYBACK_CURVE),
                hovertext=_payback_trace_hover_lines(curve, label=resolved_payback_label, lang=lang),
                hovertemplate="%{hovertext}<extra></extra>",
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

    figure.update_layout(
        template="plotly_white",
        title=full_title,
        hovermode="x unified",
        margin={"t": 108 if horizon_years is not None else 88},
    )
    figure.update_yaxes(title=_financial_axis_label(resolved_display_metric, lang=lang), tickformat=",.0f", row=1, col=1, secondary_y=False)
    figure.update_yaxes(title=resolved_payback_label, row=1, col=1, secondary_y=True)
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


def _candidate_key_from_click_point(point: dict[str, Any]) -> str | None:
    point_id = point.get("id")
    if point_id not in (None, ""):
        return str(point_id)
    customdata = point.get("customdata")
    if isinstance(customdata, str) and customdata.strip():
        return customdata.strip()
    if isinstance(customdata, (list, tuple)) and customdata:
        candidate_key = customdata[0]
        if candidate_key not in (None, ""):
            return str(candidate_key)
    if isinstance(customdata, dict):
        candidate_key = customdata.get("candidate_key")
        if candidate_key not in (None, ""):
            return str(candidate_key)
    return None


def _click_point_role(point: dict[str, Any]) -> str | None:
    customdata = point.get("customdata")
    if isinstance(customdata, (list, tuple)) and len(customdata) >= 3:
        point_role = customdata[2]
        if point_role not in (None, ""):
            return str(point_role)
    if isinstance(customdata, dict):
        point_role = customdata.get("point_role")
        if point_role not in (None, ""):
            return str(point_role)
    return None


def resolve_selected_candidate_key_for_scenario(
    scan_result,
    scenario_selected_key: str | None,
    table_rows: list[dict] | None = None,
    selected_rows: list[int] | None = None,
    click_data: dict | None = None,
) -> str | None:
    if click_data and click_data.get("points"):
        click_matches: list[tuple[int, int, str]] = []
        for index, point in enumerate(click_data["points"]):
            resolved_point = point or {}
            candidate_key = _candidate_key_from_click_point(resolved_point)
            if candidate_key not in scan_result.candidate_details:
                continue
            point_role = _click_point_role(resolved_point)
            priority = CLICK_POINT_ROLE_PRIORITY.get(point_role, len(CLICK_POINT_ROLE_PRIORITY))
            click_matches.append((priority, index, candidate_key))
        if click_matches:
            click_matches.sort(key=lambda match: (match[0], match[1]))
            return click_matches[0][2]
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
    candidate_key = resolve_financial_candidate_key(scenario)
    if not candidate_key:
        raise ValueError(f"El escenario '{scenario.name}' no tiene diseños viables en el escaneo determinístico.")
    detail = attach_candidate_financial_snapshot(scenario, scenario.scan_result.candidate_details[candidate_key], candidate_key)
    kpis = build_kpis(detail, require_financial_snapshot=True)
    snapshot = validate_candidate_financial_snapshot(detail.get("financial_snapshot"), candidate_key=candidate_key)
    return {
        "scenario_id": scenario.scenario_id,
        "scenario": scenario.name,
        "candidate_key": candidate_key,
        "best_kWp": kpis["best_kWp"],
        "battery": kpis["selected_battery"],
        "capex_client": snapshot.capex_client_COP,
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
                "capex_client",
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
        attached_details = attach_candidate_financial_snapshots(scenario)
        curve = build_npv_curve(build_candidate_table(attached_details, require_financial_snapshot=True))
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
