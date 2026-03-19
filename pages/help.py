from __future__ import annotations

from dash import Input, Output, callback, html, register_page

from services.i18n import tr


register_page(__name__, path="/help", name="Help")


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


HELP_CONTENT: dict[str, tuple[dict[str, object], ...]] = {
    "en": (
        {
            "title": "Start here",
            "paragraphs": (
                "This app helps you size PV and battery designs for a site, compare alternatives, and understand economic risk before choosing what to keep.",
                "For a first pass, import a workbook or load the example, change only the most important assumptions, run the deterministic scan, and review the selected design before moving to Compare or Risk.",
            ),
            "bullets": (
                "Create or open a project, then activate a scenario.",
                "Review Assumptions, profile tables, and hardware catalogs.",
                "Run the deterministic scan to generate feasible designs.",
                "Select a design to inspect its KPIs, charts, and single-line schematic.",
                "Use Compare to shortlist alternatives and Risk after a deterministic design exists.",
            ),
        },
        {
            "title": "Core concepts",
            "terms": (
                ("Project", "A saved workspace that keeps scenarios together."),
                ("Scenario", "One editable set of assumptions, profiles, and catalogs."),
                ("Design", "One feasible PV or PV-plus-battery option returned by the deterministic scan."),
                ("Deterministic scan", "A sweep over feasible design sizes under the current assumptions."),
                ("Compare", "A side-by-side review of selected designs from the active scenario."),
                ("Risk / Monte Carlo", "A simulation of uncertainty on one fixed design from a completed scenario."),
                ("Results package", "Exported charts and supporting files prepared for sharing outside the app."),
            ),
        },
        {
            "title": "Workbench workflow",
            "paragraphs": (
                "Workbench is where you build and rerun a scenario. It is the main page for editing assumptions and reviewing deterministic results.",
            ),
            "bullets": (
                "Assumptions change demand, sizing constraints, economics, battery behavior, and Risk inputs.",
                "Profile tables and hardware catalogs let you edit the workbook-backed data in place.",
                "The deterministic scan tests feasible design sizes and returns KPIs, curves, and detailed data for each feasible design.",
                "Selecting a row or a point on the NPV curve makes that design the active deep dive.",
                "The deep dive updates the charts and the single-line schematic for the selected design only.",
            ),
        },
        {
            "title": "Compare workflow",
            "paragraphs": (
                "Compare uses designs from the active scenario's latest deterministic scan. It does not rerun the model by itself.",
            ),
            "bullets": (
                "Select one or more rows in Available designs, then click Add designs.",
                "Use Compare when two or more designs are worth keeping on the shortlist.",
                "Start with the summary table, then use the charts to compare demand coverage, energy destination, and long-term value.",
                "If the active scenario changes, rerun the deterministic scan before comparing again.",
            ),
        },
        {
            "title": "Risk workflow",
            "paragraphs": (
                "Risk runs Monte Carlo on one fixed design from a completed deterministic scenario. It helps you understand uncertainty around a chosen design, not search for a new one.",
            ),
            "bullets": (
                "Choose a completed scenario and one feasible design from its latest deterministic scan.",
                "Configure uncertainty inputs in Risk > Monte Carlo settings.",
                "Those inputs widen or narrow the variation applied to demand, tariffs, PR, and optional fixed-kWp assumptions.",
                "Use Risk to understand downside, variability, and confidence ranges before making a final decision.",
            ),
        },
        {
            "title": "How to read results",
            "terms": (
                ("NPV / VPN", "Positive NPV means discounted savings are greater than upfront cost."),
                ("Payback", "The year when cumulative discounted cash flow turns positive."),
                ("Self-consumption", "The share of PV generation that is used on site instead of exported."),
                ("Self-sufficiency", "The share of site demand covered without importing from the grid."),
                ("Monthly balance", "How much energy comes from PV, battery, exports, and grid imports each month."),
                ("Cumulative discounted cash flow", "The running project value over time after discounting future cash flows."),
                ("Single-line / unifilar diagram", "A representative schematic of PV, inverter, battery, load, and grid connections."),
                ("Probability of negative NPV", "The share of Risk runs that end below zero NPV."),
                ("Percentiles in Risk", "P10, P50, and P90 show downside, midpoint, and upside ranges. A wider spread means more uncertainty."),
            ),
        },
        {
            "title": "Exporting and saving",
            "paragraphs": (
                "Saving and exporting are different. Saving keeps your working scenarios inside the app. Exporting creates files you can review or share outside it.",
            ),
            "bullets": (
                "Save project stores the current workspace and its scenarios.",
                "Download workbook exports the current scenario workbook or the comparison workbook.",
                "Export results package writes charts and supporting files prepared for sharing.",
                "In packaged desktop mode, exports are also copied to the runtime exports folder when that folder is available.",
            ),
        },
        {
            "title": "Glossary / key terms",
            "terms": (
                ("Demand profile", "The hourly shape used to distribute site consumption through the day and week."),
                ("PR", "Performance ratio. It summarizes PV losses between ideal production and delivered output."),
                ("Peak-ratio cap", "A sizing constraint that limits PV peak versus the chosen load-peak reference."),
                ("Import tariff", "What the site pays per kWh imported from the grid."),
                ("Export tariff", "What the site receives or is credited per kWh exported to the grid."),
                ("Battery coupling", "Whether the battery is modeled on the AC side or DC side of the system."),
                ("Results package", "The exported folder with charts and supporting files."),
                ("Monte Carlo", "Repeated simulations that vary uncertain inputs to measure spread and downside risk."),
            ),
        },
    ),
    "es": (
        {
            "title": "Empieza aquí",
            "paragraphs": (
                "Esta app te ayuda a dimensionar diseños FV y FV con batería para un sitio, comparar alternativas y entender el riesgo económico antes de decidir cuál conservar.",
                "Para una primera pasada, importa un libro o carga el ejemplo, cambia solo los supuestos más importantes, ejecuta el escaneo determinístico y revisa el diseño seleccionado antes de pasar a Comparar o Riesgo.",
            ),
            "bullets": (
                "Crea o abre un proyecto y luego activa un escenario.",
                "Revisa Supuestos, tablas de perfiles y catálogos de hardware.",
                "Ejecuta el escaneo determinístico para generar diseños factibles.",
                "Selecciona un diseño para inspeccionar sus KPIs, gráficas y esquema unifilar.",
                "Usa Comparar para cerrar la shortlist y Riesgo cuando ya exista un diseño determinístico.",
            ),
        },
        {
            "title": "Conceptos clave",
            "terms": (
                ("Proyecto", "Un espacio guardado que agrupa los escenarios de trabajo."),
                ("Escenario", "Un conjunto editable de supuestos, perfiles y catálogos."),
                ("Diseño", "Una opción factible FV o FV con batería devuelta por el escaneo determinístico."),
                ("Escaneo determinístico", "Un barrido de tamaños factibles bajo los supuestos actuales."),
                ("Comparar", "Una revisión lado a lado de diseños seleccionados del escenario activo."),
                ("Riesgo / Monte Carlo", "Una simulación de incertidumbre sobre un diseño fijo de un escenario completado."),
                ("Paquete de resultados", "Gráficas y archivos exportados para revisar o compartir fuera de la app."),
            ),
        },
        {
            "title": "Flujo de trabajo en Escenarios",
            "paragraphs": (
                "Escenarios es la página principal para construir y volver a correr un escenario. Ahí editas los supuestos y revisas los resultados determinísticos.",
            ),
            "bullets": (
                "Supuestos cambia demanda, restricciones de tamaño, economía, comportamiento de batería y entradas para Riesgo.",
                "Las tablas de perfiles y los catálogos de hardware te permiten editar los datos del libro directamente en la app.",
                "El escaneo determinístico prueba tamaños factibles y devuelve KPIs, curvas y datos detallados para cada diseño factible.",
                "Al seleccionar una fila o un punto en la curva de VPN, ese diseño pasa a ser el análisis detallado activo.",
                "El análisis detallado actualiza las gráficas y el esquema unifilar solo para el diseño seleccionado.",
            ),
        },
        {
            "title": "Flujo de trabajo en Comparar",
            "paragraphs": (
                "Comparar usa diseños del último escaneo determinístico del escenario activo. No vuelve a ejecutar el modelo por sí solo.",
            ),
            "bullets": (
                "Selecciona una o más filas en Diseños disponibles y luego haz clic en Agregar diseños.",
                "Usa Comparar cuando dos o más diseños merecen seguir en la shortlist.",
                "Empieza por la tabla de resumen y luego usa las gráficas para comparar cobertura de demanda, destino de la energía y valor económico de largo plazo.",
                "Si el escenario activo cambia, vuelve a ejecutar el escaneo determinístico antes de comparar otra vez.",
            ),
        },
        {
            "title": "Flujo de trabajo en Riesgo",
            "paragraphs": (
                "Riesgo ejecuta Monte Carlo sobre un diseño fijo de un escenario determinístico ya completado. Sirve para entender la incertidumbre alrededor de un diseño elegido, no para buscar uno nuevo.",
            ),
            "bullets": (
                "Elige un escenario completado y un diseño factible de su último escaneo determinístico.",
                "Configura las entradas de incertidumbre en Riesgo > Parámetros de Monte Carlo.",
                "Esas entradas amplían o reducen la variación aplicada a demanda, tarifas, PR y, si aplica, al kWp fijo.",
                "Usa Riesgo para entender downside, variabilidad y rangos de confianza antes de tomar una decisión final.",
            ),
        },
        {
            "title": "Cómo leer los resultados",
            "terms": (
                ("VPN / NPV", "Un VPN positivo significa que los ahorros descontados superan el costo inicial."),
                ("Payback", "El año en el que el flujo de caja descontado acumulado se vuelve positivo."),
                ("Autoconsumo", "La parte de la generación FV que se usa en el sitio en lugar de exportarse."),
                ("Autosuficiencia", "La parte de la demanda cubierta sin importar energía desde la red."),
                ("Balance mensual", "Cuánta energía viene de FV, batería, exportaciones e importaciones de red cada mes."),
                ("Flujo de caja descontado acumulado", "El valor acumulado del proyecto en el tiempo después de descontar los flujos futuros."),
                ("Esquema unifilar", "Un esquema representativo de las conexiones entre FV, inversor, batería, carga y red."),
                ("Probabilidad de VPN negativo", "La proporción de corridas de Riesgo que termina con VPN menor que cero."),
                ("Percentiles en Riesgo", "P10, P50 y P90 muestran downside, punto medio y upside. Una banda más ancha implica más incertidumbre."),
            ),
        },
        {
            "title": "Exportar y guardar",
            "paragraphs": (
                "Guardar y exportar no son lo mismo. Guardar conserva tus escenarios dentro de la app. Exportar crea archivos para revisar o compartir fuera de ella.",
            ),
            "bullets": (
                "Guardar proyecto conserva el espacio de trabajo actual y sus escenarios.",
                "Descargar libro exporta el libro del escenario actual o el libro comparativo.",
                "Exportar paquete de resultados genera gráficas y archivos de soporte listos para compartir.",
                "En modo desktop empaquetado, las exportaciones también se copian a la carpeta de exportaciones cuando esa carpeta está disponible.",
            ),
        },
        {
            "title": "Glosario / términos clave",
            "terms": (
                ("Perfil de demanda", "La forma horaria usada para repartir el consumo del sitio durante el día y la semana."),
                ("PR", "Performance ratio. Resume las pérdidas FV entre la producción ideal y la energía entregada."),
                ("Límite de pico FV", "Una restricción de tamaño que limita el pico FV frente a la referencia elegida del pico de carga."),
                ("Tarifa de compra", "Lo que el sitio paga por cada kWh importado desde la red."),
                ("Tarifa de venta", "Lo que el sitio recibe o se le reconoce por cada kWh exportado."),
                ("Acoplamiento de batería", "Si la batería se modela en el lado AC o DC del sistema."),
                ("Paquete de resultados", "La carpeta exportada con gráficas y archivos de soporte."),
                ("Monte Carlo", "Simulaciones repetidas que varían entradas inciertas para medir dispersión y riesgo bajista."),
            ),
        },
    ),
}


