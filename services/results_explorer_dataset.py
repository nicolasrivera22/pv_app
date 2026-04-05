from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import pandas as pd

from .cache import fingerprint_deterministic_input
from .candidate_financials import attach_candidate_financial_snapshots, snapshot_npv_at_horizon
from .economics_tables import compute_economics_runtime_signature
from .i18n import tr
from .result_views import EXPLORER_SUBSET_KEY_NO_BATTERY, EXPLORER_SUBSET_KEY_OPTIMAL, battery_family_key_from_detail, summarize_energy_metrics
from .ui_schema import format_metric

MAX_RESULTS_EXPLORER_DATASET_CACHE_ENTRIES = 8
MAX_RESULTS_EXPLORER_HORIZON_TABLES_PER_DATASET = 8

RESULTS_EXPLORER_BASE_ROW_COLUMNS = [
    "candidate_key",
    "scan_order",
    "kWp",
    "battery_name_raw",
    "battery_kwh",
    "battery_family_key",
    "capex_client",
    "project_payback_years",
    "self_consumption_ratio",
    "self_sufficiency_ratio",
    "annual_import_kwh",
    "annual_export_kwh",
    "peak_ratio",
]

RESULTS_EXPLORER_HORIZON_TABLE_COLUMNS = [
    "scan_order",
    "candidate_key",
    "kWp",
    "battery_name_raw",
    "battery_kwh",
    "battery_family_key",
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

RESULTS_EXPLORER_FRONTEND_PAYLOAD_COLUMNS = [
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
    "candidate_key",
    "battery_family_key",
]


@dataclass(frozen=True)
class ResultsExplorerDataset:
    scan_fingerprint: str
    economics_signature: str
    attached_details: dict[str, dict[str, Any]]
    base_rows: pd.DataFrame
    family_records: tuple[dict[str, Any], ...]


@dataclass
class _ResultsExplorerDatasetCacheEntry:
    dataset: ResultsExplorerDataset
    inserted_at: float
    last_access_at: float
    horizon_tables: OrderedDict[int, pd.DataFrame] = field(default_factory=OrderedDict)


class ResultsExplorerDatasetCache:
    def __init__(
        self,
        max_entries: int = MAX_RESULTS_EXPLORER_DATASET_CACHE_ENTRIES,
        *,
        max_horizon_tables_per_dataset: int = MAX_RESULTS_EXPLORER_HORIZON_TABLES_PER_DATASET,
    ):
        self._max_entries = max_entries
        self._max_horizon_tables_per_dataset = max_horizon_tables_per_dataset
        self._lock = Lock()
        self._entries: OrderedDict[tuple[str, str], _ResultsExplorerDatasetCacheEntry] = OrderedDict()

    def _prune_locked(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def _prune_horizon_tables_locked(self, entry: _ResultsExplorerDatasetCacheEntry) -> None:
        while len(entry.horizon_tables) > self._max_horizon_tables_per_dataset:
            entry.horizon_tables.popitem(last=False)

    def get(self, cache_key: tuple[str, str]) -> ResultsExplorerDataset | None:
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None
            entry.last_access_at = time.time()
            self._entries.move_to_end(cache_key)
            return entry.dataset

    def put(self, cache_key: tuple[str, str], dataset: ResultsExplorerDataset) -> ResultsExplorerDataset:
        now = time.time()
        with self._lock:
            self._entries[cache_key] = _ResultsExplorerDatasetCacheEntry(
                dataset=dataset,
                inserted_at=now,
                last_access_at=now,
            )
            self._entries.move_to_end(cache_key)
            self._prune_locked()
            return dataset

    def get_horizon_table(self, cache_key: tuple[str, str], horizon_years: int) -> pd.DataFrame | None:
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None
            entry.last_access_at = time.time()
            self._entries.move_to_end(cache_key)
            frame = entry.horizon_tables.get(int(horizon_years))
            if frame is None:
                return None
            entry.horizon_tables.move_to_end(int(horizon_years))
            return frame.copy()

    def put_horizon_table(self, cache_key: tuple[str, str], horizon_years: int, frame: pd.DataFrame) -> pd.DataFrame:
        now = time.time()
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                raise KeyError(f"Dataset cache key no encontrado: {cache_key!r}")
            entry.last_access_at = now
            self._entries.move_to_end(cache_key)
            entry.horizon_tables[int(horizon_years)] = frame.copy()
            entry.horizon_tables.move_to_end(int(horizon_years))
            self._prune_horizon_tables_locked(entry)
            return frame

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


_RESULTS_EXPLORER_DATASET_CACHE = ResultsExplorerDatasetCache()


def get_results_explorer_dataset_cache() -> ResultsExplorerDatasetCache:
    return _RESULTS_EXPLORER_DATASET_CACHE


def _scenario_scan_fingerprint(scenario) -> str:
    return str(scenario.scan_fingerprint or fingerprint_deterministic_input(scenario.config_bundle))


def _scenario_economics_signature(scenario) -> str:
    return compute_economics_runtime_signature(
        scenario.config_bundle.economics_cost_items_table,
        scenario.config_bundle.economics_price_items_table,
    )


def _safe_battery_kwh(detail: dict[str, Any]) -> float | None:
    battery = detail.get("battery") if isinstance(detail.get("battery"), dict) else {}
    value = (battery or {}).get("nom_kWh")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric) or numeric <= 0:
        return None
    return float(numeric)


def _family_record_from_detail(detail: dict[str, Any]) -> dict[str, Any]:
    battery_name_raw = str(detail.get("battery_name") or "").strip()
    battery_kwh = _safe_battery_kwh(detail)
    family_key = battery_family_key_from_detail(detail)
    lowered = battery_name_raw.casefold()
    is_no_battery = battery_kwh is None and lowered in {"", "none", "bat-0"}
    return {
        "battery_family_key": family_key,
        "battery_kwh": battery_kwh,
        "is_no_battery": bool(is_no_battery),
        "battery_name_raw": battery_name_raw,
    }


def _build_family_records(attached_details: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    records_by_key: dict[str, dict[str, Any]] = {}
    for detail in attached_details.values():
        record = _family_record_from_detail(detail)
        records_by_key.setdefault(str(record["battery_family_key"]), record)
    return tuple(records_by_key.values())


def _build_base_rows(attached_details: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate_key, detail in attached_details.items():
        energy = summarize_energy_metrics(detail["monthly"])
        project_summary = dict(detail.get("project_summary") or {})
        legacy_summary = dict(detail.get("summary") or {})
        project_payback_years = legacy_summary.get("payback_years")
        if project_payback_years in (None, ""):
            project_payback_years = project_summary.get("payback_years")
        rows.append(
            {
                "candidate_key": str(candidate_key),
                "scan_order": int(detail.get("scan_order", 0) or 0),
                "kWp": round(float(detail.get("kWp", 0.0) or 0.0), 3),
                "battery_name_raw": str(detail.get("battery_name") or "None"),
                "battery_kwh": _safe_battery_kwh(detail),
                "battery_family_key": battery_family_key_from_detail(detail),
                "capex_client": float(project_summary.get("capex_client")) if project_summary.get("capex_client") is not None else None,
                "project_payback_years": project_payback_years,
                "self_consumption_ratio": float(energy["self_consumption_ratio"]),
                "self_sufficiency_ratio": float(energy["self_sufficiency_ratio"]),
                "annual_import_kwh": float(energy["annual_import_kwh"]),
                "annual_export_kwh": float(energy["annual_export_kwh"]),
                "peak_ratio": float(detail.get("peak_ratio", 0.0) or 0.0),
            }
        )
    if not rows:
        return pd.DataFrame(columns=RESULTS_EXPLORER_BASE_ROW_COLUMNS)
    frame = pd.DataFrame(rows)
    return frame.loc[:, RESULTS_EXPLORER_BASE_ROW_COLUMNS].sort_values(["scan_order", "candidate_key"], kind="mergesort").reset_index(drop=True)


def _finalize_horizon_table(frame: pd.DataFrame, *, display_metric_key: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=RESULTS_EXPLORER_HORIZON_TABLE_COLUMNS)
    value_ascending = display_metric_key == "capex_client"
    ordered = frame.sort_values(
        by=["kWp", "NPV_COP", "scan_order"],
        ascending=[True, value_ascending, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ordered["best_battery_for_kwp"] = False
    best_idx = ordered.groupby("kWp", sort=False).head(1).index
    ordered.loc[best_idx, "best_battery_for_kwp"] = True
    return ordered.loc[:, RESULTS_EXPLORER_HORIZON_TABLE_COLUMNS]


def _family_sort_tuple(record: dict[str, Any]) -> tuple[Any, ...]:
    family_key = str(record.get("battery_family_key") or "")
    battery_kwh = record.get("battery_kwh")
    sort_bucket = 0 if family_key == EXPLORER_SUBSET_KEY_NO_BATTERY else 1
    sort_kwh = float(battery_kwh) if battery_kwh is not None and pd.notna(battery_kwh) else float("inf")
    return (sort_bucket, sort_kwh, str(record.get("battery_name_raw") or ""), family_key)


def _family_label_from_record(record: dict[str, Any], *, lang: str = "es") -> str:
    family_key = str(record.get("battery_family_key") or "")
    battery_name_raw = str(record.get("battery_name_raw") or "").strip()
    battery_kwh = record.get("battery_kwh")
    is_no_battery = bool(record.get("is_no_battery")) or family_key == EXPLORER_SUBSET_KEY_NO_BATTERY
    if is_no_battery:
        return tr("common.no_battery", lang)
    if battery_kwh is not None and pd.notna(battery_kwh):
        suffix = "batería" if lang == "es" else "battery"
        return f"{float(battery_kwh):.1f} kWh {suffix}"
    return battery_name_raw or tr("common.no_battery", lang)


def build_results_explorer_family_options(
    family_records: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    *,
    lang: str = "es",
) -> list[dict[str, str]]:
    options = [{"label": tr("workbench.explorer.family.optimal", lang), "value": EXPLORER_SUBSET_KEY_OPTIMAL}]
    if not family_records:
        return options
    ordered_records = sorted((dict(record) for record in family_records), key=_family_sort_tuple)
    options.extend(
        {
            "label": _family_label_from_record(record, lang=lang),
            "value": str(record["battery_family_key"]),
        }
        for record in ordered_records
    )
    return options


def subset_label_from_family_records(
    family_records: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    subset_key: str | None,
    *,
    lang: str = "es",
) -> str:
    if subset_key == EXPLORER_SUBSET_KEY_OPTIMAL:
        return tr("workbench.explorer.family.optimal", lang)
    resolved_key = str(subset_key or "").strip()
    if not resolved_key:
        return ""
    for record in family_records:
        if str(record.get("battery_family_key") or "") == resolved_key:
            return _family_label_from_record(record, lang=lang)
    return ""


def localize_results_explorer_table(candidate_table: pd.DataFrame, *, lang: str = "es") -> pd.DataFrame:
    frame = candidate_table.copy()
    if frame.empty:
        frame["battery"] = pd.Series(dtype=object)
        frame["battery_family_label"] = pd.Series(dtype=object)
        return frame
    frame["battery"] = frame["battery_name_raw"].map(lambda value: format_metric("selected_battery", value, lang))
    frame["battery_family_label"] = frame.apply(
        lambda row: _family_label_from_record(
            {
                "battery_family_key": row.get("battery_family_key"),
                "battery_kwh": row.get("battery_kwh"),
                "battery_name_raw": row.get("battery_name_raw"),
                "is_no_battery": str(row.get("battery_family_key") or "") == EXPLORER_SUBSET_KEY_NO_BATTERY,
            },
            lang=lang,
        ),
        axis=1,
    )
    return frame


def build_results_explorer_frontend_table(candidate_table: pd.DataFrame) -> pd.DataFrame:
    if candidate_table.empty:
        return pd.DataFrame(columns=RESULTS_EXPLORER_FRONTEND_PAYLOAD_COLUMNS)
    available_columns = [column for column in RESULTS_EXPLORER_FRONTEND_PAYLOAD_COLUMNS if column in candidate_table.columns]
    return candidate_table.loc[:, available_columns].copy()


def build_results_explorer_dataset(scenario) -> ResultsExplorerDataset:
    if scenario is None or scenario.scan_result is None:
        raise ValueError("No hay scan_result para construir ResultsExplorerDataset.")
    scan_fingerprint = _scenario_scan_fingerprint(scenario)
    economics_signature = _scenario_economics_signature(scenario)
    cache_key = (scan_fingerprint, economics_signature)
    cache = get_results_explorer_dataset_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    attached_details = attach_candidate_financial_snapshots(scenario)
    dataset = ResultsExplorerDataset(
        scan_fingerprint=scan_fingerprint,
        economics_signature=economics_signature,
        attached_details=attached_details,
        base_rows=_build_base_rows(attached_details),
        family_records=_build_family_records(attached_details),
    )
    return cache.put(cache_key, dataset)


def build_results_explorer_horizon_table(dataset: ResultsExplorerDataset, horizon_years: int) -> pd.DataFrame:
    cache_key = (dataset.scan_fingerprint, dataset.economics_signature)
    cache = get_results_explorer_dataset_cache()
    cached = cache.get_horizon_table(cache_key, int(horizon_years))
    if cached is not None:
        return cached

    display_metric_key = "capex_client" if int(horizon_years) == 0 else "NPV_COP"
    frame = dataset.base_rows.copy()
    if frame.empty:
        return _finalize_horizon_table(pd.DataFrame(columns=RESULTS_EXPLORER_HORIZON_TABLE_COLUMNS), display_metric_key=display_metric_key)

    if int(horizon_years) == 0:
        frame["NPV_COP"] = frame["capex_client"]
    else:
        frame["NPV_COP"] = frame["candidate_key"].map(
            lambda candidate_key: snapshot_npv_at_horizon(
                dataset.attached_details[str(candidate_key)]["financial_snapshot"],
                int(horizon_years),
            )[2]
        )
    frame["payback_years"] = frame["project_payback_years"]
    finalized = _finalize_horizon_table(frame, display_metric_key=display_metric_key)
    return cache.put_horizon_table(cache_key, int(horizon_years), finalized)
