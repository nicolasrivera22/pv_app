from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from dash import dcc
from dash.exceptions import PreventUpdate
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
help_page = importlib.import_module("pages.help")
from services import (
    ScenarioSessionState,
    add_scenario,
    build_assumption_sections,
    build_display_columns,
    build_table_display_columns,
    bootstrap_client_session,
    commit_client_session,
    create_scenario_record,
    export_deterministic_artifacts,
    export_risk_artifacts,
    extract_config_metadata,
    format_metric,
    legacy_deterministic_export_manifest,
    legacy_risk_export_manifest,
    load_config_from_excel,
    load_example_config,
    normalize_price_table_rows,
    rebuild_bundle_from_ui,
    run_monte_carlo,
    run_scan,
    run_scenario_scan,
    save_project,
    tr,
)
from services.result_views import (
    build_annual_coverage_figure,
    build_battery_load_figure,
    build_monthly_balance,
    build_monthly_balance_figure,
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


def _session_payload(state, *, lang: str = "es") -> dict:
    return commit_client_session(bootstrap_client_session(lang), state).to_payload()


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


def _find_components(node, predicate) -> list:
    matches = []
    if predicate(node):
        matches.append(node)
    children = getattr(node, "children", None)
    if children is None:
        return matches
    if isinstance(children, (list, tuple)):
        for child in children:
            matches.extend(_find_components(child, predicate))
        return matches
    matches.extend(_find_components(children, predicate))
    return matches


def _find_component_with_class(node, class_name: str):
    classes = str(getattr(node, "className", "") or "").split()
    if class_name in classes:
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_component_with_class(child, class_name)
            if found is not None:
                return found
        return None
    return _find_component_with_class(children, class_name)


def _find_field(sections: list[dict], field_key: str) -> dict:
    for section in sections:
        for bucket in ("basic", "advanced"):
            for field in section.get(bucket, []):
                if field["field"] == field_key:
                    return field
    raise AssertionError(f"Field {field_key!r} not found")


def test_app_defaults_to_spanish() -> None:
    app = create_app()
    layout = app.layout() if callable(app.layout) else app.layout
    selector = _find_component(layout, "language-selector")
    help_nav = _find_component(layout, "nav-help-label")
    assert isinstance(selector, dcc.Dropdown)
    assert selector.value == "es"
    assert help_nav is not None
    assert help_nav.children == "Ayuda"


def test_help_page_renders_real_product_help_content() -> None:
    layout = help_page.layout() if callable(help_page.layout) else help_page.layout
    title = _find_component(layout, "help-page-title")
    content = _find_component(layout, "help-content")

    assert title.children == tr("help.title", "es")
    assert content is not None


def test_first_render_placeholders_are_spanish_first() -> None:
    sidebar = scenario_sidebar()
    rename_input = _find_component(sidebar, "rename-scenario-input")
    rename_note = _find_component(sidebar, "rename-scenario-note")
    risk_controls = risk_controls_section()
    risk_scenario_dropdown = _find_component(risk_controls, "risk-scenario-dropdown")
    risk_candidate_dropdown = _find_component(risk_controls, "risk-candidate-dropdown")

    assert _find_component(sidebar, "load-example-btn") is None
    assert _find_component(sidebar, "scenario-dropdown") is None
    assert _find_component(sidebar, "set-active-scenario-btn") is None
    assert rename_input.placeholder == "Nombre del escenario"
    assert rename_note.children == tr("workbench.rename_active_note", "es")
    assert risk_scenario_dropdown.placeholder == "Selecciona un escenario completado"
    assert risk_candidate_dropdown.placeholder == "Selecciona un diseño factible"


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
    assert tr("workbench.profiles.price_others", "es") == "Otros precios variables"
    assert tr("workbench.profiles.price_others", "en") == "Other variable prices"
    assert tr("workbench.profiles.add_row", "es") == "Añadir fila"
    assert "redistribuye la demanda anual" in tr("workbench.profiles.tooltip.month", "es")
    assert "redistributes annual demand" in tr("workbench.profiles.tooltip.month", "en")


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


def test_assumption_sections_apply_ui_scaling_suffixes_and_bounds() -> None:
    bundle = load_example_config()
    bundle = replace(
        bundle,
        config={
            **bundle.config,
            "discount_rate": 0.05,
            "alpha_mix": 0.8,
            "a_Voc_pct": -0.29,
            "limit_peak_ratio": 2.5,
            "modules_span_each_side": 4,
        },
    )

    sections = build_assumption_sections(bundle, lang="es", show_all=True)

    discount_rate = _find_field(sections, "discount_rate")
    alpha_mix = _find_field(sections, "alpha_mix")
    a_voc_pct = _find_field(sections, "a_Voc_pct")
    limit_peak_ratio = _find_field(sections, "limit_peak_ratio")
    modules_span = _find_field(sections, "modules_span_each_side")

    assert discount_rate["value"] == 5
    assert discount_rate["suffix"] == "%/año"
    assert discount_rate["display_format"] == "percent_rate"
    assert alpha_mix["value"] == 80
    assert alpha_mix["suffix"] == "%"
    assert alpha_mix["min"] == 0
    assert alpha_mix["max"] == 100
    assert a_voc_pct["value"] == pytest.approx(-0.29)
    assert a_voc_pct["suffix"] == "%/°C"
    assert limit_peak_ratio["display_format"] == "ratio"
    assert limit_peak_ratio["suffix"] is None
    assert modules_span["input_step"] == 1
    assert modules_span["suffix"] == "módulos"


def test_assumption_sections_apply_contextual_disabled_states_and_notes() -> None:
    bundle = load_example_config()
    sections = build_assumption_sections(bundle, lang="es", show_all=True)

    battery_section = next(section for section in sections if section["group_key"] == "Controles de Batería y Exporte")
    peak_section = next(section for section in sections if section["group_key"] == "Restricción de Proporción Pico")

    assert _find_field(sections, "price_total_COP")["disabled"] is True
    assert _find_field(sections, "battery_name")["disabled"] is True
    assert _find_field(sections, "kWp_seed_manual_kWp")["disabled"] is True
    assert _find_field(sections, "limit_peak_month_fixed")["disabled"] is True
    assert _find_field(sections, "mc_manual_kWp")["disabled"] is True
    assert battery_section["context_note_id"] == "battery-export-context-note"
    assert "catálogo" in battery_section["context_note"]
    assert "automáticamente" in peak_section["context_note"]


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
    sun_columns, sun_tooltips = build_table_display_columns("sun_profile", ["SOL"], "es")

    assert [column["name"] for column in price_columns] == ["kWp mín", "Precio por kWp [COP/kWp]"]
    assert price_columns[1]["type"] == "numeric"
    assert battery_columns[0]["name"] == "Energía nominal [kWh]"
    assert battery_columns[1]["name"] == "Potencia máx [kW]"
    assert weight_columns[0]["name"] == "Peso res [%]"
    assert month_columns[0]["name"] == "Factor demanda"
    assert month_columns[1]["name"] == "Factor HSP"
    assert sun_columns[0]["name"] == "Participación solar [%]"
    assert "costo" in price_tooltips["PRECIO_POR_KWP"].lower()
    assert "capacidad" in battery_tooltips["nom_kWh"].lower()
    assert "peso" in weight_tooltips["W_RES"].lower()
    assert "mensual" in month_tooltips["Demand_month"].lower()
    assert "solar" in sun_tooltips["SOL"].lower()

    candidate_table = _find_component(candidate_explorer_section(), "active-candidate-table")
    profile_table = _find_component(profile_editor_section(), "month-profile-editor")
    catalog_table = _find_component(catalog_editor_section(), "inverter-table-editor")
    assert candidate_table.tooltip_delay == 0
    assert candidate_table.tooltip_duration is None
    assert profile_table.tooltip_delay == 0
    assert profile_table.tooltip_duration is None
    assert catalog_table.tooltip_delay == 0
    assert catalog_table.tooltip_duration is None


def test_profile_editor_uses_main_row_layout_title_tooltips_and_pricing_row_controls() -> None:
    section = profile_editor_section()
    main_grid = _find_component(section, "profile-main-grid")
    main_chart = _find_component(section, "profile-main-chart-panel")
    secondary_grid = _find_component(section, "profile-secondary-grid")
    secondary_chart = _find_component(section, "profile-secondary-chart-panel")
    activators = _find_components(
        section,
        lambda node: isinstance(getattr(node, "id", None), dict) and node.id.get("type") == "profile-table-activate",
    )

    assert main_grid is not None
    assert main_chart is not None
    assert secondary_grid is not None
    assert secondary_chart is not None
    assert _find_component(workbench_page.layout, "active-profile-table-state") is not None
    assert len(main_grid.children) == 3
    assert len(secondary_grid.children) == 4
    assert [getattr(child, "id", None) for child in section.children[2:6]] == [
        "profile-main-grid",
        "profile-main-chart-panel",
        "profile-secondary-grid",
        "profile-secondary-chart-panel",
    ]
    assert len(activators) == 7
    assert {component.id["table"] for component in activators} == {
        "month-profile-editor",
        "sun-profile-editor",
        "demand-profile-weights-editor",
        "price-kwp-editor",
        "price-kwp-others-editor",
        "demand-profile-editor",
        "demand-profile-general-editor",
    }
    assert _find_component(section, "month-profile-card") is not None
    assert _find_component(section, "sun-profile-card") is not None
    assert _find_component(section, "demand-profile-weights-card") is not None
    assert _find_component(section, "price-kwp-card") is not None
    assert _find_component(section, "price-kwp-others-card") is not None
    assert _find_component(section, "demand-profile-card") is not None
    assert _find_component(section, "demand-profile-general-card") is not None
    assert _find_component(main_grid.children[0], "month-profile-title").children == tr("workbench.profiles.month", "es")
    assert _find_component(main_grid.children[1], "sun-profile-title").children == tr("workbench.profiles.sun", "es")
    assert _find_component(main_grid.children[2], "demand-profile-weights-title").children == tr("workbench.profiles.demand_weights", "es")
    assert "profile-main-panel-wide" in str(_find_component(main_grid.children[2], "demand-profile-weights-panel").className)
    assert _find_component(section, "month-profile-editor").page_size == 12
    assert _find_component(section, "sun-profile-editor").page_size == 12
    assert _find_component(section, "demand-profile-weights-editor").page_size == 12
    assert _find_component(section, "price-kwp-editor").page_size == 8
    assert _find_component(section, "price-kwp-others-editor").page_size == 8
    assert _find_component(section, "month-profile-tooltip").children == tr("workbench.profiles.tooltip.month", "es")
    assert _find_component(section, "sun-profile-tooltip").children == tr("workbench.profiles.tooltip.sun", "es")
    assert _find_component(section, "price-kwp-tooltip").children == tr("workbench.profiles.tooltip.price", "es")
    assert _find_component(section, "price-kwp-others-tooltip").children == tr("workbench.profiles.tooltip.price_others", "es")
    assert _find_component(section, "demand-profile-tooltip").children == tr("workbench.profiles.tooltip.demand_weekday", "es")
    assert _find_component(section, "demand-profile-general-tooltip").children == tr("workbench.profiles.tooltip.demand_general", "es")
    assert _find_component(section, "demand-profile-weights-tooltip").children == tr("workbench.profiles.tooltip.demand_weights", "es")
    assert _find_component(section, "add-price-kwp-row-btn").children == tr("workbench.profiles.add_row", "es")
    assert _find_component(section, "add-price-kwp-others-row-btn").children == tr("workbench.profiles.add_row", "es")
    assert _find_component(workbench_page.layout, "run-scan-choice-dialog") is not None
    assert _find_component(workbench_page.layout, "run-scan-save-and-run-btn") is not None
    assert _find_component(workbench_page.layout, "run-scan-run-unsaved-btn") is not None
    assert _find_component(workbench_page.layout, "run-scan-cancel-btn") is not None


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
        "suffix": "kWh/mes",
        "display_format": "energy",
        "precision": 0,
        "input_step": 1,
        "min": None,
        "max": None,
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
    assert "input-affix" in markup
    assert "kWh/mes" in markup
    assert "scenario-meta" not in markup
    assert "'title':" not in markup


def test_assumption_editor_leaves_dropdowns_and_text_fields_without_numeric_affixes() -> None:
    fields = [
        {
            "field": "include_battery",
            "label": "Incluir batería",
            "help": "Activa el análisis con almacenamiento.",
            "kind": "dropdown",
            "value": True,
            "suffix": None,
            "options": [{"label": "Sí", "value": True}, {"label": "No", "value": False}],
        },
        {
            "field": "battery_name",
            "label": "Batería fija",
            "help": "Batería fija.",
            "kind": "text",
            "value": "",
            "suffix": None,
            "options": [],
        },
    ]
    rendered = render_assumption_sections(
        [{"group": "Batería", "help": "", "basic": fields, "advanced": []}],
        show_all=False,
        empty_message="Sin datos",
        advanced_label="Avanzado",
    )

    markup = str(rendered[0].to_plotly_json())
    assert "input-affix" not in markup


def test_assumption_editor_renders_context_notes_and_contextual_card_ids() -> None:
    sections = build_assumption_sections(load_example_config(), lang="es", show_all=True)
    rendered = render_assumption_sections(
        sections,
        show_all=True,
        empty_message="Sin datos",
        advanced_label="Avanzado",
    )

    notes = []
    cards = []
    for node in rendered:
        notes.extend(
            _find_components(
                node,
                lambda item: isinstance(getattr(item, "id", None), dict)
                and item.id.get("type") == "assumption-context-note",
            )
        )
        cards.extend(
            _find_components(
                node,
                lambda item: isinstance(getattr(item, "id", None), dict)
                and item.id.get("type") == "assumption-field-card",
            )
        )

    note_groups = {component.id["group"] for component in notes}
    note_by_group = {component.id["group"]: component for component in notes}
    card_by_field = {component.id["field"]: component for component in cards}

    assert {
        "Controles de Batería y Exporte",
        "Semilla",
        "Restricción de Proporción Pico",
        "Monte Carlo",
    }.issubset(note_groups)
    assert note_by_group["Monte Carlo"].style == {"display": "none"}
    assert "field-card-disabled" in card_by_field["battery_name"].className
    assert "field-card-highlight" not in card_by_field["battery_name"].className
    assert "precios-card" in card_by_field["price_total_COP"].className
    assert "field-card-disabled" in card_by_field["price_total_COP"].className


def test_assumption_sections_do_not_render_nan_like_helper_text() -> None:
    bundle = load_example_config()
    config_table = bundle.config_table.copy()
    mask = config_table["Item"] == "include_battery"
    config_table.loc[mask, "Descripción"] = float("nan")
    config_table.loc[mask, "Unidad"] = float("nan")
    bundle = replace(bundle, config_table=config_table)

    sections = build_assumption_sections(bundle, lang="es", show_all=True)
    field = _find_field(sections, "include_battery")
    rendered = render_assumption_sections(
        [{"group": "Batería", "help": "", "basic": [field], "advanced": []}],
        show_all=True,
        empty_message="Sin datos",
        advanced_label="Avanzado",
    )

    markup = str(rendered[0].to_plotly_json()).lower()
    assert field["unit"] == ""
    assert "nan" not in markup


def test_workbench_assumption_context_callback_disables_dependent_controls_and_shows_notes() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state, lang="en")
    field_values = {
        "pricing_mode": "variable",
        "price_total_COP": 58000000,
        "include_battery": False,
        "optimize_battery": False,
        "battery_name": "",
        "bat_DoD": 90.0,
        "bat_coupling": "dc",
        "bat_eta_rt": 90.0,
        "kWp_seed_mode": "auto",
        "kWp_seed_manual_kWp": 15.0,
        "limit_peak_ratio_enable": False,
        "limit_peak_ratio": 2.5,
        "limit_peak_year": 0,
        "limit_peak_month_mode": "max",
        "limit_peak_basis": "weighted_mean",
        "limit_peak_month_fixed": 1,
        "mc_use_manual_kWp": False,
        "mc_manual_kWp": 15.0,
    }
    input_ids = [{"type": "assumption-input", "field": field} for field in field_values]
    card_ids = [{"type": "assumption-field-card", "field": field} for field in field_values]
    note_ids = [
        {"type": "assumption-context-note", "group": "Controles de Batería y Exporte"},
        {"type": "assumption-context-note", "group": "Semilla"},
        {"type": "assumption-context-note", "group": "Restricción de Proporción Pico"},
        {"type": "assumption-context-note", "group": "Monte Carlo"},
    ]

    disabled_values, card_classes, note_children, note_styles = workbench_page.sync_assumption_context_ui(
        payload,
        input_ids,
        list(field_values.values()),
        "en",
        card_ids,
        note_ids,
    )

    disabled_by_field = dict(zip(field_values.keys(), disabled_values))
    class_by_field = dict(zip(field_values.keys(), card_classes))

    assert disabled_by_field["price_total_COP"] is True
    assert disabled_by_field["optimize_battery"] is True
    assert disabled_by_field["battery_name"] is True
    assert disabled_by_field["bat_DoD"] is True
    assert disabled_by_field["bat_coupling"] is True
    assert disabled_by_field["bat_eta_rt"] is True
    assert disabled_by_field["kWp_seed_manual_kWp"] is True
    assert disabled_by_field["limit_peak_ratio"] is True
    assert disabled_by_field["limit_peak_year"] is True
    assert disabled_by_field["limit_peak_month_mode"] is True
    assert disabled_by_field["limit_peak_basis"] is True
    assert disabled_by_field["limit_peak_month_fixed"] is True
    assert disabled_by_field["mc_manual_kWp"] is True
    assert "field-card-disabled" in class_by_field["battery_name"]
    assert "field-card-disabled" in class_by_field["price_total_COP"]
    assert note_children == [
        tr("workbench.assumptions.context.battery.off", "en"),
        tr("workbench.assumptions.context.seed.auto", "en"),
        tr("workbench.assumptions.context.peak.disabled", "en"),
        "",
    ]
    assert note_styles == [
        {"display": "block"},
        {"display": "block"},
        {"display": "block"},
        {"display": "none"},
    ]


