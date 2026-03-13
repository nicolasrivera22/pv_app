from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd


def _frame_to_payload(frame: pd.DataFrame) -> dict[str, Any]:
    return frame.to_dict(orient="split")


def _frame_from_payload(payload: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(data=payload["data"], columns=payload["columns"], index=payload["index"])


def _array_to_list(value: np.ndarray) -> list[Any]:
    return value.tolist()


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
            source_name=payload.get("source_name", "config.xlsx"),
            issues=tuple(ValidationIssue.from_payload(issue) for issue in payload.get("issues", [])),
        )


@dataclass(frozen=True)
class ScanRunResult:
    candidates: pd.DataFrame
    best_candidate_key: str
    candidate_details: dict[str, dict[str, Any]]
    seed_kwp: float
    issues: tuple[ValidationIssue, ...] = ()

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
                "candidate_key": detail["candidate_key"],
                "self_consumption_ratio": detail.get("self_consumption_ratio", 0.0),
                "monthly": _frame_to_payload(detail["monthly"]),
            }
        return {
            "candidates": _frame_to_payload(self.candidates),
            "best_candidate_key": self.best_candidate_key,
            "candidate_details": details_payload,
            "seed_kwp": self.seed_kwp,
            "issues": [issue.to_payload() for issue in self.issues],
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
                "candidate_key": detail["candidate_key"],
                "self_consumption_ratio": detail.get("self_consumption_ratio", 0.0),
                "monthly": _frame_from_payload(detail["monthly"]),
            }
        return cls(
            candidates=_frame_from_payload(payload["candidates"]),
            best_candidate_key=payload["best_candidate_key"],
            candidate_details=details,
            seed_kwp=float(payload["seed_kwp"]),
            issues=tuple(ValidationIssue.from_payload(issue) for issue in payload.get("issues", [])),
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
