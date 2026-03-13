from __future__ import annotations

import numpy as np

from .types import LoadedConfigBundle, ValidationIssue


def validate_config(config_bundle: LoadedConfigBundle) -> list[ValidationIssue]:
    cfg = config_bundle.config
    issues: list[ValidationIssue] = []

    numeric_positive_fields = ("E_month_kWh", "PR", "P_mod_W", "years", "kWp_min", "kWp_max")
    for field in numeric_positive_fields:
        if float(cfg.get(field, 0) or 0) <= 0:
            issues.append(ValidationIssue("error", field, f"El valor de '{field}' debe ser mayor que cero."))

    if float(cfg.get("ILR_min", 0)) > float(cfg.get("ILR_max", 0)):
        issues.append(ValidationIssue("error", "ILR_min", "ILR_min no puede ser mayor que ILR_max."))

    if float(cfg.get("bat_eta_rt", 0)) <= 0 or float(cfg.get("bat_eta_rt", 0)) > 1.0:
        issues.append(ValidationIssue("error", "bat_eta_rt", "La eficiencia de batería debe estar entre 0 y 1."))

    if float(cfg.get("bat_DoD", 0)) <= 0 or float(cfg.get("bat_DoD", 0)) > 1.0:
        issues.append(ValidationIssue("error", "bat_DoD", "La profundidad de descarga debe estar entre 0 y 1."))

    if config_bundle.inverter_catalog.empty:
        issues.append(ValidationIssue("error", "Inversor_Catalog", "El catálogo de inversores está vacío."))
    if cfg.get("include_battery") and config_bundle.battery_catalog.empty:
        issues.append(ValidationIssue("warning", "Battery_Catalog", "Se solicitó batería, pero el catálogo está vacío."))

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

    if cfg.get("pricing_mode") not in {"variable", "total"}:
        issues.append(ValidationIssue("error", "pricing_mode", "pricing_mode debe ser 'variable' o 'total'."))

    return issues
