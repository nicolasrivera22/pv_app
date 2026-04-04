from __future__ import annotations

from dataclasses import dataclass
from typing import Any


UI_MODE_SIMPLE = "simple"
UI_MODE_PRO = "pro"
UI_MODE_ADMIN = "admin"
UI_MODES = (UI_MODE_SIMPLE, UI_MODE_PRO, UI_MODE_ADMIN)

PAGE_RESULTS = "results"
PAGE_ASSUMPTIONS = "assumptions"
PAGE_COMPARE = "compare"
PAGE_RISK = "risk"
PAGE_HELP = "help"
PAGE_ADMIN = "admin"
PAGE_KEYS = (
    PAGE_RESULTS,
    PAGE_ASSUMPTIONS,
    PAGE_COMPARE,
    PAGE_RISK,
    PAGE_HELP,
    PAGE_ADMIN,
)
NAV_PAGE_KEYS = (
    PAGE_RESULTS,
    PAGE_ASSUMPTIONS,
    PAGE_COMPARE,
    PAGE_RISK,
    PAGE_HELP,
)

HIDDEN_STYLE = {"display": "none"}
VISIBLE_STYLE: dict[str, str] = {}


@dataclass(frozen=True)
class PageAccess:
    page_key: str
    ui_mode: str
    allowed: bool
    required_mode: str | None = None
    title_key: str | None = None
    body_key: str | None = None
    cta_label_key: str | None = None
    cta_target_mode: str | None = None

    @property
    def is_gated(self) -> bool:
        return not self.allowed


def normalize_ui_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in UI_MODES else UI_MODE_SIMPLE


def resolve_ui_mode_from_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return UI_MODE_SIMPLE
    return normalize_ui_mode(payload.get("ui_mode"))


def is_nav_page_visible(page_key: str, ui_mode: str | None) -> bool:
    mode = normalize_ui_mode(ui_mode)
    if page_key in {PAGE_RESULTS, PAGE_ASSUMPTIONS, PAGE_HELP}:
        return True
    if page_key in {PAGE_COMPARE, PAGE_RISK}:
        return mode in {UI_MODE_PRO, UI_MODE_ADMIN}
    return False


def nav_visibility_style(page_key: str, ui_mode: str | None) -> dict[str, str]:
    return VISIBLE_STYLE if is_nav_page_visible(page_key, ui_mode) else HIDDEN_STYLE


def should_show_internal_entry(ui_mode: str | None) -> bool:
    return normalize_ui_mode(ui_mode) == UI_MODE_ADMIN


def internal_entry_style(ui_mode: str | None) -> dict[str, str]:
    return VISIBLE_STYLE if should_show_internal_entry(ui_mode) else HIDDEN_STYLE


def should_show_admin_surface(ui_mode: str | None) -> bool:
    return normalize_ui_mode(ui_mode) == UI_MODE_ADMIN


def admin_surface_style(ui_mode: str | None) -> dict[str, str]:
    return VISIBLE_STYLE if should_show_admin_surface(ui_mode) else HIDDEN_STYLE


def resolve_page_access(page_key: str, ui_mode: str | None) -> PageAccess:
    mode = normalize_ui_mode(ui_mode)
    if page_key in {PAGE_RESULTS, PAGE_ASSUMPTIONS, PAGE_HELP}:
        return PageAccess(page_key=page_key, ui_mode=mode, allowed=True)
    if page_key in {PAGE_COMPARE, PAGE_RISK}:
        if mode in {UI_MODE_PRO, UI_MODE_ADMIN}:
            return PageAccess(page_key=page_key, ui_mode=mode, allowed=True)
        return PageAccess(
            page_key=page_key,
            ui_mode=mode,
            allowed=False,
            required_mode=UI_MODE_PRO,
            title_key=f"ui_mode.gate.{page_key}.title",
            body_key=f"ui_mode.gate.{page_key}.body",
            cta_label_key="ui_mode.cta.switch_pro",
            cta_target_mode=UI_MODE_PRO,
        )
    if page_key == PAGE_ADMIN:
        return PageAccess(page_key=page_key, ui_mode=mode, allowed=True)
    raise ValueError(f"Unsupported page key: {page_key}")


def is_page_allowed(page_key: str, ui_mode: str | None) -> bool:
    return resolve_page_access(page_key, ui_mode).allowed


def gate_visibility_style(access: PageAccess) -> dict[str, str]:
    return VISIBLE_STYLE if access.is_gated else HIDDEN_STYLE


def page_body_style(access: PageAccess) -> dict[str, str]:
    return HIDDEN_STYLE if access.is_gated else VISIBLE_STYLE
