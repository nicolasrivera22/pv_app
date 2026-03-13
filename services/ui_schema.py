from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dash.dash_table.Format import Format, Group, Scheme

from .config_metadata import ConfigFieldMeta, extract_config_metadata
from .i18n import tr


@dataclass(frozen=True)
class FieldUiSchema:
    kind: str
    visibility: str = "advanced"
    label_es: str | None = None
    label_en: str | None = None
    help_es: str | None = None
    help_en: str | None = None
    options: tuple[tuple[str, Any], ...] = ()


FIELD_SCHEMAS: dict[str, FieldUiSchema] = {
    "E_month_kWh": FieldUiSchema("number", "basic", "Demanda mensual", "Monthly demand"),
    "alpha_mix": FieldUiSchema("number", "advanced", "Mezcla de carga diurna", "Daytime load mix"),
    "use_excel_profile": FieldUiSchema(
        "dropdown",
        "basic",
        "Modo de perfil",
        "Profile mode",
        "Define cómo se reparte la demanda horaria. También controla qué tabla de perfiles debes editar más abajo.",
        "Defines how hourly demand is distributed. It also controls which profile table you should edit below.",
        options=(
            ("Perfil hora-día-semana", "perfil hora dia de semana"),
            ("Perfil horario relativo", "perfil horario relativo"),
            ("Perfil general", "perfil general"),
        ),
    ),
    "PR": FieldUiSchema("number", "basic", "PR", "PR"),
    "Tmin_C": FieldUiSchema("number", "advanced", "Temperatura mínima", "Minimum temperature"),
    "P_mod_W": FieldUiSchema("number", "basic", "Potencia del módulo", "Module power"),
    "Voc25": FieldUiSchema("number", "advanced", "Voc a 25 °C", "Voc at 25 °C"),
    "Vmp25": FieldUiSchema("number", "advanced", "Vmp a 25 °C", "Vmp at 25 °C"),
    "Isc": FieldUiSchema("number", "advanced", "Isc", "Isc"),
    "a_Voc_pct": FieldUiSchema("number", "advanced", "Coef. térmico Voc", "Voc thermal coefficient"),
    "ILR_min": FieldUiSchema("number", "advanced", "ILR mínimo", "Minimum ILR"),
    "ILR_max": FieldUiSchema("number", "advanced", "ILR máximo", "Maximum ILR"),
    "buy_tariff_COP_kWh": FieldUiSchema("number", "basic", "Tarifa de compra", "Buy tariff"),
    "sell_tariff_COP_kWh": FieldUiSchema("number", "basic", "Tarifa de venta", "Sell tariff"),
    "g_tar_buy": FieldUiSchema("number", "advanced", "Crecimiento tarifa compra", "Buy tariff growth"),
    "g_tar_sell": FieldUiSchema("number", "advanced", "Crecimiento tarifa venta", "Sell tariff growth"),
    "deg_rate": FieldUiSchema("number", "advanced", "Degradación anual", "Annual degradation"),
    "discount_rate": FieldUiSchema("number", "basic", "Tasa de descuento", "Discount rate"),
    "years": FieldUiSchema("number", "basic", "Horizonte (años)", "Project years"),
    "pricing_mode": FieldUiSchema(
        "dropdown",
        "basic",
        "Modo de precio",
        "Pricing mode",
        "Elige si el costo base se calcula por bandas de kWp o como un total fijo del proyecto.",
        "Choose whether the base cost is calculated from kWp pricing bands or from a fixed project total.",
        options=(("Variable", "variable"), ("Total", "total")),
    ),
    "price_total_COP": FieldUiSchema("number", "advanced", "Precio total", "Total price"),
    "include_hw_in_price": FieldUiSchema(
        "dropdown",
        "advanced",
        "Agregar hardware aparte",
        "Add hardware on top",
        "Si activas esta opción, inversor y batería se suman aparte del precio base del proyecto.",
        "If enabled, inverter and battery are added on top of the base project price.",
        options=(("Sí", True), ("No", False)),
    ),
    "include_var_others": FieldUiSchema(
        "dropdown",
        "advanced",
        "Incluir otros variables",
        "Include variable others",
        "Suma la tabla de 'otros costos variables' además del precio principal por kWp.",
        "Adds the 'other variable costs' table on top of the main kWp pricing table.",
        options=(("Sí", True), ("No", False)),
    ),
    "price_others_total": FieldUiSchema("number", "advanced", "Otros fijos", "Fixed others"),
    "price_per_kWp_COP": FieldUiSchema("number", "advanced", "Precio por kWp", "Price per kWp"),
    "mc_PR_std": FieldUiSchema("number", "advanced", "MC desv. PR", "MC PR std"),
    "mc_buy_std": FieldUiSchema("number", "advanced", "MC desv. compra", "MC buy std"),
    "mc_sell_std": FieldUiSchema("number", "advanced", "MC desv. venta", "MC sell std"),
    "mc_demand_std": FieldUiSchema("number", "advanced", "MC desv. demanda", "MC demand std"),
    "mc_use_manual_kWp": FieldUiSchema(
        "dropdown",
        "advanced",
        "MC kWp manual",
        "MC manual kWp",
        options=(("Sí", True), ("No", False)),
    ),
    "mc_manual_kWp": FieldUiSchema("number", "advanced", "MC kWp manual fijo", "MC fixed manual kWp"),
    "mc_n_simulations": FieldUiSchema("number", "advanced", "MC simulaciones", "MC simulations"),
    "mc_battery_name": FieldUiSchema("text", "advanced", "MC batería fija", "MC fixed battery"),
    "limit_peak_ratio_enable": FieldUiSchema(
        "dropdown",
        "basic",
        "Limitar relación pico",
        "Enable peak-ratio limit",
        options=(("Sí", True), ("No", False)),
    ),
    "limit_peak_ratio": FieldUiSchema("number", "basic", "Relación pico máxima", "Peak-ratio limit"),
    "limit_peak_year": FieldUiSchema("number", "advanced", "Año de pico", "Peak year"),
    "limit_peak_month_mode": FieldUiSchema(
        "dropdown",
        "advanced",
        "Modo de mes pico",
        "Peak month mode",
        options=(("Máximo", "max"), ("Fijo", "fixed")),
    ),
    "limit_peak_basis": FieldUiSchema(
        "dropdown",
        "advanced",
        "Base del pico",
        "Peak basis",
        options=(
            ("Promedio ponderado", "weighted_mean"),
            ("Máximo", "max"),
            ("Día hábil", "weekday"),
            ("P95", "p95"),
        ),
    ),
    "limit_peak_month_fixed": FieldUiSchema("number", "advanced", "Mes pico fijo", "Fixed peak month"),
    "kWp_seed_mode": FieldUiSchema(
        "dropdown",
        "basic",
        "Modo de semilla",
        "Seed mode",
        options=(("Auto", "auto"), ("Manual", "manual")),
    ),
    "kWp_seed_manual_kWp": FieldUiSchema("number", "advanced", "Semilla manual kWp", "Manual seed kWp"),
    "modules_span_each_side": FieldUiSchema("number", "basic", "Módulos alrededor de semilla", "Modules around seed"),
    "kWp_min": FieldUiSchema("number", "basic", "kWp mínimo", "Minimum kWp"),
    "kWp_max": FieldUiSchema("number", "basic", "kWp máximo", "Maximum kWp"),
    "export_allowed": FieldUiSchema(
        "dropdown",
        "basic",
        "Permitir exportación",
        "Allow export",
        "Permite vender excedentes a la red. Si se desactiva, el modelo opera como cero inyección.",
        "Allows exports to the grid. If disabled, the model behaves as zero-export.",
        options=(("Sí", True), ("No", False)),
    ),
    "include_battery": FieldUiSchema(
        "dropdown",
        "basic",
        "Incluir batería",
        "Include battery",
        "Activa el análisis con almacenamiento. Si lo desactivas, solo se evaluarán diseños FV sin batería.",
        "Enables storage analysis. If disabled, only PV-only designs are evaluated.",
        options=(("Sí", True), ("No", False)),
    ),
    "battery_name": FieldUiSchema("text", "advanced", "Batería fija", "Fixed battery"),
    "optimize_battery": FieldUiSchema(
        "dropdown",
        "basic",
        "Optimizar batería",
        "Optimize battery",
        "Prueba el catálogo de baterías para cada kWp. Si está desactivado, se usa la batería fija elegida arriba.",
        "Tries the battery catalog for each kWp. If disabled, the fixed battery selected above is used.",
        options=(("Sí", True), ("No", False)),
    ),
    "bat_DoD": FieldUiSchema("number", "advanced", "Profundidad de descarga", "Depth of discharge"),
    "bat_coupling": FieldUiSchema(
        "dropdown",
        "advanced",
        "Acoplamiento de batería",
        "Battery coupling",
        "Define si la batería se conecta en AC o DC dentro del modelo.",
        "Defines whether the battery is modeled as AC-coupled or DC-coupled.",
        options=(("AC", "ac"), ("DC", "dc")),
    ),
    "bat_eta_rt": FieldUiSchema("number", "advanced", "Eficiencia batería", "Battery efficiency"),
    "profile_type": FieldUiSchema("text", "hidden", "Tipo de perfil", "Profile type"),
}