def test_workbench_assumption_context_callback_highlights_fixed_battery_selection() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state, lang="en")
    field_values = {
        "pricing_mode": "total",
        "price_total_COP": 58000000,
        "include_battery": True,
        "optimize_battery": False,
        "battery_name": "BAT-10",
    }
    input_ids = [{"type": "assumption-input", "field": field} for field in field_values]
    card_ids = [{"type": "assumption-field-card", "field": field} for field in field_values]
    note_ids = [{"type": "assumption-context-note", "group": "Controles de Batería y Exporte"}]

    disabled_values, card_classes, note_children, note_styles = workbench_page.sync_assumption_context_ui(
        payload,
        input_ids,
        list(field_values.values()),
        "en",
        card_ids,
        note_ids,
    )

    disabled_by_field = dict(zip(field_values.keys(), disabled_values))
    class_by_field = dict(zip(field_values.keys(), card_classes))

    assert disabled_by_field["price_total_COP"] is False
    assert disabled_by_field["battery_name"] is False
    assert "field-card-highlight" in class_by_field["battery_name"]
    assert "field-card-disabled" not in class_by_field["battery_name"]
    assert note_children == [tr("workbench.assumptions.context.battery.fixed", "en")]
    assert note_styles == [{"display": "block"}]


def test_populate_assumptions_keeps_monte_carlo_group_visible_in_workbench() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state, lang="es")

    rendered = workbench_page.populate_assumptions(payload, [], "es")

    assert any("Monte Carlo" in str(section.to_plotly_json()) for section in rendered)


