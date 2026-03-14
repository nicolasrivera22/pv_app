from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from uuid import uuid4

from .types import MonteCarloRunResult

MAX_RISK_RESULTS = 16

_LOCK = Lock()
_RESULTS: OrderedDict[str, MonteCarloRunResult] = OrderedDict()


def _prune_locked(max_entries: int = MAX_RISK_RESULTS) -> None:
    while len(_RESULTS) > max_entries:
        _RESULTS.popitem(last=False)


def store_risk_result(result: MonteCarloRunResult) -> str:
    result_id = f"mc-{uuid4().hex[:10]}"
    with _LOCK:
        _RESULTS[result_id] = result
        _RESULTS.move_to_end(result_id)
        _prune_locked()
    return result_id


def get_risk_result(result_id: str) -> MonteCarloRunResult | None:
    with _LOCK:
        result = _RESULTS.get(result_id)
        if result is None:
            return None
        _RESULTS.move_to_end(result_id)
        return result


def clear_expired_risk_results(max_entries: int = MAX_RISK_RESULTS) -> None:
    with _LOCK:
        _prune_locked(max_entries=max_entries)


def clear_risk_results() -> None:
    with _LOCK:
        _RESULTS.clear()
