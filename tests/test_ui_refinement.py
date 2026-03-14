from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dash import dcc
import pandas as pd
import pytest

from app import create_app
from components.risk_controls import risk_controls_section
from components.risk_charts import risk_charts_section
from components.risk_tables import risk_tables_section
from components.scenario_controls import scenario_sidebar
from components.risk_charts import build_histogram_figure
from components.assumption_editor import render_assumption_sections
from components.candidate_explorer import candidate_explorer_section
from components.selected_candidate_deep_dive import selected_candidate_deep_dive_section
from components.profile_editor import profile_editor_section
from components.catalog_editor import catalog_editor_section
from pages import workbench as workbench_page
from services import (
    ScenarioSessionState,
    add_scenario,
    build_assumption_sections,
    build_display_columns,
    build_table_display_columns,
    create_scenario_record,
    export_deterministic_artifacts,
    export_risk_artifacts,
    extract_config_metadata,
    format_metric,
    legacy_deterministic_export_manifest,
    legacy_risk_export_manifest,
    load_config_from_excel,
    load_example_config,
    rebuild_bundle_from_ui,
    run_monte_carlo,
    run_scan,
    run_scenario_scan,
    tr,
)
from services.result_views import (
    build_annual_coverage_figure,
    build_battery_load_figure,
    build_npv_figure,
    build_pv_destination_figure,
    build_typical_day_figure,
)
from services.result_views import build_cash_flow, build_cash_flow_figure
from services.ui_schema import field_help, field_label, metric_label
from services.workbench_ui import demand_profile_visibility, frame_from_rows


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
        "mc_n_simulations": 8,
    }
    return replace(bundle, config=config)


def _find_component(node, component_id: str):
    if getattr(node, "id", None) == component_id:
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    return _find_component(children, component_id)


def test_app_defaults_to_spanish() -> None:
    app = create_app()
    layout = app.layout() if callable(app.layout) else app.layout
    selector = _find_component(layout, "language-selector")
    assert isinstance(selector, dcc.Dropdown)
    assert selector.value == "es"


def test_first_render_placeholders_are_spanish_first() -> None:
    sidebar = scenario_sidebar()
    scenario_dropdown = _find_component(sidebar, "scenario-dropdown")
    rename_input = _find_component(sidebar, "rename-scenario-input")
    risk_controls = risk_controls_section()
    risk_scenario_dropdown = _find_component(risk_controls, "risk-scenario-dropdown")
    risk_candidate_dropdown = _find_component(risk_controls, "risk-candidate-dropdown")

    assert scenario_dropdown.placeholder == "No hay escenarios cargados"
    assert rename_input.placeholder == "Nombre del escenario"
    assert risk_scenario_dropdown.placeholder == "Selecciona un escenario completado"
    assert risk_candidate_dropdown.placeholder == "Selecciona un candidato factible"


def test_risk_chart_section_stacks_full_width_cards_with_descriptions() -> None:
    chart_section = risk_charts_section()
    chart_stack = _find_component(chart_section, "risk-chart-stack")
    assert chart_stack is not None
    assert chart_stack.style["display"] == "grid"
    assert chart_stack.style["width"] == "100%"
    assert chart_stack.style["minWidth"] == 0
    assert [child.id for child in chart_stack.children] == [
        "risk-payback-histogram-card",
        "risk-npv-histogram-card",
        "risk-payback-ecdf-card",
        "risk-npv-ecdf-card",
    ]

    for card_id in [
        "risk-payback-histogram-card",
        "risk-npv-histogram-card",
        "risk-payback-ecdf-card",
        "risk-npv-ecdf-card",
    ]:
        card = _find_component(chart_section, card_id)
        assert card.style["boxSizing"] == "border-box"
        assert card.style["minWidth"] == 0
        assert card.style["maxWidth"] == "100%"
        assert card.style["overflow"] == "hidden"

    for graph_id in [
        "risk-payback-histogram",
        "risk-npv-histogram",
        "risk-payback-ecdf",
        "risk-npv-ecdf",
    ]:
        graph = _find_component(chart_section, graph_id)
        assert graph.responsive is False
        assert "width" not in graph.style
        assert graph.style["minWidth"] == 0
        assert graph.style["height"] == "420px"

    assert _find_component(chart_section, "risk-payback-histogram-description").children == tr("risk.chart.payback_hist.description", "es")
    assert _find_component(chart_section, "risk-npv-histogram-description").children == tr("risk.chart.npv_hist.description", "es")
    assert _find_component(chart_section, "risk-payback-ecdf-description").children == tr("risk.chart.payback_ecdf.description", "es")
    assert _find_component(chart_section, "risk-npv-ecdf-description").children == tr("risk.chart.npv_ecdf.description", "es")

    tables_section = risk_tables_section()
    assert _find_component(tables_section, "risk-payback-note") is None
    assert _find_component(tables_section, "risk-payback-band-note") is None


