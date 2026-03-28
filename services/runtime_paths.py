from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_NAME = "PV_inputs.xlsx"
QUICK_GUIDE_NAME = "PVWorkbench_Guia_Rapida.html"
PROJECTS_DIRNAME = "proyectos"
RUNTIME_CACHE_DIRNAME = ".pv_runtime_cache"
USER_EXPORTS_DIRNAME = "PVWorkbench Exports"
APP_STORAGE_DIRNAME = "PVWorkbench"
INTERNAL_PROJECTS_DIRNAME = "projects"
INTERNAL_RUNTIME_DIRNAME = "runtime"
INTERNAL_CACHE_DIRNAME = "cache"
INTERNAL_RESULTS_DIRNAME = "results"
MIGRATION_DIRNAME = "migration"
STORAGE_LAYOUT_MIGRATION_VERSION = 1
LEGACY_RESULTS_DIRS = ("Resultados", "Resultados_rel")

_MIGRATION_ATTEMPTED = False


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None))


def resource_root() -> Path:
    if is_frozen_runtime():
        return Path(str(getattr(sys, "_MEIPASS"))).resolve()
    return REPO_ROOT


def _local_appdata_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata).expanduser().resolve()
    return (Path.home() / "AppData" / "Local").resolve()


def _internal_app_root_base() -> Path:
    if is_frozen_runtime():
        return (_local_appdata_root() / APP_STORAGE_DIRNAME).resolve()
    return REPO_ROOT


def _migration_marker_path() -> Path:
    return (_internal_app_root_base() / MIGRATION_DIRNAME / f"storage_layout_v{STORAGE_LAYOUT_MIGRATION_VERSION}.json").resolve()


def _read_migration_marker() -> dict[str, Any] | None:
    path = _migration_marker_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _write_migration_marker(payload: dict[str, Any]) -> None:
    path = _migration_marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("storage_migration event=marker_write_failed path=%s error=%s", path, exc)


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".pvw_write_", delete=True):
            pass
        return True
    except OSError:
        return False


def _copy_tree_conservative(source: Path, destination: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "source": str(source),
        "destination": str(destination),
        "copied": 0,
        "skipped_existing": 0,
        "errors": [],
        "status": "missing",
    }
    if not source.exists():
        return summary

    summary["status"] = "complete"
    destination.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.rglob("*")):
        relative = entry.relative_to(source)
        target = destination / relative
        try:
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                summary["skipped_existing"] += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, target)
            summary["copied"] += 1
        except OSError as exc:
            summary["errors"].append(f"{relative}: {exc}")

    if summary["errors"]:
        summary["status"] = "partial"
        summary["error_count"] = len(summary["errors"])
        summary["errors"] = summary["errors"][:3]
    else:
        summary.pop("errors")
    return summary


def legacy_packaged_root() -> Path | None:
    if not is_frozen_runtime():
        return None
    return Path(sys.executable).resolve().parent


def migrate_legacy_packaged_storage() -> dict[str, Any] | None:
    global _MIGRATION_ATTEMPTED
    if not is_frozen_runtime():
        return None
    if _MIGRATION_ATTEMPTED:
        return _read_migration_marker()

    existing_marker = _read_migration_marker()
    if existing_marker is not None:
        _MIGRATION_ATTEMPTED = True
        return existing_marker

    destination_root = _internal_app_root_base()
    destination_root.mkdir(parents=True, exist_ok=True)
    legacy_root = legacy_packaged_root()
    payload: dict[str, Any] = {
        "schema_version": STORAGE_LAYOUT_MIGRATION_VERSION,
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "legacy_source_path": str(legacy_root) if legacy_root is not None else None,
        "ignored_legacy_outputs": list(LEGACY_RESULTS_DIRS),
        "categories": {},
        "status": "complete",
    }

    if legacy_root is None or legacy_root.resolve() == destination_root.resolve():
        payload["status"] = "skipped"
        _write_migration_marker(payload)
        _MIGRATION_ATTEMPTED = True
        return payload

    categories = {
        "projects": _copy_tree_conservative(legacy_root / PROJECTS_DIRNAME, destination_root / INTERNAL_PROJECTS_DIRNAME),
        "matplotlib_cache": _copy_tree_conservative(
            legacy_root / RUNTIME_CACHE_DIRNAME / "matplotlib",
            destination_root / INTERNAL_CACHE_DIRNAME / "matplotlib",
        ),
    }
    # Legacy top-level Resultados/ and Resultados_rel/ are treated as old export
    # output, not internal app state, so they are intentionally not migrated.
    payload["categories"] = categories
    if any(category.get("status") == "partial" for category in categories.values()):
        payload["status"] = "partial"
        logger.warning(
            "storage_migration event=partial legacy_source=%s destination=%s",
            legacy_root,
            destination_root,
        )

    _write_migration_marker(payload)
    _MIGRATION_ATTEMPTED = True
    return payload