def test_active_summary_uses_copy_and_meta_classes_for_hierarchy() -> None:
    guidance = _find_component(workbench_page.layout, "active-scan-guidance")
    source_status = _find_component(workbench_page.layout, "active-source-status")
    run_status = _find_component(workbench_page.layout, "active-run-status")
    run_button = _find_component(workbench_page.layout, "run-active-scan-btn")
    state_strip = _find_component(workbench_page.layout, "workbench-state-strip")

    assert "active-summary-copy" in guidance.className
    assert "active-summary-meta" in source_status.className
    assert "active-summary-meta" in run_status.className
    assert run_button is not None
    assert state_strip is not None
    assert "workbench-state-strip" in state_strip.className


def test_active_summary_uses_two_column_layout_with_dedicated_content_and_action_areas() -> None:
    top = _find_component_with_class(workbench_page.layout, "active-summary-top")
    content = _find_component_with_class(workbench_page.layout, "active-summary-content")
    actions = _find_component_with_class(workbench_page.layout, "active-summary-actions")

    assert top is not None
    assert content is not None
    assert actions is not None
    assert _find_component(content, "active-scan-guidance") is not None
    assert _find_component(content, "workbench-state-strip") is not None
    assert _find_component(actions, "run-active-scan-btn") is not None


def test_workbench_state_strip_reflects_saved_clean_scenario() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    state = save_project(state, project_name="Demo", language="en")
    active = state.get_scenario()
    payload = _session_payload(state, lang="en")

    chips = workbench_page.sync_workbench_state_strip(
        payload,
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        active.config_bundle.cop_kwp_table.to_dict("records"),
        active.config_bundle.cop_kwp_table_others.to_dict("records"),
        active.config_bundle.demand_profile_table.to_dict("records"),
        active.config_bundle.demand_profile_general_table.to_dict("records"),
        active.config_bundle.demand_profile_weights_table.to_dict("records"),
        "en",
    )

    assert [chip.children for chip in chips] == [
        tr("workbench.state.applied", "en"),
        tr("workbench.state.project_saved", "en"),
        tr("workbench.state.ready_to_run", "en"),
    ]
    assert chips[1].className.endswith("workbench-state-chip-success")


