from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd

from .types import LoadedConfigBundle, ScanRunResult

DETERMINISTIC_CACHE_SCHEMA_VERSION = 1
MAX_DETERMINISTIC_CACHE_ENTRIES = 16
_MONTE_CARLO_CONFIG_FIELDS = ("mc_PR_std", "mc_buy_std", "mc_sell_std", "mc_demand_std", "mc_n_simulations")


def _normalize_deterministic_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(config)
    for field in _MONTE_CARLO_CONFIG_FIELDS:
        if field in normalized:
            if field == "mc_n_simulations":
                normalized[field] = 0
            else:
                normalized[field] = 0.0
    return normalized


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"Unsupported value for fingerprint serialization: {type(value)!r}")


def _frame_payload(frame: pd.DataFrame) -> dict[str, Any]:
    sanitized = frame.copy()
    sanitized.columns = [str(column) for column in sanitized.columns]
    return sanitized.to_dict(orient="split")


def fingerprint_deterministic_input(config_bundle: LoadedConfigBundle) -> str:
    fingerprint_payload = {
        "cache_schema_version": DETERMINISTIC_CACHE_SCHEMA_VERSION,
        "config": _normalize_deterministic_config(config_bundle.config),
        "inverter_catalog": _frame_payload(config_bundle.inverter_catalog),
        "battery_catalog": _frame_payload(config_bundle.battery_catalog),
        "solar_profile": np.asarray(config_bundle.solar_profile, dtype=float).tolist(),
        "hsp_month": np.asarray(config_bundle.hsp_month, dtype=float).tolist(),
        "demand_profile_7x24": np.asarray(config_bundle.demand_profile_7x24, dtype=float).tolist(),
        "day_weights": np.asarray(config_bundle.day_weights, dtype=float).tolist(),
        "demand_month_factor": np.asarray(config_bundle.demand_month_factor, dtype=float).tolist(),
        "cop_kwp_table": _frame_payload(config_bundle.cop_kwp_table),
        "cop_kwp_table_others": _frame_payload(config_bundle.cop_kwp_table_others),
        "config_table": _frame_payload(config_bundle.config_table),
        "demand_profile_table": _frame_payload(config_bundle.demand_profile_table),
        "demand_profile_general_table": _frame_payload(config_bundle.demand_profile_general_table),
        "demand_profile_weights_table": _frame_payload(config_bundle.demand_profile_weights_table),
        "month_profile_table": _frame_payload(config_bundle.month_profile_table),
        "sun_profile_table": _frame_payload(config_bundle.sun_profile_table),
    }
    encoded = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class _DeterministicCacheEntry:
    scan_result: ScanRunResult
    inserted_at: float
    last_access_at: float


class DeterministicScanCache:
    def __init__(self, max_entries: int = MAX_DETERMINISTIC_CACHE_ENTRIES):
        self._max_entries = max_entries
        self._lock = Lock()
        self._entries: OrderedDict[str, _DeterministicCacheEntry] = OrderedDict()

    def _prune_locked(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get(self, fingerprint: str) -> ScanRunResult | None:
        with self._lock:
            entry = self._entries.get(fingerprint)
            if entry is None:
                return None
            entry.last_access_at = time.time()
            self._entries.move_to_end(fingerprint)
            return entry.scan_result

    def put(self, fingerprint: str, scan_result: ScanRunResult) -> None:
        now = time.time()
        with self._lock:
            self._entries[fingerprint] = _DeterministicCacheEntry(
                scan_result=scan_result,
                inserted_at=now,
                last_access_at=now,
            )
            self._entries.move_to_end(fingerprint)
            self._prune_locked()

    def invalidate(self, fingerprint: str | None = None) -> None:
        with self._lock:
            if fingerprint is None:
                self._entries.clear()
            else:
                self._entries.pop(fingerprint, None)

    def clear(self) -> None:
        self.invalidate(None)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


_DETERMINISTIC_SCAN_CACHE = DeterministicScanCache()


def get_deterministic_cache() -> DeterministicScanCache:
    return _DETERMINISTIC_SCAN_CACHE