def internal_app_root() -> Path:
    root = _internal_app_root_base()
    root.mkdir(parents=True, exist_ok=True)
    if is_frozen_runtime():
        migrate_legacy_packaged_storage()
    return root.resolve()


def private_config_root() -> Path:
    explicit_root = os.environ.get("PVW_PRIVATE_CONFIG_ROOT")
    if explicit_root:
        root = Path(explicit_root).expanduser().resolve()
    elif os.name == "nt":
        root = (_local_appdata_root() / APP_STORAGE_DIRNAME).resolve()
    elif sys.platform == "darwin":
        root = (Path.home() / "Library" / "Application Support" / APP_STORAGE_DIRNAME).expanduser().resolve()
    else:
        xdg_root = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_root).expanduser() if xdg_root else (Path.home() / ".config").expanduser()
        root = (base / APP_STORAGE_DIRNAME).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_root() -> Path:
    # Compatibility alias retained for older callers. New code should prefer the
    # explicit packaged-mode helpers such as internal_app_root() or
    # internal_results_root() so internal storage semantics remain clear.
    if is_frozen_runtime():
        return internal_app_root()
    return REPO_ROOT


def assets_dir() -> Path:
    return (resource_root() / "assets").resolve()


def pages_dir() -> Path:
    return (resource_root() / "pages").resolve()


def bundled_workbook_path() -> Path:
    return (resource_root() / WORKBOOK_NAME).resolve()


def bundled_quick_guide_path() -> Path:
    return (resource_root() / QUICK_GUIDE_NAME).resolve()


def user_workbook_path() -> Path:
    return (user_root() / WORKBOOK_NAME).resolve()


def internal_results_root() -> Path:
    if is_frozen_runtime():
        root = internal_app_root() / INTERNAL_RESULTS_DIRNAME
    else:
        root = user_root() / "Resultados"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def default_results_root() -> Path:
    # Compatibility alias. In frozen mode this is internal staging/output
    # storage under LocalAppData, not the user-facing Documents export folder.
    return internal_results_root()


def projects_root() -> Path:
    if is_frozen_runtime():
        root = internal_app_root() / INTERNAL_PROJECTS_DIRNAME
    else:
        root = user_root() / PROJECTS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def project_root(slug: str) -> Path:
    root = (projects_root() / str(slug)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_inputs_root(slug: str) -> Path:
    root = project_root(slug) / "inputs"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def project_exports_root(slug: str) -> Path:
    root = project_root(slug) / "exports" / "Resultados"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def internal_runtime_root() -> Path:
    if is_frozen_runtime():
        root = internal_app_root() / INTERNAL_RUNTIME_DIRNAME
    else:
        root = runtime_cache_root() / "desktop"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def runtime_cache_root() -> Path:
    if is_frozen_runtime():
        root = internal_app_root() / INTERNAL_CACHE_DIRNAME
    else:
        root = user_root() / RUNTIME_CACHE_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_windows_documents_root() -> Path | None:
    if os.name != "nt":
        return None
    try:
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        folder_id = GUID(
            0xFDD39AD0,
            0x238F,
            0x46AF,
            (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        )
        path_ptr = ctypes.c_void_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr))
        if result != 0 or not path_ptr.value:
            return None
        try:
            value = ctypes.wstring_at(path_ptr.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path_ptr.value)
        return Path(value).expanduser().resolve()
    except Exception:
        return None


def _fallback_local_exports_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return (Path(local_appdata).expanduser() / APP_STORAGE_DIRNAME / "Exports").resolve()
    if os.name == "nt":
        return (Path.home() / "AppData" / "Local" / APP_STORAGE_DIRNAME / "Exports").resolve()
    return (Path.home() / ".pvworkbench" / "exports").resolve()


def user_friendly_exports_root() -> Path | None:
    if not is_frozen_runtime():
        return None

    candidates: list[Path] = []
    documents_root = _resolve_windows_documents_root()
    if documents_root is not None:
        candidates.append(documents_root / USER_EXPORTS_DIRNAME)
    candidates.append(_fallback_local_exports_root())

    for candidate in candidates:
        if _is_writable_directory(candidate):
            return candidate.resolve()
    return None


def configure_runtime_environment() -> None:
    matplotlib_root = runtime_cache_root() / "matplotlib"
    matplotlib_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_root))
