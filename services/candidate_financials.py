from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any

import pandas as pd

from pv_product.utils import ann_to_month_rate

from .cache import fingerprint_deterministic_input
from .economics_engine import (
    ResolvedHardwarePrice,
    calculate_economics_result,
    resolve_battery_hardware_price,
    resolve_economics_quantities,
    resolve_inverter_hardware_price,
    resolve_panel_hardware_price,
)
from .economics_tables import compute_economics_runtime_signature, normalize_economics_cost_items_frame, normalize_economics_price_items_frame
from .types import ScenarioRecord

MAX_CANDIDATE_FINANCIAL_SNAPSHOT_CACHE_ENTRIES = 128


class CandidateFinancialSnapshotUnavailableError(RuntimeError):
    """Raised when live scenario-backed finance cannot attach or validate a snapshot."""


@dataclass(frozen=True)
class CandidateFinancialSnapshot:
    """Canonical candidate finance contract.

    `project_price_year0_COP` is the canonical year-0 outflow.
    `capex_client_COP` is a presentation alias over the same value.
    """

    candidate_key: str
    project_price_year0_COP: float
    capex_client_COP: float
    monthly_cash_flow_series: tuple[float, ...]
    monthly_discounted_cash_flow_series: tuple[float, ...]
    cumulative_cash_flow_series: tuple[float, ...]
    cumulative_discounted_cash_flow_series: tuple[float, ...]
    visible_npv_COP: float
    payback_month: int | None
    payback_years: float | None
    financial_horizon_months: int
    financial_horizon_years: int
    economics_signature: str
    scan_fingerprint: str


@dataclass
class _CandidateFinancialSnapshotCacheEntry:
    snapshot: CandidateFinancialSnapshot
    inserted_at: float
    last_access_at: float