def _render_term_grid(terms: tuple[tuple[str, str], ...]) -> html.Div:
    return html.Div(
        className="compare-grid",
        children=[
            html.Div(
                className="subpanel",
                children=[
                    html.Div(term, className="scenario-meta"),
                    html.P(description, className="section-copy", style={"marginBottom": 0}),
                ],
            )
            for term, description in terms
        ],
    )


def _render_section(section: dict[str, object]) -> html.Div:
    children: list[object] = [
        html.Div(
            className="section-head",
            children=[html.H3(str(section["title"]))],
        )
    ]
    for paragraph in section.get("paragraphs", ()):
        children.append(html.P(str(paragraph), className="section-copy section-copy-wide"))
    bullets = section.get("bullets", ())
    if bullets:
        children.append(
            html.Ul(
                [html.Li(str(item)) for item in bullets],
                style={"margin": 0, "paddingLeft": "1.2rem"},
            )
        )
    terms = section.get("terms", ())
    if terms:
        children.append(_render_term_grid(tuple(terms)))
    return html.Div(className="panel", children=children)


def build_help_sections(lang: str = "es") -> list[html.Div]:
    selected = lang if lang in HELP_CONTENT else "es"
    return [_render_section(section) for section in HELP_CONTENT[selected]]


def layout():
    return html.Div(
        className="page",
        children=[
            html.Div(
                className="main-stack",
                children=[
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[html.H2(tr("help.title", "es"), id="help-page-title")],
                            ),
                            html.P(tr("help.intro", "es"), id="help-page-intro", className="section-copy section-copy-wide"),
                        ],
                    ),
                    html.Div(id="help-content", className="main-stack", children=build_help_sections("es")),
                ],
            )
        ],
    )


@callback(
    Output("help-page-title", "children"),
    Output("help-page-intro", "children"),
    Output("help-content", "children"),
    Input("language-selector", "value"),
)
def translate_help_page(language_value):
    lang = _lang(language_value)
    return (
        tr("help.title", lang),
        tr("help.intro", lang),
        build_help_sections(lang),
    )
