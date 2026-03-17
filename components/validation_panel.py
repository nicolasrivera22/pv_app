from __future__ import annotations

from dash import html

from services.i18n import tr
from services.ui_schema import FIELD_SCHEMAS


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
        "Precios_kWp_relativos_Otros": {"es": "Costos variables adicionales", "en": "Additional variable costs"},
    }
    if field in labels:
        return labels[field]["en" if lang == "en" else "es"]
    return field.replace("_", " ").strip()


def render_validation_panel(issues, *, lang: str = "es") -> html.Div:
    if not issues:
        return html.Div(tr("common.no_validation", lang), className="validation-empty")
    items = []
    for issue in issues:
        color = "#9f1239" if issue.level == "error" else "#92400e"
        level = "Error" if issue.level == "error" else ("Warning" if lang == "en" else "Advertencia")
        field = _pretty_field(issue.field, lang=lang)
        prefix = f"{level}: {field}: " if field else f"{level}: "
        items.append(html.Li(f"{prefix}{issue.message}", style={"color": color}))
    return html.Div(html.Ul(items, style={"margin": 0, "paddingLeft": "1.2rem"}), className="validation-box")
