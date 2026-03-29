from __future__ import annotations

from dataclasses import replace
import re

import numpy as np
import pandas as pd

from pv_product.hardware import generate_kwp_candidates
from pv_product.panel_catalog import (
    MANUAL_PANEL_TOKEN,
    PANEL_CATALOG_COLUMNS,
    canonical_panel_name,
    resolve_selected_panel,
)
from pv_product.panel_technology import (
    is_supported_panel_technology_mode,
    panel_technology_catalog_label,
    normalize_panel_technology_mode,
)

from .economics_tables import (
    VALID_ECONOMICS_COST_HARDWARE_BINDINGS,
    VALID_ECONOMICS_COST_STAGES,
    VALID_ECONOMICS_COST_SOURCE_MODES,
    VALID_ECONOMICS_PRICE_LAYERS,
    economics_note_has_rich_migration,
)
from .types import LoadedConfigBundle, ValidationIssue

VALID_PRICING_MODES = {"variable", "total"}
VALID_SEED_MODES = {"auto", "manual"}
VALID_COUPLINGS = {"ac", "dc"}
VALID_PEAK_MONTH_MODES = {"max", "fixed"}
VALID_PEAK_BASES = {"weighted_mean", "max", "weekday", "p95"}
VALID_PROFILE_MODES = {"perfil horario relativo", "perfil hora dia de semana", "perfil general"}

INVERTER_REQUIRED_COLUMNS = ["name", "AC_kW", "Vmppt_min", "Vmppt_max", "Vdc_max", "Imax_mppt", "n_mppt", "price_COP"]
BATTERY_REQUIRED_COLUMNS = ["name", "nom_kWh", "max_kW", "max_ch_kW", "max_dis_kW", "price_COP"]
PANEL_REQUIRED_COLUMNS = list(PANEL_CATALOG_COLUMNS)
INVERTER_NUMERIC_COLUMNS = ["AC_kW", "Vmppt_min", "Vmppt_max", "Vdc_max", "Imax_mppt", "n_mppt", "price_COP"]
BATTERY_NUMERIC_COLUMNS = ["nom_kWh", "max_kW", "max_ch_kW", "max_dis_kW", "price_COP"]
PANEL_NUMERIC_COLUMNS = ["P_mod_W", "Voc25", "Vmp25", "Isc", "length_m", "width_m", "price_COP"]
PANEL_OPTIONAL_COLUMNS = {"price_COP"}
PRICE_TABLE_REQUIRED_COLUMNS = ["MIN", "MAX", "PRECIO_POR_KWP"]
PRICE_TABLE_NUMERIC_COLUMNS = ["MIN", "MAX", "PRECIO_POR_KWP"]

_ROW_REQUIRED_RE = re.compile(r"Fila (\d+): el campo '([^']+)' es obligatorio\.")
_ROW_NUMERIC_RE = re.compile(r"Fila (\d+): '([^']+)' debe ser numérico\.")
_DUPLICATES_RE = re.compile(r"Los nombres deben ser únicos\. Duplicados: (.+)\.")
_PANEL_RESERVED_RE = re.compile(r"Fila (\d+): el nombre '__manual__' está reservado\.")
_PANEL_TECH_MODE_RE = re.compile(r"Fila (\d+): panel_technology_mode debe ser un modo soportado\.")
_VALUE_GT_ZERO_RE = re.compile(r"El valor de '([^']+)' debe ser mayor que cero\.")
_INVALID_VALUE_RE = re.compile(r"Valor inválido para '([^']+)': (.+)\.")
_INVALID_BOOL_RE = re.compile(r"Valor booleano inválido para '([^']+)': (.+)\.")
_DAY_PROFILE_RE = re.compile(r"El perfil del día (\d+) no suma 1 exactamente; se usará tal como quedó normalizado\.")
_SCAN_BUILD_RE = re.compile(r"No se pudo generar el barrido de candidatos: (.+)")
_BASE_PRICE_BAND_RE = re.compile(r"No hay banda de precio base para ([0-9.]+) kWp\.")
_OTHER_PRICE_BAND_RE = re.compile(r"No hay banda de precio variable adicional para ([0-9.]+) kWp\.")
_ECON_DISABLED_EMPTY_NAME_RE = re.compile(r"(Economics_(?:Cost|Price)_Items) fila (\d+): se desactivó por nombre vacío\.")
_ECON_DISABLED_INVALID_VALUE_RE = re.compile(r"(Economics_(?:Cost|Price)_Items) fila (\d+): se desactivó por valor inválido en '([^']+)'\.")
_ECON_DISABLED_INVALID_ENUM_RE = re.compile(r"(Economics_(?:Cost|Price)_Items) fila (\d+): se desactivó por enum inválido en '([^']+)'\.")
_ECON_DISABLED_INVALID_BOOL_RE = re.compile(r"(Economics_(?:Cost|Price)_Items) fila (\d+): se desactivó por booleano inválido en '([^']+)'\.")
_ECON_DISABLED_RICH_MIGRATION_RE = re.compile(
    r"(Economics_(?:Cost|Price)_Items) fila (\d+): migrada desde schema rico y desactivada por método no soportado '([^']+)'\."
)
_ECON_RECOVERED_MODE_RE = re.compile(r"(Economics_(?:Cost|Price)_Items) fila (\d+): se recuperó '([^']+)' inválido; se usará '([^']+)'\.")
_ECON_SELECTED_HARDWARE_BINDING_RE = re.compile(
    r"(Economics_Cost_Items) fila (\d+): 'selected_hardware' requiere un 'hardware_binding' distinto de 'none'\."
)
_ECON_HARDWARE_PRICE_MISSING_RE = re.compile(
    r"(Economics_Cost_Items) fila (\d+): falta 'price_COP' para el hardware seleccionado '([^']+)'\."
)
_ECON_HARDWARE_UNRESOLVED_RE = re.compile(
    r"(Economics_Cost_Items) fila (\d+): no se pudo resolver el hardware seleccionado para '([^']+)'\."
)
_ECON_DUPLICATES_RE = re.compile(r"(Economics_(?:Cost|Price)_Items): nombres habilitados duplicados: (.+)\.")
_ECON_MISSING_LAYER_RE = re.compile(r"(Economics_(?:Cost|Price)_Items): no hay filas habilitadas en '([^']+)'\.")
_ECON_MIGRATED_DISABLED_RE = re.compile(r"(Economics_(?:Cost|Price)_Items): (\d+) filas migradas desde schema rico siguen deshabilitadas\.")