def test_translation_helper_prefers_spanish_fallback_for_workbench_labels() -> None:
    assert tr("workbench.sidebar.title", "es") == "Escenarios"
    assert tr("workbench.run_scan", "fr") == "Ejecutar escaneo determinístico"
    assert tr("nav.compare", "fr") == "Comparar"
    assert tr("risk.placeholder.scenario", "fr") == "Selecciona un escenario completado"
    assert tr("risk.chart.payback_hist.description", "fr").startswith("Muestra con qué frecuencia")


def test_extract_config_metadata_preserves_workbook_order_and_groups() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))
    metadata = extract_config_metadata(bundle.config_table, bundle.config)

    assert metadata[0].group == "Demanda y Perfil"
    assert metadata[0].item == "E_month_kWh"
    assert any(meta.item == "coupling" and meta.config_key == "bat_coupling" for meta in metadata)
    assert any(meta.group == "Precios" for meta in metadata)


def test_assumption_sections_group_and_fallback_help() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))
    sections = build_assumption_sections(bundle, lang="es", show_all=False)

    groups = [section["group"] for section in sections]
    assert "Demanda y Perfil" in groups
    assert "Economía" in groups

    meta = next(meta for meta in extract_config_metadata(bundle.config_table, bundle.config) if meta.item == "E_month_kWh")
    section = next(section for section in sections if section["group"] == "Demanda y Perfil")
    field = next(field for field in section["basic"] if field["field"] == "E_month_kWh")

    assert field["label"] == field_label(meta, "es")
    assert field["help"] == field_help(meta, "es")
    assert section["help"]


def test_display_schema_formats_metrics_and_labels() -> None:
    assert format_metric("NPV_COP", 12500000, "es") == "COP 12,500,000"
    assert format_metric("self_consumption_ratio", 0.456, "es") == "45.6%"
    assert format_metric("peak_ratio", 1.125, "es") == "112.5%"
    assert format_metric("payback_years", 7.25, "en") == "7.25 years"
    assert format_metric("selected_battery", "None", "es") == "Sin batería"
    columns, tooltips = build_display_columns(["kWp", "NPV_COP", "self_consumption_ratio", "peak_ratio"], "es")
    assert [column["name"] for column in columns] == ["kWp", "VPN [COP]", "Autoconsumo [%]", "Pico FV / pico carga [%]"]
    assert tooltips["NPV_COP"].startswith("Valor presente")
    assert metric_label("annual_import_kwh", "es") == "Importación anual [kWh]"


def test_table_display_schema_covers_editable_tables_and_immediate_tooltips() -> None:
    price_columns, price_tooltips = build_table_display_columns("cop_kwp", ["MIN", "PRECIO_POR_KWP"], "es")
    battery_columns, battery_tooltips = build_table_display_columns("battery_catalog", ["nom_kWh", "max_kW"], "es")
    weight_columns, weight_tooltips = build_table_display_columns("demand_profile_weights", ["W_RES", "TOTAL_kWh"], "es")
    month_columns, month_tooltips = build_table_display_columns("month_profile", ["Demand_month", "HSP_month"], "es")

    assert [column["name"] for column in price_columns] == ["kWp mín", "Precio por kWp [COP]"]
    assert price_columns[1]["type"] == "numeric"
    assert battery_columns[0]["name"] == "Energía nominal [kWh]"
    assert battery_columns[1]["name"] == "Potencia máx [kW]"
    assert weight_columns[0]["name"] == "Peso res [%]"
    assert month_columns[0]["name"] == "Factor demanda"
    assert month_columns[1]["name"] == "Factor HSP"
    assert "costo" in price_tooltips["PRECIO_POR_KWP"].lower()
    assert "capacidad" in battery_tooltips["nom_kWh"].lower()
    assert "peso" in weight_tooltips["W_RES"].lower()
    assert "mensual" in month_tooltips["Demand_month"].lower()

    candidate_table = _find_component(candidate_explorer_section(), "active-candidate-table")
    profile_table = _find_component(profile_editor_section(), "month-profile-editor")
    catalog_table = _find_component(catalog_editor_section(), "inverter-table-editor")
    assert candidate_table.tooltip_delay == 0
    assert candidate_table.tooltip_duration is None
    assert profile_table.tooltip_delay == 0
    assert profile_table.tooltip_duration is None
    assert catalog_table.tooltip_delay == 0
    assert catalog_table.tooltip_duration is None


