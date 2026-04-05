from __future__ import annotations

import os
from dataclasses import dataclass

from .runtime_paths import is_frozen_runtime

DEFAULT_PARALLEL_WORKERS = 4
ALLOW_FROZEN_MULTIPROCESS_ENV = "PV_ALLOW_FROZEN_MULTIPROCESS"


@dataclass(frozen=True)
class ParallelWorkerDecision:
    requested_workers: int
    effective_workers: int
    worker_source: str
    serial_reason: str | None
    execution_mode: str
    frozen_runtime: bool
    frozen_parallel_opt_in: bool


def frozen_parallel_opt_in_enabled(*, env_var: str = ALLOW_FROZEN_MULTIPROCESS_ENV) -> bool:
    value = os.getenv(env_var)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def resolve_requested_workers(
    *,
    max_workers: int | None,
    primary_env_var: str,
    fallback_env_var: str | None = None,
) -> tuple[int, str]:
    if max_workers is not None:
        return max(1, int(max_workers)), "explicit"

    for env_var in (primary_env_var, fallback_env_var):
        if not env_var:
            continue
        env_value = os.getenv(env_var)
        if env_value:
            try:
                return max(1, int(env_value)), "env"
            except ValueError:
                return 1, "env"

    cpu_count = os.cpu_count() or 1
    return min(max(cpu_count - 1, 1), DEFAULT_PARALLEL_WORKERS), "heuristic"


def resolve_parallel_worker_decision(
    *,
    allow_parallel: bool,
    task_count: int,
    max_workers: int | None,
    primary_env_var: str,
    fallback_env_var: str | None = None,
    frozen_opt_in_env_var: str = ALLOW_FROZEN_MULTIPROCESS_ENV,
) -> ParallelWorkerDecision:
    requested_workers, worker_source = resolve_requested_workers(
        max_workers=max_workers,
        primary_env_var=primary_env_var,
        fallback_env_var=fallback_env_var,
    )
    frozen_runtime = bool(is_frozen_runtime())
    frozen_parallel_opt_in = frozen_parallel_opt_in_enabled(env_var=frozen_opt_in_env_var)

    serial_reason: str | None = None
    if not allow_parallel:
        serial_reason = "allow_parallel_false"
    elif requested_workers <= 1:
        serial_reason = "worker_count_leq_1"
    elif task_count <= 1:
        serial_reason = "single_task"
    elif frozen_runtime and not frozen_parallel_opt_in:
        serial_reason = "frozen_runtime_default_serial"

    execution_mode = "serial" if serial_reason else "parallel"
    effective_workers = 1 if execution_mode == "serial" else requested_workers
    return ParallelWorkerDecision(
        requested_workers=requested_workers,
        effective_workers=effective_workers,
        worker_source=worker_source,
        serial_reason=serial_reason,
        execution_mode=execution_mode,
        frozen_runtime=frozen_runtime,
        frozen_parallel_opt_in=frozen_parallel_opt_in,
    )