_TABLE_COLUMN_LABELS = {
    "name": {"es": "Nombre", "en": "Name"},
    "AC_kW": {"es": "Potencia AC", "en": "AC power"},
    "Vmppt_min": {"es": "Vmppt mínimo", "en": "Minimum MPPT voltage"},
    "Vmppt_max": {"es": "Vmppt máximo", "en": "Maximum MPPT voltage"},
    "Vdc_max": {"es": "Vdc máximo", "en": "Maximum DC voltage"},
    "Imax_mppt": {"es": "Corriente máxima MPPT", "en": "Maximum MPPT current"},
    "n_mppt": {"es": "Cantidad de MPPT", "en": "MPPT count"},
    "price_COP": {"es": "Precio", "en": "Price"},
    "nom_kWh": {"es": "Energía nominal", "en": "Nominal energy"},
    "max_kW": {"es": "Potencia máxima", "en": "Maximum power"},
    "max_ch_kW": {"es": "Potencia máxima de carga", "en": "Maximum charge power"},
    "max_dis_kW": {"es": "Potencia máxima de descarga", "en": "Maximum discharge power"},
    "P_mod_W": {"es": "Potencia módulo", "en": "Module power"},
    "Voc25": {"es": "Voc a 25 °C", "en": "Voc at 25 °C"},
    "Vmp25": {"es": "Vmp a 25 °C", "en": "Vmp at 25 °C"},
    "Isc": {"es": "Isc", "en": "Isc"},
    "length_m": {"es": "Largo", "en": "Length"},
    "width_m": {"es": "Ancho", "en": "Width"},
    "panel_technology_mode": {"es": "Tecnología de panel", "en": "Panel technology"},
    "stage": {"es": "Etapa", "en": "Stage"},
    "basis": {"es": "Base", "en": "Basis"},
    "amount_COP": {"es": "Monto", "en": "Amount"},
    "source_mode": {"es": "Fuente del costo", "en": "Cost source"},
    "hardware_binding": {"es": "Vínculo hardware", "en": "Hardware binding"},
    "panel": {"es": "panel", "en": "panel"},
    "inverter": {"es": "inversor", "en": "inverter"},
    "battery": {"es": "batería", "en": "battery"},
    "none": {"es": "sin vínculo", "en": "no binding"},
    "layer": {"es": "Capa", "en": "Layer"},
    "method": {"es": "Método", "en": "Method"},
    "value": {"es": "Valor", "en": "Value"},
    "enabled": {"es": "Activo", "en": "Enabled"},
    "notes": {"es": "Notas", "en": "Notes"},
    "MIN": {"es": "kWp mínimo", "en": "Minimum kWp"},
    "MAX": {"es": "kWp máximo", "en": "Maximum kWp"},
    "PRECIO_POR_KWP": {"es": "Precio por kWp", "en": "Price per kWp"},
}


def _economics_table_label(table_name: str, lang: str) -> str:
    if table_name == "Economics_Cost_Items":
        return "economics cost items" if lang == "en" else "las partidas de costo de economics"
    if table_name == "Economics_Price_Items":
        return "economics price items" if lang == "en" else "las partidas de precio de economics"
    return table_name


def _normalized_economics_name(value: object) -> str:
    return str(value or "").strip()


def _enabled_economics_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "enabled" not in frame.columns:
        return frame.iloc[0:0].copy()
    enabled = frame.copy()
    enabled["enabled"] = enabled["enabled"].fillna(False).astype(bool)
    return enabled.loc[enabled["enabled"]].copy()


def _add_duplicate_warning(frame: pd.DataFrame, *, issue_field: str, table_name: str, issues: list[ValidationIssue]) -> None:
    enabled = _enabled_economics_rows(frame)
    if enabled.empty or "name" not in enabled.columns:
        return
    names = enabled["name"].map(_normalized_economics_name)
    named = enabled.loc[names != ""].copy()
    if named.empty:
        return
    display_names = named["name"].map(_normalized_economics_name)
    normalized = display_names.str.casefold()
    duplicate_keys = normalized.loc[normalized.duplicated(keep=False)]
    if duplicate_keys.empty:
        return
    duplicate_key_set = set(duplicate_keys.tolist())
    seen: set[str] = set()
    duplicate_names: list[str] = []
    for display_name, folded_name in zip(display_names.tolist(), normalized.tolist()):
        if folded_name not in duplicate_key_set or folded_name in seen:
            continue
        duplicate_names.append(display_name)
        seen.add(folded_name)
    if duplicate_names:
        issues.append(ValidationIssue("warning", issue_field, f"{table_name}: nombres habilitados duplicados: {', '.join(duplicate_names)}."))


