from __future__ import annotations

import logging
from pathlib import Path

import pytest

import services.deterministic_executor as deterministic_executor


def test_gitignore_covers_runtime_noise_and_keeps_repo_inputs() -> None:
    contents = Path(".gitignore").read_text(encoding="utf-8")

    for required in [
        ".DS_Store",
        "__MACOSX/",
        "__pycache__/",
        "*.py[cod]",
        ".pytest_cache/",
        ".coverage*",
        "htmlcov/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".venv/",
        "venv/",
        "env/",
        "build/",
        "dist/",
        "*.egg-info/",
        ".pv_runtime_cache/",
        "Resultados/",
        "Resultados_rel/",
        "proyectos/*/exports/",
        "proyectos/*/inputs/",
        "*.log",
    ]:
        assert required in contents

    for keep in [
        "!PV_inputs.xlsx",
        "!pv_app.spec",
        "!proyectos/*/project.json",
    ]:
        assert keep in contents


def test_worker_selection_prefers_explicit_then_env_then_heuristic(monkeypatch) -> None:
    monkeypatch.setenv("PV_SCAN_MAX_WORKERS", "7")
    monkeypatch.setattr(deterministic_executor.execution_parallel.os, "cpu_count", lambda: 12)
    monkeypatch.setattr(deterministic_executor.execution_parallel, "is_frozen_runtime", lambda: False)

    explicit = deterministic_executor._resolve_worker_decision(
        allow_parallel=True,
        task_count=3,
        max_workers=2,
    )
    assert explicit.requested_workers == 2
    assert explicit.effective_workers == 2
    assert explicit.worker_source == "explicit"
    assert explicit.execution_mode == "parallel"
    assert explicit.serial_reason is None

    env = deterministic_executor._resolve_worker_decision(
        allow_parallel=True,
        task_count=3,
        max_workers=None,
    )
    assert env.requested_workers == 7
    assert env.effective_workers == 7
    assert env.worker_source == "env"
    assert env.execution_mode == "parallel"

    monkeypatch.delenv("PV_SCAN_MAX_WORKERS", raising=False)
    heuristic = deterministic_executor._resolve_worker_decision(
        allow_parallel=True,
        task_count=3,
        max_workers=None,
    )
    assert heuristic.requested_workers == deterministic_executor.DEFAULT_PARALLEL_WORKERS
    assert heuristic.effective_workers == deterministic_executor.DEFAULT_PARALLEL_WORKERS
    assert heuristic.worker_source == "heuristic"
    assert heuristic.execution_mode == "parallel"


@pytest.mark.parametrize(
    ("allow_parallel", "task_count", "max_workers", "frozen", "reason"),
    [
        (False, 3, 4, False, "allow_parallel_false"),
        (True, 3, 1, False, "worker_count_leq_1"),
        (True, 1, 4, False, "single_task"),
        (True, 3, 4, True, "frozen_runtime_default_serial"),
    ],
)
def test_worker_decision_exposes_serial_reasons(monkeypatch, allow_parallel, task_count, max_workers, frozen, reason) -> None:
    monkeypatch.setattr(deterministic_executor.execution_parallel, "is_frozen_runtime", lambda: frozen)
    monkeypatch.delenv("PV_ALLOW_FROZEN_MULTIPROCESS", raising=False)
    decision = deterministic_executor._resolve_worker_decision(
        allow_parallel=allow_parallel,
        task_count=task_count,
        max_workers=max_workers,
    )

    assert decision.execution_mode == "serial"
    assert decision.effective_workers == 1
    assert decision.serial_reason == reason


def test_invalid_env_worker_setting_resolves_to_single_worker(monkeypatch) -> None:
    monkeypatch.setenv("PV_SCAN_MAX_WORKERS", "not-a-number")
    monkeypatch.setattr(deterministic_executor.execution_parallel, "is_frozen_runtime", lambda: False)

    decision = deterministic_executor._resolve_worker_decision(
        allow_parallel=True,
        task_count=3,
        max_workers=None,
    )

    assert decision.requested_workers == 1
    assert decision.effective_workers == 1
    assert decision.worker_source == "env"
    assert decision.execution_mode == "serial"
    assert decision.serial_reason == "worker_count_leq_1"


def test_frozen_runtime_can_opt_in_to_parallel(monkeypatch) -> None:
    monkeypatch.setattr(deterministic_executor.execution_parallel, "is_frozen_runtime", lambda: True)
    monkeypatch.setenv("PV_ALLOW_FROZEN_MULTIPROCESS", "1")

    decision = deterministic_executor._resolve_worker_decision(
        allow_parallel=True,
        task_count=3,
        max_workers=2,
    )

    assert decision.execution_mode == "parallel"
    assert decision.serial_reason is None
    assert decision.frozen_runtime is True
    assert decision.frozen_parallel_opt_in is True


def test_parallel_exception_logs_fallback_and_runs_serial(monkeypatch, caplog) -> None:
    expected_rows = ({"candidate": "serial"},)

    monkeypatch.setattr(deterministic_executor.execution_parallel, "is_frozen_runtime", lambda: False)
    monkeypatch.setattr(deterministic_executor, "_build_tasks", lambda config_bundle: (5.0, ("task-1", "task-2", "task-3")))
    monkeypatch.setattr(deterministic_executor, "_run_tasks_serial", lambda tasks: expected_rows)
    monkeypatch.setattr(
        deterministic_executor,
        "_run_tasks_parallel",
        lambda tasks, max_workers: (_ for _ in ()).throw(RuntimeError("parallel boom")),
    )
    caplog.set_level(logging.INFO, logger=deterministic_executor.__name__)

    seed, rows = deterministic_executor.run_deterministic_scan_tasks(object(), allow_parallel=True, max_workers=3)

    assert seed == 5.0
    assert rows == expected_rows

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=deterministic_scan_parallel_fallback" in messages
    assert "fallback_reason=parallel_exception" in messages
    assert "exc_class=RuntimeError" in messages
    assert "event=deterministic_scan" in messages
    assert "candidate_tasks=3" in messages
    assert "execution_mode=serial" in messages
    assert "requested_workers=3" in messages
    assert "effective_workers=1" in messages
    assert "worker_source=explicit" in messages
    assert "fallback_to_serial=true" in messages
    assert "serial_reason=parallel_exception" in messages


def test_entrypoints_include_freeze_support_call() -> None:
    for path in [Path("main.py"), Path("desktop_launcher.py"), Path("app.py")]:
        contents = path.read_text(encoding="utf-8")
        assert "freeze_support()" in contents
