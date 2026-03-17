from __future__ import annotations

from dataclasses import replace
import re

import numpy as np
import pandas as pd

from pv_product.hardware import generate_kwp_candidates

from .types import LoadedConfigBundle, ValidationIssue

VALID_PRICING_MODES = {"variable", "total"}
VALID_SEED_MODES = {"auto", "manual"}
VALID_COUPLINGS = {"ac", "dc"}
VALID_PEAK_MONTH_MODES = {"max", "fixed"}
VALID_PEAK_BASES = {"weighted_mean", "max", "weekday", "p95"}
VALID_PROFILE_MODES = {"perfil horario relativo", "perfil hora dia de semana", "perfil general"}

INVERTER_REQUIRED_COLUMNS = ["name", "AC_kW", "Vmppt_min", "Vmppt_max", "Vdc_max", "Imax_mppt", "n_mppt", "price_COP"]
BATTERY_REQUIRED_COLUMNS = ["name", "nom_kWh", "max_kW", "max_ch_kW", "max_dis_kW", "price_COP"]
INVERTER_NUMERIC_COLUMNS = ["AC_kW", "Vmppt_min", "Vmppt_max", "Vdc_max", "Imax_mppt", "n_mppt", "price_COP"]
BATTERY_NUMERIC_COLUMNS = ["nom_kWh", "max_kW", "max_ch_kW", "max_dis_kW", "price_COP"]

_ROW_REQUIRED_RE = re.compile(r"Fila (\d+): el campo '([^']+)' es obligatorio\.")
_ROW_NUMERIC_RE = re.compile(r"Fila (\d+): '([^']+)' debe ser numérico\.")
_DUPLICATES_RE = re.compile(r"Los nombres deben ser únicos\. Duplicados: (.+)\.")
_VALUE_GT_ZERO_RE = re.compile(r"El valor de '([^']+)' debe ser mayor que cero\.")
_INVALID_VALUE_RE = re.compile(r"Valor inválido para '([^']+)': (.+)\.")
_INVALID_BOOL_RE = re.compile(r"Valor booleano inválido para '([^']+)': (.+)\.")
_DAY_PROFILE_RE = re.compile(r"El perfil del día (\d+) no suma 1 exactamente; se usará tal como quedó normalizado\.")
_SCAN_BUILD_RE = re.compile(r"No se pudo generar el barrido de candidatos: (.+)")
_BASE_PRICE_BAND_RE = re.compile(r"No hay banda de precio base para ([0-9.]+) kWp\.")
_OTHER_PRICE_BAND_RE = re.compile(r"No hay banda de precio variable adicional para ([0-9.]+) kWp\.")

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
}


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


def _table_column_label(column: str, lang: str) -> str:
    mapping = _TABLE_COLUMN_LABELS.get(column)
    if mapping is None:
        return column.replace("_", " ").strip()
    return mapping["en" if lang == "en" else "es"]


def localize_validation_message(issue: ValidationIssue, *, lang: str = "es") -> str:
    message = issue.message
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
            return f"No additional-cost band covers {kwp} kWp. Extend that table or turn off additional variable costs."
        return f"Ninguna banda de costos adicionales cubre {kwp} kWp. Amplía esa tabla o desactiva los costos variables adicionales."
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