def _add_missing_layer_warning(
    frame: pd.DataFrame,
    *,
    column_name: str,
    required_values: tuple[str, ...],
    issue_field: str,
    table_name: str,
    issues: list[ValidationIssue],
) -> None:
    enabled = _enabled_economics_rows(frame)
    if enabled.empty or column_name not in enabled.columns:
        current_values: set[str] = set()
    else:
        named = enabled
        if "name" in named.columns:
            named = named.loc[named["name"].map(_normalized_economics_name) != ""].copy()
        current_values = {str(value).strip() for value in named[column_name].tolist() if str(value).strip()}
    for required_value in required_values:
        if required_value not in current_values:
            issues.append(ValidationIssue("warning", issue_field, f"{table_name}: no hay filas habilitadas en '{required_value}'."))


def _add_migrated_disabled_warning(frame: pd.DataFrame, *, issue_field: str, table_name: str, issues: list[ValidationIssue]) -> None:
    if frame.empty or "notes" not in frame.columns or "enabled" not in frame.columns:
        return
    disabled_migrated = frame.loc[
        (~frame["enabled"].fillna(False).astype(bool)) & frame["notes"].map(economics_note_has_rich_migration)
    ]
    if disabled_migrated.empty:
        return
    issues.append(
        ValidationIssue(
            "warning",
            issue_field,
            f"{table_name}: {len(disabled_migrated)} filas migradas desde schema rico siguen deshabilitadas.",
        )
    )


def validate_economics_tables(config_bundle: LoadedConfigBundle) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    cost_frame = config_bundle.economics_cost_items_table.copy()
    price_frame = config_bundle.economics_price_items_table.copy()

    _add_duplicate_warning(cost_frame, issue_field="economics_cost_items", table_name="Economics_Cost_Items", issues=issues)
    _add_duplicate_warning(price_frame, issue_field="economics_price_items", table_name="Economics_Price_Items", issues=issues)
    _add_missing_layer_warning(
        cost_frame,
        column_name="stage",
        required_values=("technical", "installed"),
        issue_field="economics_cost_items",
        table_name="Economics_Cost_Items",
        issues=issues,
    )
    _add_missing_layer_warning(
        price_frame,
        column_name="layer",
        required_values=("commercial",),
        issue_field="economics_price_items",
        table_name="Economics_Price_Items",
        issues=issues,
    )
    _add_migrated_disabled_warning(cost_frame, issue_field="economics_cost_items", table_name="Economics_Cost_Items", issues=issues)
    _add_migrated_disabled_warning(price_frame, issue_field="economics_price_items", table_name="Economics_Price_Items", issues=issues)
    return issues


def _price_table_covers_candidate(table: pd.DataFrame, k_wp: float) -> bool:
    mask = (table["MIN"] < k_wp) & (table["MAX"] >= k_wp)
    return bool(mask.any())


def normalize_catalog_rows(
    rows: list[dict] | None,
    required_columns: list[str],
    numeric_columns: list[str],
    field_prefix: str,
) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    frame = pd.DataFrame(rows or [])
    issues: list[ValidationIssue] = []

    for column in required_columns:
        if column not in frame.columns:
            frame[column] = np.nan

    frame = frame[required_columns].copy()
    frame = frame.replace(r"^\s*$", np.nan, regex=True)
    frame = frame.dropna(how="all").reset_index(drop=True)

    if frame.empty:
        return frame, issues

    for index, value in frame.get("name", pd.Series(dtype=object)).items():
        if pd.isna(value) or not str(value).strip():
            issues.append(
                ValidationIssue("error", field_prefix, f"Fila {index + 1}: el campo 'name' es obligatorio.")
            )
        else:
            frame.at[index, "name"] = str(value).strip()

    duplicated = frame["name"].dropna().astype(str).duplicated(keep=False)
    if duplicated.any():
        duplicate_names = sorted(frame.loc[duplicated, "name"].astype(str).unique().tolist())
        issues.append(
            ValidationIssue(
                "error",
                field_prefix,
                f"Los nombres deben ser únicos. Duplicados: {', '.join(duplicate_names)}.",
            )
        )

    for column in numeric_columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame[column].notna() & series.isna()
        for index in frame.index[invalid]:
            issues.append(
                ValidationIssue(
                    "error",
                    field_prefix,
                    f"Fila {index + 1}: '{column}' debe ser numérico.",
                )
            )
        frame[column] = series

    return frame, issues


