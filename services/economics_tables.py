from __future__ import annotations

from typing import Any

import pandas as pd

ECONOMICS_COST_COLUMNS = ["stage", "name", "basis", "amount_COP", "enabled", "notes"]
ECONOMICS_PRICE_COLUMNS = ["layer", "name", "method", "value", "enabled", "notes"]

VALID_ECONOMICS_COST_STAGES = {"technical", "installed"}
VALID_ECONOMICS_COST_BASES = {"fixed_project", "per_kwp", "per_panel", "per_inverter", "per_battery_kwh"}
VALID_ECONOMICS_PRICE_LAYERS = {"commercial", "sale"}
VALID_ECONOMICS_PRICE_METHODS = {"markup_pct", "fixed_project", "per_kwp"}
ECONOMICS_PRICE_PERCENT_METHODS = {"markup_pct"}

_RICH_COST_STAGE_MAP = {"technical_cost": "technical", "installed_cost": "installed"}
_RICH_PRICE_LAYER_MAP = {"commercial_offer": "commercial", "final_sale_price": "sale"}
_RICH_COST_BASIS_MAP = {
    "fixed_project": "fixed_project",
    "per_kwp": "per_kwp",
    "per_panel": "per_panel",
    "per_inverter": "per_inverter",
    "per_battery_kwh": "per_battery_kwh",
}
_RICH_PRICE_METHOD_MAP = {
    "markup_pct": "markup_pct",
    "fixed_project": "fixed_project",
    "per_kwp": "per_kwp",
}
_TECHNICAL_COST_NAMES = {"Panel hardware", "Inverter hardware", "Battery hardware"}
_COMMERCIAL_PRICE_NAMES = {"Contingencia", "Margen comercial"}


def default_economics_cost_items_rows() -> list[dict[str, Any]]:
    return [
        {"stage": "technical", "name": "Panel hardware", "basis": "per_panel", "amount_COP": 0.0, "enabled": True, "notes": ""},
        {"stage": "technical", "name": "Inverter hardware", "basis": "per_inverter", "amount_COP": 0.0, "enabled": True, "notes": ""},
        {"stage": "technical", "name": "Battery hardware", "basis": "per_battery_kwh", "amount_COP": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "BOS eléctrico", "basis": "per_kwp", "amount_COP": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "Estructura", "basis": "per_kwp", "amount_COP": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "Mano de obra", "basis": "per_kwp", "amount_COP": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "Ingeniería", "basis": "fixed_project", "amount_COP": 0.0, "enabled": True, "notes": ""},
        {"stage": "installed", "name": "Logística", "basis": "fixed_project", "amount_COP": 0.0, "enabled": True, "notes": ""},
    ]


def default_economics_price_items_rows() -> list[dict[str, Any]]:
    return [
        {"layer": "commercial", "name": "Contingencia", "method": "markup_pct", "value": 0.0, "enabled": True, "notes": ""},
        {"layer": "commercial", "name": "Margen comercial", "method": "markup_pct", "value": 0.0, "enabled": True, "notes": ""},
        {"layer": "sale", "name": "Ajuste final", "method": "fixed_project", "value": 0.0, "enabled": False, "notes": ""},
    ]


def empty_economics_cost_items_table() -> pd.DataFrame:
    return pd.DataFrame(columns=ECONOMICS_COST_COLUMNS)


def empty_economics_price_items_table() -> pd.DataFrame:
    return pd.DataFrame(columns=ECONOMICS_PRICE_COLUMNS)


def default_economics_cost_items_table() -> pd.DataFrame:
    return pd.DataFrame(default_economics_cost_items_rows(), columns=ECONOMICS_COST_COLUMNS)


def default_economics_price_items_table() -> pd.DataFrame:
    return pd.DataFrame(default_economics_price_items_rows(), columns=ECONOMICS_PRICE_COLUMNS)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _strip_text(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _parse_enabled(value: Any, *, default: bool = True) -> tuple[bool, bool]:
    if isinstance(value, bool):
        return value, False
    if _is_missing(value):
        return default, False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value), False
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "si", "sí", "on"}:
        return True, False
    if normalized in {"false", "0", "no", "n", "off"}:
        return False, False
    return False, True


def _coerce_numeric(value: Any, *, allow_percent_text: bool = False) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.endswith("%"):
            if not allow_percent_text:
                return None
            cleaned = cleaned[:-1].strip()
        if cleaned == "":
            return None
        value = cleaned
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_is_blank(record: dict[str, Any]) -> bool:
    return all(_is_missing(value) for value in record.values())


def _append_note(existing: str, extra: str) -> str:
    clean_existing = _strip_text(existing)
    clean_extra = _strip_text(extra)
    if not clean_extra:
        return clean_existing
    if not clean_existing:
        return clean_extra
    return f"{clean_existing} | {clean_extra}"