def test_workbench_state_strip_reflects_pending_unsaved_and_outdated_state() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    state = save_project(state, project_name="Demo", language="es")
    active = state.get_scenario()
    payload = _session_payload(state, lang="es")

    chips = workbench_page.sync_workbench_state_strip(
        payload,
        [{"type": "assumption-input", "field": "E_month_kWh"}],
        [float(active.config_bundle.config["E_month_kWh"]) + 25.0],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        active.config_bundle.cop_kwp_table.to_dict("records"),
        active.config_bundle.cop_kwp_table_others.to_dict("records"),
        active.config_bundle.demand_profile_table.to_dict("records"),
        active.config_bundle.demand_profile_general_table.to_dict("records"),
        active.config_bundle.demand_profile_weights_table.to_dict("records"),
        "es",
    )

    assert [chip.children for chip in chips] == [
        tr("workbench.state.pending_apply", "es"),
        tr("workbench.state.project_unsaved", "es"),
        tr("workbench.state.scan_outdated", "es"),
    ]
    assert all("workbench-state-chip-warning" in chip.className for chip in chips)


def test_css_is_loaded_from_assets_instead_of_inline_app_block() -> None:
    asset_css = Path("assets/app.css")
    app_source = Path("app.py").read_text(encoding="utf-8")
    css_source = asset_css.read_text(encoding="utf-8")

    assert asset_css.exists()
    assert "app.index_string" not in app_source
    assert ".assumption-input-shell" in css_source
    assert ".candidate-selection-helper" in css_source
    assert "body {" in css_source
    assert ".active-summary-copy" in css_source
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css_source
    assert ".active-summary-top" in css_source
    assert ".active-summary-actions" in css_source
    assert ".profile-main-grid" in css_source
    assert "minmax(0, 1.35fr)" in css_source
    assert ".profile-secondary-grid" in css_source
    assert ".profile-inline-btn" in css_source
    assert ".profile-table-activator" in css_source
    assert ".profile-chart-panel" in css_source
    assert ".profile-table-card-active" in css_source
    assert ".workbench-state-strip" in css_source
    assert ".workbench-state-chip" in css_source


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


