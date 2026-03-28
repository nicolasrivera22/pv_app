from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from dash.dash_table.Format import Format, Group, Scheme

from pv_product.panel_catalog import (
    MANUAL_PANEL_TOKEN,
    panel_catalog_options,
    resolve_selected_panel,
)
from pv_product.panel_technology import panel_technology_options
from pv_product.utils import DEFAULT_CONFIG

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
    display_format: str | None = None
    precision: int = 0
    input_step: float | int | None = None
    suffix_es: str | None = None
    suffix_en: str | None = None
    ui_scale: float | None = None
    min_value: float | int | None = None
    max_value: float | int | None = None


@dataclass(frozen=True)
class TableColumnUiSchema:
    label_es: str | None = None
    label_en: str | None = None
    help_es: str | None = None
    help_en: str | None = None
    format: str = "text"
    precision: int = 0
    type: str | None = None


_YES_NO_OPTIONS = (("Sí", True), ("No", False))
_PERCENT_PER_YEAR_ES = "%/año"
_PERCENT_PER_YEAR_EN = "%/year"


FIELD_SCHEMAS: dict[str, FieldUiSchema] = {
    "E_month_kWh": FieldUiSchema(
        "number",
        "basic",
        "Demanda mensual de referencia",
        "Reference monthly demand",
        "Usa el consumo mensual típico del sitio. Este valor ancla el tamaño del sistema y los ahorros.",
        "Use the site's typical monthly consumption. This value anchors system size and savings.",
        display_format="energy",
        precision=0,
        input_step=1,
        suffix_es="kWh/mes",
        suffix_en="kWh/month",
    ),
    "alpha_mix": FieldUiSchema(
        "number",
        "advanced",
        "Participación de demanda diurna",
        "Daytime demand share",
        "Qué parte del consumo ocurre en horas solares. Valores más altos suelen favorecer el autoconsumo.",
        "How much demand happens during solar hours. Higher values usually favor self-consumption.",
        display_format="percent",
        precision=1,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
        min_value=0,
        max_value=100,
    ),
    "use_excel_profile": FieldUiSchema(
        "dropdown",
        "basic",
        "Método del perfil de demanda",
        "Demand profile method",
        "Define cómo se reparte la demanda horaria y qué tabla de perfiles debes editar abajo.",
        "Defines how hourly demand is distributed and which profile table you should edit below.",
        options=(
            ("Perfil Hora Dia de Semana", "perfil hora dia de semana"),
            ("Perfil Hora Relativo", "perfil horario relativo"),
            ("Perfil Hora Total", "perfil general"),
        ),
    ),
    "PR": FieldUiSchema(
        "number",
        "basic",
        "PR del sistema",
        "System PR",
        "Resume las pérdidas eléctricas y operativas del sistema FV. Un PR más bajo da una estimación más conservadora.",
        "Summarizes electrical and operational PV losses. A lower PR gives a more conservative estimate.",
        display_format="percent",
        precision=1,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
        min_value=0,
        max_value=100,
    ),
    "panel_name": FieldUiSchema(
        "dropdown",
        "basic",
        "Modelo de panel",
        "Panel model",
        "Selecciona un panel del catálogo para este escenario o vuelve a la configuración manual.",
        "Select a catalog panel for this scenario or switch back to manual configuration.",
    ),
    "panel_technology_mode": FieldUiSchema(
        "dropdown",
        "basic",
        "Tecnología de panel",
        "Panel technology",
        "Supuesto simple del escenario para el comportamiento de generación del panel. Solo cambia el rendimiento de energía; no cambia módulo, área ni hardware.",
        "Simple scenario assumption for panel generation behavior. It changes energy yield only; it does not change module, area, or hardware choices.",
    ),
    "Tmin_C": FieldUiSchema(
        "number",
        "advanced",
        "Temperatura mínima",
        "Minimum temperature",
        display_format="temperature",
        precision=1,
        suffix_es="°C",
        suffix_en="°C",
    ),
    "P_mod_W": FieldUiSchema(
        "number",
        "basic",
        "Potencia del módulo",
        "Module power",
        "Potencia nominal de cada módulo solar.",
        "Rated power of each solar module.",
        display_format="power_wp",
        precision=0,
        input_step=1,
        suffix_es="Wp",
        suffix_en="Wp",
    ),
    "Voc25": FieldUiSchema(
        "number",
        "advanced",
        "Voc a 25 °C",
        "Voc at 25 °C",
        display_format="voltage",
        precision=1,
        suffix_es="V",
        suffix_en="V",
    ),
    "Vmp25": FieldUiSchema(
        "number",
        "advanced",
        "Vmp a 25 °C",
        "Vmp at 25 °C",
        display_format="voltage",
        precision=1,
        suffix_es="V",
        suffix_en="V",
    ),
    "Isc": FieldUiSchema(
        "number",
        "advanced",
        "Isc",
        "Isc",
        display_format="current",
        precision=2,
        suffix_es="A",
        suffix_en="A",
    ),
    "a_Voc_pct": FieldUiSchema(
        "number",
        "advanced",
        "Coef. térmico Voc",
        "Voc thermal coefficient",
        display_format="percent_per_degree",
        precision=2,
        suffix_es="%/°C",
        suffix_en="%/°C",
    ),
    "ILR_min": FieldUiSchema(
        "number",
        "advanced",
        "ILR mínimo",
        "Minimum ILR",
        display_format="ratio",
        precision=2,
    ),
    "ILR_max": FieldUiSchema(
        "number",
        "advanced",
        "ILR máximo",
        "Maximum ILR",
        display_format="ratio",
        precision=2,
    ),
    "buy_tariff_COP_kWh": FieldUiSchema(
        "number",
        "basic",
        "Tarifa de compra",
        "Import tariff",
        "Tarifa pagada por cada kWh importado desde la red.",
        "Tariff paid for each kWh imported from the grid.",
        display_format="currency_rate",
        precision=0,
        input_step=1,
        suffix_es="COP/kWh",
        suffix_en="COP/kWh",
    ),
    "sell_tariff_COP_kWh": FieldUiSchema(
        "number",
        "basic",
        "Tarifa de venta",
        "Export tariff",
        "Tarifa reconocida por cada kWh exportado a la red.",
        "Tariff credited for each kWh exported to the grid.",
        display_format="currency_rate",
        precision=0,
        input_step=1,
        suffix_es="COP/kWh",
        suffix_en="COP/kWh",
    ),
    "g_tar_buy": FieldUiSchema(
        "number",
        "advanced",
        "Crecimiento tarifa compra",
        "Buy tariff growth",
        "Crecimiento anual asumido para la tarifa de compra.",
        "Assumed annual growth applied to the import tariff.",
        display_format="percent_rate",
        precision=2,
        suffix_es=_PERCENT_PER_YEAR_ES,
        suffix_en=_PERCENT_PER_YEAR_EN,
        ui_scale=100.0,
    ),
    "g_tar_sell": FieldUiSchema(
        "number",
        "advanced",
        "Crecimiento tarifa venta",
        "Sell tariff growth",
        "Crecimiento anual asumido para la tarifa de venta.",
        "Assumed annual growth applied to the export tariff.",
        display_format="percent_rate",
        precision=2,
        suffix_es=_PERCENT_PER_YEAR_ES,
        suffix_en=_PERCENT_PER_YEAR_EN,
        ui_scale=100.0,
    ),
    "deg_rate": FieldUiSchema(
        "number",
        "advanced",
        "Degradación anual",
        "Annual degradation",
        "Pérdida anual de producción del sistema FV a lo largo del horizonte del proyecto.",
        "Annual PV production loss across the project horizon.",
        display_format="percent_rate",
        precision=2,
        suffix_es=_PERCENT_PER_YEAR_ES,
        suffix_en=_PERCENT_PER_YEAR_EN,
        ui_scale=100.0,
    ),
    "discount_rate": FieldUiSchema(
        "number",
        "basic",
        "Tasa de descuento",
        "Discount rate",
        "Se usa para descontar ahorros futuros y calcular VPN y payback. Tasas más altas castigan más los flujos tardíos.",
        "Used to discount future savings when calculating NPV and payback. Higher values penalize late cash flows more.",
        display_format="percent_rate",
        precision=2,
        suffix_es=_PERCENT_PER_YEAR_ES,
        suffix_en=_PERCENT_PER_YEAR_EN,
        ui_scale=100.0,
    ),
    "years": FieldUiSchema(
        "number",
        "basic",
        "Horizonte (años)",
        "Project horizon",
        "Cantidad de años incluidos en la evaluación económica y en las proyecciones de flujo de caja.",
        "Number of years included in the economic evaluation and cash-flow projection.",
        display_format="integer",
        precision=0,
        input_step=1,
        suffix_es="años",
        suffix_en="years",
    ),
    "pricing_mode": FieldUiSchema(
        "dropdown",
        "basic",
        "Cómo fijar el costo base",
        "Base project pricing",
        "Elige si el costo base sale de bandas por kWp o de un total fijo del proyecto.",
        "Choose whether the base cost comes from kWp pricing bands or from a fixed total project cost.",
        options=(("Variable", "variable"), ("Total", "total")),
    ),
    "price_total_COP": FieldUiSchema(
        "number",
        "advanced",
        "Total fijo del proyecto",
        "Fixed project total",
        "Costo total usado cuando no trabajas con bandas de precio por kWp.",
        "Total project cost used when kWp pricing bands are not being used.",
        display_format="currency",
        precision=0,
        input_step=1,
        suffix_es="COP",
        suffix_en="COP",
    ),
    "include_hw_in_price": FieldUiSchema(
        "dropdown",
        "advanced",
        "Sumar inversor y batería por separado",
        "Add inverter and battery separately",
        "Si activas esta opción, inversor y batería se suman aparte del costo base del proyecto.",
        "If enabled, inverter and battery are added on top of the base project cost.",
        options=_YES_NO_OPTIONS,
    ),
    "include_var_others": FieldUiSchema(
        "dropdown",
        "advanced",
        "Incluir otros precios variables",
        "Include other variable prices",
        "Suma la tabla de otros precios variables además del precio principal por kWp.",
        "Adds the other-variable-prices table on top of the main kWp pricing table.",
        options=_YES_NO_OPTIONS,
    ),
    "price_others_total": FieldUiSchema(
        "number",
        "advanced",
        "Otros costos fijos",
        "Other fixed costs",
        "Costos fijos adicionales que no dependen del tamaño del sistema.",
        "Additional fixed costs that do not depend on system size.",
        display_format="currency",
        precision=0,
        input_step=1,
        suffix_es="COP",
        suffix_en="COP",
    ),
    "price_per_kWp_COP": FieldUiSchema(
        "number",
        "hidden",
        "Precio por kWp",
        "Base price per kWp",
        "Precio base aplicado por cada kWp instalado cuando usas precio variable.",
        "Base price applied per installed kWp when variable pricing is used.",
        display_format="currency_rate",
        precision=0,
        input_step=1,
        suffix_es="COP/kWp",
        suffix_en="COP/kWp",
    ),
    "mc_PR_std": FieldUiSchema(
        "number",
        "advanced",
        "Variación de PR en Riesgo",
        "PR variation in Risk",
        "Desviación usada por Riesgo para variar el PR. En 0% el PR queda fijo.",
        "Spread used by Risk to vary PR. At 0%, PR stays fixed.",
        display_format="percent",
        precision=2,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
    ),
    "mc_buy_std": FieldUiSchema(
        "number",
        "advanced",
        "Variación de tarifa de compra",
        "Import tariff variation",
        "Desviación usada por Riesgo para variar la tarifa de compra. En 0% la tarifa queda fija.",
        "Spread used by Risk to vary the import tariff. At 0%, the tariff stays fixed.",
        display_format="percent",
        precision=2,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
    ),
    "mc_sell_std": FieldUiSchema(
        "number",
        "advanced",
        "Variación de tarifa de venta",
        "Export tariff variation",
        "Desviación usada por Riesgo para variar la tarifa de venta. En 0% la tarifa queda fija.",
        "Spread used by Risk to vary the export tariff. At 0%, the tariff stays fixed.",
        display_format="percent",
        precision=2,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
    ),
    "mc_demand_std": FieldUiSchema(
        "number",
        "advanced",
        "Variación de demanda en Riesgo",
        "Demand variation in Risk",
        "Desviación usada por Riesgo para variar la demanda. En 0% la demanda queda fija.",
        "Spread used by Risk to vary demand. At 0%, demand stays fixed.",
        display_format="percent",
        precision=2,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
    ),
    "mc_use_manual_kWp": FieldUiSchema(
        "dropdown",
        "advanced",
        "Fijar kWp en Riesgo",
        "Use a fixed kWp in Risk",
        "Si lo activas, Riesgo ignora el tamaño del diseño seleccionado y usa el kWp manual de abajo.",
        "If enabled, Risk ignores the selected design size and uses the manual kWp below.",
        options=_YES_NO_OPTIONS,
    ),
    "mc_manual_kWp": FieldUiSchema(
        "number",
        "advanced",
        "kWp fijo en Riesgo",
        "Fixed kWp in Risk",
        "kWp usado por Riesgo cuando activas el tamaño manual.",
        "kWp used by Risk when manual size is enabled.",
        display_format="power_kwp",
        precision=3,
        suffix_es="kWp",
        suffix_en="kWp",
    ),
    "mc_n_simulations": FieldUiSchema(
        "number",
        "advanced",
        "Simulaciones por defecto en Riesgo",
        "Default simulation count",
        "Cantidad sugerida por defecto en Riesgo. Más simulaciones estabilizan percentiles y probabilidades, pero tardan más.",
        "Default value suggested on the Risk page. Higher counts stabilize percentiles and probabilities, but take longer.",
        display_format="integer",
        precision=0,
        input_step=1,
        suffix_es="sim",
        suffix_en="sims",
    ),
    "mc_battery_name": FieldUiSchema(
        "text",
        "advanced",
        "Batería fija para Riesgo",
        "Fixed battery for Risk",
        "Batería fija usada por Riesgo cuando no corresponde optimizar batería.",
        "Fixed battery used by Risk when battery optimization does not apply.",
    ),
    "limit_peak_ratio_enable": FieldUiSchema(
        "dropdown",
        "basic",
        "Limitar pico FV frente a carga",
        "Limit PV peak versus load",
        "Activa un tope para que el pico FV no supere demasiado la referencia elegida del pico de carga.",
        "Turns on a cap so PV peak does not exceed the chosen load-peak reference by too much.",
        options=_YES_NO_OPTIONS,
    ),
    "limit_peak_ratio": FieldUiSchema(
        "number",
        "basic",
        "Relación máxima FV / carga",
        "Maximum PV-to-load ratio",
        "Tope permitido para la relación entre el pico FV y el pico de carga. Por ejemplo, 1.5 equivale a 150%.",
        "Allowed cap between PV peak and load peak. For example, 1.5 means 150%.",
        display_format="ratio",
        precision=2,
    ),
    "limit_peak_year": FieldUiSchema(
        "number",
        "advanced",
        "Año de referencia del pico",
        "Peak reference year",
        "Año usado para construir la referencia de pico de carga cuando ese cálculo depende del horizonte.",
        "Year used to build the load-peak reference when that calculation depends on the project horizon.",
        display_format="integer",
        precision=0,
        input_step=1,
    ),
    "limit_peak_month_mode": FieldUiSchema(
        "dropdown",
        "advanced",
        "Cómo elegir el mes pico",
        "How to choose the peak month",
        "Define si el mes pico se toma automáticamente o si lo fijas manualmente.",
        "Sets whether the peak month is chosen automatically or fixed manually.",
        options=(("Máximo", "max"), ("Fijo", "fixed")),
    ),
    "limit_peak_basis": FieldUiSchema(
        "dropdown",
        "advanced",
        "Referencia del pico de carga",
        "Load-peak reference",
        "Define qué referencia de carga usa el límite de pico FV: promedio ponderado, máximo, día hábil o P95.",
        "Defines which load reference the PV peak cap uses: weighted mean, max, weekday, or P95.",
        options=(
            ("Promedio ponderado", "weighted_mean"),
            ("Máximo", "max"),
            ("Día hábil", "weekday"),
            ("P95", "p95"),
        ),
    ),
    "limit_peak_month_fixed": FieldUiSchema(
        "number",
        "advanced",
        "Mes pico fijo",
        "Fixed peak month",
        "Mes manual usado por la restricción cuando eliges modo fijo.",
        "Manual month used by the constraint when Fixed mode is selected.",
        display_format="integer",
        precision=0,
        input_step=1,
        min_value=1,
        max_value=12,
    ),
    "kWp_seed_mode": FieldUiSchema(
        "dropdown",
        "basic",
        "Punto inicial del escaneo",
        "Scan starting point",
        "Define si el barrido arranca desde un tamaño calculado automáticamente o desde un kWp manual.",
        "Sets whether the scan starts from an automatically calculated size or from a manual kWp.",
        options=(("Auto", "auto"), ("Manual", "manual")),
    ),
    "kWp_seed_manual_kWp": FieldUiSchema(
        "number",
        "advanced",
        "kWp inicial manual",
        "Manual starting kWp",
        "kWp desde el que empieza el barrido cuando eliges modo manual.",
        "kWp from which the scan starts when Manual is selected.",
        display_format="power_kwp",
        precision=3,
        suffix_es="kWp",
        suffix_en="kWp",
    ),
    "modules_span_each_side": FieldUiSchema(
        "number",
        "basic",
        "Módulos explorados a cada lado",
        "Modules explored on each side",
        "Cantidad de módulos que el barrido agrega y quita alrededor del punto inicial.",
        "Number of module steps the scan explores above and below the starting point.",
        display_format="integer",
        precision=0,
        input_step=1,
        suffix_es="módulos",
        suffix_en="modules",
    ),
    "kWp_min": FieldUiSchema(
        "number",
        "basic",
        "kWp mínimo del escaneo",
        "Minimum scan kWp",
        "Límite inferior del barrido determinístico, aunque el punto inicial sugiera un valor menor.",
        "Lower bound of the deterministic scan, even if the starting point would suggest a smaller size.",
        display_format="power_kwp",
        precision=3,
        suffix_es="kWp",
        suffix_en="kWp",
    ),
    "kWp_max": FieldUiSchema(
        "number",
        "basic",
        "kWp máximo del escaneo",
        "Maximum scan kWp",
        "Límite superior del barrido determinístico, aunque el punto inicial sugiera un valor mayor.",
        "Upper bound of the deterministic scan, even if the starting point would suggest a larger size.",
        display_format="power_kwp",
        precision=3,
        suffix_es="kWp",
        suffix_en="kWp",
    ),
    "export_allowed": FieldUiSchema(
        "dropdown",
        "basic",
        "Permitir venta a la red",
        "Allow grid export",
        "Permite vender excedentes a la red. Si se desactiva, el diseño opera como cero inyección.",
        "Allows surplus energy to be exported to the grid. If disabled, the design behaves as zero export.",
        options=_YES_NO_OPTIONS,
    ),
    "include_battery": FieldUiSchema(
        "dropdown",
        "basic",
        "Evaluar batería",
        "Evaluate battery",
        "Activa el análisis con almacenamiento. Si lo desactivas, solo se evaluarán diseños FV sin batería.",
        "Enables storage analysis. If disabled, only PV-only designs are evaluated.",
        options=_YES_NO_OPTIONS,
    ),
    "battery_name": FieldUiSchema(
        "text",
        "advanced",
        "Batería fija",
        "Fixed battery",
        "Batería usada cuando no pruebas el catálogo completo. Debe existir en el catálogo de baterías.",
        "Battery used when you are not testing the full catalog. It must exist in the battery catalog.",
    ),
    "optimize_battery": FieldUiSchema(
        "dropdown",
        "basic",
        "Probar catálogo de baterías",
        "Try battery catalog",
        "Prueba las baterías del catálogo para cada tamaño. Si se desactiva, se usa solo la batería fija de arriba.",
        "Tests batteries from the catalog for each design size. If disabled, only the fixed battery above is used.",
        options=_YES_NO_OPTIONS,
    ),
    "bat_DoD": FieldUiSchema(
        "number",
        "advanced",
        "Profundidad de descarga",
        "Depth of discharge",
        "Porcentaje utilizable de la capacidad nominal. Por ejemplo, 80% significa que el modelo usa 80% de la energía nominal.",
        "Usable share of nominal capacity. For example, 80% means the model uses 80% of the nominal energy.",
        display_format="percent",
        precision=1,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
        min_value=0,
        max_value=100,
    ),
    "bat_coupling": FieldUiSchema(
        "dropdown",
        "advanced",
        "Acoplamiento de batería",
        "Battery coupling",
        "Define si la batería se modela en el lado AC o en el lado DC del sistema.",
        "Defines whether the battery is modeled on the AC side or the DC side of the system.",
        options=(("AC", "ac"), ("DC", "dc")),
    ),
    "bat_eta_rt": FieldUiSchema(
        "number",
        "advanced",
        "Eficiencia ida y vuelta",
        "Round-trip efficiency",
        "Representa las pérdidas de almacenamiento entre carga y descarga.",
        "Represents storage losses between charging and discharging.",
        display_format="percent",
        precision=1,
        suffix_es="%",
        suffix_en="%",
        ui_scale=100.0,
        min_value=0,
        max_value=100,
    ),
    "profile_type": FieldUiSchema("text", "hidden", "Tipo de perfil", "Profile type"),
}

