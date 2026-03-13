from __future__ import annotations

from dataclasses import replace

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