def _fallback_cost_stage(name: str) -> str:
    return "technical" if _strip_text(name) in _TECHNICAL_COST_NAMES else "installed"


def _fallback_price_layer(name: str) -> str:
    return "commercial" if _strip_text(name) in _COMMERCIAL_PRICE_NAMES else "sale"


def _rich_origin_note(*, stage: str, method: str, value: Any) -> str:
    parts = []
    if stage:
        parts.append(f"stage={stage}")
    if method:
        parts.append(f"method={method}")
    if not _is_missing(value):
        parts.append(f"value={value}")
    if not parts:
        return "Migrated from prior economics schema."
    return f"Migrated from prior economics schema ({', '.join(parts)})."


def _normalize_cost_row(record: dict[str, Any], *, row_number: int) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    if _row_is_blank(record):
        return None, issues

    name = _strip_text(record.get("name"))
    notes = _strip_text(record.get("notes"))
    raw_stage = _strip_text(record.get("stage"))
    raw_basis = _strip_text(record.get("basis"))
    raw_method = _strip_text(record.get("calculation_method"))
    raw_amount = record.get("amount_COP") if "amount_COP" in record else record.get("value")
    enabled, enabled_invalid = _parse_enabled(record.get("enabled"))

    if not name:
        issues.append(f"Economics_Cost_Items fila {row_number}: falta 'name'; la fila se ignora.")
        return None, issues

    stage = _RICH_COST_STAGE_MAP.get(raw_stage, raw_stage)
    basis = raw_basis or _RICH_COST_BASIS_MAP.get(raw_method, raw_method)
    amount = _coerce_numeric(raw_amount)

    if enabled_invalid:
        issues.append(f"Economics_Cost_Items fila {row_number}: 'enabled' inválido; la fila se desactiva.")
        enabled = False

    if stage not in VALID_ECONOMICS_COST_STAGES:
        issues.append(f"Economics_Cost_Items fila {row_number}: 'stage' inválido; se usa fallback y la fila se desactiva.")
        notes = _append_note(notes, _rich_origin_note(stage=raw_stage, method=raw_method or raw_basis, value=raw_amount))
        stage = _fallback_cost_stage(name)
        enabled = False

    if basis not in VALID_ECONOMICS_COST_BASES:
        issues.append(f"Economics_Cost_Items fila {row_number}: base o método no soportado; la fila se desactiva.")
        notes = _append_note(notes, _rich_origin_note(stage=raw_stage, method=raw_method or raw_basis, value=raw_amount))
        basis = "fixed_project"
        amount = 0.0
        enabled = False

    if amount is None:
        issues.append(f"Economics_Cost_Items fila {row_number}: 'amount_COP' debe ser numérico; la fila se desactiva.")
        notes = _append_note(notes, _rich_origin_note(stage=raw_stage, method=raw_method or raw_basis, value=raw_amount))
        amount = 0.0
        enabled = False

    return {
        "stage": stage,
        "name": name,
        "basis": basis,
        "amount_COP": float(amount),
        "enabled": bool(enabled),
        "notes": notes,
    }, issues


def _normalize_price_row(record: dict[str, Any], *, row_number: int) -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    if _row_is_blank(record):
        return None, issues

    name = _strip_text(record.get("name"))
    notes = _strip_text(record.get("notes"))
    raw_layer = _strip_text(record.get("layer"))
    raw_stage = _strip_text(record.get("stage"))
    raw_method = _strip_text(record.get("method"))
    raw_calculation_method = _strip_text(record.get("calculation_method"))
    raw_value = record.get("value")
    enabled, enabled_invalid = _parse_enabled(record.get("enabled"))

    if not name:
        issues.append(f"Economics_Price_Items fila {row_number}: falta 'name'; la fila se ignora.")
        return None, issues

    layer = raw_layer or _RICH_PRICE_LAYER_MAP.get(raw_stage, raw_stage)
    method = raw_method or _RICH_PRICE_METHOD_MAP.get(raw_calculation_method, raw_calculation_method)
    numeric_value = _coerce_numeric(raw_value, allow_percent_text=method in ECONOMICS_PRICE_PERCENT_METHODS)
    if numeric_value is not None and method in ECONOMICS_PRICE_PERCENT_METHODS and abs(numeric_value) > 1.0:
        numeric_value = numeric_value / 100.0

    if enabled_invalid:
        issues.append(f"Economics_Price_Items fila {row_number}: 'enabled' inválido; la fila se desactiva.")
        enabled = False

    if layer not in VALID_ECONOMICS_PRICE_LAYERS:
        issues.append(f"Economics_Price_Items fila {row_number}: 'layer' inválido; se usa fallback y la fila se desactiva.")
        notes = _append_note(notes, _rich_origin_note(stage=raw_stage or raw_layer, method=raw_calculation_method or raw_method, value=raw_value))
        layer = _fallback_price_layer(name)
        enabled = False

    if method not in VALID_ECONOMICS_PRICE_METHODS:
        issues.append(f"Economics_Price_Items fila {row_number}: método no soportado; la fila se desactiva.")
        notes = _append_note(notes, _rich_origin_note(stage=raw_stage or raw_layer, method=raw_calculation_method or raw_method, value=raw_value))
        method = "fixed_project"
        numeric_value = 0.0
        enabled = False

    if numeric_value is None:
        issues.append(f"Economics_Price_Items fila {row_number}: 'value' debe ser numérico; la fila se desactiva.")
        notes = _append_note(notes, _rich_origin_note(stage=raw_stage or raw_layer, method=raw_calculation_method or raw_method, value=raw_value))
        numeric_value = 0.0
        enabled = False

    return {
        "layer": layer,
        "name": name,
        "method": method,
        "value": float(numeric_value),
        "enabled": bool(enabled),
        "notes": notes,
    }, issues


