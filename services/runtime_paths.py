from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_NAME = "PV_inputs.xlsx"


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


def user_workbook_path() -> Path:
    return (user_root() / WORKBOOK_NAME).resolve()


def default_results_root() -> Path:
    root = user_root() / "Resultados"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()
