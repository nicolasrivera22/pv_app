from __future__ import annotations

from typing import Any

import pandas as pd

from .i18n import tr
from .types import MonteCarloRunResult, RiskViewBundle, ScenarioRecord, ScenarioSessionState
from .ui_schema import metric_label

RATIO_METRICS = {"self_consumption_ratio", "self_sufficiency_ratio"}


def ready_risk_scenarios(state: ScenarioSessionState) -> list[ScenarioRecord]:
    return [scenario for scenario in state.scenarios if scenario.scan_result is not None and not scenario.dirty]


def resolve_default_risk_scenario(state: ScenarioSessionState, preferred_id: str | None = None) -> str | None:
    ready = ready_risk_scenarios(state)
    ready_ids = {scenario.scenario_id for scenario in ready}
    if preferred_id in ready_ids:
        return preferred_id
    if state.active_scenario_id in ready_ids:
        return state.active_scenario_id
    return ready[0].scenario_id if ready else None


def resolve_default_risk_candidate(scenario_record: ScenarioRecord) -> str | None:
    scan = scenario_record.scan_result
    if scan is None or scenario_record.dirty:
        return None
    if scenario_record.selected_candidate_key in scan.candidate_details:
        return str(scenario_record.selected_candidate_key)
    if scan.best_candidate_key in scan.candidate_details:
        return scan.best_candidate_key
    return next(iter(scan.candidate_details), None)


def build_risk_candidate_options(scenario_record: ScenarioRecord, lang: str = "en") -> list[dict[str, str]]:
    scan = scenario_record.scan_result
    if scan is None or scenario_record.dirty:
        return []

    table = scan.candidates.sort_values(["kWp", "NPV_COP", "scan_order"], ascending=[True, False, True], kind="mergesort")
    options: list[dict[str, str]] = []
    for row in table.to_dict("records"):
        marker = f" · {tr('risk.best_marker', lang)}" if row["candidate_key"] == scan.best_candidate_key else ""
        label = f"{float(row['kWp']):.3f} kWp · {row['battery']} · COP {float(row['NPV_COP']):,.0f}{marker}"
        options.append({"label": label, "value": str(row["candidate_key"])})
    return options


def _coerce_positive_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def _coerce_non_negative_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced >= 0 else None


def validate_risk_run_inputs(
    scenario_record: ScenarioRecord | None,
    candidate_key: str | None,
    n_simulations: Any,
    seed: Any,
    *,
    lang: str = "en",
) -> list[str]:
    issues: list[str] = []
    if scenario_record is None:
        return [tr("risk.error.no_scenario", lang)]
    if scenario_record.dirty:
        issues.append(tr("risk.error.scenario_dirty", lang))
    if not candidate_key:
        issues.append(tr("risk.error.no_candidate", lang))
    if scenario_record.scan_result is None:
        issues.append(tr("risk.error.no_baseline", lang))
    elif candidate_key not in scenario_record.scan_result.candidate_details:
        issues.append(tr("risk.error.no_candidate", lang))
    if _coerce_positive_int(n_simulations) is None:
        issues.append(tr("risk.error.invalid_n_simulations", lang))
    if _coerce_non_negative_int(seed) is None:
        issues.append(tr("risk.error.invalid_seed", lang))
    return issues


def build_risk_metadata_rows(
    scenario_record: ScenarioRecord,
    result: MonteCarloRunResult,
    *,
    lang: str = "en",
) -> pd.DataFrame:
    active_uncertainty = ", ".join(
        f"{name}={value:.4f}" for name, value in result.active_uncertainty.items() if float(value or 0.0) > 0
    ) or tr("risk.metadata.none_active", lang)
    return pd.DataFrame(
        [
            {"label": tr("risk.metadata.scenario", lang), "value": scenario_record.name},
            {"label": tr("risk.metadata.candidate", lang), "value": result.selected_candidate_key},
            {"label": tr("risk.metadata.kwp", lang), "value": f"{result.selected_kWp:.3f}"},
            {"label": tr("risk.metadata.battery", lang), "value": result.selected_battery},
            {"label": tr("risk.metadata.n_simulations", lang), "value": str(result.n_simulations)},
            {"label": tr("risk.metadata.seed", lang), "value": str(result.seed)},
            {"label": tr("risk.metadata.active_uncertainty", lang), "value": active_uncertainty},
        ]
    )


def build_risk_result_store_payload(
    *,
    result_id: str | None,
    scenario_id: str | None,
    candidate_key: str | None,
    n_simulations: int | None,
    seed: int | None,
    retain_samples: bool,
    status: str | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "result_id": result_id,
        "scenario_id": scenario_id,
        "candidate_key": candidate_key,
        "n_simulations": n_simulations,
        "seed": seed,
        "retain_samples": retain_samples,
        "status": status,
        "errors": list(errors or []),
        "warnings": list(warnings or []),
    }


def prepare_percentile_table_for_display(views: RiskViewBundle, *, lang: str = "en") -> pd.DataFrame:
    frame = views.percentile_table.copy()
    if frame.empty:
        return frame
    frame = frame.drop(columns=["percentiles_over_finite_values"], errors="ignore")
    frame["metric"] = frame["metric"].map(lambda value: metric_label(value, lang) if value in {"NPV_COP", "payback_years", "self_consumption_ratio", "self_sufficiency_ratio", "annual_import_kwh", "annual_export_kwh"} else tr(f"risk.metric.{value}", lang))
    ratio_mask = frame["metric"].isin(
        [metric_label("self_consumption_ratio", lang), metric_label("self_sufficiency_ratio", lang)]
    )
    numeric_columns = ["mean", "std", "min", "max", "p5", "p10", "p25", "p50", "p75", "p90", "p95"]
    frame.loc[ratio_mask, numeric_columns] = frame.loc[ratio_mask, numeric_columns].apply(lambda column: column * 100.0)
    frame[numeric_columns] = frame[numeric_columns].round(2)
    return frame