def normalize_price_table_rows(
    rows: list[dict] | None,
    field_prefix: str,
) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    frame = pd.DataFrame(rows or [])
    issues: list[ValidationIssue] = []

    for column in PRICE_TABLE_REQUIRED_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan

    frame = frame[PRICE_TABLE_REQUIRED_COLUMNS].copy()
    frame["_source_row"] = range(1, len(frame) + 1)
    frame[PRICE_TABLE_REQUIRED_COLUMNS] = frame[PRICE_TABLE_REQUIRED_COLUMNS].replace(r"^\s*$", np.nan, regex=True)
    frame = frame.loc[~frame[PRICE_TABLE_REQUIRED_COLUMNS].isna().all(axis=1)].reset_index(drop=True)

    if frame.empty:
        return frame[PRICE_TABLE_REQUIRED_COLUMNS], issues

    for column in PRICE_TABLE_REQUIRED_COLUMNS:
        missing = frame[column].isna()
        for index in frame.index[missing]:
            issues.append(
                ValidationIssue(
                    "error",
                    field_prefix,
                    f"Fila {int(frame.at[index, '_source_row'])}: el campo '{column}' es obligatorio.",
                )
            )

    for column in PRICE_TABLE_NUMERIC_COLUMNS:
        series = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame[column].notna() & series.isna()
        for index in frame.index[invalid]:
            issues.append(
                ValidationIssue(
                    "error",
                    field_prefix,
                    f"Fila {int(frame.at[index, '_source_row'])}: '{column}' debe ser numérico.",
                )
            )
        frame[column] = series

    return frame[PRICE_TABLE_REQUIRED_COLUMNS], issues


def _table_column_label(column: str, lang: str) -> str:
    mapping = _TABLE_COLUMN_LABELS.get(column)
    if mapping is None:
        return column.replace("_", " ").strip()
    return mapping["en" if lang == "en" else "es"]


def _economics_message_column_label(column: str, lang: str) -> str:
    return _table_column_label(column, lang)


