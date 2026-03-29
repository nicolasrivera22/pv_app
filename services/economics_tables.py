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
RICH_MIGRATION_NOTE_PREFIX = "Migrated from prior economics schema"

_ECONOMICS_UI_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "stage": {
        "technical": {"es": "Costo técnico", "en": "Technical cost"},
        "installed": {"es": "Costo instalado", "en": "Installed cost"},
    },
    "basis": {
        "fixed_project": {"es": "Fijo por proyecto", "en": "Fixed per project"},
        "per_kwp": {"es": "Por kWp", "en": "Per kWp"},
        "per_panel": {"es": "Por panel", "en": "Per panel"},
        "per_inverter": {"es": "Por inversor", "en": "Per inverter"},
        "per_battery_kwh": {"es": "Por kWh de batería", "en": "Per battery kWh"},
    },
    "layer": {
        "commercial": {"es": "Oferta comercial", "en": "Commercial offer"},
        "sale": {"es": "Ajuste final de venta", "en": "Final sale adjustment"},
    },
    "method": {
        "markup_pct": {"es": "Ajuste porcentual", "en": "Percentage adjustment"},
        "fixed_project": {"es": "Monto fijo por proyecto", "en": "Fixed project amount"},
        "per_kwp": {"es": "Monto por kWp", "en": "Amount per kWp"},
    },
    "source_table": {
        "Economics_Cost_Items": {"es": "Capas de costo", "en": "Cost layers"},
        "Economics_Price_Items": {"es": "Capas de precio", "en": "Price layers"},
    },
}

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


def _editor_lang(lang: str | None) -> str:
    return "en" if lang == "en" else "es"


def economics_ui_label(field: str, value: Any, *, lang: str = "es") -> str:
    raw_value = _strip_text(value)
    if not raw_value:
        return ""
    field_map = _ECONOMICS_UI_LABELS.get(field, {})
    label_map = field_map.get(raw_value)
    if not label_map:
        return raw_value
    active_lang = _editor_lang(lang)
    return label_map.get(active_lang, label_map.get("es", raw_value))


def _economics_ui_raw_value(field: str, value: Any) -> str:
    text = _strip_text(value)
    if not text:
        return ""
    field_map = _ECONOMICS_UI_LABELS.get(field, {})
    if text in field_map:
        return text
    for raw_value, labels in field_map.items():
        if text == labels.get("es") or text == labels.get("en"):
            return raw_value
    return text


def economics_editor_dropdowns(table_kind: str, *, lang: str = "es") -> dict[str, dict[str, list[dict[str, str]]]]:
    if table_kind == "economics_cost_items":
        fields = ("stage", "basis")
    elif table_kind == "economics_price_items":
        fields = ("layer", "method")
    else:
        return {}
    active_lang = _editor_lang(lang)
    return {
        field: {
            "options": [
                {"label": labels.get(active_lang, labels.get("es", raw_value)), "value": labels.get(active_lang, labels.get("es", raw_value))}
                for raw_value, labels in _ECONOMICS_UI_LABELS[field].items()
            ]
        }
        for field in fields
    }


def _map_editor_labels(rows: list[dict[str, Any]], *, fields: tuple[str, ...], lang: str) -> list[dict[str, Any]]:
    mapped_rows: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        for field in fields:
            mapped[field] = economics_ui_label(field, mapped.get(field), lang=lang)
        mapped_rows.append(mapped)
    return mapped_rows