GROUP_LABELS = {
    "Demanda y Perfil": {"es": "Demanda y Perfil", "en": "Demand and Profile"},
    "Sol y módulos": {"es": "Sol y módulos", "en": "Solar and Modules"},
    "Inversor": {"es": "Inversor", "en": "Inverter"},
    "Economía": {"es": "Economía", "en": "Economics"},
    "Precios": {"es": "Precios", "en": "Pricing"},
    "Monte Carlo": {"es": "Monte Carlo", "en": "Monte Carlo"},
    "Restricción de Proporción Pico": {"es": "Restricción de Proporción Pico", "en": "Peak-Ratio Constraint"},
    "Semilla": {"es": "Semilla", "en": "Seed"},
    "Controles de Batería y Exporte": {"es": "Batería y Exporte", "en": "Battery and Export"},
}

GROUP_HELP = {
    "Demanda y Perfil": {
        "es": "Estos parámetros cambian el tamaño y la forma de la demanda que el sistema debe cubrir.",
        "en": "These parameters change the size and shape of the demand the system must cover.",
    },
    "Economía": {
        "es": "Afecta los ahorros, el VPN y el payback del proyecto.",
        "en": "These values affect savings, NPV, and project payback.",
    },
    "Precios": {
        "es": "Controla cómo se calcula el CAPEX base y cómo se aplican las bandas variables por kWp.",
        "en": "Controls how base CAPEX is calculated and how variable kWp bands are applied.",
    },
    "Semilla": {
        "es": "Define desde dónde empieza el barrido de kWp y hasta qué tan amplio será.",
        "en": "Defines where the kWp sweep starts and how wide it is.",
    },
    "Controles de Batería y Exporte": {
        "es": "Reúne las decisiones más prácticas sobre batería, exportación y autoconsumo.",
        "en": "Collects the most practical battery, export, and self-consumption decisions.",
    },
    "Monte Carlo": {
        "es": "Estos valores solo afectan el análisis de riesgo en la página de Monte Carlo.",
        "en": "These values only affect risk analysis on the Monte Carlo page.",
    },
}