def localize_validation_message(issue: ValidationIssue, *, lang: str = "es") -> str:
    message = issue.message
    if match := _ECON_DISABLED_EMPTY_NAME_RE.fullmatch(message):
        table_name, row = match.groups()
        table_label = _economics_table_label(table_name, lang)
        if lang == "en":
            return f"Row {row} in {table_label} was disabled because Name is empty."
        return f"Fila {row} en {table_label}: se desactivó porque Nombre está vacío."
    if match := _ECON_DISABLED_INVALID_VALUE_RE.fullmatch(message):
        table_name, row, column = match.groups()
        table_label = _economics_table_label(table_name, lang)
        column_label = _economics_message_column_label(column, lang)
        if lang == "en":
            return f"Row {row} in {table_label} was disabled because {column_label} is invalid."
        return f"Fila {row} en {table_label}: se desactivó porque {column_label} es inválido."
    if match := _ECON_DISABLED_INVALID_ENUM_RE.fullmatch(message):
        table_name, row, column = match.groups()
        table_label = _economics_table_label(table_name, lang)
        column_label = _economics_message_column_label(column, lang)
        if lang == "en":
            return f"Row {row} in {table_label} was disabled because {column_label} uses an unsupported value."
        return f"Fila {row} en {table_label}: se desactivó porque {column_label} usa un valor no soportado."
    if match := _ECON_DISABLED_INVALID_BOOL_RE.fullmatch(message):
        table_name, row, column = match.groups()
        table_label = _economics_table_label(table_name, lang)
        column_label = _economics_message_column_label(column, lang)
        if lang == "en":
            return f"Row {row} in {table_label} was disabled because {column_label} is invalid."
        return f"Fila {row} en {table_label}: se desactivó porque {column_label} es inválido."
    if match := _ECON_DISABLED_RICH_MIGRATION_RE.fullmatch(message):
        table_name, row, method_value = match.groups()
        table_label = _economics_table_label(table_name, lang)
        if lang == "en":
            return (
                f"Row {row} in {table_label} was migrated from the previous economics schema and disabled because "
                f"method '{method_value}' is not supported in Phase 1."
            )
        return (
            f"Fila {row} en {table_label}: se migró desde el schema económico anterior y se desactivó porque "
            f"el método '{method_value}' no está soportado en Fase 1."
        )
    if match := _ECON_RECOVERED_MODE_RE.fullmatch(message):
        table_name, row, column, fallback = match.groups()
        table_label = _economics_table_label(table_name, lang)
        column_label = _economics_message_column_label(column, lang)
        if lang == "en":
            return f"Row {row} in {table_label} used the fallback '{fallback}' because {column_label} was invalid."
        return f"Fila {row} en {table_label}: se usó el fallback '{fallback}' porque {column_label} era inválido."
    if match := _ECON_SELECTED_HARDWARE_BINDING_RE.fullmatch(message):
        table_name, row = match.groups()
        table_label = _economics_table_label(table_name, lang)
        if lang == "en":
            return f"Row {row} in {table_label} uses Selected hardware but has no hardware binding."
        return f"Fila {row} en {table_label}: Hardware seleccionado requiere un vínculo hardware."
    if match := _ECON_HARDWARE_PRICE_MISSING_RE.fullmatch(message):
        table_name, row, hardware_name = match.groups()
        table_label = _economics_table_label(table_name, lang)
        if lang == "en":
            return f"Row {row} in {table_label} resolved hardware '{hardware_name}', but it has no price."
        return f"Fila {row} en {table_label}: el hardware '{hardware_name}' se resolvió, pero no tiene precio."
    if match := _ECON_HARDWARE_UNRESOLVED_RE.fullmatch(message):
        table_name, row, binding = match.groups()
        table_label = _economics_table_label(table_name, lang)
        binding_label = _economics_message_column_label(binding, lang)
        if lang == "en":
            return f"Row {row} in {table_label} could not resolve the selected {binding_label.lower()}."
        return f"Fila {row} en {table_label}: no se pudo resolver el {binding_label.lower()} seleccionado."
    if match := _ECON_DUPLICATES_RE.fullmatch(message):
        table_name, duplicates = match.groups()
        table_label = _economics_table_label(table_name, lang)
        if lang == "en":
            return f"Enabled items in {table_label} must have unique names. Duplicate names: {duplicates}."
        return f"Las filas activas en {table_label} deben tener nombres únicos. Nombres duplicados: {duplicates}."
    if match := _ECON_MISSING_LAYER_RE.fullmatch(message):
        table_name, required_value = match.groups()
        table_label = _economics_table_label(table_name, lang)
        if lang == "en":
            return f"{table_label} has no enabled rows in '{required_value}'."
        return f"No hay filas activas en '{required_value}' dentro de {table_label}."
    if match := _ECON_MIGRATED_DISABLED_RE.fullmatch(message):
        table_name, count = match.groups()
        table_label = _economics_table_label(table_name, lang)
        if lang == "en":
            return f"{count} rows migrated from the previous economics schema remain disabled in {table_label}."
        return f"{count} filas migradas desde el schema económico anterior siguen deshabilitadas en {table_label}."
    if match := _ROW_REQUIRED_RE.fullmatch(message):
        row, column = match.groups()
        column_label = _table_column_label(column, lang)
        if lang == "en":
            return f"Row {row}: add a value for {column_label}."
        return f"Fila {row}: agrega un valor en {column_label}."
    if match := _ROW_NUMERIC_RE.fullmatch(message):
        row, column = match.groups()
        column_label = _table_column_label(column, lang)
        if lang == "en":
            return f"Row {row}: enter a numeric value for {column_label}."
        return f"Fila {row}: ingresa un valor numérico en {column_label}."
    if match := _DUPLICATES_RE.fullmatch(message):
        duplicates = match.group(1)
        if lang == "en":
            return f"Each item must have a unique name. Duplicate names: {duplicates}."
        return f"Cada elemento debe tener un nombre único. Nombres duplicados: {duplicates}."
    if match := _PANEL_RESERVED_RE.fullmatch(message):
        row = match.group(1)
        if lang == "en":
            return f"Row {row}: '__manual__' is reserved for the manual panel-selection mode."
        return f"Fila {row}: '__manual__' está reservado para el modo manual de selección de panel."
    if match := _PANEL_TECH_MODE_RE.fullmatch(message):
        row = match.group(1)
        if lang == "en":
            return f"Row {row}: choose a supported panel technology mode."
        return f"Fila {row}: elige una tecnología de panel compatible."
    if _VALUE_GT_ZERO_RE.fullmatch(message):
        if lang == "en":
            return "Enter a value greater than zero."
        return "Ingresa un valor mayor que cero."
    if message == "modules_span_each_side no puede ser negativo.":
        if lang == "en":
            return "Use zero or a positive number of modules."
        return "Usa cero o un número positivo de módulos."
    if message == "limit_peak_month_fixed debe estar entre 1 y 12.":
        if lang == "en":
            return "Choose a month between 1 and 12."
        return "Elige un mes entre 1 y 12."
    if message == "ILR_min no puede ser mayor que ILR_max.":
        if lang == "en":
            return "Minimum ILR cannot be higher than Maximum ILR."
        return "El ILR mínimo no puede ser mayor que el ILR máximo."
    if message == "kWp_min no puede ser mayor que kWp_max.":
        if lang == "en":
            return "Minimum scan size cannot be higher than Maximum scan size."
        return "El tamaño mínimo del escaneo no puede ser mayor que el tamaño máximo."
    if message == "La eficiencia de batería debe estar entre 0 y 1.":
        if lang == "en":
            return "Enter a round-trip efficiency above 0% and up to 100%."
        return "Ingresa una eficiencia ida y vuelta mayor a 0% y hasta 100%."
    if message == "La profundidad de descarga debe estar entre 0 y 1.":
        if lang == "en":
            return "Enter a depth of discharge above 0% and up to 100%."
        return "Ingresa una profundidad de descarga mayor a 0% y hasta 100%."
    if message == "pricing_mode debe ser 'variable' o 'total'.":
        if lang == "en":
            return "Choose Variable (by kWp bands) or Fixed project total."
        return "Elige Variable (por bandas de kWp) o Total fijo del proyecto."
    if message == "kWp_seed_mode debe ser 'auto' o 'manual'.":
        if lang == "en":
            return "Choose Auto or Manual for the scan starting point."
        return "Elige Auto o Manual para el punto inicial del escaneo."
    if message == "bat_coupling debe ser 'ac' o 'dc'.":
        if lang == "en":
            return "Choose AC or DC for the battery connection model."
        return "Elige AC o DC para el modelo de conexión de la batería."
    if message == "limit_peak_month_mode debe ser 'max' o 'fixed'.":
        if lang == "en":
            return "Choose Max or Fixed to define the peak month."
        return "Elige Máximo o Fijo para definir el mes pico."
    if message == "limit_peak_basis debe ser weighted_mean, max, weekday o p95.":
        if lang == "en":
            return "Choose how to measure the load peak: Weighted mean, Max, Weekday, or P95."
        return "Elige cómo medir el pico de carga: Promedio ponderado, Máximo, Día hábil o P95."
    if message == "use_excel_profile debe ser un modo de perfil soportado.":
        if lang == "en":
            return "Choose a supported demand profile method."
        return "Elige un método de perfil de demanda compatible."
    if message == "El catálogo de inversores está vacío.":
        if lang == "en":
            return "Add at least one inverter in Hardware catalogs before running the deterministic scan."
        return "Agrega al menos un inversor en Catálogos de hardware antes de ejecutar el escaneo determinístico."
    if message == "Se solicitó batería, pero el catálogo está vacío.":
        if lang == "en":
            return "Battery analysis is enabled, but the battery catalog is empty. Add a battery or turn battery analysis off."
        return "El análisis con batería está activado, pero el catálogo está vacío. Agrega una batería o desactiva el análisis con batería."
    if message == "battery_name no existe en el catálogo de baterías.":
        if lang == "en":
            return "Choose a fixed battery that exists in the battery catalog, or turn on battery optimization."
        return "Elige una batería fija que exista en el catálogo o activa la optimización de baterías."
    if message == "panel_name no existe en el catálogo de paneles.":
        if lang == "en":
            return "Choose a panel that exists in the panel catalog, or switch back to manual configuration."
        return "Elige un panel que exista en el catálogo o vuelve a la configuración manual."
    if message == "El perfil 7x24 debe tener forma (7, 24).":
        if lang == "en":
            return "The weekday 7x24 demand table must contain 7 days and 24 hourly values."
        return "La tabla de demanda hora-día-semana debe tener 7 días y 24 valores horarios."
    if message == "Los pesos diarios deben tener 7 valores.":
        if lang == "en":
            return "The daily-weight table must contain 7 values, one for each day."
        return "La tabla de pesos diarios debe tener 7 valores, uno por cada día."
    if message == "Los perfiles mensuales deben tener 12 meses.":
        if lang == "en":
            return "The monthly demand and HSP table must contain 12 months."
        return "La tabla de demanda mensual y HSP debe tener 12 meses."
    if message == "El perfil solar debe tener 24 horas.":
        if lang == "en":
            return "The hourly solar profile must contain 24 values."
        return "El perfil solar horario debe tener 24 valores."
    if message == "El perfil solar se normalizó para que sume 1.":
        if lang == "en":
            return "The solar profile did not sum to 100%, so the app normalized it automatically. Review it if that was not intentional."
        return "El perfil solar no sumaba 100%, así que la app lo normalizó automáticamente. Revísalo si eso no era intencional."
    if match := _DAY_PROFILE_RE.fullmatch(message):
        day = match.group(1)
        if lang == "en":
            return f"Day {day} in the 7x24 demand profile does not sum to 100%. The normalized version will be used."
        return f"El día {day} del perfil 7x24 no suma 100%. Se usará la versión normalizada."
    if match := _SCAN_BUILD_RE.fullmatch(message):
        detail = match.group(1)
        if lang == "en":
            return f"The current scan settings could not build a feasible design range. Review the starting size, module span, and kWp limits. Details: {detail}"
        return f"La configuración actual no pudo construir un rango factible de diseños. Revisa el punto inicial, el span de módulos y los límites de kWp. Detalle: {detail}"
    if message == "La configuración actual no genera ningún candidato de kWp.":
        if lang == "en":
            return "The current scan settings do not produce any feasible designs. Widen the scan range or relax the peak-ratio limit."
        return "La configuración actual no produce diseños factibles. Amplía el rango de escaneo o relaja el límite de pico FV."
    if match := _BASE_PRICE_BAND_RE.fullmatch(message):
        kwp = match.group(1)
        if lang == "en":
            return f"No base pricing band covers {kwp} kWp. Extend the pricing table or narrow the design scan."
        return f"Ninguna banda de precio base cubre {kwp} kWp. Amplía la tabla de precios o estrecha el escaneo."
    if match := _OTHER_PRICE_BAND_RE.fullmatch(message):
        kwp = match.group(1)
        if lang == "en":
            return f"No additional-cost band covers {kwp} kWp. Extend that table or turn off other variable prices."
        return f"Ninguna banda de costos adicionales cubre {kwp} kWp. Amplía esa tabla o desactiva los otros precios variables."
    if match := _INVALID_VALUE_RE.fullmatch(message):
        raw_value = match.group(2)
        if lang == "en":
            return f"The imported value could not be read. Check the workbook cell and try again. Current value: {raw_value}."
        return f"No se pudo interpretar el valor importado. Revisa la celda del libro e inténtalo de nuevo. Valor actual: {raw_value}."
    if match := _INVALID_BOOL_RE.fullmatch(message):
        raw_value = match.group(2)
        if lang == "en":
            return f"Use Yes or No for this field. Current value: {raw_value}."
        return f"Usa Sí o No en este campo. Valor actual: {raw_value}."
    return message