def test_profile_pricing_add_row_callbacks_use_current_column_ids() -> None:
    columns = [{"id": "MIN"}, {"id": "MAX"}, {"id": "PRECIO_POR_KWP"}]
    rows = [{"MIN": 1.0, "MAX": 5.0, "PRECIO_POR_KWP": 5_500_000}]

    price_rows = workbench_page.add_price_kwp_row(1, rows, columns)
    other_rows = workbench_page.add_price_kwp_others_row(1, rows, columns)

    assert price_rows[-1] == {"MIN": "", "MAX": "", "PRECIO_POR_KWP": ""}
    assert other_rows[-1] == {"MIN": "", "MAX": "", "PRECIO_POR_KWP": ""}


def test_run_scan_choice_dialog_disables_save_until_project_name_exists() -> None:
    style, title, copy, save_label, disabled, unsaved_label, cancel_label = workbench_page.sync_run_scan_choice_dialog({"open": True}, "", "en")
    named = workbench_page.sync_run_scan_choice_dialog({"open": True}, "Demo", "es")

    assert style["display"] == "flex"
    assert title == "Save before running?"
    assert "Enter a project name" in copy
    assert save_label == "Save and run"
    assert disabled is True
    assert unsaved_label == "Run without saving"
    assert cancel_label == "Cancel"
    assert named[0]["display"] == "flex"
    assert named[4] is False
    assert "Guárdala como 'Demo'" in named[2]


def test_profile_table_activator_translation_uses_current_language() -> None:
    assert workbench_page.translate_profile_table_activators("en") == ["Preview chart"] * 7
    assert workbench_page.translate_profile_table_activators("es") == ["Ver gráfica"] * 7


def test_profile_table_header_click_toggles_the_active_chart(monkeypatch) -> None:
    monkeypatch.setattr(
        workbench_page,
        "ctx",
        SimpleNamespace(triggered_id={"type": "profile-table-activate", "table": "sun-profile-editor"}),
    )

    activated = workbench_page.sync_active_profile_table([], None, None, None, None, None, None, None, {"table_id": None})
    cleared = workbench_page.sync_active_profile_table([], None, None, None, None, None, None, None, {"table_id": "sun-profile-editor"})

    assert activated == {"table_id": "sun-profile-editor"}
    assert cleared == {"table_id": None}


def test_profile_table_active_cell_activates_without_toggling_off(monkeypatch) -> None:
    monkeypatch.setattr(workbench_page, "ctx", SimpleNamespace(triggered_id="sun-profile-editor"))

    activated = workbench_page.sync_active_profile_table(
        [],
        None,
        {"row": 2, "column": 1},
        None,
        None,
        None,
        None,
        None,
        {"table_id": None},
    )

    assert activated == {"table_id": "sun-profile-editor"}

    with pytest.raises(PreventUpdate):
        workbench_page.sync_active_profile_table(
            [],
            None,
            {"row": 2, "column": 1},
            None,
            None,
            None,
            None,
            None,
            {"table_id": "sun-profile-editor"},
        )