def _normalize_cost_like_rows(source: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[pd.DataFrame, list[str]]:
    if source is None:
        return empty_economics_cost_items_table(), []
    frame = source.copy() if isinstance(source, pd.DataFrame) else pd.DataFrame(source)
    records = frame.to_dict("records")
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    for row_number, record in enumerate(records, start=1):
        row, row_issues = _normalize_cost_row(record, row_number=row_number)
        issues.extend(row_issues)
        if row is not None:
            rows.append(row)
    if not rows:
        return empty_economics_cost_items_table(), issues
    return pd.DataFrame(rows, columns=ECONOMICS_COST_COLUMNS), issues


def _normalize_price_like_rows(source: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[pd.DataFrame, list[str]]:
    if source is None:
        return empty_economics_price_items_table(), []
    frame = source.copy() if isinstance(source, pd.DataFrame) else pd.DataFrame(source)
    records = frame.to_dict("records")
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    for row_number, record in enumerate(records, start=1):
        row, row_issues = _normalize_price_row(record, row_number=row_number)
        issues.extend(row_issues)
        if row is not None:
            rows.append(row)
    if not rows:
        return empty_economics_price_items_table(), issues
    return pd.DataFrame(rows, columns=ECONOMICS_PRICE_COLUMNS), issues


def normalize_economics_cost_items_with_issues(source: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[pd.DataFrame, list[str]]:
    return _normalize_cost_like_rows(source)


def normalize_economics_price_items_with_issues(source: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[pd.DataFrame, list[str]]:
    return _normalize_price_like_rows(source)


def hydrate_economics_cost_items_table(source: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[pd.DataFrame, list[str]]:
    frame, issues = _normalize_cost_like_rows(source)
    if not frame.empty:
        return frame, issues
    if source is None:
        return default_economics_cost_items_table(), issues
    source_frame = source.copy() if isinstance(source, pd.DataFrame) else pd.DataFrame(source)
    if source_frame.empty:
        return default_economics_cost_items_table(), issues
    return default_economics_cost_items_table(), [*issues, "Economics_Cost_Items vacío o incompleto; se restauraron los defaults."]


def hydrate_economics_price_items_table(source: pd.DataFrame | list[dict[str, Any]] | None) -> tuple[pd.DataFrame, list[str]]:
    frame, issues = _normalize_price_like_rows(source)
    if not frame.empty:
        return frame, issues
    if source is None:
        return default_economics_price_items_table(), issues
    source_frame = source.copy() if isinstance(source, pd.DataFrame) else pd.DataFrame(source)
    if source_frame.empty:
        return default_economics_price_items_table(), issues
    return default_economics_price_items_table(), [*issues, "Economics_Price_Items vacío o incompleto; se restauraron los defaults."]


def normalize_economics_cost_items_frame(frame: pd.DataFrame | list[dict[str, Any]] | None) -> pd.DataFrame:
    normalized, _issues = _normalize_cost_like_rows(frame)
    return normalized


def normalize_economics_price_items_frame(frame: pd.DataFrame | list[dict[str, Any]] | None) -> pd.DataFrame:
    normalized, _issues = _normalize_price_like_rows(frame)
    return normalized


def economics_cost_items_rows_to_editor(frame: pd.DataFrame | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = normalize_economics_cost_items_frame(frame)
    return normalized.to_dict("records")


def economics_price_items_rows_to_editor(frame: pd.DataFrame | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = normalize_economics_price_items_frame(frame)
    if normalized.empty:
        return []
    editor_frame = normalized.copy()
    mask = editor_frame["method"].astype(str).isin(ECONOMICS_PRICE_PERCENT_METHODS)
    editor_frame.loc[mask, "value"] = editor_frame.loc[mask, "value"].astype(float) * 100.0
    return editor_frame.to_dict("records")


def economics_cost_items_rows_from_editor(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return normalize_economics_cost_items_frame(rows).to_dict("records")


def economics_price_items_rows_from_editor(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return normalize_economics_price_items_frame(rows).to_dict("records")