def normalize_inverter_catalog_rows(rows: list[dict] | None) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    return normalize_catalog_rows(rows, INVERTER_REQUIRED_COLUMNS, INVERTER_NUMERIC_COLUMNS, "Inversor_Catalog")


def normalize_battery_catalog_rows(rows: list[dict] | None) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    return normalize_catalog_rows(rows, BATTERY_REQUIRED_COLUMNS, BATTERY_NUMERIC_COLUMNS, "Battery_Catalog")


def normalize_panel_catalog_rows(rows: list[dict] | None) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    frame = pd.DataFrame(rows or [])
    issues: list[ValidationIssue] = []

    for column in PANEL_REQUIRED_COLUMNS:
        if column not in frame.columns:
            frame[column] = 0.0 if column in PANEL_OPTIONAL_COLUMNS else np.nan

    frame = frame[PANEL_REQUIRED_COLUMNS].copy()
    frame["_source_row"] = range(1, len(frame) + 1)
    frame[PANEL_REQUIRED_COLUMNS] = frame[PANEL_REQUIRED_COLUMNS].replace(r"^\s*$", np.nan, regex=True)
    frame = frame.loc[~frame[PANEL_REQUIRED_COLUMNS].isna().all(axis=1)].reset_index(drop=True)

    if frame.empty:
        return frame[PANEL_REQUIRED_COLUMNS], issues

    for column in PANEL_REQUIRED_COLUMNS:
        if column in PANEL_OPTIONAL_COLUMNS:
            frame[column] = frame[column].fillna(0.0)
            continue
        missing = frame[column].isna()
        for index in frame.index[missing]:
            issues.append(
                ValidationIssue(
                    "error",
                    "Panel_Catalog",
                    f"Fila {int(frame.at[index, '_source_row'])}: el campo '{column}' es obligatorio.",
                )
            )

    canonical_names: list[str] = []
    for index, value in frame["name"].items():
        if pd.isna(value) or not str(value).strip():
            canonical_names.append("")
            continue
        name = str(value).strip()
        frame.at[index, "name"] = name
        canonical = canonical_panel_name(name)
        canonical_names.append(canonical)
        if canonical == canonical_panel_name(MANUAL_PANEL_TOKEN):
            issues.append(
                ValidationIssue(
                    "error",
                    "Panel_Catalog",
                    f"Fila {int(frame.at[index, '_source_row'])}: el nombre '__manual__' está reservado.",
                )
            )

    duplicated = pd.Series(canonical_names).replace("", np.nan).duplicated(keep=False)
    if duplicated.any():
        duplicate_names = sorted(frame.loc[duplicated, "name"].astype(str).unique().tolist())
        issues.append(
            ValidationIssue(
                "error",
                "Panel_Catalog",
                f"Los nombres deben ser únicos. Duplicados: {', '.join(duplicate_names)}.",
            )
        )

    for column in PANEL_NUMERIC_COLUMNS:
        series = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame[column].notna() & series.isna()
        for index in frame.index[invalid]:
            issues.append(
                ValidationIssue(
                    "error",
                    "Panel_Catalog",
                    f"Fila {int(frame.at[index, '_source_row'])}: '{column}' debe ser numérico.",
                )
            )
        frame[column] = series.fillna(0.0) if column in PANEL_OPTIONAL_COLUMNS else series

    for index, value in frame["panel_technology_mode"].items():
        if pd.isna(value):
            continue
        normalized = normalize_panel_technology_mode(value)
        if not is_supported_panel_technology_mode(value):
            issues.append(
                ValidationIssue(
                    "error",
                    "Panel_Catalog",
                    f"Fila {int(frame.at[index, '_source_row'])}: panel_technology_mode debe ser un modo soportado.",
                )
            )
        frame.at[index, "panel_technology_mode"] = panel_technology_catalog_label(normalized, "es")

    return frame[PANEL_REQUIRED_COLUMNS], issues