def test_hidden_profile_table_sanitization_clears_active_chart() -> None:
    cleared = workbench_page.sanitize_active_profile_table(
        {"table_id": "demand-profile-editor"},
        {"display": "block"},
        {"display": "block"},
        {"display": "none"},
        {"display": "block"},
        {"display": "block"},
    )

    assert cleared == {"table_id": None}


def test_profile_chart_render_routes_main_and_secondary_tables_and_marks_one_active_card() -> None:
    bundle = load_example_config()
    month_columns, _ = build_table_display_columns("month_profile", list(bundle.month_profile_table.columns), "en")
    sun_columns, _ = build_table_display_columns("sun_profile", list(bundle.sun_profile_table.columns), "en")
    demand_weights_columns, _ = build_table_display_columns("demand_profile_weights", list(bundle.demand_profile_weights_table.columns), "en")
    price_columns, _ = build_table_display_columns("cop_kwp", list(bundle.cop_kwp_table.columns), "en")
    price_others_columns, _ = build_table_display_columns("cop_kwp_others", list(bundle.cop_kwp_table_others.columns), "en")
    demand_columns, _ = build_table_display_columns("demand_profile", list(bundle.demand_profile_table.columns), "en")
    demand_general_columns, _ = build_table_display_columns("demand_profile_general", list(bundle.demand_profile_general_table.columns), "en")

    main = workbench_page.render_active_profile_chart(
        {"table_id": "sun-profile-editor"},
        bundle.month_profile_table.to_dict("records"),
        month_columns,
        bundle.sun_profile_table.to_dict("records"),
        sun_columns,
        bundle.demand_profile_weights_table.to_dict("records"),
        demand_weights_columns,
        bundle.cop_kwp_table.to_dict("records"),
        price_columns,
        bundle.cop_kwp_table_others.to_dict("records"),
        price_others_columns,
        bundle.demand_profile_table.to_dict("records"),
        demand_columns,
        bundle.demand_profile_general_table.to_dict("records"),
        demand_general_columns,
        "en",
        {"display": "block"},
        {"display": "block"},
        {"display": "block"},
        {"display": "block"},
        {"display": "block"},
    )
    secondary = workbench_page.render_active_profile_chart(
        {"table_id": "price-kwp-editor"},
        bundle.month_profile_table.to_dict("records"),
        month_columns,
        bundle.sun_profile_table.to_dict("records"),
        sun_columns,
        bundle.demand_profile_weights_table.to_dict("records"),
        demand_weights_columns,
        bundle.cop_kwp_table.to_dict("records"),
        price_columns,
        bundle.cop_kwp_table_others.to_dict("records"),
        price_others_columns,
        bundle.demand_profile_table.to_dict("records"),
        demand_columns,
        bundle.demand_profile_general_table.to_dict("records"),
        demand_general_columns,
        "en",
        {"display": "block"},
        {"display": "block"},
        {"display": "block"},
        {"display": "block"},
        {"display": "block"},
    )

    assert main[0]["display"] == "grid"
    assert main[1] == tr("workbench.profiles.sun", "en")
    assert main[4]["display"] == "none"
    assert sum("profile-table-card-active" in class_name for class_name in main[8:]) == 1

    assert secondary[0]["display"] == "none"
    assert secondary[4]["display"] == "grid"
    assert secondary[5] == tr("workbench.profiles.price", "en")
    assert sum("profile-table-card-active" in class_name for class_name in secondary[8:]) == 1


def test_hidden_active_profile_table_hides_chart_shells_and_active_classes() -> None:
    bundle = load_example_config()
    month_columns, _ = build_table_display_columns("month_profile", list(bundle.month_profile_table.columns), "es")
    sun_columns, _ = build_table_display_columns("sun_profile", list(bundle.sun_profile_table.columns), "es")
    demand_weights_columns, _ = build_table_display_columns("demand_profile_weights", list(bundle.demand_profile_weights_table.columns), "es")
    price_columns, _ = build_table_display_columns("cop_kwp", list(bundle.cop_kwp_table.columns), "es")
    price_others_columns, _ = build_table_display_columns("cop_kwp_others", list(bundle.cop_kwp_table_others.columns), "es")
    demand_columns, _ = build_table_display_columns("demand_profile", list(bundle.demand_profile_table.columns), "es")
    demand_general_columns, _ = build_table_display_columns("demand_profile_general", list(bundle.demand_profile_general_table.columns), "es")

    rendered = workbench_page.render_active_profile_chart(
        {"table_id": "demand-profile-editor"},
        bundle.month_profile_table.to_dict("records"),
        month_columns,
        bundle.sun_profile_table.to_dict("records"),
        sun_columns,
        bundle.demand_profile_weights_table.to_dict("records"),
        demand_weights_columns,
        bundle.cop_kwp_table.to_dict("records"),
        price_columns,
        bundle.cop_kwp_table_others.to_dict("records"),
        price_others_columns,
        bundle.demand_profile_table.to_dict("records"),
        demand_columns,
        bundle.demand_profile_general_table.to_dict("records"),
        demand_general_columns,
        "es",
        {"display": "block"},
        {"display": "block"},
        {"display": "none"},
        {"display": "block"},
        {"display": "block"},
    )

    assert rendered[0]["display"] == "none"
    assert rendered[4]["display"] == "none"
    assert all("profile-table-card-active" not in class_name for class_name in rendered[8:])


