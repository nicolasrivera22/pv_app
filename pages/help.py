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
                "This app helps you size PV and battery designs for a site, compare feasible alternatives, and understand economic risk before deciding what to keep.",
                "The simplest current path is: go to Assumptions, start with Load example or Import Excel, review General and Demand setup, run the deterministic scan, then use Results, Compare, and Risk as needed.",
            ),
            "bullets": (
                "Start or reopen a project, then activate a scenario.",
                "Use the sidebar in Assumptions to load the bundled example or import a workbook.",
                "Review setup first, then run the deterministic scan.",
                "Use Results to inspect viable designs and the active deep dive.",
                "Use Compare and Risk only after a deterministic design already exists.",
            ),
        },
        {
            "title": "Navigation map",
            "terms": (
                ("Results", "Customer-facing deterministic outputs, candidate exploration, deep-dive charts, and the unifilar/schematic view."),
                ("Assumptions", "Scenario setup page with start actions, client-safe fields, and the detailed demand workflow."),
                ("Admin", "Internal page behind the local PIN gate for pricing-sensitive assumptions, catalogs, and internal month/solar/pricing tables."),
                ("Compare", "A side-by-side review of shortlisted designs from the active scenario's latest deterministic scan."),
                ("Risk / Monte Carlo", "A simulation of uncertainty for one fixed deterministic design."),
                ("Help", "The in-app product guide. The bundled quick guide is also available through the local help route."),
            ),
        },
        {
            "title": "Setup workflow",
            "paragraphs": (
                "Assumptions owns the setup workflow. It is where you start from zero, import a workbook, review client-safe fields, and edit demand in detail.",
            ),
            "bullets": (
                "Use General for client-safe assumptions and sizing controls.",
                "Use Demand for detailed demand editing and its auxiliary views.",
                "The internal access card lives only in Assumptions.",
                "Admin is for internal pricing/catalog work and no longer duplicates the detailed demand editor.",
                "If you need demand editing, go to Assumptions > Demand.",
            ),
        },
        {
            "title": "Results workflow",
            "paragraphs": (
                "Results is the main review page for deterministic outputs. It shows only viable designs that survive the technical constraints under the current scenario.",
            ),
            "bullets": (
                "Run the deterministic scan after changing setup inputs.",
                "The scan may evaluate more sizes than the chart ultimately shows.",
                "Discard counters and markers indicate evaluated sizes that were filtered out before economics were shown.",
                "Selecting a candidate row or viable point makes that design the active deep dive.",
                "The deep dive updates the KPIs, charts, and schematic for the selected design only.",
            ),
        },
        {
            "title": "Compare workflow",
            "paragraphs": (
                "Compare works from the active scenario's latest deterministic scan. It does not rerun the deterministic model by itself.",
            ),
            "bullets": (
                "Select one or more rows in Available designs, then add them to the shortlist.",
                "Use Compare when two or more viable designs are worth keeping on the shortlist.",
                "Start with the summary table, then inspect the comparison charts.",
                "If setup changes, rerun the deterministic scan before comparing again.",
            ),
        },
        {
            "title": "Risk workflow",
            "paragraphs": (
                "Risk runs Monte Carlo on one fixed design from a completed deterministic scenario. It is used to understand uncertainty around a chosen design, not to search for a new one.",
            ),
            "bullets": (
                "Choose a completed scenario and one feasible design from its latest deterministic scan.",
                "Configure the uncertainty inputs in Risk.",
                "Those inputs widen or narrow the variation applied to demand, tariffs, PR, and optional fixed-kWp assumptions.",
                "Use Risk to understand downside, variability, and confidence ranges before making a final decision.",
            ),
        },
        {
            "title": "How to read the main outputs",
            "terms": (
                ("NPV / VPN", "Positive NPV means discounted savings are greater than upfront cost."),
                ("NPV vs kWp chart", "The curve plots only viable designs with economic results. If the scan summary shows discards, the last viable point is not necessarily the largest size that was evaluated."),
                ("Discard counters and markers", "They show kWp sizes that were evaluated inside the scan range but were filtered out before economics were calculated. They are warnings about feasibility, not low-NPV designs."),
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
                "Help and the bundled quick guide should be kept in sync with the current workflow.",
            ),
        },
        {
            "title": "Glossary / key terms",
            "terms": (
                ("Project", "A saved workspace that keeps scenarios together."),
                ("Scenario", "One editable set of assumptions, profiles, and catalogs."),
                ("Design", "One feasible PV or PV-plus-battery option returned by the deterministic scan."),
                ("Deterministic scan", "A sweep over feasible design sizes under the current assumptions."),
                ("Demand profile", "The hourly shape used to distribute site consumption through the day and week."),
                ("PR", "Performance ratio. It summarizes PV losses between ideal production and delivered output."),
                ("Peak-ratio cap", "A sizing constraint that limits PV peak versus the chosen load-peak reference. When it becomes active, larger scan sizes may be evaluated but discarded before they appear in the NPV chart or candidate table."),
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
                "Esta app te ayuda a dimensionar diseños FV y FV con batería para un sitio, comparar alternativas factibles y entender el riesgo económico antes de decidir cuál conservar.",
                "La ruta más simple hoy es: entra a Supuestos, empieza con Cargar ejemplo o Importar Excel, revisa Generales y Demanda, ejecuta el escaneo determinístico y luego usa Resultados, Comparar y Riesgo según corresponda.",
            ),
            "bullets": (
                "Crea o abre un proyecto y luego activa un escenario.",
                "Usa la sidebar de Supuestos para cargar el ejemplo incluido o importar un libro.",
                "Revisa la configuración antes de correr el determinístico.",
                "Usa Resultados para inspeccionar diseños viables y el análisis detallado activo.",
                "Usa Comparar y Riesgo solo cuando ya exista un diseño determinístico.",
            ),
        },
        {
            "title": "Mapa de navegación",
            "terms": (
                ("Resultados", "Salidas determinísticas de cara al cliente, exploración de candidatos, gráficas de detalle y vista unifilar/esquemática."),
                ("Supuestos", "Página de configuración del escenario con acciones de arranque, campos seguros para cliente y flujo detallado de demanda."),
                ("Admin", "Página interna detrás del PIN local para supuestos sensibles en precio, catálogos y tablas internas mensuales/solares/de precios."),
                ("Comparar", "Revisión lado a lado de diseños en shortlist del último escaneo determinístico del escenario activo."),
                ("Riesgo / Monte Carlo", "Simulación de incertidumbre sobre un diseño determinístico fijo."),
                ("Ayuda", "Guía de producto dentro de la app. La guía rápida empaquetada también está disponible por la ruta local de ayuda."),
            ),
        },
        {
            "title": "Flujo de configuración",
            "paragraphs": (
                "Supuestos es el dueño del flujo de configuración. Ahí arrancas desde cero, importas un libro, revisas campos seguros para cliente y editas la demanda en detalle.",
            ),
            "bullets": (
                "Usa Generales para supuestos seguros para cliente y controles de tamaño.",
                "Usa Demanda para la edición detallada de demanda y sus vistas auxiliares.",
                "La tarjeta de acceso interno vive solo en Supuestos.",
                "Admin es para trabajo interno de precios/catálogos y ya no duplica el editor detallado de demanda.",
                "Si necesitas editar demanda, ve a Supuestos > Demanda.",
            ),
        },
        {
            "title": "Flujo de Resultados",
            "paragraphs": (
                "Resultados es la página principal para revisar las salidas determinísticas. Solo muestra diseños viables que superan las restricciones técnicas del escenario actual.",
            ),
            "bullets": (
                "Ejecuta el escaneo determinístico después de cambiar la configuración.",
                "El escaneo puede evaluar más tamaños de los que la gráfica termina mostrando.",
                "Los contadores y marcadores de descarte indican tamaños evaluados que fueron filtrados antes de mostrar economía.",
                "Al seleccionar una fila o punto viable, ese diseño pasa a ser el análisis detallado activo.",
                "El análisis detallado actualiza KPIs, gráficas y esquema solo para el diseño seleccionado.",
            ),
        },
        {
            "title": "Flujo de Comparar",
            "paragraphs": (
                "Comparar usa diseños del último escaneo determinístico del escenario activo. No vuelve a ejecutar el modelo por sí solo.",
            ),
            "bullets": (
                "Selecciona una o más filas en Diseños disponibles y luego agrégalas a la shortlist.",
                "Usa Comparar cuando dos o más diseños viables merecen seguir en evaluación.",
                "Empieza por la tabla resumen y luego revisa las gráficas comparativas.",
                "Si cambias la configuración, vuelve a ejecutar el determinístico antes de comparar otra vez.",
            ),
        },
        {
            "title": "Flujo de Riesgo",
            "paragraphs": (
                "Riesgo ejecuta Monte Carlo sobre un diseño fijo de un escenario determinístico ya completado. Sirve para entender la incertidumbre alrededor de un diseño elegido, no para buscar uno nuevo.",
            ),
            "bullets": (
                "Elige un escenario completado y un diseño factible de su último escaneo determinístico.",
                "Configura las entradas de incertidumbre en Riesgo.",
                "Esas entradas amplían o reducen la variación aplicada a demanda, tarifas, PR y, si aplica, al kWp fijo.",
                "Usa Riesgo para entender downside, variabilidad y rangos de confianza antes de tomar una decisión final.",
            ),
        },
        {
            "title": "Cómo leer las salidas principales",
            "terms": (
                ("VPN / NPV", "Un VPN positivo significa que los ahorros descontados superan el costo inicial."),
                ("Gráfica VPN vs kWp", "La curva solo grafica diseños viables con resultados económicos. Si el resumen del escaneo muestra descartes, el último punto viable no necesariamente es el tamaño más grande que se evaluó."),
                ("Contadores y marcadores de descarte", "Muestran tamaños kWp que sí se evaluaron dentro del rango del escaneo pero fueron filtrados antes de calcular la economía. Indican factibilidad técnica, no diseños con VPN bajo."),
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
                "Ayuda y la guía rápida empaquetada deben mantenerse alineadas con el flujo actual.",
            ),
        },
        {
            "title": "Glosario / términos clave",
            "terms": (
                ("Proyecto", "Un espacio guardado que agrupa los escenarios de trabajo."),
                ("Escenario", "Un conjunto editable de supuestos, perfiles y catálogos."),
                ("Diseño", "Una opción factible FV o FV con batería devuelta por el escaneo determinístico."),
                ("Escaneo determinístico", "Un barrido de tamaños factibles bajo los supuestos actuales."),
                ("Perfil de demanda", "La forma horaria usada para repartir el consumo del sitio durante el día y la semana."),
                ("PR", "Performance ratio. Resume las pérdidas FV entre la producción ideal y la energía entregada."),
                ("Límite de pico FV", "Una restricción de tamaño que limita el pico FV frente a la referencia elegida del pico de carga. Cuando se vuelve activa, tamaños más grandes pueden evaluarse y luego descartarse antes de aparecer en la curva de VPN o en la tabla de candidatos."),
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
