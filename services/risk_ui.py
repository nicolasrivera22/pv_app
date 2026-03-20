from __future__ import annotations

from typing import Any

import pandas as pd

from .i18n import tr
from .types import MonteCarloRunResult, RiskViewBundle, ScenarioRecord, ScenarioSessionState
from .ui_schema import FIELD_SCHEMAS, format_metric, metric_label

RATIO_METRICS = {"self_consumption_ratio", "self_sufficiency_ratio"}


def _scenario_has_viable_scan(scenario: ScenarioRecord) -> bool:
    scan = scenario.scan_result
    return scan is not None and not scenario.dirty and not scan.candidates.empty and bool(scan.candidate_details)


def _field_display_label(field_key: str, lang: str) -> str:
    schema = FIELD_SCHEMAS.get(field_key)
    if schema is None:
        return field_key
    if lang == "en":
        return schema.label_en or schema.label_es or field_key
    return schema.label_es or schema.label_en or field_key


def ready_risk_scenarios(state: ScenarioSessionState) -> list[ScenarioRecord]:
    return [scenario for scenario in state.scenarios if _scenario_has_viable_scan(scenario)]


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
    if scan is None or scenario_record.dirty or scan.candidates.empty or not scan.candidate_details:
        return None
    if scenario_record.selected_candidate_key in scan.candidate_details:
        return str(scenario_record.selected_candidate_key)
    if scan.best_candidate_key in scan.candidate_details:
        return scan.best_candidate_key
    return next(iter(scan.candidate_details), None)


def build_risk_candidate_options(scenario_record: ScenarioRecord, lang: str = "en") -> list[dict[str, str]]:
    scan = scenario_record.scan_result
    if scan is None or scenario_record.dirty or scan.candidates.empty or not scan.candidate_details:
        return []

    table = scan.candidates.sort_values(["kWp", "NPV_COP", "scan_order"], ascending=[True, False, True], kind="mergesort")
    options: list[dict[str, str]] = []
    for row in table.to_dict("records"):
        marker = f" · {tr('risk.best_marker', lang)}" if row["candidate_key"] == scan.best_candidate_key else ""
        battery_label = format_metric("selected_battery", row["battery"], lang)
        label = f"{format_metric('kWp', row['kWp'], lang)} · {battery_label} · {format_metric('NPV_COP', row['NPV_COP'], lang)}{marker}"
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
    mc_settings: dict[str, Any] | None = None,
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
    effective_config = dict((scenario_record.config_bundle.config if scenario_record is not None else {}) or {})
    effective_config.update(dict(mc_settings or {}))
    try:
        manual_k_wp = float(effective_config.get("mc_manual_kWp", 0) or 0)
    except (TypeError, ValueError):
        manual_k_wp = 0.0
    if bool(effective_config.get("mc_use_manual_kWp")) and manual_k_wp <= 0:
        issues.append(tr("risk.error.invalid_manual_kWp", lang))
    return issues


def build_risk_metadata_rows(
    scenario_record: ScenarioRecord,
    result: MonteCarloRunResult,
    *,
    lang: str = "en",
) -> pd.DataFrame:
    active_uncertainty = ", ".join(
        f"{_field_display_label(name, lang)}={100.0 * value:.1f}%"
        for name, value in result.active_uncertainty.items()
        if float(value or 0.0) > 0
    ) or tr("risk.metadata.none_active", lang)
    design_summary = " · ".join(
        [
            format_metric("kWp", result.selected_kWp, lang),
            format_metric("selected_battery", result.selected_battery, lang),
        ]
    )
    return pd.DataFrame(
        [
            {"label": tr("risk.metadata.scenario", lang), "value": scenario_record.name},
            {"label": tr("risk.metadata.design", lang), "value": design_summary},
            {"label": tr("risk.metadata.kwp", lang), "value": format_metric("kWp", result.selected_kWp, lang)},
            {"label": tr("risk.metadata.battery", lang), "value": format_metric("selected_battery", result.selected_battery, lang)},
            {"label": tr("risk.metadata.n_simulations", lang), "value": f"{int(result.n_simulations):,}"},
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
    mc_settings: dict[str, Any] | None = None,
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
        "mc_settings": dict(mc_settings or {}),
        "status": status,
        "errors": list(errors or []),
        "warnings": list(warnings or []),
    }


def clear_missing_risk_result_payload(payload: dict[str, Any] | None, *, lang: str = "es") -> dict[str, Any]:
    payload = payload or {}
    return build_risk_result_store_payload(
        result_id=None,
        scenario_id=payload.get("scenario_id"),
        candidate_key=payload.get("candidate_key"),
        n_simulations=payload.get("n_simulations"),
        seed=payload.get("seed"),
        retain_samples=bool(payload.get("retain_samples")),
        mc_settings=dict(payload.get("mc_settings") or {}),
        status=tr("risk.status.rerun_needed", lang),
        errors=[tr("risk.error.result_missing", lang)],
    )


def prepare_percentile_table_for_display(views: RiskViewBundle, *, lang: str = "en") -> pd.DataFrame:
    frame = views.percentile_table.copy()
    if frame.empty:
        return frame
    frame["metric_key"] = frame["metric"]
    frame["metric"] = frame["metric_key"].map(lambda value: metric_label(value, lang))

    count_columns = ["n_total", "n_finite", "n_missing"]
    numeric_columns = ["mean", "std", "min", "max", "p5", "p10", "p25", "p50", "p75", "p90", "p95"]
    frame[count_columns + numeric_columns] = frame[count_columns + numeric_columns].astype(object)

    for column in count_columns:
        frame[column] = frame[column].map(lambda value: "-" if pd.isna(value) else f"{int(value):,}")

    for index, row in frame.iterrows():
        metric_key = str(row["metric_key"])
        for column in numeric_columns:
            frame.at[index, column] = format_metric(metric_key, row[column], lang)

    return frame.drop(columns=["metric_key", "percentiles_over_finite_values"], errors="ignore")