def test_apply_button_auto_saves_bound_project_after_rebuild(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = save_project(state, project_name="Demo", language="en")
    payload = _session_payload(state, lang="en")
    calls: list[str] = []

    monkeypatch.setattr(workbench_page, "ctx", SimpleNamespace(triggered_id="apply-edits-btn"))
    monkeypatch.setattr(workbench_page, "apply_workbench_editor_state", lambda *args, **kwargs: calls.append("apply") or state.get_scenario().config_bundle)
    monkeypatch.setattr(workbench_page, "save_project", lambda current_state, project_name, language: calls.append(f"save:{project_name}") or current_state)

    _, status, dialog = workbench_page.mutate_session_state(
        upload_contents=None,
        _new_scenario_clicks=0,
        _duplicate_clicks=0,
        _rename_clicks=0,
        _delete_clicks=0,
        _scenario_pill_clicks=[],
        _apply_clicks=1,
        _run_clicks=0,
        _save_project_clicks=0,
        _save_project_as_clicks=0,
        _open_project_clicks=0,
        upload_filename=None,
        rename_value=None,
        project_name_value="Demo",
        project_dropdown_value=None,
        session_payload=payload,
        assumption_input_ids=[],
        assumption_values=[],
        inverter_rows=[],
        battery_rows=[],
        month_profile_rows=[],
        sun_profile_rows=[],
        price_kwp_rows=[],
        price_kwp_others_rows=[],
        demand_profile_rows=[],
        demand_profile_general_rows=[],
        demand_profile_weights_rows=[],
        language_value="en",
    )

    assert calls == ["apply", "save:Demo"]
    assert "Current edits applied." in status
    assert "Project saved." in status
    assert "Deterministic results marked dirty until rerun." in status
    assert dialog == {"open": False}


def test_run_scan_applies_then_prompts_when_project_is_unbound(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state, lang="en")
    calls: list[str] = []

    monkeypatch.setattr(workbench_page, "ctx", SimpleNamespace(triggered_id="run-active-scan-btn"))
    monkeypatch.setattr(workbench_page, "apply_workbench_editor_state", lambda *args, **kwargs: calls.append("apply") or state.get_scenario().config_bundle)
    monkeypatch.setattr(workbench_page, "run_scenario_scan", lambda *args, **kwargs: calls.append("run") or state)

    _, status, dialog = workbench_page.mutate_session_state(
        upload_contents=None,
        _new_scenario_clicks=0,
        _duplicate_clicks=0,
        _rename_clicks=0,
        _delete_clicks=0,
        _scenario_pill_clicks=[],
        _apply_clicks=0,
        _run_clicks=1,
        _save_project_clicks=0,
        _save_project_as_clicks=0,
        _open_project_clicks=0,
        upload_filename=None,
        rename_value=None,
        project_name_value="",
        project_dropdown_value=None,
        session_payload=payload,
        assumption_input_ids=[],
        assumption_values=[],
        inverter_rows=[],
        battery_rows=[],
        month_profile_rows=[],
        sun_profile_rows=[],
        price_kwp_rows=[],
        price_kwp_others_rows=[],
        demand_profile_rows=[],
        demand_profile_general_rows=[],
        demand_profile_weights_rows=[],
        language_value="en",
    )

    assert calls == ["apply"]
    assert "Current edits applied." in status
    assert "Choose whether to save before running." in status
    assert dialog == {"open": True}


def test_run_scan_applies_saves_and_runs_for_bound_project(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = save_project(state, project_name="Demo", language="en")
    payload = _session_payload(state, lang="en")
    calls: list[str] = []

    monkeypatch.setattr(workbench_page, "ctx", SimpleNamespace(triggered_id="run-active-scan-btn"))
    monkeypatch.setattr(workbench_page, "apply_workbench_editor_state", lambda *args, **kwargs: calls.append("apply") or state.get_scenario().config_bundle)
    monkeypatch.setattr(workbench_page, "save_project", lambda current_state, project_name, language: calls.append(f"save:{project_name}") or current_state)
    monkeypatch.setattr(workbench_page, "run_scenario_scan", lambda current_state, scenario_id: calls.append(f"run:{scenario_id}") or current_state)

    _, status, dialog = workbench_page.mutate_session_state(
        upload_contents=None,
        _new_scenario_clicks=0,
        _duplicate_clicks=0,
        _rename_clicks=0,
        _delete_clicks=0,
        _scenario_pill_clicks=[],
        _apply_clicks=0,
        _run_clicks=1,
        _save_project_clicks=0,
        _save_project_as_clicks=0,
        _open_project_clicks=0,
        upload_filename=None,
        rename_value=None,
        project_name_value="Demo",
        project_dropdown_value=None,
        session_payload=payload,
        assumption_input_ids=[],
        assumption_values=[],
        inverter_rows=[],
        battery_rows=[],
        month_profile_rows=[],
        sun_profile_rows=[],
        price_kwp_rows=[],
        price_kwp_others_rows=[],
        demand_profile_rows=[],
        demand_profile_general_rows=[],
        demand_profile_weights_rows=[],
        language_value="en",
    )

    assert calls == ["apply", "save:Demo", f"run:{state.active_scenario_id}"]
    assert "Current edits applied." in status
    assert "Project saved." in status
    assert "Deterministic scan completed for 'Base'." in status
    assert dialog == {"open": False}


def test_clicking_a_scenario_pill_sets_it_active_immediately(monkeypatch) -> None:
    base_state = ScenarioSessionState.empty()
    first = create_scenario_record("Base", _fast_bundle())
    second = create_scenario_record("Alt", _fast_bundle())
    state = add_scenario(base_state, first, make_active=True)
    state = add_scenario(state, second, make_active=False)
    payload = _session_payload(state, lang="en")

    monkeypatch.setattr(
        workbench_page,
        "ctx",
        SimpleNamespace(triggered_id={"type": "scenario-pill", "scenario_id": second.scenario_id}),
    )

    next_payload, status, dialog = workbench_page.mutate_session_state(
        upload_contents=None,
        _new_scenario_clicks=0,
        _duplicate_clicks=0,
        _rename_clicks=0,
        _delete_clicks=0,
        _scenario_pill_clicks=[0, 1],
        _apply_clicks=0,
        _run_clicks=0,
        _save_project_clicks=0,
        _save_project_as_clicks=0,
        _open_project_clicks=0,
        upload_filename=None,
        rename_value=None,
        project_name_value="",
        project_dropdown_value=None,
        session_payload=payload,
        assumption_input_ids=[],
        assumption_values=[],
        inverter_rows=[],
        battery_rows=[],
        month_profile_rows=[],
        sun_profile_rows=[],
        price_kwp_rows=[],
        price_kwp_others_rows=[],
        demand_profile_rows=[],
        demand_profile_general_rows=[],
        demand_profile_weights_rows=[],
        language_value="en",
    )
    _, next_state = workbench_page._session(next_payload, "en")

    assert next_state.active_scenario_id == second.scenario_id
    assert "Active scenario set to 'Alt'." in status
    assert dialog == {"open": False}


def test_cancel_run_scan_choice_closes_dialog_without_running() -> None:
    status, dialog = workbench_page.cancel_run_scan_choice(1, {"open": True}, "en")

    assert "Current edits applied." in status
    assert "Run cancelled." in status
    assert dialog == {"open": False}


def test_price_table_normalizer_ignores_fully_blank_draft_rows_and_preserves_bundle_shape() -> None:
    bundle = _fast_bundle()
    rows = [*bundle.cop_kwp_table.to_dict("records"), {"MIN": "", "MAX": "", "PRECIO_POR_KWP": ""}]

    normalized, issues = normalize_price_table_rows(rows, "Precios_kWp_relativos")
    rebuilt = rebuild_bundle_from_ui(
        bundle,
        config_updates=dict(bundle.config),
        inverter_catalog=bundle.inverter_catalog,
        battery_catalog=bundle.battery_catalog,
        demand_profile=bundle.demand_profile_table,
        demand_profile_weights=bundle.demand_profile_weights_table,
        demand_profile_general=bundle.demand_profile_general_table,
        month_profile=bundle.month_profile_table,
        sun_profile=bundle.sun_profile_table,
        cop_kwp_table=frame_from_rows(normalized.to_dict("records"), list(bundle.cop_kwp_table.columns)),
        cop_kwp_table_others=bundle.cop_kwp_table_others,
    )

    assert not issues
    assert len(normalized) == len(bundle.cop_kwp_table)
    assert list(rebuilt.cop_kwp_table.columns) == list(bundle.cop_kwp_table.columns)
    assert len(rebuilt.cop_kwp_table) == len(bundle.cop_kwp_table)


def test_price_table_normalizer_reports_partial_and_non_numeric_rows_without_crashing_rebuild() -> None:
    bundle = _fast_bundle()
    draft_row_number = len(bundle.cop_kwp_table) + 1
    rows = [
        *bundle.cop_kwp_table.to_dict("records"),
        {"MIN": "10", "MAX": "", "PRECIO_POR_KWP": "oops"},
    ]

    normalized, issues = normalize_price_table_rows(rows, "Precios_kWp_relativos")
    rebuilt = rebuild_bundle_from_ui(
        bundle,
        config_updates=dict(bundle.config),
        inverter_catalog=bundle.inverter_catalog,
        battery_catalog=bundle.battery_catalog,
        demand_profile=bundle.demand_profile_table,
        demand_profile_weights=bundle.demand_profile_weights_table,
        demand_profile_general=bundle.demand_profile_general_table,
        month_profile=bundle.month_profile_table,
        sun_profile=bundle.sun_profile_table,
        cop_kwp_table=frame_from_rows(normalized.to_dict("records"), list(bundle.cop_kwp_table.columns)),
        cop_kwp_table_others=bundle.cop_kwp_table_others,
    )

    messages = {issue.message for issue in issues}
    assert f"Fila {draft_row_number}: el campo 'MAX' es obligatorio." in messages
    assert f"Fila {draft_row_number}: 'PRECIO_POR_KWP' debe ser numérico." in messages
    assert len(normalized) == len(bundle.cop_kwp_table) + 1
    assert rebuilt.cop_kwp_table.shape[1] == bundle.cop_kwp_table.shape[1]


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
    assert any(trace.name == "Diseño seleccionado" for trace in figure.data)


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


def test_workbench_monthly_figures_use_abbreviated_month_labels() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None
    detail = scenario.scan_result.candidate_details[scenario.selected_candidate_key or scenario.scan_result.best_candidate_key]

    monthly_balance = build_monthly_balance(detail["monthly"], lang="es")
    monthly_balance_figure = build_monthly_balance_figure(monthly_balance, lang="es")
    annual = build_annual_coverage_figure(detail, scenario.config_bundle.config, lang="es")
    battery_load = build_battery_load_figure(detail, scenario.config_bundle.config, lang="es")

    expected = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    assert list(monthly_balance_figure.layout.xaxis.ticktext) == expected
    assert list(annual.layout.xaxis.ticktext) == expected
    assert list(battery_load.layout.xaxis.ticktext) == expected


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