METRIC_SCHEMA = {
    "scenario": {
        "label_es": "Escenario",
        "label_en": "Scenario",
        "help_es": "Nombre visible del escenario.",
        "help_en": "Visible scenario name.",
        "format": "text",
        "precision": 0,
    },
    "kWp": {
        "label_es": "kWp",
        "label_en": "kWp",
        "help_es": "Capacidad instalada del sistema fotovoltaico.",
        "help_en": "Installed PV system capacity.",
        "format": "number",
        "precision": 3,
    },
    "NPV_COP": {
        "label_es": "VPN [COP]",
        "label_en": "NPV [COP]",
        "help_es": "Valor presente neto descontado del escenario.",
        "help_en": "Discounted net present value of the candidate.",
        "format": "currency_cop",
        "precision": 0,
    },
    "payback_years": {
        "label_es": "Payback [años]",
        "label_en": "Payback Years",
        "help_es": "Años hasta recuperar la inversión descontada.",
        "help_en": "Years until discounted payback is reached.",
        "format": "years",
        "precision": 2,
    },
    "capex_client": {
        "label_es": "CAPEX cliente [COP]",
        "label_en": "Client CAPEX [COP]",
        "help_es": "Inversión inicial asumida por el cliente.",
        "help_en": "Upfront capital cost assumed for the client.",
        "format": "currency_cop",
        "precision": 0,
    },
    "self_consumption_ratio": {
        "label_es": "Autoconsumo [%]",
        "label_en": "Self-consumption [%]",
        "help_es": "Porción de la generación utilizada localmente.",
        "help_en": "Share of generation consumed locally.",
        "format": "percent",
        "precision": 1,
    },
    "self_sufficiency_ratio": {
        "label_es": "Autosuficiencia [%]",
        "label_en": "Self-sufficiency [%]",
        "help_es": "Porción de la demanda cubierta sin importación de red.",
        "help_en": "Share of demand covered without grid imports.",
        "format": "percent",
        "precision": 1,
    },
    "annual_import_kwh": {
        "label_es": "Importación anual [kWh]",
        "label_en": "Annual import [kWh]",
        "help_es": "Energía comprada a la red durante el primer año.",
        "help_en": "Energy imported from the grid during year one.",
        "format": "kwh",
        "precision": 0,
    },
    "annual_export_kwh": {
        "label_es": "Exportación anual [kWh]",
        "label_en": "Annual export [kWh]",
        "help_es": "Energía exportada a la red durante el primer año.",
        "help_en": "Energy exported to the grid during year one.",
        "format": "kwh",
        "precision": 0,
    },
    "peak_ratio": {
        "label_es": "Relación pico",
        "label_en": "Peak ratio",
        "help_es": "Relación entre el pico FV y el pico de carga usado por la restricción.",
        "help_en": "Ratio between PV peak and the load peak used by the constraint.",
        "format": "number",
        "precision": 3,
    },
    "battery": {
        "label_es": "Batería",
        "label_en": "Battery",
        "help_es": "Batería seleccionada para el candidato.",
        "help_en": "Battery selected for the candidate.",
        "format": "text",
        "precision": 0,
    },
    "candidate_key": {
        "label_es": "Clave de candidato",
        "label_en": "Candidate key",
        "help_es": "Identificador interno estable del candidato.",
        "help_en": "Stable internal candidate identifier.",
        "format": "text",
        "precision": 0,
    },
    "best_kWp": {
        "label_es": "kWp óptimo",
        "label_en": "Best kWp",
        "help_es": "Potencia instalada del candidato seleccionado.",
        "help_en": "Installed capacity of the selected candidate.",
        "format": "number",
        "precision": 3,
    },
    "selected_battery": {
        "label_es": "Batería seleccionada",
        "label_en": "Selected battery",
        "help_es": "Batería asociada al candidato seleccionado.",
        "help_en": "Battery associated with the selected candidate.",
        "format": "text",
        "precision": 0,
    },
    "NPV": {
        "label_es": "VPN [COP]",
        "label_en": "NPV [COP]",
        "help_es": "Valor presente neto descontado.",
        "help_en": "Discounted net present value.",
        "format": "currency_cop",
        "precision": 0,
    },
    "scan_order": {
        "label_es": "Orden de barrido",
        "label_en": "Scan order",
        "help_es": "Orden estable en el que el candidato fue evaluado.",
        "help_en": "Stable order in which the candidate was evaluated.",
        "format": "number",
        "precision": 0,
    },
}


