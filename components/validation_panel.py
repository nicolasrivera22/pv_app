from __future__ import annotations

from dash import html

from services.i18n import tr
from services.ui_schema import FIELD_SCHEMAS
from services.validation import localize_validation_message


def _pretty_field(field: str, *, lang: str = "es") -> str:
    if not field:
        return ""
    schema = FIELD_SCHEMAS.get(field)
    if schema is not None:
        if lang == "en":
            return schema.label_en or schema.label_es or field
        return schema.label_es or schema.label_en or field
    labels = {
        "Inversor_Catalog": {"es": "Catálogo de inversores", "en": "Inverter catalog"},
        "Battery_Catalog": {"es": "Catálogo de baterías", "en": "Battery catalog"},
        "Demand_Profile": {"es": "Perfil de demanda", "en": "Demand profile"},
        "Month_Demand_Profile": {"es": "Demanda mensual / HSP", "en": "Monthly demand / HSP"},
        "SUN_HSP_PROFILE": {"es": "Perfil solar", "en": "Solar profile"},
        "scan_range": {"es": "Rango de escaneo", "en": "Scan range"},
        "Precios_kWp_relativos": {"es": "Precio base por kWp", "en": "Base kWp pricing"},
        "Precios_kWp_relativos_Otros": {"es": "Otros precios variables", "en": "Other variable prices"},
    }
    if field in labels:
        return labels[field]["en" if lang == "en" else "es"]
    return field.replace("_", " ").strip()


def _section_id(field: str) -> str | None:
    if field in {"Demand_Profile"}:
        return "profile_demand"
    if field in {"Month_Demand_Profile"}:
        return "profile_month"
    if field in {"SUN_HSP_PROFILE"}:
        return "profile_solar"
    if field in {"Precios_kWp_relativos"}:
        return "profile_price"
    if field in {"Precios_kWp_relativos_Otros"}:
        return "profile_price_others"
    if field == "Inversor_Catalog":
        return "catalog_inverters"
    if field == "Battery_Catalog":
        return "catalog_batteries"
    if field in {"E_month_kWh", "alpha_mix", "use_excel_profile", "profile_type"}:
        return "assumptions_demand"
    if field in {"PR", "P_mod_W", "Voc25", "Vmp25", "Isc", "a_Voc_pct"}:
        return "assumptions_solar"
    if field in {"buy_tariff_COP_kWh", "sell_tariff_COP_kWh", "g_tar_buy", "g_tar_sell", "discount_rate", "deg_rate", "years", "pricing_mode", "price_total_COP", "include_hw_in_price", "include_var_others", "price_others_total", "price_per_kWp_COP"}:
        return "assumptions_pricing"
    if field.startswith("mc_"):
        return "assumptions_monte_carlo"
    if field in {"limit_peak_ratio_enable", "limit_peak_ratio", "limit_peak_year", "limit_peak_month_mode", "limit_peak_basis", "limit_peak_month_fixed"}:
        return "assumptions_peak_ratio"
    if field in {"kWp_seed_mode", "kWp_seed_manual_kWp", "modules_span_each_side", "kWp_min", "kWp_max", "scan_range"}:
        return "assumptions_scan"
    if field in {"export_allowed", "include_battery", "battery_name", "optimize_battery", "bat_DoD", "bat_coupling", "bat_eta_rt"}:
        return "assumptions_battery"
    return None


def _section_label(field: str, *, lang: str = "es") -> str:
    section_id = _section_id(field)
    if section_id is None:
        return ""
    labels = {
        "assumptions_demand": {"es": "Supuestos > Demanda y perfil", "en": "Assumptions > Demand and profile"},
        "assumptions_solar": {"es": "Supuestos > Sol y módulos", "en": "Assumptions > Solar and modules"},
        "assumptions_pricing": {"es": "Supuestos > Economía y precios", "en": "Assumptions > Economics and pricing"},
        "assumptions_monte_carlo": {"es": "Supuestos > Generales > Monte Carlo", "en": "Assumptions > General > Monte Carlo"},
        "assumptions_peak_ratio": {"es": "Supuestos > Límite de pico FV", "en": "Assumptions > PV peak cap"},
        "assumptions_scan": {"es": "Supuestos > Barrido de diseños", "en": "Assumptions > Design scan"},
        "assumptions_battery": {"es": "Supuestos > Batería y exportación", "en": "Assumptions > Battery and export"},
        "profile_demand": {"es": "Perfiles > Perfil de demanda", "en": "Profiles > Demand profile"},
        "profile_month": {"es": "Perfiles > Demanda mensual / HSP", "en": "Profiles > Monthly demand / HSP"},
        "profile_solar": {"es": "Perfiles > Perfil solar", "en": "Profiles > Solar profile"},
        "profile_price": {"es": "Perfiles > Precio variable por kWp", "en": "Profiles > Variable kWp pricing"},
        "profile_price_others": {"es": "Perfiles > Otros precios variables", "en": "Profiles > Other variable prices"},
        "catalog_inverters": {"es": "Catálogos > Inversores", "en": "Catalogs > Inverters"},
        "catalog_batteries": {"es": "Catálogos > Baterías", "en": "Catalogs > Batteries"},
    }
    return labels[section_id]["en" if lang == "en" else "es"]


def _issue_sort_key(issue, *, lang: str = "es") -> tuple[int, str, str]:
    severity = 0 if issue.level == "error" else 1
    section = _section_label(issue.field, lang=lang)
    field = _pretty_field(issue.field, lang=lang)
    return severity, section, field


def render_validation_panel(issues, *, lang: str = "es") -> html.Div:
    if not issues:
        return html.Div(tr("common.no_validation", lang), className="validation-empty")
    sorted_issues = sorted(issues, key=lambda issue: _issue_sort_key(issue, lang=lang))
    has_errors = any(issue.level == "error" for issue in sorted_issues)
    intro = tr("common.validation.errors_intro", lang) if has_errors else tr("common.validation.warnings_intro", lang)
    items = []
    for issue in sorted_issues:
        color = "#9f1239" if issue.level == "error" else "#92400e"
        level = "Error" if issue.level == "error" else ("Warning" if lang == "en" else "Advertencia")
        field = _pretty_field(issue.field, lang=lang)
        section = _section_label(issue.field, lang=lang)
        prefix_parts = [level]
        if section:
            prefix_parts.append(section)
        if field and issue.field not in {"Inversor_Catalog", "Battery_Catalog", "Demand_Profile", "Month_Demand_Profile", "SUN_HSP_PROFILE", "Precios_kWp_relativos", "Precios_kWp_relativos_Otros", "scan_range"}:
            prefix_parts.append(field)
        prefix = " · ".join(prefix_parts)
        items.append(
            html.Li(
                [html.Strong(f"{prefix}: "), localize_validation_message(issue, lang=lang)],
                style={"color": color},
            )
        )
    return html.Div(
        [
            html.P(intro, className="section-copy", style={"marginBottom": "0.6rem"}),
            html.Ul(items, style={"margin": 0, "paddingLeft": "1.2rem"}),
        ],
        className="validation-box",
    )