def _map_editor_raw_values(rows: list[dict[str, Any]], *, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    mapped_rows: list[dict[str, Any]] = []
    for row in rows or []:
        mapped = dict(row)
        for field in fields:
            mapped[field] = _economics_ui_raw_value(field, mapped.get(field))
        mapped_rows.append(mapped)
    return mapped_rows


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
        return f"{RICH_MIGRATION_NOTE_PREFIX}."
    return f"{RICH_MIGRATION_NOTE_PREFIX} ({', '.join(parts)})."


def economics_note_has_rich_migration(note: Any) -> bool:
    return RICH_MIGRATION_NOTE_PREFIX in _strip_text(note)


def _recovery_note(*, field: str, raw_value: Any) -> str:
    if _is_missing(raw_value):
        return f"Recovered invalid row ({field}=empty)."
    return f"Recovered invalid row ({field}={raw_value!r})."


def _invalid_name_warning(table_name: str, row_number: int) -> str:
    return f"{table_name} fila {row_number}: se desactivó por nombre vacío."


def _invalid_bool_warning(table_name: str, row_number: int) -> str:
    return f"{table_name} fila {row_number}: se desactivó por booleano inválido en 'enabled'."


def _invalid_enum_warning(table_name: str, row_number: int, field_name: str) -> str:
    return f"{table_name} fila {row_number}: se desactivó por enum inválido en '{field_name}'."


def _invalid_value_warning(table_name: str, row_number: int, field_name: str) -> str:
    return f"{table_name} fila {row_number}: se desactivó por valor inválido en '{field_name}'."


def _rich_migration_warning(table_name: str, row_number: int, method_value: str) -> str:
    return f"{table_name} fila {row_number}: migrada desde schema rico y desactivada por método no soportado '{method_value}'."


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
    raw_enabled = record.get("enabled")
    enabled, enabled_invalid = _parse_enabled(record.get("enabled"))

    stage = _RICH_COST_STAGE_MAP.get(raw_stage, raw_stage)
    basis = raw_basis or _RICH_COST_BASIS_MAP.get(raw_method, raw_method)
    amount = _coerce_numeric(raw_amount)
    if not name:
        issues.append(_invalid_name_warning("Economics_Cost_Items", row_number))
        notes = _append_note(notes, _recovery_note(field="name", raw_value=record.get("name")))
        enabled = False

    if enabled_invalid:
        issues.append(_invalid_bool_warning("Economics_Cost_Items", row_number))
        notes = _append_note(notes, _recovery_note(field="enabled", raw_value=raw_enabled))
        enabled = False

    if stage not in VALID_ECONOMICS_COST_STAGES:
        issues.append(_invalid_enum_warning("Economics_Cost_Items", row_number, "stage"))
        notes = _append_note(notes, _recovery_note(field="stage", raw_value=record.get("stage")))
        stage = _fallback_cost_stage(name)
        enabled = False

    if basis not in VALID_ECONOMICS_COST_BASES:
        if raw_basis:
            issues.append(_invalid_enum_warning("Economics_Cost_Items", row_number, "basis"))
            notes = _append_note(notes, _recovery_note(field="basis", raw_value=record.get("basis")))
        else:
            issues.append(_rich_migration_warning("Economics_Cost_Items", row_number, raw_method or "<empty>"))
            notes = _append_note(notes, _rich_origin_note(stage=raw_stage, method=raw_method or raw_basis, value=raw_amount))
        basis = "fixed_project"
        amount = 0.0
        enabled = False

    if amount is None:
        issues.append(_invalid_value_warning("Economics_Cost_Items", row_number, "amount_COP"))
        notes = _append_note(notes, _recovery_note(field="amount_COP", raw_value=raw_amount))
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
    raw_enabled = record.get("enabled")
    enabled, enabled_invalid = _parse_enabled(record.get("enabled"))

    layer = raw_layer or _RICH_PRICE_LAYER_MAP.get(raw_stage, raw_stage)
    method = raw_method or _RICH_PRICE_METHOD_MAP.get(raw_calculation_method, raw_calculation_method)
    numeric_value = _coerce_numeric(raw_value, allow_percent_text=method in ECONOMICS_PRICE_PERCENT_METHODS)
    if numeric_value is not None and method in ECONOMICS_PRICE_PERCENT_METHODS and abs(numeric_value) > 1.0:
        numeric_value = numeric_value / 100.0
    if not name:
        issues.append(_invalid_name_warning("Economics_Price_Items", row_number))
        notes = _append_note(notes, _recovery_note(field="name", raw_value=record.get("name")))
        enabled = False

    if enabled_invalid:
        issues.append(_invalid_bool_warning("Economics_Price_Items", row_number))
        notes = _append_note(notes, _recovery_note(field="enabled", raw_value=raw_enabled))
        enabled = False

    if layer not in VALID_ECONOMICS_PRICE_LAYERS:
        issues.append(_invalid_enum_warning("Economics_Price_Items", row_number, "layer"))
        notes = _append_note(notes, _recovery_note(field="layer", raw_value=record.get("layer") or record.get("stage")))
        layer = _fallback_price_layer(name)
        enabled = False

    if method not in VALID_ECONOMICS_PRICE_METHODS:
        if raw_method:
            issues.append(_invalid_enum_warning("Economics_Price_Items", row_number, "method"))
            notes = _append_note(notes, _recovery_note(field="method", raw_value=record.get("method")))
        else:
            issues.append(_rich_migration_warning("Economics_Price_Items", row_number, raw_calculation_method or "<empty>"))
            notes = _append_note(notes, _rich_origin_note(stage=raw_stage or raw_layer, method=raw_calculation_method or raw_method, value=raw_value))
        method = "fixed_project"
        numeric_value = 0.0
        enabled = False

    if numeric_value is None:
        issues.append(_invalid_value_warning("Economics_Price_Items", row_number, "value"))
        notes = _append_note(notes, _recovery_note(field="value", raw_value=raw_value))
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


def economics_cost_items_rows_to_editor(frame: pd.DataFrame | list[dict[str, Any]] | None, *, lang: str = "es") -> list[dict[str, Any]]:
    normalized = normalize_economics_cost_items_frame(frame)
    return _map_editor_labels(normalized.to_dict("records"), fields=("stage", "basis"), lang=lang)


def economics_price_items_rows_to_editor(frame: pd.DataFrame | list[dict[str, Any]] | None, *, lang: str = "es") -> list[dict[str, Any]]:
    normalized = normalize_economics_price_items_frame(frame)
    if normalized.empty:
        return []
    editor_frame = normalized.copy()
    mask = editor_frame["method"].astype(str).isin(ECONOMICS_PRICE_PERCENT_METHODS)
    editor_frame.loc[mask, "value"] = editor_frame.loc[mask, "value"].astype(float) * 100.0
    return _map_editor_labels(editor_frame.to_dict("records"), fields=("layer", "method"), lang=lang)


def economics_cost_items_rows_from_editor(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return normalize_economics_cost_items_frame(_map_editor_raw_values(rows or [], fields=("stage", "basis"))).to_dict("records")


def economics_price_items_rows_from_editor(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return normalize_economics_price_items_frame(_map_editor_raw_values(rows or [], fields=("layer", "method"))).to_dict("records")