def test_workbench_results_sections_are_split_by_stable_wrapper_ids() -> None:
    section = candidate_explorer_section()
    assert section.id == "candidate-selection-section"
    assert _find_component(section, "active-kpi-cards") is not None
    assert _find_component(section, "active-npv-graph") is not None
    assert _find_component(section, "candidate-selection-helper") is not None
    assert _find_component(section, "selected-candidate-banner") is not None
    assert _find_component(section, "active-candidate-table") is not None
    assert _find_component(section, "active-monthly-balance-graph") is None
    assert _find_component(section, "active-cash-flow-graph") is None

    deep_dive = selected_candidate_deep_dive_section()
    assert deep_dive.id == "selected-candidate-deep-dive-section"
    assert _find_component(deep_dive, "active-monthly-balance-graph") is not None
    assert _find_component(deep_dive, "active-cash-flow-graph") is not None
    assert _find_component(deep_dive, "unifilar-diagram-shell") is not None
    assert _find_component(deep_dive, "active-annual-coverage-graph") is not None
    assert _find_component(deep_dive, "active-battery-load-graph") is not None
    assert _find_component(deep_dive, "active-pv-destination-graph") is None
    assert _find_component(deep_dive, "active-typical-day-graph") is not None

    results_area = _find_component(workbench_page.layout, "deterministic-results-area")
    assert results_area is not None
    assert [child.id for child in results_area.children] == [
        "candidate-selection-section",
        "selected-candidate-deep-dive-section",
    ]


def test_candidate_selection_affordances_and_styles_use_stable_candidate_keys() -> None:
    section = candidate_explorer_section()
    assert _find_component(section, "selected-candidate-kpi-title").children == tr("workbench.selected_design.summary", "es")
    assert _find_component(section, "candidate-selection-helper").children == tr("workbench.candidate_selection.helper", "es")

    styles = workbench_page._candidate_table_styles("18.000::BAT-10", "12.000::None")
    assert styles[-1]["if"]["filter_query"] == '{candidate_key} = "18.000::BAT-10"'
    assert styles[-1]["backgroundColor"] == "#fee2e2"


def test_selected_candidate_banner_tolerates_partial_detail_payload() -> None:
    children = workbench_page._selected_candidate_banner({"kWp": 12.0, "summary": {}}, lang="es")

    assert len(children) == 4
    assert any("12.000 kWp" in str(child.to_plotly_json()) for child in children)
    assert any("—" in str(child.to_plotly_json()) for child in children)


def test_assumption_editor_uses_inline_help_instead_of_native_title() -> None:
    field = {
        "field": "E_month_kWh",
        "label": "Demanda mensual",
        "help": "Define la energía mensual de referencia.",
        "kind": "number",
        "value": 1234,
        "unit": "kWh/mes",
        "options": [],
    }
    rendered = render_assumption_sections(
        [{"group": "Demanda y Perfil", "help": "Ayuda", "basic": [field], "advanced": []}],
        show_all=False,
        empty_message="Sin datos",
        advanced_label="Avanzado",
    )
    markup = str(rendered[0].to_plotly_json())
    assert "field-help-tooltip" in markup
    assert "'title':" not in markup


