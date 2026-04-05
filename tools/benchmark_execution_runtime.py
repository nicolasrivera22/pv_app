from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
from dataclasses import replace
from pathlib import Path
import sys
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("MPLCONFIGDIR", str((REPO_ROOT / ".pv_runtime_cache" / "mpl_benchmark").resolve()))

from services.runtime_paths import configure_runtime_environment

configure_runtime_environment()

import services.deterministic_executor as deterministic_executor
import services.execution_parallel as execution_parallel
import services.stochastic_runner as stochastic_runner
from services import load_example_config, run_scan


def _fast_bundle():
    bundle = load_example_config()
    return replace(
        bundle,
        config={
            **bundle.config,
            "years": 5,
            "modules_span_each_side": 4,
            "kWp_min": 12.0,
            "kWp_max": 18.0,
            "mc_n_simulations": 32,
        },
    )


@contextmanager
def _temporary_env(**values):
    previous: dict[str, str | None] = {}
    for key, value in values.items():
        previous[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = str(value)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _measure(label: str, fn) -> tuple[str, float, object]:
    started = perf_counter()
    value = fn()
    return label, perf_counter() - started, value


def _capture_logger(logger_name: str):
    logger = logging.getLogger(logger_name)
    handler = _ListHandler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger, handler, previous_level


def _release_logger(logger_obj: logging.Logger, handler: logging.Handler, previous_level: int) -> None:
    logger_obj.removeHandler(handler)
    logger_obj.setLevel(previous_level)


def _measure_deterministic(bundle, *, allow_parallel: bool, max_workers: int):
    logger_obj, handler, previous_level = _capture_logger(deterministic_executor.__name__)
    try:
        label, seconds, payload = _measure(
            f"deterministic_allow_{int(allow_parallel)}_workers_{max_workers}",
            lambda: deterministic_executor.run_deterministic_scan_tasks(
                bundle,
                allow_parallel=allow_parallel,
                max_workers=max_workers,
            ),
        )
    finally:
        _release_logger(logger_obj, handler, previous_level)

    _seed_kwp, tasks = deterministic_executor._build_tasks(bundle)
    decision = deterministic_executor._resolve_worker_decision(
        allow_parallel=allow_parallel,
        task_count=len(tasks),
        max_workers=max_workers,
    )
    return {
        "label": label,
        "seconds": seconds,
        "row_count": len(payload[1]),
        "planned_execution_mode": decision.execution_mode,
        "planned_serial_reason": decision.serial_reason,
        "planned_requested_workers": decision.requested_workers,
        "planned_effective_workers": decision.effective_workers,
        "frozen_runtime": decision.frozen_runtime,
        "frozen_parallel_opt_in": decision.frozen_parallel_opt_in,
        "fallback_logged": any("event=deterministic_scan_parallel_fallback" in message for message in handler.messages),
    }


def _simulate_frozen_decisions():
    original = execution_parallel.is_frozen_runtime
    execution_parallel.is_frozen_runtime = lambda: True
    try:
        with _temporary_env(PV_ALLOW_FROZEN_MULTIPROCESS=None):
            default_serial = deterministic_executor._resolve_worker_decision(
                allow_parallel=True,
                task_count=4,
                max_workers=4,
            )
        with _temporary_env(PV_ALLOW_FROZEN_MULTIPROCESS="1"):
            opt_in_parallel = deterministic_executor._resolve_worker_decision(
                allow_parallel=True,
                task_count=4,
                max_workers=4,
            )
    finally:
        execution_parallel.is_frozen_runtime = original

    return {
        "default": {
            "execution_mode": default_serial.execution_mode,
            "serial_reason": default_serial.serial_reason,
        },
        "opt_in": {
            "execution_mode": opt_in_parallel.execution_mode,
            "serial_reason": opt_in_parallel.serial_reason,
        },
    }


def _measure_monte_carlo(bundle, baseline, *, n_simulations: int, max_workers: int):
    request, _ = stochastic_runner._resolve_request(
        bundle,
        baseline.best_candidate_key,
        seed=7,
        n_simulations=n_simulations,
        return_samples=False,
        mode=stochastic_runner.MC_SUPPORTED_MODE,
        lang="es",
    )
    detail = baseline.candidate_details[baseline.best_candidate_key]

    with _temporary_env(
        PV_MC_MAX_WORKERS=str(max_workers),
        PV_SCAN_MAX_WORKERS=None,
        PV_ALLOW_FROZEN_MULTIPROCESS=None,
    ):
        label, seconds, payload = _measure(
            f"mc_n_{n_simulations}_workers_{max_workers}",
            lambda: stochastic_runner._simulate_fixed_candidate_draws(bundle, detail, request, lang="es"),
        )
    _, _, report = payload
    return {
        "label": label,
        "seconds": seconds,
        "execution_mode": report.execution_mode,
        "serial_reason": report.serial_reason,
        "requested_workers": report.requested_workers,
        "effective_workers": report.effective_workers,
        "chunk_count": report.chunk_count,
        "chunk_size": report.chunk_size,
        "fallback_to_serial": report.fallback_to_serial,
        "fallback_reason": report.fallback_reason,
        "frozen_runtime": report.frozen_runtime,
        "frozen_parallel_opt_in": report.frozen_parallel_opt_in,
    }


def main() -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)

    deterministic_results = {
        "serial": _measure_deterministic(bundle, allow_parallel=False, max_workers=1),
        "parallel_attempt": _measure_deterministic(bundle, allow_parallel=True, max_workers=4),
        "frozen_policy_simulation": _simulate_frozen_decisions(),
    }

    monte_carlo_results = {
        str(n_simulations): {
            "serial": _measure_monte_carlo(bundle, baseline, n_simulations=n_simulations, max_workers=1),
            "parallel_attempt": _measure_monte_carlo(bundle, baseline, n_simulations=n_simulations, max_workers=4),
        }
        for n_simulations in (8, 32, 128, 512)
    }

    print(
        json.dumps(
            {
                "candidate_count": len(baseline.candidates),
                "best_candidate_key": baseline.best_candidate_key,
                "deterministic": deterministic_results,
                "monte_carlo": monte_carlo_results,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