GROUP_ORDER: list[str] = [
    "Demanda y Perfil",
    "Sol y módulos",
    "Inversor",
    "Semilla",
    "Economía",
    "Restricción de Proporción Pico",
    "Controles de Batería y Exporte",
    "Monte Carlo",
    "Precios",
]

CURRENCY_INPUT_FIELDS: set[str] = {"price_total_COP", "price_others_total"}

GROUP_LABELS = {
    "Demanda y Perfil": {"es": "Demanda y Perfil", "en": "Demand and Profile"},
    "Sol y módulos": {"es": "Sol y módulos", "en": "Solar and Modules"},
    "Inversor": {"es": "Inversor", "en": "Inverter"},
    "Economía": {"es": "Economía", "en": "Economics"},
    "Precios": {"es": "Precios", "en": "Pricing"},
    "Monte Carlo": {"es": "Monte Carlo", "en": "Monte Carlo"},
    "Restricción de Proporción Pico": {"es": "Límite de pico FV", "en": "PV Peak Cap"},
    "Semilla": {"es": "Barrido de diseños", "en": "Design Scan"},
    "Controles de Batería y Exporte": {"es": "Batería y exportación", "en": "Battery and export"},
}

GROUP_HELP = {
    "Demanda y Perfil": {
        "es": "Estos parámetros definen cuánto consume el sitio y cómo se reparte ese consumo por hora, día y mes.",
        "en": "These parameters define how much the site consumes and how that demand is distributed by hour, day, and month.",
    },
    "Sol y módulos": {
        "es": "Estos valores describen el comportamiento del campo FV y del módulo usado para construir los diseños.",
        "en": "These values describe the PV field behavior and the module used to build designs.",
    },
    "Economía": {
        "es": "Estos valores cambian los ahorros proyectados, el VPN y el payback del proyecto.",
        "en": "These values change projected savings, NPV, and project payback.",
    },
    "Precios": {
        "es": "Controla cómo se calcula el CAPEX base, qué costos escalan con el tamaño y qué costos quedan fijos.",
        "en": "Controls how base CAPEX is calculated, which costs scale with size, and which costs stay fixed.",
    },
    "Semilla": {
        "es": "Define desde dónde empieza el barrido de tamaños y qué límites tiene el escaneo determinístico.",
        "en": "Defines where the size sweep starts and what limits the deterministic scan must respect.",
    },
    "Controles de Batería y Exporte": {
        "es": "Reúne las decisiones principales sobre batería fija u optimizada, exportación a red y uso del almacenamiento.",
        "en": "Collects the main choices about fixed or optimized batteries, grid export, and storage behavior.",
    },
    "Monte Carlo": {
        "es": "Estos valores solo afectan la página de Riesgo. Controlan cuánta variación introduce Monte Carlo en demanda, tarifas, PR y tamaño fijo.",
        "en": "These values only affect the Risk page. They control how much variation Monte Carlo adds to demand, tariffs, PR, and optional fixed size.",
    },
    "Restricción de Proporción Pico": {
        "es": "Este bloque limita cuánto puede crecer el pico FV frente a la referencia elegida del pico de carga.",
        "en": "This block limits how large PV peak is allowed to grow versus the chosen load-peak reference.",
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
        "help_es": "Valor presente neto descontado del diseño.",
        "help_en": "Discounted net present value of the design.",
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
        "label_es": "Pico FV / pico carga [%]",
        "label_en": "PV peak / load peak [%]",
        "help_es": "Relación entre el pico FV y el pico de carga usada por la restricción, mostrada como porcentaje.",
        "help_en": "Ratio between PV peak and the load peak used by the constraint, shown as a percentage.",
        "format": "percent",
        "precision": 1,
    },
    "battery": {
        "label_es": "Batería",
        "label_en": "Battery",
        "help_es": "Batería seleccionada para el diseño.",
        "help_en": "Battery selected for the design.",
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
    "design_label": {
        "label_es": "Diseño",
        "label_en": "Design",
        "help_es": "Etiqueta corta usada para comparar diseños seleccionados.",
        "help_en": "Short label used to compare selected designs.",
        "format": "text",
        "precision": 0,
    },
    "best_kWp": {
        "label_es": "kWp óptimo",
        "label_en": "Best kWp",
        "help_es": "Potencia instalada del diseño seleccionado.",
        "help_en": "Installed capacity of the selected design.",
        "format": "number",
        "precision": 3,
    },
    "panel_count": {
        "label_es": "Paneles",
        "label_en": "Panels",
        "help_es": "Número estimado de módulos solares instalados para el diseño.",
        "help_en": "Estimated number of installed solar modules for the design.",
        "format": "integer",
        "precision": 0,
    },
    "selected_battery": {
        "label_es": "Batería seleccionada",
        "label_en": "Selected battery",
        "help_es": "Batería asociada al diseño seleccionado.",
        "help_en": "Battery associated with the selected design.",
        "format": "text",
        "precision": 0,
    },
    "inverter_name": {
        "label_es": "Inversor",
        "label_en": "Inverter",
        "help_es": "Modelo de inversor asociado al diseño.",
        "help_en": "Inverter model associated with the design.",
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
        "help_es": "Orden estable en el que se evaluó el diseño.",
        "help_en": "Stable order in which the design was evaluated.",
        "format": "number",
        "precision": 0,
    },
}

TABLE_COLUMN_SCHEMAS: dict[str, dict[str, TableColumnUiSchema]] = {
    "inverter_catalog": {
        "name": TableColumnUiSchema("Nombre", "Name", "Modelo o referencia visible del inversor.", "Visible inverter model or reference."),
        "AC_kW": TableColumnUiSchema("Potencia AC [kW]", "AC power [kW]", "Potencia AC nominal del inversor.", "Rated inverter AC power.", "kw", 1, "numeric"),
        "Vmppt_min": TableColumnUiSchema("V MPPT mín [V]", "Min MPPT V [V]", "Voltaje mínimo de seguimiento MPPT.", "Minimum MPPT tracking voltage.", "volts", 0, "numeric"),
        "Vmppt_max": TableColumnUiSchema("V MPPT máx [V]", "Max MPPT V [V]", "Voltaje máximo de seguimiento MPPT.", "Maximum MPPT tracking voltage.", "volts", 0, "numeric"),
        "Vdc_max": TableColumnUiSchema("V DC máx [V]", "Max DC V [V]", "Voltaje DC máximo permitido en la entrada.", "Maximum allowed DC input voltage.", "volts", 0, "numeric"),
        "Imax_mppt": TableColumnUiSchema("I MPPT máx [A]", "Max MPPT I [A]", "Corriente máxima por MPPT.", "Maximum current per MPPT.", "amps", 1, "numeric"),
        "n_mppt": TableColumnUiSchema("Cantidad MPPT", "MPPT count", "Número de seguidores MPPT disponibles.", "Number of available MPPT trackers.", "integer", 0, "numeric"),
        "price_COP": TableColumnUiSchema("Precio [COP]", "Price [COP]", "Costo del inversor.", "Inverter cost.", "currency_cop", 0, "numeric"),
    },
    "battery_catalog": {
        "name": TableColumnUiSchema("Nombre", "Name", "Nombre o referencia visible de la batería.", "Visible battery name or reference."),
        "nom_kWh": TableColumnUiSchema("Energía nominal [kWh]", "Nominal energy [kWh]", "Capacidad nominal de la batería.", "Battery nominal capacity.", "kwh", 1, "numeric"),
        "max_kW": TableColumnUiSchema("Potencia máx [kW]", "Max power [kW]", "Potencia máxima general de la batería.", "Overall battery maximum power.", "kw", 1, "numeric"),
        "max_ch_kW": TableColumnUiSchema("Carga máx [kW]", "Max charge [kW]", "Potencia máxima de carga.", "Maximum charge power.", "kw", 1, "numeric"),
        "max_dis_kW": TableColumnUiSchema("Descarga máx [kW]", "Max discharge [kW]", "Potencia máxima de descarga.", "Maximum discharge power.", "kw", 1, "numeric"),
        "price_COP": TableColumnUiSchema("Precio [COP]", "Price [COP]", "Costo de la batería.", "Battery cost.", "currency_cop", 0, "numeric"),
    },
    "panel_catalog": {
        "name": TableColumnUiSchema("Nombre", "Name", "Modelo o referencia visible del panel.", "Visible panel model or reference."),
        "P_mod_W": TableColumnUiSchema("Potencia módulo [Wp]", "Module power [Wp]", "Potencia nominal del módulo.", "Rated module power.", "number", 0, "numeric"),
        "Voc25": TableColumnUiSchema("Voc a 25 °C [V]", "Voc at 25 °C [V]", "Voltaje de circuito abierto del módulo a 25 °C.", "Module open-circuit voltage at 25 °C.", "volts", 1, "numeric"),
        "Vmp25": TableColumnUiSchema("Vmp a 25 °C [V]", "Vmp at 25 °C [V]", "Voltaje de máxima potencia del módulo a 25 °C.", "Module maximum-power voltage at 25 °C.", "volts", 1, "numeric"),
        "Isc": TableColumnUiSchema("Isc [A]", "Isc [A]", "Corriente de cortocircuito del módulo.", "Module short-circuit current.", "amps", 2, "numeric"),
        "length_m": TableColumnUiSchema("Largo [m]", "Length [m]", "Largo del panel para referencia de huella.", "Panel length for footprint reference.", "number", 3, "numeric"),
        "width_m": TableColumnUiSchema("Ancho [m]", "Width [m]", "Ancho del panel para referencia de huella.", "Panel width for footprint reference.", "number", 3, "numeric"),
        "panel_technology_mode": TableColumnUiSchema("Tecnología", "Technology", "Tecnología de generación asociada al modelo.", "Generation technology associated with the model.", "text", 0),
        "price_COP": TableColumnUiSchema("Precio [COP]", "Price [COP]", "Costo de referencia del panel para la capa económica.", "Reference panel cost for the economics layer.", "currency_cop", 0, "numeric"),
    },
    "economics_cost_items": {
        "stage": TableColumnUiSchema("Etapa", "Stage", "Etapa económica de costo: technical o installed.", "Cost stage: technical or installed."),
        "name": TableColumnUiSchema("Partida", "Item", "Nombre visible de la partida de costo.", "Visible cost item name."),
        "basis": TableColumnUiSchema("Base", "Basis", "Base de costo: fijo por proyecto o por unidad física.", "Cost basis: fixed per project or per physical unit."),
        "amount_COP": TableColumnUiSchema("Monto [COP]", "Amount [COP]", "Monto en COP o COP por unidad según la base elegida.", "Amount in COP or COP per unit depending on the selected basis.", "currency_cop", 0, "numeric"),
        "enabled": TableColumnUiSchema("Activo", "Enabled", "Permite desactivar temporalmente esta partida sin eliminarla.", "Lets you temporarily disable this line without deleting it."),
        "notes": TableColumnUiSchema("Notas", "Notes", "Notas internas para explicar la fuente o el uso de la partida.", "Internal notes that explain the source or intent of the line."),
    },
    "economics_price_items": {
        "layer": TableColumnUiSchema("Capa", "Layer", "Capa comercial: commercial o sale.", "Commercial layer: commercial or sale."),
        "name": TableColumnUiSchema("Ajuste", "Adjustment", "Nombre visible del ajuste comercial o final.", "Visible commercial or final-price adjustment name."),
        "method": TableColumnUiSchema("Método", "Method", "Método de pricing: markup_pct, fixed_project o per_kwp.", "Pricing method: markup_pct, fixed_project, or per_kwp."),
        "value": TableColumnUiSchema("Valor [COP o %]", "Value [COP or %]", "Usa 12 para 12% en markup_pct. Los otros métodos usan COP o COP por kWp.", "Use 12 for 12% in markup_pct. Other methods use COP or COP per kWp.", "text", 0, "numeric"),
        "enabled": TableColumnUiSchema("Activo", "Enabled", "Permite desactivar temporalmente este ajuste sin eliminarlo.", "Lets you temporarily disable this adjustment without deleting it."),
        "notes": TableColumnUiSchema("Notas", "Notes", "Notas internas para aclarar el criterio comercial o de cierre.", "Internal notes that clarify the commercial or final-sale rationale."),
    },
    "economics_breakdown": {
        "source_table": TableColumnUiSchema("Tabla", "Table", "Tabla de economics que originó la línea calculada.", "Economics table that produced the calculated line."),
        "source_row": TableColumnUiSchema("Fila", "Row", "Fila 1-based del input normalizado usada en el cálculo.", "1-based normalized input row used in the calculation.", "integer", 0, "numeric"),
        "group": TableColumnUiSchema("Grupo", "Group", "Separa líneas de costo y líneas de precio.", "Separates cost lines from price lines."),
        "stage_or_layer": TableColumnUiSchema("Etapa / capa", "Stage / layer", "Etapa de costo o capa de precio usada en la línea.", "Cost stage or price layer used in the line."),
        "name": TableColumnUiSchema("Partida", "Item", "Nombre visible de la línea calculada.", "Visible name of the calculated line."),
        "rule": TableColumnUiSchema("Regla", "Rule", "Basis o method aplicado en la línea.", "Basis or method applied in the line."),
        "multiplier": TableColumnUiSchema("Multiplicador", "Multiplier", "Cantidad usada para multiplicar la tarifa o monto.", "Quantity used to multiply the rate or amount.", "number", 3, "numeric"),
        "unit_rate_COP": TableColumnUiSchema("Tarifa / monto", "Rate / amount", "Monto unitario normalizado usado en la línea. Para markup_pct guarda la tasa decimal.", "Normalized unit amount used in the line. For markup_pct it stores the decimal rate.", "number", 3, "numeric"),
        "base_amount_COP": TableColumnUiSchema("Base [COP]", "Base [COP]", "Base monetaria usada por markup_pct. Queda vacía cuando no aplica.", "Monetary base used by markup_pct. Empty when not applicable.", "currency_cop", 0, "numeric"),
        "line_amount_COP": TableColumnUiSchema("Resultado [COP]", "Result [COP]", "Monto total calculado para la línea.", "Total amount calculated for the line.", "currency_cop", 0, "numeric"),
        "notes": TableColumnUiSchema("Notas", "Notes", "Notas internas preservadas desde la fila de origen.", "Internal notes preserved from the source row."),
    },
    "month_profile": {
        "MONTH": TableColumnUiSchema("Mes", "Month", "Mes del año.", "Month of the year.", "integer", 0, "numeric"),
        "Demand_month": TableColumnUiSchema("Factor demanda", "Demand factor", "Multiplicador relativo de demanda mensual.", "Relative monthly demand multiplier.", "ratio", 3, "numeric"),
        "HSP_month": TableColumnUiSchema("Factor HSP", "HSP factor", "Multiplicador relativo de HSP mensual.", "Relative monthly HSP multiplier.", "ratio", 3, "numeric"),
    },
    "sun_profile": {
        "HOUR": TableColumnUiSchema("Hora", "Hour", "Hora del día.", "Hour of the day.", "integer", 0, "numeric"),
        "SOL": TableColumnUiSchema("Participación solar [%]", "Solar share [%]", "Participación horaria relativa del recurso solar.", "Relative hourly share of the solar resource.", "percent", 1, "numeric"),
    },
    "cop_kwp": {
        "MIN": TableColumnUiSchema("kWp mín", "Min kWp", "Límite inferior de la banda.", "Lower bound of the band.", "number", 3, "numeric"),
        "MAX": TableColumnUiSchema("kWp máx", "Max kWp", "Límite superior de la banda.", "Upper bound of the band.", "number", 3, "numeric"),
        "PRECIO_POR_KWP": TableColumnUiSchema("Precio por kWp [COP/kWp]", "Price per kWp [COP/kWp]", "Costo aplicado a esa banda de tamaño.", "Cost applied to that size band.", "currency_cop", 0, "numeric"),
    },
    "cop_kwp_others": {
        "MIN": TableColumnUiSchema("kWp mín", "Min kWp", "Límite inferior de la banda.", "Lower bound of the band.", "number", 3, "numeric"),
        "MAX": TableColumnUiSchema("kWp máx", "Max kWp", "Límite superior de la banda.", "Upper bound of the band.", "number", 3, "numeric"),
        "PRECIO_POR_KWP": TableColumnUiSchema("Otros variables [COP/kWp]", "Other variable costs [COP/kWp]", "Otros costos variables aplicados por banda.", "Other variable costs applied by band.", "currency_cop", 0, "numeric"),
    },
    "demand_profile": {
        "Dia": TableColumnUiSchema("Día", "Day", "Nombre opcional del dia asociado a la fila.", "Optional day name for the row."),
        "DOW": TableColumnUiSchema("Dia semana", "DOW", "Dia de la semana en la tabla 7x24.", "Day of week in the 7x24 table.", "integer", 0, "numeric"),
        "HOUR": TableColumnUiSchema("Hora", "Hour", "Hora del dia.", "Hour of the day.", "integer", 0, "numeric"),
        "RES": TableColumnUiSchema("Demanda Residencial [kWh]", "Residential Demand [kWh]", "Demanda residencial de esa hora.", "Residential demand for that hour.", "kwh", 2, "numeric"),
        
        "IND": TableColumnUiSchema("Demanda Industrial [kWh]", "Industrial Demand [kWh]", "Demanda industrial de esa hora.", "Industrial demand for that hour.", "kwh", 2, "numeric"),
        "TOTAL_kWh": TableColumnUiSchema("Demanda total [kWh]", "Total demand [kWh]", "Demanda total derivada de la hora.", "Total hourly demand derived from RES + IND.", "kwh", 2, "numeric"),
    },
    "demand_profile_general": {
        "HOUR": TableColumnUiSchema("Hora", "Hour", "Hora del dia.", "Hour of the day.", "integer", 0, "numeric"),
        "RES": TableColumnUiSchema("Demanda Residencial [kWh]", "Residential Demand [kWh]", "Demanda residencial de esa hora.", "Residential demand for that hour.", "kwh", 2, "numeric"),
        "IND": TableColumnUiSchema("Demanda Industrial [kWh]", "Industrial Demand [kWh]]", "Demanda industrial de esa hora.", "Industrial demand for that hour.", "kwh", 2, "numeric"),
        "TOTAL_kWh": TableColumnUiSchema("Demanda total [kWh]", "Total demand [kWh]", "Demanda total derivada de la hora.", "Total hourly demand derived from RES + IND.", "kwh", 2, "numeric"),
    },
    "demand_profile_weights": {
        "HOUR": TableColumnUiSchema("Hora", "Hour", "Hora del dia.", "Hour of the day.", "integer", 0, "numeric"),
        "W_RES": TableColumnUiSchema("Peso residencial", "Residential weight", "Peso relativo residencial editable.", "Editable residential weight.", "percent", 3, "numeric"),
        "W_IND": TableColumnUiSchema("Peso industrial", "Industrial weight", "Peso relativo industrial editable.", "Editable industrial weight.", "percent", 3, "numeric"),
        "W_RES_BASE": TableColumnUiSchema("Base residencial", "Residential base", "Base residencial usada para normalizar.", "Residential base used for normalization.", "percent", 3, "numeric"),
        "W_IND_BASE": TableColumnUiSchema("Base industrial", "Industrial base", "Base industrial usada para normalizar.", "Industrial base used for normalization.", "percent", 3, "numeric"),
        "W_TOTAL": TableColumnUiSchema("Peso total", "Total weight", "Peso total combinado.", "Combined total weight.", "percent", 3, "numeric"),
        "TOTAL_kWh": TableColumnUiSchema("Demanda total [kWh]", "Total demand [kWh]", "Demanda total resultante.", "Resulting total demand.", "kwh", 2, "numeric"),
    },
}

_MISSING = object()


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
    if lang == "en":
        return field_label(meta, lang)
    if meta.description:
        return meta.description
    return field_label(meta, lang)


def field_options(meta: ConfigFieldMeta, bundle, lang: str = "es") -> list[dict[str, Any]]:
    if meta.config_key == "panel_name":
        options = [{"label": label, "value": value} for label, value in panel_catalog_options(bundle.panel_catalog, lang=lang)]
        current_value = str(bundle.config.get("panel_name") or "").strip()
        if current_value and current_value != MANUAL_PANEL_TOKEN and all(option["value"] != current_value for option in options):
            options.append({"label": current_value, "value": current_value})
        return options
    if meta.config_key == "panel_technology_mode":
        return [
            {"label": label, "value": value}
            for label, value in panel_technology_options(lang)
        ]
    schema = field_schema_for(meta)
    if not schema.options:
        return []
    options = []
    for label, value in schema.options:
        options.append({"label": label, "value": value})
    if lang == "en":
        replacements = {
            "Sí": "Yes",
            "No": "No",
            "Máximo": "Max",
            "Fijo": "Fixed",
            "Promedio ponderado": "Weighted mean",
            "Día hábil": "Weekday",
            "Perfil hora-día-semana": "Weekday 7x24 profile",
            "Perfil horario relativo": "Relative hourly profile",
            "Perfil general": "General profile",
            "Variable": "Variable (by kWp bands)",
            "Total": "Fixed project total",
            "Auto": "Auto",
            "Manual": "Manual",
        }
        return [{"label": replacements.get(option["label"], option["label"]), "value": option["value"]} for option in options]
    return options


def field_suffix(meta: ConfigFieldMeta, lang: str = "es") -> str | None:
    schema = field_schema_for(meta)
    if lang == "en":
        suffix = schema.suffix_en or schema.suffix_es
    else:
        suffix = schema.suffix_es or schema.suffix_en
    if meta.config_key in FIELD_SCHEMAS:
        return suffix
    unit = str(meta.unit or "").strip()
    return unit or None


def _default_input_step(precision: int) -> float | int:
    if precision <= 0:
        return 1
    return 10 ** (-precision)


def field_input_step(meta: ConfigFieldMeta) -> float | int | None:
    schema = field_schema_for(meta)
    if schema.kind != "number":
        return None
    if schema.input_step is not None:
        return schema.input_step
    return _default_input_step(schema.precision)


def _normalize_display_number(value: float, precision: int) -> float | int:
    normalized = round(float(value), precision)
    if precision == 0:
        return int(round(normalized))
    return normalized


def display_assumption_value(field_key: str, value: Any) -> Any:
    schema = FIELD_SCHEMAS.get(field_key)
    if schema is None or schema.kind != "number" or _is_missing_config_input(value):
        return value
    numeric = float(value)
    if schema.ui_scale is not None:
        numeric *= schema.ui_scale
    return _normalize_display_number(numeric, schema.precision)


def parse_assumption_input_value(field_key: str, value: Any) -> Any:
    schema = FIELD_SCHEMAS.get(field_key)
    if schema is None or _is_missing_config_input(value):
        return value
    if field_key in CURRENCY_INPUT_FIELDS:
        cleaned = str(value).replace(",", "").replace(".", "").strip()
        if not cleaned:
            return value
        try:
            return float(cleaned)
        except ValueError:
            return value
    if schema.kind != "number":
        return value
    numeric = float(value)
    if schema.ui_scale is not None:
        numeric /= schema.ui_scale
    return numeric


def _field_payload(meta: ConfigFieldMeta, bundle, *, lang: str = "es") -> dict[str, Any]:
    schema = field_schema_for(meta)
    payload = {
        "field": meta.config_key,
        "item": meta.item,
        "label": field_label(meta, lang),
        "help": field_help(meta, lang),
        "unit": meta.unit,
        "suffix": field_suffix(meta, lang),
        "kind": schema.kind,
        "display_format": schema.display_format,
        "precision": schema.precision,
        "input_step": field_input_step(meta),
        "min": schema.min_value,
        "max": schema.max_value,
        "options": field_options(meta, bundle, lang),
        "value": display_assumption_value(meta.config_key, bundle.config.get(meta.config_key, meta.value)),
        "supported": meta.supported,
    }
    if meta.config_key == "panel_name":
        payload["value"] = str(payload["value"] or MANUAL_PANEL_TOKEN)
    if meta.config_key == "mc_battery_name":
        names = [
            str(value).strip()
            for value in bundle.battery_catalog.get("name", pd.Series(dtype=object)).astype(str).tolist()
            if str(value).strip() and str(value).strip().lower() != "nan"
        ]
        payload["kind"] = "dropdown"
        payload["options"] = [{"label": tr("common.no_battery", lang), "value": ""}] + [
            {"label": name, "value": name} for name in dict.fromkeys(names)
        ]
        payload["value"] = str(payload["value"] or "")
    return payload


def build_config_fields(
    bundle,
    field_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> list[dict[str, Any]]:
    if not field_keys:
        return []
    order = {field_key: index for index, field_key in enumerate(field_keys)}
    fields: list[dict[str, Any]] = []
    for meta in extract_config_metadata(bundle.config_table, bundle.config):
        if meta.config_key not in order:
            continue
        schema = field_schema_for(meta)
        if schema.visibility == "hidden":
            continue
        fields.append(_field_payload(meta, bundle, lang=lang))
    return sorted(fields, key=lambda field: order.get(field["field"], len(order)))


ASSUMPTION_CONTEXT_NOTE_IDS = {
    "Sol y módulos": "panel-selection-context-note",
    "Controles de Batería y Exporte": "battery-export-context-note",
    "Semilla": "seed-context-note",
    "Restricción de Proporción Pico": "peak-ratio-context-note",
    "Monte Carlo": "risk-context-note",
}


def _to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
    return bool(value)


def _assumption_context_note(
    config: dict[str, Any],
    group_key: str,
    *,
    panel_catalog: pd.DataFrame | None = None,
    lang: str = "es",
) -> str:
    panel_catalog_frame = panel_catalog if panel_catalog is not None else pd.DataFrame()
    if group_key == "Sol y módulos":
        panel_resolution = resolve_selected_panel(config, panel_catalog_frame)
        if panel_resolution.selection_mode == "catalog":
            if lang == "en":
                return "Module power, electrical values, and panel technology are derived from the selected panel model."
            return "La potencia del módulo, los valores eléctricos y la tecnología del panel se derivan del modelo seleccionado."
    if group_key == "Controles de Batería y Exporte":
        include_battery = _to_bool(config.get("include_battery"))
        optimize_battery = _to_bool(config.get("optimize_battery"))
        if not include_battery:
            return tr("workbench.assumptions.context.battery.off", lang)
        if optimize_battery:
            return tr("workbench.assumptions.context.battery.optimize", lang)
        return tr("workbench.assumptions.context.battery.fixed", lang)
    if group_key == "Semilla" and str(config.get("kWp_seed_mode", "")).strip().lower() == "auto":
        return tr("workbench.assumptions.context.seed.auto", lang)
    if group_key == "Restricción de Proporción Pico":
        if not _to_bool(config.get("limit_peak_ratio_enable")):
            return tr("workbench.assumptions.context.peak.disabled", lang)
        if str(config.get("limit_peak_month_mode", "")).strip().lower() == "max":
            return tr("workbench.assumptions.context.peak.auto_month", lang)
    return ""


def assumption_context_map(
    config: dict[str, Any],
    *,
    panel_catalog: pd.DataFrame | None = None,
    lang: str = "es",
) -> dict[str, Any]:
    include_battery = _to_bool(config.get("include_battery"))
    optimize_battery = _to_bool(config.get("optimize_battery"))
    pricing_mode = str(config.get("pricing_mode", "")).strip().lower()
    peak_enabled = _to_bool(config.get("limit_peak_ratio_enable"))
    seed_mode = str(config.get("kWp_seed_mode", "")).strip().lower()
    peak_month_mode = str(config.get("limit_peak_month_mode", "")).strip().lower()
    use_manual_risk_kwp = _to_bool(config.get("mc_use_manual_kWp"))
    panel_resolution = resolve_selected_panel(config, panel_catalog if panel_catalog is not None else pd.DataFrame())
    panel_fields_derived = panel_resolution.selection_mode == "catalog"

    field_disabled = {
        "P_mod_W": panel_fields_derived,
        "Voc25": panel_fields_derived,
        "Vmp25": panel_fields_derived,
        "Isc": panel_fields_derived,
        "panel_technology_mode": panel_fields_derived,
        "price_total_COP": pricing_mode == "variable",
        "optimize_battery": not include_battery,
        "battery_name": (not include_battery) or optimize_battery,
        "bat_DoD": not include_battery,
        "bat_coupling": not include_battery,
        "bat_eta_rt": not include_battery,
        "kWp_seed_manual_kWp": seed_mode != "manual",
        "limit_peak_ratio": not peak_enabled,
        "limit_peak_year": not peak_enabled,
        "limit_peak_month_mode": not peak_enabled,
        "limit_peak_basis": not peak_enabled,
        "limit_peak_month_fixed": (not peak_enabled) or peak_month_mode != "fixed",
        "mc_manual_kWp": not use_manual_risk_kwp,
    }
    field_emphasis = {
        "battery_name": include_battery and not optimize_battery,
    }
    notes = {
        group_key: _assumption_context_note(config, group_key, panel_catalog=panel_catalog, lang=lang)
        for group_key in ASSUMPTION_CONTEXT_NOTE_IDS
    }
    return {
        "field_disabled": field_disabled,
        "field_emphasis": field_emphasis,
        "notes": notes,
    }


def build_assumption_sections(
    bundle,
    lang: str = "es",
    show_all: bool = False,
    *,
    exclude_groups: set[str] | None = None,
    exclude_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    excluded = {str(group).strip() for group in (exclude_groups or set()) if str(group).strip()}
    hidden_fields = {str(field).strip() for field in (exclude_fields or set()) if str(field).strip()}
    sections_by_group: dict[str, dict[str, Any]] = {}
    raw_key_for_group: dict[str, str] = {}
    context = assumption_context_map(bundle.config, panel_catalog=bundle.panel_catalog, lang=lang)
    for meta in extract_config_metadata(bundle.config_table, bundle.config):
        if meta.group in excluded:
            continue
        if meta.config_key in hidden_fields:
            continue
        schema = field_schema_for(meta)
        if schema.visibility == "hidden":
            continue
        target = "all" if show_all or schema.visibility == "basic" else "advanced"
        group = group_label(meta.group, lang)
        raw_key_for_group.setdefault(group, meta.group)
        bucket = sections_by_group.setdefault(
            group,
            {
                "group": group,
                "group_key": meta.group,
                "help": section_help(meta.group, lang),
                "context_note_id": ASSUMPTION_CONTEXT_NOTE_IDS.get(meta.group),
                "context_note": context["notes"].get(meta.group, ""),
                "basic": [],
                "advanced": [],
            },
        )
        payload = _field_payload(meta, bundle, lang=lang)
        if meta.config_key in CURRENCY_INPUT_FIELDS:
            payload["currency_input"] = True
        payload["disabled"] = bool(context["field_disabled"].get(meta.config_key, False))
        payload["emphasize"] = bool(context["field_emphasis"].get(meta.config_key, False))
        bucket["basic" if target == "all" else target].append(payload)

    order_map = {name: index for index, name in enumerate(GROUP_ORDER)}
    fallback = len(GROUP_ORDER)
    sections = sorted(
        sections_by_group.values(),
        key=lambda section: order_map.get(section.get("group_key", ""), fallback),
    )
    return sections


def _is_missing_config_input(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _schema_default_value(field_key: str) -> Any:
    schema = FIELD_SCHEMAS.get(field_key)
    if schema is None:
        return _MISSING
    for _, option_value in schema.options:
        if not _is_missing_config_input(option_value):
            return option_value
    if schema.kind == "number":
        return 0.0
    if schema.kind in {"text", "dropdown"}:
        return ""
    return _MISSING


def _default_is_schema_ambiguous(field_key: str, default_value: Any) -> bool:
    schema = FIELD_SCHEMAS.get(field_key)
    if schema is None:
        return False
    option_values = [option_value for _, option_value in schema.options if not _is_missing_config_input(option_value)]
    if option_values:
        option_types = {type(option_value) for option_value in option_values}
        if len(option_types) == 1:
            option_type = next(iter(option_types))
            return not isinstance(default_value, option_type)
    if schema.kind == "text":
        return not isinstance(default_value, str)
    if schema.kind == "number":
        return not (isinstance(default_value, (int, float)) and not isinstance(default_value, bool))
    return False


def _expected_config_value(field_key: str, base_config: dict[str, Any]) -> Any:
    default_value = DEFAULT_CONFIG.get(field_key, _MISSING)
    if default_value is not _MISSING and default_value is not None and not _default_is_schema_ambiguous(field_key, default_value):
        return default_value
    schema_value = _schema_default_value(field_key)
    if schema_value is not _MISSING and schema_value is not None:
        return schema_value
    current = base_config.get(field_key, _MISSING)
    if current is not _MISSING and not _is_missing_config_input(current):
        return current
    return None


def coerce_config_value(field_key: str, value: Any, base_config: dict[str, Any]) -> Any:
    current = base_config.get(field_key)
    expected = _expected_config_value(field_key, base_config)
    if _is_missing_config_input(value):
        if isinstance(expected, str):
            return ""
        if not _is_missing_config_input(current):
            return current
        return expected
    if isinstance(expected, bool):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
        return bool(value)
    if isinstance(expected, int) and not isinstance(expected, bool):
        return int(float(value))
    if isinstance(expected, float):
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


def _format_kind(format_type: str, precision: int) -> Format | None:
    if format_type in {"currency_cop", "kwh", "kw", "volts", "amps", "percent", "years", "number", "ratio", "integer"}:
        if format_type == "integer":
            return Format(group=Group.yes, precision=0, scheme=Scheme.fixed)
        return _numeric_format(format_type, precision)
    return None


def _prettify_column(column_key: str) -> str:
    return column_key.replace("_", " ").replace("kWh", "kWh").strip().capitalize()


def build_table_display_columns(
    table_kind: str,
    column_keys: list[str],
    lang: str = "es",
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    schema_map = TABLE_COLUMN_SCHEMAS.get(table_kind, {})
    columns: list[dict[str, Any]] = []
    tooltip_header: dict[str, str] = {}
    for key in column_keys:
        schema = schema_map.get(key, TableColumnUiSchema(label_es=_prettify_column(key), label_en=_prettify_column(key)))
        label = schema.label_en if lang == "en" and schema.label_en else schema.label_es or schema.label_en or _prettify_column(key)
        help_text = schema.help_en if lang == "en" and schema.help_en else schema.help_es or schema.help_en or label
        column: dict[str, Any] = {"name": label, "id": key}
        if schema.type:
            column["type"] = schema.type
        data_format = _format_kind(schema.format, schema.precision)
        if data_format is not None:
            column["format"] = data_format
        columns.append(column)
        tooltip_header[key] = help_text
    return columns, tooltip_header


def build_display_columns(column_keys: list[str], lang: str = "es") -> tuple[list[dict[str, Any]], dict[str, str]]:
    columns: list[dict[str, Any]] = []
    tooltip_header: dict[str, str] = {}
    for key in column_keys:
        schema = METRIC_SCHEMA.get(key, {"format": "text", "precision": 0})
        column = {"name": metric_label(key, lang), "id": key}
        data_format = _format_kind(str(schema.get("format")), int(schema.get("precision", 0)))
        if data_format is not None:
            column["type"] = "numeric"
            column["format"] = data_format
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