def refresh_bundle_issues(
    bundle: LoadedConfigBundle,
    extra_issues: list[ValidationIssue] | tuple[ValidationIssue, ...] = (),
) -> LoadedConfigBundle:
    issue_map: dict[tuple[str, str, str], ValidationIssue] = {}
    for issue in [*bundle.issues, *extra_issues]:
        issue_map[(issue.level, issue.field, issue.message)] = issue
    base_bundle = replace(bundle, issues=())
    for issue in validate_config(base_bundle):
        issue_map[(issue.level, issue.field, issue.message)] = issue
    return replace(base_bundle, issues=tuple(issue_map.values()))


def validate_config(config_bundle: LoadedConfigBundle) -> list[ValidationIssue]:
    cfg = config_bundle.config
    issues: list[ValidationIssue] = []

    numeric_positive_fields = ("E_month_kWh", "PR", "P_mod_W", "years", "kWp_min", "kWp_max")
    for field in numeric_positive_fields:
        if float(cfg.get(field, 0) or 0) <= 0:
            issues.append(ValidationIssue("error", field, f"El valor de '{field}' debe ser mayor que cero."))

    if int(cfg.get("modules_span_each_side", 0) or 0) < 0:
        issues.append(ValidationIssue("error", "modules_span_each_side", "modules_span_each_side no puede ser negativo."))

    if not (1 <= int(cfg.get("limit_peak_month_fixed", 1) or 1) <= 12):
        issues.append(ValidationIssue("error", "limit_peak_month_fixed", "limit_peak_month_fixed debe estar entre 1 y 12."))

    if float(cfg.get("ILR_min", 0)) > float(cfg.get("ILR_max", 0)):
        issues.append(ValidationIssue("error", "ILR_min", "ILR_min no puede ser mayor que ILR_max."))

    if float(cfg.get("kWp_min", 0)) > float(cfg.get("kWp_max", 0)):
        issues.append(ValidationIssue("error", "kWp_min", "kWp_min no puede ser mayor que kWp_max."))

    if float(cfg.get("bat_eta_rt", 0)) <= 0 or float(cfg.get("bat_eta_rt", 0)) > 1.0:
        issues.append(ValidationIssue("error", "bat_eta_rt", "La eficiencia de batería debe estar entre 0 y 1."))

    if float(cfg.get("bat_DoD", 0)) <= 0 or float(cfg.get("bat_DoD", 0)) > 1.0:
        issues.append(ValidationIssue("error", "bat_DoD", "La profundidad de descarga debe estar entre 0 y 1."))

    if cfg.get("pricing_mode") not in VALID_PRICING_MODES:
        issues.append(ValidationIssue("error", "pricing_mode", "pricing_mode debe ser 'variable' o 'total'."))
    if cfg.get("kWp_seed_mode") not in VALID_SEED_MODES:
        issues.append(ValidationIssue("error", "kWp_seed_mode", "kWp_seed_mode debe ser 'auto' o 'manual'."))
    if cfg.get("bat_coupling") not in VALID_COUPLINGS:
        issues.append(ValidationIssue("error", "bat_coupling", "bat_coupling debe ser 'ac' o 'dc'."))
    if cfg.get("limit_peak_month_mode") not in VALID_PEAK_MONTH_MODES:
        issues.append(ValidationIssue("error", "limit_peak_month_mode", "limit_peak_month_mode debe ser 'max' o 'fixed'."))
    if cfg.get("limit_peak_basis") not in VALID_PEAK_BASES:
        issues.append(ValidationIssue("error", "limit_peak_basis", "limit_peak_basis debe ser weighted_mean, max, weekday o p95."))
    if cfg.get("use_excel_profile") not in VALID_PROFILE_MODES:
        issues.append(ValidationIssue("error", "use_excel_profile", "use_excel_profile debe ser un modo de perfil soportado."))

    if config_bundle.inverter_catalog.empty:
        issues.append(ValidationIssue("error", "Inversor_Catalog", "El catálogo de inversores está vacío."))
    if cfg.get("include_battery") and config_bundle.battery_catalog.empty:
        issues.append(ValidationIssue("error", "Battery_Catalog", "Se solicitó batería, pero el catálogo está vacío."))
    panel_selection = resolve_selected_panel(cfg, config_bundle.panel_catalog)
    if panel_selection.selection_mode == "invalid" and panel_selection.error_message:
        issues.append(ValidationIssue("error", "panel_name", panel_selection.error_message))

    if cfg.get("include_battery") and (not cfg.get("optimize_battery")) and str(cfg.get("battery_name", "")).strip():
        names = set(config_bundle.battery_catalog.get("name", pd.Series(dtype=object)).astype(str).tolist())
        if str(cfg["battery_name"]) not in names:
            issues.append(ValidationIssue("error", "battery_name", "battery_name no existe en el catálogo de baterías."))

    if config_bundle.demand_profile_7x24.shape != (7, 24):
        issues.append(ValidationIssue("error", "Demand_Profile", "El perfil 7x24 debe tener forma (7, 24)."))
    if config_bundle.day_weights.shape != (7,):
        issues.append(ValidationIssue("error", "Demand_Profile", "Los pesos diarios deben tener 7 valores."))
    if config_bundle.hsp_month.shape != (12,) or config_bundle.demand_month_factor.shape != (12,):
        issues.append(ValidationIssue("error", "Month_Demand_Profile", "Los perfiles mensuales deben tener 12 meses."))
    if config_bundle.solar_profile.shape != (24,):
        issues.append(ValidationIssue("error", "SUN_HSP_PROFILE", "El perfil solar debe tener 24 horas."))

    if not np.isclose(config_bundle.solar_profile.sum(), 1.0, atol=1e-6):
        issues.append(ValidationIssue("warning", "SUN_HSP_PROFILE", "El perfil solar se normalizó para que sume 1."))

    for idx, row in enumerate(config_bundle.demand_profile_7x24):
        if not np.isclose(row.sum(), 1.0, atol=1e-6):
            issues.append(
                ValidationIssue(
                    "warning",
                    "Demand_Profile",
                    f"El perfil del día {idx + 1} no suma 1 exactamente; se usará tal como quedó normalizado.",
                )
            )

    issues.extend(validate_economics_tables(config_bundle))

    fatal_fields = {issue.field for issue in issues if issue.level == "error"}
    if fatal_fields.isdisjoint({"kWp_min", "kWp_max", "modules_span_each_side", "P_mod_W", "E_month_kWh", "PR", "HSP"}):
        try:
            candidates, _ = generate_kwp_candidates(cfg)
        except Exception as exc:
            issues.append(ValidationIssue("error", "scan_range", f"No se pudo generar el barrido de candidatos: {exc}"))
        else:
            if not candidates:
                issues.append(ValidationIssue("error", "scan_range", "La configuración actual no genera ningún candidato de kWp."))
            else:
                for k_wp in candidates:
                    if not _price_table_covers_candidate(config_bundle.cop_kwp_table, k_wp):
                        issues.append(
                            ValidationIssue(
                                "error",
                                "Precios_kWp_relativos",
                                f"No hay banda de precio base para {k_wp:.3f} kWp.",
                            )
                        )
                        break
                    if cfg.get("include_var_others") and not _price_table_covers_candidate(config_bundle.cop_kwp_table_others, k_wp):
                        issues.append(
                            ValidationIssue(
                                "error",
                                "Precios_kWp_relativos_Otros",
                                f"No hay banda de precio variable adicional para {k_wp:.3f} kWp.",
                            )
                        )
                        break

    return issues
