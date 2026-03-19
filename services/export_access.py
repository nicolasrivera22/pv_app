from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence

from .runtime_paths import is_frozen_runtime, user_friendly_exports_root


@dataclass(frozen=True)
class ExportPublishResult:
    internal_root: Path
    published_root: Path | None
    display_root: Path
    publish_error: str | None = None


def _safe_segment(value: str | None, *, fallback: str) -> str:
    text = str(value or "").strip()
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in text)
    return cleaned.strip("_") or fallback


def _artifact_root(artifact_paths: Sequence[Path]) -> Path:
    if not artifact_paths:
        raise ValueError("No export artifact paths were provided.")
    resolved = [Path(path).resolve() for path in artifact_paths]
    common = Path(os.path.commonpath([str(path) for path in resolved]))
    return common.parent if common.is_file() else common


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    suffix = 2
    while True:
        candidate = path.parent / f"{path.name}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def build_published_export_destination(
    project_slug: str | None,
    scenario_slug: str | None,
    export_kind: str,
    timestamp: datetime,
) -> Path | None:
    root = user_friendly_exports_root()
    if root is None:
        return None
    project_segment = _safe_segment(project_slug, fallback="unsaved-project")
    export_segment = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{_safe_segment(export_kind, fallback='export')}"
    scenario_segment = _safe_segment(scenario_slug, fallback="scenario")
    return _unique_destination(root / project_segment / export_segment / scenario_segment)


def publish_export_artifacts(
    artifact_paths: Sequence[Path],
    *,
    project_slug: str | None,
    scenario_slug: str | None,
    export_kind: str,
    timestamp: datetime | None = None,
) -> ExportPublishResult:
    internal_root = _artifact_root(artifact_paths)
    export_time = timestamp or datetime.now()
    destination = build_published_export_destination(project_slug, scenario_slug, export_kind, export_time)
    if destination is None:
        if is_frozen_runtime():
            return ExportPublishResult(
                internal_root=internal_root,
                published_root=None,
                display_root=internal_root,
                publish_error="No writable user exports folder is available.",
            )
        return ExportPublishResult(
            internal_root=internal_root,
            published_root=None,
            display_root=internal_root,
            publish_error=None,
        )

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(internal_root, destination)
        return ExportPublishResult(
            internal_root=internal_root,
            published_root=destination.resolve(),
            display_root=destination.resolve(),
            publish_error=None,
        )
    except OSError as exc:
        return ExportPublishResult(
            internal_root=internal_root,
            published_root=None,
            display_root=internal_root,
            publish_error=str(exc) or exc.__class__.__name__,
        )


def _open_path_in_explorer(path: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(str(path))
        return
    if os.name == "posix":
        command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
        subprocess.Popen(command)
        return
    raise RuntimeError("Opening export folders is not supported in this runtime.")


def open_export_folder(path_str: str) -> None:
    path = Path(path_str).expanduser()
    if not path_str.strip():
        raise FileNotFoundError("No export folder is available yet.")
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Export folder '{path}' is not available.")
    _open_path_in_explorer(path.resolve())