def test_profile_visibility_and_bundle_rebuild_round_trip() -> None:
    bundle = _fast_bundle()
    visibility = demand_profile_visibility("perfil horario relativo")
    assert visibility["demand-profile-weights-panel"]["display"] == "block"
    assert visibility["demand-profile-panel"]["display"] == "none"

    edited_month = bundle.month_profile_table.copy()
    edited_month.loc[0, "Demand_month"] = 1.15
    rebuilt = rebuild_bundle_from_ui(
        bundle,
        config_updates=dict(bundle.config),
        inverter_catalog=bundle.inverter_catalog,
        battery_catalog=bundle.battery_catalog,
        demand_profile=frame_from_rows(bundle.demand_profile_table.to_dict("records"), list(bundle.demand_profile_table.columns)),
        demand_profile_weights=frame_from_rows(bundle.demand_profile_weights_table.to_dict("records"), list(bundle.demand_profile_weights_table.columns)),
        demand_profile_general=frame_from_rows(bundle.demand_profile_general_table.to_dict("records"), list(bundle.demand_profile_general_table.columns)),
        month_profile=edited_month,
        sun_profile=bundle.sun_profile_table,
        cop_kwp_table=bundle.cop_kwp_table,
        cop_kwp_table_others=bundle.cop_kwp_table_others,
    )

    assert float(rebuilt.month_profile_table.loc[0, "Demand_month"]) == 1.15
    assert float(rebuilt.demand_month_factor[0]) == 1.15


def test_npv_chart_adds_top_axis_for_panel_count() -> None:
    table = pd.DataFrame(
        [
            {
                "candidate_key": "12.000::None",
                "kWp": 12.0,
                "battery": "None",
                "NPV_COP": 10_000_000,
                "payback_years": 5.5,
                "self_consumption_ratio": 0.45,
                "peak_ratio": 1.1,
                "scan_order": 0,
            },
            {
                "candidate_key": "18.000::BAT-10",
                "kWp": 18.0,
                "battery": "BAT-10",
                "NPV_COP": 16_000_000,
                "payback_years": 6.2,
                "self_consumption_ratio": 0.52,
                "peak_ratio": 1.25,
                "scan_order": 1,
            },
        ]
    )

    figure = build_npv_figure(table, selected_key="18.000::BAT-10", lang="es", module_power_w=600.0)

    assert figure.layout.xaxis.title.text == "kWp instalado"
    assert figure.layout.xaxis2.title.text == "Número de paneles"
    assert list(figure.layout.xaxis2.ticktext) == ["20", "30"]
    assert list(figure.layout.xaxis2.tickvals) == pytest.approx([12.0, 18.0])
    assert list(figure.data[0].customdata[0][:2]) == ["12.000::None", 20]
    assert any(trace.name == "Candidato seleccionado" for trace in figure.data)


def test_npv_chart_omits_top_axis_without_valid_module_power() -> None:
    table = pd.DataFrame(
        [
            {
                "candidate_key": "12.000::None",
                "kWp": 12.0,
                "battery": "None",
                "NPV_COP": 10_000_000,
                "payback_years": 5.5,
                "self_consumption_ratio": 0.45,
                "peak_ratio": 1.1,
                "scan_order": 0,
            },
            {
                "candidate_key": "18.000::BAT-10",
                "kWp": 18.0,
                "battery": "BAT-10",
                "NPV_COP": 16_000_000,
                "payback_years": 6.2,
                "self_consumption_ratio": 0.52,
                "peak_ratio": 1.25,
                "scan_order": 1,
            },
        ]
    )

    figure = build_npv_figure(table, lang="es", module_power_w=0.0)

    assert "xaxis2" not in figure.layout


def test_deep_dive_figure_builders_return_non_empty_plotly_figures() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None
    detail = scenario.scan_result.candidate_details[scenario.selected_candidate_key or scenario.scan_result.best_candidate_key]

    annual = build_annual_coverage_figure(detail, scenario.config_bundle.config, lang="es")
    battery_load = build_battery_load_figure(detail, scenario.config_bundle.config, lang="es")
    pv_destination = build_pv_destination_figure(detail, scenario.config_bundle.config, lang="es")
    typical_day = build_typical_day_figure(detail, scenario, lang="es")

    assert annual.data and all(trace.type == "bar" for trace in annual.data)
    assert annual.layout.barmode == "stack"
    assert battery_load.data and all(trace.type == "bar" for trace in battery_load.data)
    assert battery_load.layout.barmode == "stack"
    assert pv_destination.data and all(trace.type == "bar" for trace in pv_destination.data)
    assert pv_destination.layout.barmode == "stack"
    assert typical_day.data
    assert typical_day.data[0].type == "bar"
    assert typical_day.data[1].type == "bar"
    assert typical_day.data[2].type == "scatter"