class CandidateFinancialSnapshotCache:
    def __init__(self, max_entries: int = MAX_CANDIDATE_FINANCIAL_SNAPSHOT_CACHE_ENTRIES):
        self._max_entries = max_entries
        self._lock = Lock()
        self._entries: OrderedDict[tuple[str, str, str], _CandidateFinancialSnapshotCacheEntry] = OrderedDict()

    def _prune_locked(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get(self, cache_key: tuple[str, str, str]) -> CandidateFinancialSnapshot | None:
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None
            entry.last_access_at = time.time()
            self._entries.move_to_end(cache_key)
            return entry.snapshot

    def put(self, cache_key: tuple[str, str, str], snapshot: CandidateFinancialSnapshot) -> None:
        now = time.time()
        with self._lock:
            self._entries[cache_key] = _CandidateFinancialSnapshotCacheEntry(
                snapshot=snapshot,
                inserted_at=now,
                last_access_at=now,
            )
            self._entries.move_to_end(cache_key)
            self._prune_locked()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


_CANDIDATE_FINANCIAL_SNAPSHOT_CACHE = CandidateFinancialSnapshotCache()


def get_candidate_financial_snapshot_cache() -> CandidateFinancialSnapshotCache:
    return _CANDIDATE_FINANCIAL_SNAPSHOT_CACHE


def _raise_snapshot_unavailable(candidate_key: str, message: str) -> None:
    raise CandidateFinancialSnapshotUnavailableError(f"Candidato '{candidate_key}': {message}")


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    return float(numeric) if pd.notna(numeric) else float(default)


def _scenario_scan_fingerprint(scenario: ScenarioRecord) -> str:
    return str(scenario.scan_fingerprint or fingerprint_deterministic_input(scenario.config_bundle))


def _financial_horizon_months(monthly: pd.DataFrame, config: dict[str, Any]) -> int:
    configured_years = max(0, int(round(_coerce_float(config.get("years"), default=0.0))))
    configured_months = configured_years * 12
    if configured_months <= 0:
        return int(len(monthly))
    return min(int(len(monthly)), configured_months)


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([0.0] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)


def _monthly_cash_flow_series(monthly: pd.DataFrame, *, month_count: int) -> tuple[float, ...]:
    if month_count <= 0:
        return ()
    truncated = monthly.iloc[:month_count].copy()
    if "Ahorro_COP" in truncated.columns:
        values = pd.to_numeric(truncated["Ahorro_COP"], errors="coerce").fillna(0.0)
        return tuple(float(value) for value in values.tolist())
    if "Utilidades_Netas_COP" in truncated.columns:
        values = pd.to_numeric(truncated["Utilidades_Netas_COP"], errors="coerce").fillna(0.0)
        return tuple(float(value) for value in values.tolist())

    pv_to_load = _numeric_series(truncated, "PV_a_Carga_kWh")
    batt_to_load = _numeric_series(truncated, "Bateria_a_Carga_kWh")
    exports = _numeric_series(truncated, "Exportacion_kWh")
    buy_tariff = _numeric_series(truncated, "Tarifa_Compra_COP_kWh")
    sell_tariff = _numeric_series(truncated, "Tarifa_Venta_COP_kWh")
    savings = (pv_to_load + batt_to_load) * buy_tariff
    export_income = exports * sell_tariff
    return tuple(float(value) for value in (savings + export_income).tolist())


def _hardware_prices_for_candidate(scenario: ScenarioRecord, detail: dict[str, Any]) -> dict[str, ResolvedHardwarePrice]:
    return {
        "none": ResolvedHardwarePrice(
            value_source="unavailable",
            hardware_binding="none",
            hardware_name="",
            unit_rate_COP=0.0,
        ),
        "panel": resolve_panel_hardware_price(scenario.config_bundle.config, scenario.config_bundle.panel_catalog),
        "inverter": resolve_inverter_hardware_price(detail, scenario.config_bundle.inverter_catalog),
        "battery": resolve_battery_hardware_price(detail, scenario.config_bundle.battery_catalog),
    }


def _economics_result_for_candidate(
    scenario: ScenarioRecord,
    candidate_key: str,
    *,
    normalized_cost_items: pd.DataFrame,
    normalized_price_items: pd.DataFrame,
):
    assert scenario.scan_result is not None
    detail = scenario.scan_result.candidate_details[candidate_key]
    quantities = resolve_economics_quantities(
        candidate_key=candidate_key,
        detail=detail,
        config=scenario.config_bundle.config,
        panel_catalog=scenario.config_bundle.panel_catalog,
    )
    return calculate_economics_result(
        economics_cost_items=normalized_cost_items,
        economics_price_items=normalized_price_items,
        quantities=quantities,
        hardware_prices=_hardware_prices_for_candidate(scenario, detail),
    )


def build_candidate_financial_snapshot(
    scenario: ScenarioRecord,
    candidate_key: str,
    *,
    use_cache: bool = True,
) -> CandidateFinancialSnapshot:
    if scenario.scan_result is None:
        raise ValueError(f"El escenario '{scenario.name}' no tiene un escaneo determinístico.")
    if candidate_key not in scenario.scan_result.candidate_details:
        raise KeyError(f"No existe el candidato '{candidate_key}' en el escenario '{scenario.name}'.")

    normalized_cost_items = normalize_economics_cost_items_frame(scenario.config_bundle.economics_cost_items_table)
    normalized_price_items = normalize_economics_price_items_frame(scenario.config_bundle.economics_price_items_table)
    economics_signature = compute_economics_runtime_signature(normalized_cost_items, normalized_price_items)
    scan_fingerprint = _scenario_scan_fingerprint(scenario)
    cache_key = (scan_fingerprint, economics_signature, str(candidate_key))
    cache = get_candidate_financial_snapshot_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    detail = scenario.scan_result.candidate_details[candidate_key]
    monthly = detail.get("monthly")
    monthly_frame = monthly.copy() if isinstance(monthly, pd.DataFrame) else pd.DataFrame()
    horizon_months = _financial_horizon_months(monthly_frame, scenario.config_bundle.config)
    monthly_cash_flow_series = _monthly_cash_flow_series(monthly_frame, month_count=horizon_months)

    monthly_discount_rate = ann_to_month_rate(_coerce_float(scenario.config_bundle.config.get("discount_rate"), default=0.0))
    discounted_cash_flow_series = tuple(
        float(value / ((1.0 + monthly_discount_rate) ** month_index))
        for month_index, value in enumerate(monthly_cash_flow_series, start=1)
    )

    economics_result = _economics_result_for_candidate(
        scenario,
        candidate_key,
        normalized_cost_items=normalized_cost_items,
        normalized_price_items=normalized_price_items,
    )
    project_price_year0 = float(economics_result.final_price_COP)

    cumulative_cash_flow: list[float] = []
    cumulative_discounted_cash_flow: list[float] = []
    running_nominal = -project_price_year0
    running_discounted = -project_price_year0
    payback_month: int | None = None
    for month_index, monthly_cash_flow in enumerate(monthly_cash_flow_series, start=1):
        running_nominal += float(monthly_cash_flow)
        running_discounted += float(discounted_cash_flow_series[month_index - 1])
        cumulative_cash_flow.append(float(running_nominal))
        cumulative_discounted_cash_flow.append(float(running_discounted))
        if payback_month is None and running_nominal >= 0.0:
            payback_month = month_index

    visible_npv = float(cumulative_discounted_cash_flow[-1]) if cumulative_discounted_cash_flow else float(-project_price_year0)
    horizon_years = int(math.ceil(horizon_months / 12.0)) if horizon_months > 0 else 0
    snapshot = CandidateFinancialSnapshot(
        candidate_key=str(candidate_key),
        project_price_year0_COP=float(project_price_year0),
        capex_client_COP=float(project_price_year0),
        monthly_cash_flow_series=tuple(float(value) for value in monthly_cash_flow_series),
        monthly_discounted_cash_flow_series=tuple(float(value) for value in discounted_cash_flow_series),
        cumulative_cash_flow_series=tuple(float(value) for value in cumulative_cash_flow),
        cumulative_discounted_cash_flow_series=tuple(float(value) for value in cumulative_discounted_cash_flow),
        visible_npv_COP=float(visible_npv),
        payback_month=payback_month,
        payback_years=None if payback_month is None else float(payback_month / 12.0),
        financial_horizon_months=int(horizon_months),
        financial_horizon_years=int(horizon_years),
        economics_signature=economics_signature,
        scan_fingerprint=scan_fingerprint,
    )
    cache.put(cache_key, snapshot)
    return snapshot


def validate_candidate_financial_snapshot(snapshot: CandidateFinancialSnapshot, *, candidate_key: str | None = None) -> CandidateFinancialSnapshot:
    resolved_candidate_key = str(candidate_key or getattr(snapshot, "candidate_key", "<unknown>"))
    if not isinstance(snapshot, CandidateFinancialSnapshot):
        _raise_snapshot_unavailable(resolved_candidate_key, "snapshot financiero inválido o ausente.")

    project_price_year0 = _coerce_float(getattr(snapshot, "project_price_year0_COP", None), default=float("nan"))
    capex_client = _coerce_float(getattr(snapshot, "capex_client_COP", None), default=float("nan"))
    visible_npv = _coerce_float(getattr(snapshot, "visible_npv_COP", None), default=float("nan"))
    if not math.isfinite(project_price_year0):
        _raise_snapshot_unavailable(resolved_candidate_key, "project_price_year0_COP inválido.")
    if not math.isfinite(capex_client):
        _raise_snapshot_unavailable(resolved_candidate_key, "capex_client_COP inválido.")
    if not math.isfinite(visible_npv):
        _raise_snapshot_unavailable(resolved_candidate_key, "visible_npv_COP inválido.")

    horizon_months = int(getattr(snapshot, "financial_horizon_months", -1))
    if horizon_months < 0:
        _raise_snapshot_unavailable(resolved_candidate_key, "financial_horizon_months inválido.")

    monthly_cash_flow_series = tuple(float(value) for value in getattr(snapshot, "monthly_cash_flow_series", ()))
    monthly_discounted_cash_flow_series = tuple(float(value) for value in getattr(snapshot, "monthly_discounted_cash_flow_series", ()))
    cumulative_cash_flow_series = tuple(float(value) for value in getattr(snapshot, "cumulative_cash_flow_series", ()))
    cumulative_discounted_cash_flow_series = tuple(
        float(value) for value in getattr(snapshot, "cumulative_discounted_cash_flow_series", ())
    )
    expected_length = horizon_months
    actual_lengths = {
        "monthly_cash_flow_series": len(monthly_cash_flow_series),
        "monthly_discounted_cash_flow_series": len(monthly_discounted_cash_flow_series),
        "cumulative_cash_flow_series": len(cumulative_cash_flow_series),
        "cumulative_discounted_cash_flow_series": len(cumulative_discounted_cash_flow_series),
    }
    invalid_lengths = {field: length for field, length in actual_lengths.items() if length != expected_length}
    if invalid_lengths:
        _raise_snapshot_unavailable(
            resolved_candidate_key,
            f"series financieras inconsistentes para horizon={expected_length}: {invalid_lengths}.",
        )

    if expected_length > 0:
        terminal_npv = cumulative_discounted_cash_flow_series[-1]
    else:
        terminal_npv = float(-project_price_year0)
    if not math.isclose(visible_npv, terminal_npv, rel_tol=0.0, abs_tol=1e-6):
        _raise_snapshot_unavailable(
            resolved_candidate_key,
            "visible_npv_COP no coincide con la serie acumulada descontada del snapshot.",
        )

    payback_month = getattr(snapshot, "payback_month", None)
    if payback_month is not None and int(payback_month) <= 0:
        _raise_snapshot_unavailable(resolved_candidate_key, "payback_month inválido.")
    payback_years = getattr(snapshot, "payback_years", None)
    if payback_month is not None:
        expected_payback_years = float(int(payback_month) / 12.0)
        if payback_years is None or not math.isclose(float(payback_years), expected_payback_years, rel_tol=0.0, abs_tol=1e-9):
            _raise_snapshot_unavailable(
                resolved_candidate_key,
                "payback_years no coincide con payback_month del snapshot.",
            )
    return snapshot


def build_candidate_financial_snapshots(scenario: ScenarioRecord) -> dict[str, CandidateFinancialSnapshot]:
    if scenario.scan_result is None:
        return {}
    return {
        candidate_key: build_candidate_financial_snapshot(scenario, candidate_key)
        for candidate_key in scenario.scan_result.candidate_details
    }


def resolve_financial_best_candidate_key(scenario: ScenarioRecord) -> str | None:
    snapshots = build_candidate_financial_snapshots(scenario)
    if not snapshots or scenario.scan_result is None:
        return None
    ordered = sorted(
        snapshots.items(),
        key=lambda item: (
            -float(item[1].visible_npv_COP),
            int(scenario.scan_result.candidate_details[item[0]].get("scan_order", 0)),
            item[0],
        ),
    )
    return str(ordered[0][0]) if ordered else None


def resolve_financial_candidate_key(
    scenario: ScenarioRecord,
    candidate_key: str | None = None,
) -> str | None:
    if scenario.scan_result is None:
        return None
    explicit_candidate_key = None if candidate_key in (None, "") else str(candidate_key)
    if explicit_candidate_key in scenario.scan_result.candidate_details:
        return explicit_candidate_key
    selected_candidate_key = None if scenario.selected_candidate_key in (None, "") else str(scenario.selected_candidate_key)
    if selected_candidate_key in scenario.scan_result.candidate_details:
        return selected_candidate_key
    return resolve_financial_best_candidate_key(scenario)


def snapshot_project_summary(snapshot: CandidateFinancialSnapshot) -> dict[str, Any]:
    validated_snapshot = validate_candidate_financial_snapshot(snapshot)
    return {
        "project_price_year0_COP": float(validated_snapshot.project_price_year0_COP),
        "capex_client": float(validated_snapshot.capex_client_COP),
        "cum_disc_final": float(validated_snapshot.visible_npv_COP),
        "payback_month": validated_snapshot.payback_month,
        "payback_years": validated_snapshot.payback_years,
        "financial_horizon_months": int(validated_snapshot.financial_horizon_months),
        "financial_horizon_years": int(validated_snapshot.financial_horizon_years),
        "economics_signature": validated_snapshot.economics_signature,
        "scan_fingerprint": validated_snapshot.scan_fingerprint,
    }


def snapshot_npv_at_horizon(snapshot: CandidateFinancialSnapshot, horizon_years: int) -> tuple[int, int, float]:
    validated_snapshot = validate_candidate_financial_snapshot(snapshot)
    if int(horizon_years) <= 0:
        return 0, 0, float(validated_snapshot.project_price_year0_COP)
    effective_years = max(1, min(int(horizon_years), int(validated_snapshot.financial_horizon_years)))
    horizon_months = min(int(validated_snapshot.financial_horizon_months), effective_years * 12)
    if horizon_months <= 0 or not validated_snapshot.cumulative_discounted_cash_flow_series:
        return effective_years, 0, float(-validated_snapshot.project_price_year0_COP)
    return effective_years, horizon_months, float(validated_snapshot.cumulative_discounted_cash_flow_series[horizon_months - 1])


def attach_candidate_financial_snapshot(
    scenario: ScenarioRecord,
    candidate_detail: dict[str, Any],
    candidate_key: str | None = None,
) -> dict[str, Any]:
    resolved_candidate_key = str(candidate_key or candidate_detail.get("candidate_key") or "")
    if not resolved_candidate_key:
        _raise_snapshot_unavailable("<missing>", "candidate_key ausente al adjuntar snapshot financiero.")
    try:
        snapshot = build_candidate_financial_snapshot(scenario, resolved_candidate_key)
    except Exception as exc:  # pragma: no cover - wrapped for fail-closed clarity
        raise CandidateFinancialSnapshotUnavailableError(
            f"Escenario '{scenario.name}', candidato '{resolved_candidate_key}': no se pudo construir CandidateFinancialSnapshot."
        ) from exc
    validated_snapshot = validate_candidate_financial_snapshot(snapshot, candidate_key=resolved_candidate_key)
    return {
        **candidate_detail,
        "financial_snapshot": validated_snapshot,
        "project_summary": snapshot_project_summary(validated_snapshot),
    }


def attach_candidate_financial_snapshots(
    scenario: ScenarioRecord,
    detail_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    if scenario.scan_result is None:
        raise CandidateFinancialSnapshotUnavailableError(
            f"Escenario '{scenario.name}': no hay scan_result para adjuntar snapshots financieros."
        )
    source_map = detail_map if detail_map is not None else scenario.scan_result.candidate_details
    return {
        str(candidate_key): attach_candidate_financial_snapshot(scenario, detail, candidate_key=str(candidate_key))
        for candidate_key, detail in source_map.items()
    }


def build_snapshot_monthly_frame(
    monthly: pd.DataFrame | None,
    snapshot: CandidateFinancialSnapshot,
) -> pd.DataFrame:
    validated_snapshot = validate_candidate_financial_snapshot(snapshot)
    horizon_months = int(validated_snapshot.financial_horizon_months)
    if isinstance(monthly, pd.DataFrame) and not monthly.empty:
        frame = monthly.iloc[:horizon_months].copy().reset_index(drop=True)
    else:
        frame = pd.DataFrame(index=range(horizon_months))
    if "Año_mes" not in frame.columns:
        frame["Año_mes"] = [f"{((index // 12) + 1):02d}-{((index % 12) + 1):02d}" for index in range(horizon_months)]
    frame["Ahorro_COP"] = list(validated_snapshot.monthly_cash_flow_series)
    frame["Cash_Flow_Discounted_COP"] = list(validated_snapshot.monthly_discounted_cash_flow_series)
    frame["Cumulative_Cash_Flow_COP"] = list(validated_snapshot.cumulative_cash_flow_series)
    frame["NPV_COP"] = list(validated_snapshot.cumulative_discounted_cash_flow_series)
    return frame
