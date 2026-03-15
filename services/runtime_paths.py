from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_NAME = "PV_inputs.xlsx"
QUICK_GUIDE_NAME = "PVWorkbench_Guia_Rapida.html"
PROJECTS_DIRNAME = "proyectos"
RUNTIME_CACHE_DIRNAME = ".pv_runtime_cache"
USER_EXPORTS_DIRNAME = "PVWorkbench Exports"


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None))


def resource_root() -> Path:
    if is_frozen_runtime():
        return Path(str(getattr(sys, "_MEIPASS"))).resolve()
    return REPO_ROOT


def user_root() -> Path:
    if is_frozen_runtime():
        return Path(sys.executable).resolve().parent
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


def default_results_root() -> Path:
    root = user_root() / "Resultados"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def projects_root() -> Path:
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


def runtime_cache_root() -> Path:
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
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata).expanduser() / "PVWorkbench" / "Exports"
        return Path.home() / "AppData" / "Local" / "PVWorkbench" / "Exports"
    return Path.home() / ".pvworkbench" / "exports"


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".pvw_write_", delete=True):
            pass
        return True
    except OSError:
        return False


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