def _prettify_item(item: str) -> str:
    return item.replace("_", " ").strip().capitalize()


def group_label(group: str, lang: str = "es") -> str:
    mapping = GROUP_LABELS.get(group)
    if mapping is None:
        return group or ("Config" if lang == "en" else "Configuración")
    return mapping.get(lang, mapping.get("es", group))


def section_help(group: str, lang: str = "es") -> str:
    mapping = GROUP_HELP.get(group)
    if mapping is None:
        return ""
    return mapping.get(lang, mapping.get("es", ""))


def field_schema_for(meta: ConfigFieldMeta) -> FieldUiSchema:
    default_kind = "number" if isinstance(meta.value, (int, float)) and not isinstance(meta.value, bool) else "text"
    if isinstance(meta.value, bool):
        default_kind = "dropdown"
    return FIELD_SCHEMAS.get(meta.config_key, FieldUiSchema(default_kind))


def field_label(meta: ConfigFieldMeta, lang: str = "es") -> str:
    schema = field_schema_for(meta)
    if lang == "en" and schema.label_en:
        return schema.label_en
    if lang == "es" and schema.label_es:
        return schema.label_es
    if lang == "en" and schema.label_es:
        return schema.label_es
    if lang == "es" and schema.label_en:
        return schema.label_en
    return _prettify_item(meta.item)


def field_help(meta: ConfigFieldMeta, lang: str = "es") -> str:
    schema = field_schema_for(meta)
    if lang == "en" and schema.help_en:
        return schema.help_en
    if lang == "es" and schema.help_es:
        return schema.help_es
    if meta.description:
        return meta.description
    return field_label(meta, lang)


