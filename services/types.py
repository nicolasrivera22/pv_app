from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


def _frame_to_payload(frame: pd.DataFrame) -> dict[str, Any]:
    return frame.to_dict(orient="split")


def _frame_from_payload(payload: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(data=payload["data"], columns=payload["columns"], index=payload["index"])


def _array_to_list(value: np.ndarray) -> list[Any]:
    return value.tolist()


def _distinct_viable_kwp_count(
    candidates: pd.DataFrame,
    candidate_details: dict[str, dict[str, Any]],
) -> int:
    if not candidates.empty and "kWp" in candidates.columns:
        return int(candidates["kWp"].nunique())
    viable_kwp = {
        round(float(detail.get("kWp", 0.0) or 0.0), 6)
        for detail in candidate_details.values()
        if detail.get("kWp") not in (None, "")
    }
    return len(viable_kwp)


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    field: str
    message: str

    def to_payload(self) -> dict[str, str]:
        return {"level": self.level, "field": self.field, "message": self.message}

    @classmethod
    def from_payload(cls, payload: dict[str, str]) -> "ValidationIssue":
        return cls(level=payload["level"], field=payload["field"], message=payload["message"])


@dataclass(frozen=True)
class LoadedConfigBundle:
    config: dict[str, Any]
    inverter_catalog: pd.DataFrame
    battery_catalog: pd.DataFrame
    solar_profile: np.ndarray
    hsp_month: np.ndarray
    demand_profile_7x24: np.ndarray
    day_weights: np.ndarray
    demand_month_factor: np.ndarray
    cop_kwp_table: pd.DataFrame
    cop_kwp_table_others: pd.DataFrame
    config_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    demand_profile_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    demand_profile_general_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    demand_profile_weights_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    month_profile_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    sun_profile_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_name: str = "config.xlsx"
    issues: tuple[ValidationIssue, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "inverter_catalog": _frame_to_payload(self.inverter_catalog),
            "battery_catalog": _frame_to_payload(self.battery_catalog),
            "solar_profile": _array_to_list(self.solar_profile),
            "hsp_month": _array_to_list(self.hsp_month),
            "demand_profile_7x24": _array_to_list(self.demand_profile_7x24),
            "day_weights": _array_to_list(self.day_weights),
            "demand_month_factor": _array_to_list(self.demand_month_factor),
            "cop_kwp_table": _frame_to_payload(self.cop_kwp_table),
            "cop_kwp_table_others": _frame_to_payload(self.cop_kwp_table_others),
            "config_table": _frame_to_payload(self.config_table),
            "demand_profile_table": _frame_to_payload(self.demand_profile_table),
            "demand_profile_general_table": _frame_to_payload(self.demand_profile_general_table),
            "demand_profile_weights_table": _frame_to_payload(self.demand_profile_weights_table),
            "month_profile_table": _frame_to_payload(self.month_profile_table),
            "sun_profile_table": _frame_to_payload(self.sun_profile_table),
            "source_name": self.source_name,
            "issues": [issue.to_payload() for issue in self.issues],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LoadedConfigBundle":
        return cls(
            config=payload["config"],
            inverter_catalog=_frame_from_payload(payload["inverter_catalog"]),
            battery_catalog=_frame_from_payload(payload["battery_catalog"]),
            solar_profile=np.asarray(payload["solar_profile"], dtype=float),
            hsp_month=np.asarray(payload["hsp_month"], dtype=float),
            demand_profile_7x24=np.asarray(payload["demand_profile_7x24"], dtype=float),
            day_weights=np.asarray(payload["day_weights"], dtype=float),
            demand_month_factor=np.asarray(payload["demand_month_factor"], dtype=float),
            cop_kwp_table=_frame_from_payload(payload["cop_kwp_table"]),
            cop_kwp_table_others=_frame_from_payload(payload["cop_kwp_table_others"]),
            config_table=_frame_from_payload(payload["config_table"]) if "config_table" in payload else pd.DataFrame(),
            demand_profile_table=_frame_from_payload(payload["demand_profile_table"]) if "demand_profile_table" in payload else pd.DataFrame(),
            demand_profile_general_table=_frame_from_payload(payload["demand_profile_general_table"]) if "demand_profile_general_table" in payload else pd.DataFrame(),
            demand_profile_weights_table=_frame_from_payload(payload["demand_profile_weights_table"]) if "demand_profile_weights_table" in payload else pd.DataFrame(),
            month_profile_table=_frame_from_payload(payload["month_profile_table"]) if "month_profile_table" in payload else pd.DataFrame(),
            sun_profile_table=_frame_from_payload(payload["sun_profile_table"]) if "sun_profile_table" in payload else pd.DataFrame(),
            source_name=payload.get("source_name", "config.xlsx"),
            issues=tuple(ValidationIssue.from_payload(issue) for issue in payload.get("issues", [])),
        )


@dataclass(frozen=True)
class ScanRunResult:
    candidates: pd.DataFrame
    best_candidate_key: str | None
    candidate_details: dict[str, dict[str, Any]]
    seed_kwp: float
    issues: tuple[ValidationIssue, ...] = ()
    evaluated_kwp_count: int = 0
    viable_kwp_count: int = 0
    discard_counts: dict[str, int] = field(default_factory=dict)
    discarded_points: tuple[dict[str, Any], ...] = ()

    def to_payload(self) -> dict[str, Any]:
        details_payload: dict[str, dict[str, Any]] = {}
        for key, detail in self.candidate_details.items():
            details_payload[key] = {
                "kWp": detail["kWp"],
                "battery_name": detail["battery_name"],
                "battery": detail["battery"],
                "inv_sel": detail["inv_sel"],
                "summary": detail["summary"],
                "value": detail["value"],
                "peak_ratio": detail["peak_ratio"],
                "best_battery": detail["best_battery"],
                "scan_order": detail["scan_order"],
                "candidate_key": detail["candidate_key"],
                "self_consumption_ratio": detail.get("self_consumption_ratio", 0.0),
                "self_sufficiency_ratio": detail.get("self_sufficiency_ratio", 0.0),
                "monthly": _frame_to_payload(detail["monthly"]),
            }
        return {
            "candidates": _frame_to_payload(self.candidates),
            "best_candidate_key": self.best_candidate_key,
            "candidate_details": details_payload,
            "seed_kwp": self.seed_kwp,
            "issues": [issue.to_payload() for issue in self.issues],
            "evaluated_kwp_count": int(self.evaluated_kwp_count),
            "viable_kwp_count": int(self.viable_kwp_count),
            "discard_counts": {str(key): int(value) for key, value in self.discard_counts.items()},
            "discarded_points": [dict(point) for point in self.discarded_points],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ScanRunResult":
        details: dict[str, dict[str, Any]] = {}
        for key, detail in payload["candidate_details"].items():
            details[key] = {
                "kWp": detail["kWp"],
                "battery_name": detail["battery_name"],
                "battery": detail["battery"],
                "inv_sel": detail["inv_sel"],
                "summary": detail["summary"],
                "value": detail["value"],
                "peak_ratio": detail["peak_ratio"],
                "best_battery": detail["best_battery"],
                "scan_order": detail["scan_order"],
                "candidate_key": detail["candidate_key"],
                "self_consumption_ratio": detail.get("self_consumption_ratio", 0.0),
                "self_sufficiency_ratio": detail.get("self_sufficiency_ratio", 0.0),
                "monthly": _frame_from_payload(detail["monthly"]),
            }
        candidates = _frame_from_payload(payload["candidates"])
        viable_kwp_count = int(payload.get("viable_kwp_count", _distinct_viable_kwp_count(candidates, details)))
        evaluated_kwp_count = int(payload.get("evaluated_kwp_count", viable_kwp_count))
        discard_counts = {
            str(key): int(value)
            for key, value in dict(payload.get("discard_counts") or {}).items()
        }
        discarded_points = tuple(dict(point) for point in (payload.get("discarded_points") or []))
        return cls(
            candidates=candidates,
            best_candidate_key=payload.get("best_candidate_key"),
            candidate_details=details,
            seed_kwp=float(payload["seed_kwp"]),
            issues=tuple(ValidationIssue.from_payload(issue) for issue in payload.get("issues", [])),
            evaluated_kwp_count=evaluated_kwp_count,
            viable_kwp_count=viable_kwp_count,
            discard_counts=discard_counts,
            discarded_points=discarded_points,
        )


@dataclass(frozen=True)
class ScenarioRunResult:
    candidate_key: str
    candidate: dict[str, Any]
    monthly: pd.DataFrame
    kpis: dict[str, Any]
    cash_flow: pd.DataFrame
    monthly_balance: pd.DataFrame
    npv_curve: pd.DataFrame
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioRecord:
    scenario_id: str
    name: str
    source_name: str
    config_bundle: LoadedConfigBundle
    scan_result: ScanRunResult | None = None
    scan_fingerprint: str | None = None
    selected_candidate_key: str | None = None
    dirty: bool = True
    last_run_at: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "source_name": self.source_name,
            "config_bundle": self.config_bundle.to_payload(),
            "scan_result": None if self.scan_result is None else self.scan_result.to_payload(),
            "scan_fingerprint": self.scan_fingerprint,
            "selected_candidate_key": self.selected_candidate_key,
            "dirty": self.dirty,
            "last_run_at": self.last_run_at,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ScenarioRecord":
        scan_payload = payload.get("scan_result")
        return cls(
            scenario_id=payload["scenario_id"],
            name=payload["name"],
            source_name=payload.get("source_name", "config.xlsx"),
            config_bundle=LoadedConfigBundle.from_payload(payload["config_bundle"]),
            scan_result=None if scan_payload is None else ScanRunResult.from_payload(scan_payload),
            scan_fingerprint=payload.get("scan_fingerprint"),
            selected_candidate_key=payload.get("selected_candidate_key"),
            dirty=bool(payload.get("dirty", True)),
            last_run_at=payload.get("last_run_at"),
        )


@dataclass(frozen=True)
class ScenarioSessionState:
    scenarios: tuple[ScenarioRecord, ...] = ()
    active_scenario_id: str | None = None
    comparison_scenario_ids: tuple[str, ...] = ()
    design_comparison_candidate_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    project_slug: str | None = None
    project_name: str | None = None
    project_dirty: bool = False

    @classmethod
    def empty(cls) -> "ScenarioSessionState":
        return cls()

    def to_payload(self) -> dict[str, Any]:
        return {
            "scenarios": [scenario.to_payload() for scenario in self.scenarios],
            "active_scenario_id": self.active_scenario_id,
            "comparison_scenario_ids": list(self.comparison_scenario_ids),
            "design_comparison_candidate_keys": {
                scenario_id: list(candidate_keys)
                for scenario_id, candidate_keys in self.design_comparison_candidate_keys.items()
            },
            "project_slug": self.project_slug,
            "project_name": self.project_name,
            "project_dirty": self.project_dirty,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ScenarioSessionState":
        if not payload:
            return cls.empty()
        return cls(
            scenarios=tuple(ScenarioRecord.from_payload(item) for item in payload.get("scenarios", [])),
            active_scenario_id=payload.get("active_scenario_id"),
            comparison_scenario_ids=tuple(payload.get("comparison_scenario_ids", [])),
            design_comparison_candidate_keys={
                str(scenario_id): tuple(candidate_keys)
                for scenario_id, candidate_keys in payload.get("design_comparison_candidate_keys", {}).items()
            },
            project_slug=payload.get("project_slug"),
            project_name=payload.get("project_name"),
            project_dirty=bool(payload.get("project_dirty", False)),
        )

    def get_scenario(self, scenario_id: str | None = None) -> ScenarioRecord | None:
        target_id = scenario_id or self.active_scenario_id
        if target_id is None:
            return None
        for scenario in self.scenarios:
            if scenario.scenario_id == target_id:
                return scenario
        return None


@dataclass(frozen=True)
class ClientSessionState:
    session_id: str
    active_scenario_id: str | None = None
    comparison_scenario_ids: tuple[str, ...] = ()
    design_comparison_candidate_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    selected_candidate_keys: dict[str, str | None] = field(default_factory=dict)
    project_slug: str | None = None
    project_name: str | None = None
    project_dirty: bool = False
    language: str = "es"
    revision: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "active_scenario_id": self.active_scenario_id,
            "comparison_scenario_ids": list(self.comparison_scenario_ids),
            "design_comparison_candidate_keys": {
                scenario_id: list(candidate_keys)
                for scenario_id, candidate_keys in self.design_comparison_candidate_keys.items()
            },
            "selected_candidate_keys": self.selected_candidate_keys,
            "project_slug": self.project_slug,
            "project_name": self.project_name,
            "project_dirty": self.project_dirty,
            "language": self.language,
            "revision": self.revision,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ClientSessionState | None":
        if not payload or not payload.get("session_id"):
            return None
        return cls(
            session_id=str(payload["session_id"]),
            active_scenario_id=payload.get("active_scenario_id"),
            comparison_scenario_ids=tuple(payload.get("comparison_scenario_ids", [])),
            design_comparison_candidate_keys={
                str(scenario_id): tuple(candidate_keys)
                for scenario_id, candidate_keys in payload.get("design_comparison_candidate_keys", {}).items()
            },
            selected_candidate_keys={
                str(scenario_id): None if candidate_key in (None, "") else str(candidate_key)
                for scenario_id, candidate_key in payload.get("selected_candidate_keys", {}).items()
            },
            project_slug=payload.get("project_slug"),
            project_name=payload.get("project_name"),
            project_dirty=bool(payload.get("project_dirty", False)),
            language=str(payload.get("language", "es")),
            revision=int(payload.get("revision", 0) or 0),
        )


@dataclass(frozen=True)
class ProjectScenarioManifest:
    scenario_id: str
    name: str
    source_name: str
    selected_candidate_key: str | None = None
    dirty: bool = True
    last_run_at: str | None = None
    scan_fingerprint: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "source_name": self.source_name,
            "selected_candidate_key": self.selected_candidate_key,
            "dirty": self.dirty,
            "last_run_at": self.last_run_at,
            "scan_fingerprint": self.scan_fingerprint,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ProjectScenarioManifest":
        return cls(
            scenario_id=str(payload["scenario_id"]),
            name=str(payload["name"]),
            source_name=str(payload.get("source_name", "config.xlsx")),
            selected_candidate_key=payload.get("selected_candidate_key"),
            dirty=bool(payload.get("dirty", True)),
            last_run_at=payload.get("last_run_at"),
            scan_fingerprint=payload.get("scan_fingerprint"),
        )


@dataclass(frozen=True)
class ProjectManifest:
    format_version: int
    name: str
    slug: str
    active_scenario_id: str | None = None
    comparison_scenario_ids: tuple[str, ...] = ()
    design_comparison_candidate_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    scenarios: tuple[ProjectScenarioManifest, ...] = ()
    ui_prefs: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "name": self.name,
            "slug": self.slug,
            "active_scenario_id": self.active_scenario_id,
            "comparison_scenario_ids": list(self.comparison_scenario_ids),
            "design_comparison_candidate_keys": {
                scenario_id: list(candidate_keys)
                for scenario_id, candidate_keys in self.design_comparison_candidate_keys.items()
            },
            "scenarios": [scenario.to_payload() for scenario in self.scenarios],
            "ui_prefs": self.ui_prefs,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ProjectManifest":
        return cls(
            format_version=int(payload["format_version"]),
            name=str(payload["name"]),
            slug=str(payload["slug"]),
            active_scenario_id=payload.get("active_scenario_id"),
            comparison_scenario_ids=tuple(payload.get("comparison_scenario_ids", [])),
            design_comparison_candidate_keys={
                str(scenario_id): tuple(candidate_keys)
                for scenario_id, candidate_keys in payload.get("design_comparison_candidate_keys", {}).items()
            },
            scenarios=tuple(ProjectScenarioManifest.from_payload(item) for item in payload.get("scenarios", [])),
            ui_prefs=dict(payload.get("ui_prefs", {})),
        )


@dataclass(frozen=True)
class MonteCarloRunRequest:
    mode: str = "fixed_candidate"
    selected_candidate_key: str | None = None
    seed: int = 0
    n_simulations: int | None = None
    return_samples: bool = False


@dataclass(frozen=True)
class PercentileSummary:
    p5: float | None = None
    p10: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None
    p95: float | None = None


@dataclass(frozen=True)
class MetricDistributionSummary:
    n_total: int
    n_finite: int
    n_missing: int
    mean: float | None
    std: float | None
    min: float | None
    max: float | None
    percentiles: PercentileSummary
    percentiles_over_finite_values: bool = True

    @property
    def p5(self) -> float | None:
        return self.percentiles.p5

    @property
    def p10(self) -> float | None:
        return self.percentiles.p10

    @property
    def p25(self) -> float | None:
        return self.percentiles.p25

    @property
    def p50(self) -> float | None:
        return self.percentiles.p50

    @property
    def p75(self) -> float | None:
        return self.percentiles.p75

    @property
    def p90(self) -> float | None:
        return self.percentiles.p90

    @property
    def p95(self) -> float | None:
        return self.percentiles.p95


@dataclass(frozen=True)
class RiskMetricSummary:
    probability_negative_npv: float
    probability_payback_within_horizon: float


@dataclass(frozen=True)
class MonteCarloSummary:
    npv: MetricDistributionSummary
    payback_years: MetricDistributionSummary
    self_consumption_ratio: MetricDistributionSummary
    self_sufficiency_ratio: MetricDistributionSummary
    annual_import_kwh: MetricDistributionSummary
    annual_export_kwh: MetricDistributionSummary


@dataclass(frozen=True)
class RiskViewBundle:
    histogram_bins: int
    ecdf_points: int
    histograms: dict[str, pd.DataFrame]
    densities: dict[str, pd.DataFrame]
    ecdfs: dict[str, pd.DataFrame]
    percentile_table: pd.DataFrame
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MonteCarloRunResult:
    request: MonteCarloRunRequest
    seed: int
    n_simulations: int
    selected_candidate_key: str
    baseline_best_candidate_key: str
    selected_kWp: float
    selected_battery: str
    active_uncertainty: dict[str, float]
    warnings: tuple[str, ...]
    summary: MonteCarloSummary
    risk_metrics: RiskMetricSummary
    views: RiskViewBundle
    samples: pd.DataFrame | None = None