def test_cash_flow_timeline_starts_next_calendar_year_and_uses_dual_x_axis() -> None:
    monthly = pd.DataFrame(
        {
            "Año_mes": list(range(1, 25)),
            "NPV_COP": [-(24 - idx) * 1000 for idx in range(24)],
            "Ahorro_COP": [1500.0] * 24,
        }
    )

    cash_flow = build_cash_flow(monthly, base_year=2026)
    figure = build_cash_flow_figure(cash_flow, lang="es", base_year=2026)

    assert {"month_index", "calendar_year", "project_year"}.issubset(cash_flow.columns)
    assert cash_flow.loc[0, "calendar_year"] == 2027
    assert cash_flow.loc[11, "calendar_year"] == 2027
    assert cash_flow.loc[12, "calendar_year"] == 2028
    assert cash_flow.loc[0, "project_year"] == 1
    assert cash_flow.loc[12, "project_year"] == 2
    assert figure.data[0].type == "bar"
    assert figure.layout.xaxis.title.text == "Año calendario"
    assert figure.layout.xaxis.ticktext[0] == "2027"
    assert figure.layout.xaxis2.title.text == "Horizonte del proyecto"
    assert figure.layout.xaxis2.ticktext[0] == "Año 1"


def test_cash_flow_figure_uses_sign_aware_bars_and_crossing_marker() -> None:
    monthly = pd.DataFrame(
        {
            "Año_mes": ["01-01", "01-02", "01-03", "01-04"],
            "NPV_COP": [-2_000.0, -1_000.0, 1_000.0, 2_000.0],
            "Ahorro_COP": [500.0, 500.0, 500.0, 500.0],
        }
    )

    cash_flow = build_cash_flow(monthly, base_year=2026)
    figure = build_cash_flow_figure(cash_flow, lang="es", base_year=2026)

    assert figure.data[0].type == "bar"
    assert list(figure.data[0].marker.color) == ["red", "red", "green", "green"]
    assert len(figure.layout.shapes) >= 2


def test_artifact_exports_write_into_resultados_without_deleting_existing_files(tmp_path) -> None:
    base_dir = tmp_path / "Resultados"
    keep_file = base_dir / "keep.txt"
    base_dir.mkdir(parents=True, exist_ok=True)
    keep_file.write_text("keep", encoding="utf-8")

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()

    deterministic_paths = export_deterministic_artifacts(scenario, output_root=base_dir)
    assert keep_file.exists()
    assert deterministic_paths
    assert any(path.suffix == ".png" for path in deterministic_paths)
    assert {path.name for path in deterministic_paths}.issuperset({"chart_npv_vs_kWp.png", "resumen_valor_presente_neto.csv", "resumen_optimizacion.txt"})
    scenario_root = next(path for path in deterministic_paths if path.name == "chart_npv_vs_kWp.png").parent
    assert set(legacy_deterministic_export_manifest()).issubset({path.name for path in scenario_root.iterdir()})
    assert any(path.name == "candidatos_factibles.csv" for path in deterministic_paths)

    candidate_key = scenario.selected_candidate_key or scenario.scan_result.best_candidate_key
    risk_result = run_monte_carlo(
        scenario.config_bundle,
        selected_candidate_key=candidate_key,
        seed=0,
        n_simulations=6,
        return_samples=False,
        baseline_scan=scenario.scan_result,
    )
    risk_paths = export_risk_artifacts(scenario, risk_result, output_root=base_dir)
    assert {path.name for path in risk_paths}.issuperset(set(legacy_risk_export_manifest()))
    assert any(path.name == "histograma_payback.png" for path in risk_paths)
    assert any(path.name == "riesgo_percentiles.csv" for path in risk_paths)
    assert keep_file.exists()


def test_relative_output_root_resolves_to_absolute_path(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()

    paths = export_deterministic_artifacts(scenario, output_root=Path("Resultados_rel"))

    assert paths
    assert all(path.is_absolute() for path in paths)
    assert paths[0].parts[-2] == "Base"


def test_payback_histogram_highlight_band_is_rendered() -> None:
    frame = pd.DataFrame(
        {
            "bin_left": [1.0, 2.0, 3.0],
            "bin_right": [2.0, 3.0, 4.0],
            "count": [2, 3, 1],
            "probability": [0.2, 0.5, 0.3],
        }
    )
    figure = build_histogram_figure(
        frame,
        title="Histograma",
        x_title="Payback [años]",
        lang="es",
        highlight_range=(1.5, 3.5),
        density_frame=pd.DataFrame({"value": [1.0, 2.0, 3.0], "density": [0.1, 0.2, 0.1]}),
    )
    assert len(figure.layout.shapes or []) == 1
    assert len(figure.data) == 2