def field_options(meta: ConfigFieldMeta, lang: str = "es") -> list[dict[str, Any]]:
    schema = field_schema_for(meta)
    if not schema.options:
        return []
    options = []
    for label, value in schema.options:
        options.append({"label": label, "value": value})
    if lang == "en":
        replacements = {"Sí": "Yes", "No": "No", "Máximo": "Max", "Promedio ponderado": "Weighted mean", "Día hábil": "Weekday"}
        return [{"label": replacements.get(option["label"], option["label"]), "value": option["value"]} for option in options]
    return options


def build_assumption_sections(bundle, lang: str = "es", show_all: bool = False) -> list[dict[str, Any]]:
    sections_by_group: dict[str, dict[str, Any]] = {}
    for meta in extract_config_metadata(bundle.config_table, bundle.config):
        schema = field_schema_for(meta)
        if schema.visibility == "hidden":
            continue
        target = "all" if show_all or schema.visibility == "basic" else "advanced"
        group = group_label(meta.group, lang)
        bucket = sections_by_group.setdefault(
            group,
            {
                "group": group,
                "help": section_help(meta.group, lang),
                "basic": [],
                "advanced": [],
            },
        )
        bucket["basic" if target == "all" else target].append(
            {
                "field": meta.config_key,
                "item": meta.item,
                "label": field_label(meta, lang),
                "help": field_help(meta, lang),
                "unit": meta.unit,
                "kind": schema.kind,
                "options": field_options(meta, lang),
                "value": bundle.config.get(meta.config_key),
                "supported": meta.supported,
            }
        )
    return list(sections_by_group.values())


def coerce_config_value(field_key: str, value: Any, base_config: dict[str, Any]) -> Any:
    current = base_config.get(field_key)
    if value in (None, ""):
        if isinstance(current, str):
            return ""
        return current
    if isinstance(current, bool):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(float(value))
    if isinstance(current, float):
        return float(value)
    return value


def metric_label(metric_key: str, lang: str = "es") -> str:
    schema = METRIC_SCHEMA.get(metric_key, {})
    if lang == "en":
        return schema.get("label_en") or schema.get("label_es") or metric_key
    return schema.get("label_es") or schema.get("label_en") or metric_key


def metric_help(metric_key: str, lang: str = "es") -> str:
    schema = METRIC_SCHEMA.get(metric_key, {})
    if lang == "en":
        return schema.get("help_en") or schema.get("help_es") or metric_key
    return schema.get("help_es") or schema.get("help_en") or metric_key


def _numeric_format(format_type: str, precision: int) -> Format:
    if format_type == "percent":
        return Format(group=Group.yes, precision=precision, scheme=Scheme.percentage)
    return Format(group=Group.yes, precision=precision, scheme=Scheme.fixed)


def build_display_columns(column_keys: list[str], lang: str = "es") -> tuple[list[dict[str, Any]], dict[str, str]]:
    columns: list[dict[str, Any]] = []
    tooltip_header: dict[str, str] = {}
    for key in column_keys:
        schema = METRIC_SCHEMA.get(key, {"format": "text", "precision": 0})
        column = {"name": metric_label(key, lang), "id": key}
        if schema.get("format") in {"currency_cop", "kwh", "percent", "years", "number", "ratio"}:
            column["type"] = "numeric"
            column["format"] = _numeric_format(schema["format"], int(schema.get("precision", 0)))
        columns.append(column)
        tooltip_header[key] = metric_help(key, lang)
    return columns, tooltip_header


def format_metric(metric_key: str, value: Any, lang: str = "es") -> str:
    if value is None or value == "":
        return "-"
    schema = METRIC_SCHEMA.get(metric_key, {"format": "text", "precision": 0})
    fmt = schema.get("format", "text")
    precision = int(schema.get("precision", 0))
    if metric_key in {"battery", "selected_battery"} and str(value).strip().lower() == "none":
        return tr("common.no_battery", lang)
    if fmt == "currency_cop":
        return f"COP {float(value):,.{precision}f}" if precision else f"COP {float(value):,.0f}"
    if fmt == "kwh":
        return f"{float(value):,.{precision}f} kWh" if precision else f"{float(value):,.0f} kWh"
    if fmt == "percent":
        return f"{100 * float(value):,.{precision}f}%"
    if fmt == "years":
        suffix = " years" if lang == "en" else " años"
        return f"{float(value):,.{precision}f}{suffix}"
    if fmt in {"number", "ratio"}:
        return f"{float(value):,.{precision}f}"
    return str(value)
