from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from dash import dcc, no_update
from dash.exceptions import PreventUpdate
import pandas as pd
import pytest

from app import _nav_link_class_name, create_app
import services.workspace_shared_callbacks as shared_callbacks
import services.workspace_results_callbacks as results_callbacks
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
from components.workspace_frame import workspace_frame
from pages import risk as risk_page
from pages import workbench as workbench_page
help_page = importlib.import_module("pages.help")
from services.candidate_financials import CandidateFinancialSnapshotUnavailableError, build_candidate_financial_snapshot
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
    prepare_economics_runtime_price_bridge,
    rebuild_bundle_from_ui,
    resolve_client_session,
    run_monte_carlo,
    run_scan,
    run_scenario_scan,
    resolve_runtime_price_bridge_state,
    save_project,
    tr,
    update_selected_candidate,
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
from services.workspace_shared_callbacks import populate_workspace_shell


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


def test_nav_link_class_name_uses_exact_root_and_prefix_matches() -> None:
    assert _nav_link_class_name("/", "/") == "nav-link nav-link-active"
    assert _nav_link_class_name("/assumptions", "/") == "nav-link"
    assert _nav_link_class_name("/assumptions", "/assumptions") == "nav-link nav-link-active"
    assert _nav_link_class_name("/assumptions/demand", "/assumptions") == "nav-link nav-link-active"
    assert _nav_link_class_name("/help/", "/help") == "nav-link nav-link-active"


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
    project_delete_btn = _find_component(sidebar, "delete-project-btn")
    risk_controls = risk_controls_section()
    risk_scenario_dropdown = _find_component(risk_controls, "risk-scenario-dropdown")
    risk_candidate_dropdown = _find_component(risk_controls, "risk-candidate-dropdown")

    assert _find_component(sidebar, "scenario-start-title").children == tr("workbench.sidebar.start.title", "es")
    assert _find_component(sidebar, "scenario-upload-title").children == tr("workbench.import_excel.title", "es")
    assert _find_component(sidebar, "new-scenario-btn").children == tr("workbench.load_example", "es")
    assert project_delete_btn is not None
    assert _find_component(sidebar, "scenario-dropdown") is None
    assert _find_component(sidebar, "set-active-scenario-btn") is None
    assert rename_input.placeholder == "Nombre del escenario"
    assert rename_note.children == tr("workbench.rename_active_note", "es")
    assert risk_scenario_dropdown.placeholder == "Selecciona un escenario completado"
    assert risk_candidate_dropdown.placeholder == "Selecciona un diseño factible"


def test_project_toolbar_uses_two_row_grid_and_includes_delete_project() -> None:
    sidebar = scenario_sidebar()
    action_grid = _find_component_with_class(sidebar, "project-action-grid")

    assert action_grid is not None
    assert [child.id for child in action_grid.children] == [
        "save-project-btn",
        "open-project-btn",
        "save-project-as-btn",
        "delete-project-btn",
    ]
    assert all("project-action-btn" in str(getattr(child, "className", "")) for child in action_grid.children)


def test_workspace_shell_empty_state_surfaces_start_ctas_and_disables_irrelevant_actions(monkeypatch) -> None:
    monkeypatch.setattr("services.workspace_shared_callbacks.list_projects", lambda: [])
    payload = _session_payload(ScenarioSessionState.empty())

    outputs = populate_workspace_shell(payload, "es")

    assert outputs[4] == tr("workbench.project.empty_note", "es")
    assert outputs[5] == {"display": "block"}
    assert outputs[7] is True
    assert outputs[8] is True
    assert outputs[9] is True
    assert outputs[10] == {"display": "none"}
    assert outputs[12] == tr("workbench.sidebar.start.copy", "es")
    assert outputs[13] == {"display": "grid"}
    assert outputs[14] == tr("workbench.no_active_scenario", "es")
    assert outputs[15] == {"display": "block"}


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
    assert weight_columns[0]["name"] == "Peso residencial"
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


def test_catalog_editor_stacks_inverter_then_battery_tables() -> None:
    section = catalog_editor_section()
    stack = section.children[1]
    first_panel, second_panel, third_panel = stack.children

    assert "catalog-stack" in str(getattr(stack, "className", "")).split()
    assert len(stack.children) == 3
    assert _find_component(first_panel, "inverter-editor-title") is not None
    assert _find_component(first_panel, "inverter-table-editor") is not None
    assert _find_component(first_panel, "battery-table-editor") is None
    assert _find_component(second_panel, "battery-editor-title") is not None
    assert _find_component(second_panel, "battery-table-editor") is not None
    assert _find_component(second_panel, "inverter-table-editor") is None
    assert _find_component(third_panel, "panel-editor-title") is not None
    assert _find_component(third_panel, "panel-table-editor") is not None
    assert _find_component(third_panel, "battery-table-editor") is None


def test_profile_editor_uses_main_row_layout_title_tooltips_and_only_resource_profile_controls() -> None:
    section = profile_editor_section()
    main_grid = _find_component(section, "profile-main-grid")
    main_chart = _find_component(section, "profile-main-chart-panel")
    activators = _find_components(
        section,
        lambda node: isinstance(getattr(node, "id", None), dict) and node.id.get("type") == "profile-table-activate",
    )

    assert main_grid is not None
    assert main_chart is not None
    assert _find_component(section, "profile-secondary-grid") is None
    assert _find_component(section, "profile-secondary-chart-panel") is None
    assert _find_component(section, "profile-demand-relocated-card") is None
    assert _find_component(section, "profile-demand-legacy-shell") is None
    assert _find_component(workbench_page.layout, "active-profile-table-state") is not None
    assert len(main_grid.children) == 2
    assert [getattr(child, "id", None) for child in section.children[2:4]] == [
        "profile-main-grid",
        "profile-main-chart-panel",
    ]
    assert len(activators) == 2
    assert {component.id["table"] for component in activators} == {
        "month-profile-editor",
        "sun-profile-editor",
    }
    assert _find_component(section, "month-profile-card") is not None
    assert _find_component(section, "sun-profile-card") is not None
    assert _find_component(section, "price-kwp-card") is None
    assert _find_component(section, "price-kwp-others-card") is None
    assert _find_component(main_grid, "demand-profile-weights-card") is None
    assert _find_component(main_grid.children[0], "month-profile-title").children == tr("workbench.profiles.month", "es")
    assert _find_component(main_grid.children[1], "sun-profile-title").children == tr("workbench.profiles.sun", "es")
    assert _find_component(section, "month-profile-editor").page_size == 12
    assert _find_component(section, "sun-profile-editor").page_size == 12
    assert _find_component(section, "month-profile-editor").row_deletable is False
    assert _find_component(section, "month-profile-tooltip").children == tr("workbench.profiles.tooltip.month", "es")
    assert _find_component(section, "sun-profile-tooltip").children == tr("workbench.profiles.tooltip.sun", "es")
    assert _find_component(workbench_page.layout, "run-scan-choice-dialog") is not None
    assert _find_component(workbench_page.layout, "run-scan-save-and-run-btn") is not None
    assert _find_component(workbench_page.layout, "run-scan-run-unsaved-btn") is not None
    assert _find_component(workbench_page.layout, "run-scan-cancel-btn") is not None


def test_workbench_results_sections_are_split_by_stable_wrapper_ids() -> None:
    section = candidate_explorer_section()
    assert section.id == "candidate-selection-section"
    assert _find_component(section, "scan-summary-strip") is not None
    assert _find_component(section, "scan-discard-explainer") is not None
    assert _find_component(section, "active-kpi-cards") is not None
    assert _find_component(section, "candidate-horizon-toolbar") is not None
    assert _find_component(section, "candidate-horizon-slider") is not None
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
    assert _find_component(section, "candidate-horizon-label").children == tr("workbench.horizon.label", "es")
    assert _find_component(section, "candidate-selection-helper").children == tr("workbench.candidate_selection.helper", "es")

    styles = workbench_page._candidate_table_styles("18.000::BAT-10", "12.000::None")
    assert styles[-1]["if"]["filter_query"] == '{candidate_key} = "18.000::BAT-10"'
    assert styles[-1]["backgroundColor"] == "#fee2e2"


def test_candidate_horizon_slider_defaults_to_scan_horizon_and_preserves_current_value() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    payload = _session_payload(state)

    minimum, maximum, marks, value, disabled, style, value_label, context = workbench_page.sync_candidate_horizon_slider(payload, "es", None, {})

    assert minimum == 0
    assert maximum == 5
    assert marks[0] == "0"
    assert marks[1] == "1"
    assert value == 5
    assert disabled is False
    assert style == {}
    assert value_label == "5 años"
    assert context["scenario_id"] == state.active_scenario_id

    preserved = workbench_page.sync_candidate_horizon_slider(payload, "es", 3, context)
    assert preserved[3] == 3
    assert preserved[6] == "3 años"


def test_candidate_horizon_slider_hides_cleanly_without_results() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state)

    minimum, maximum, marks, value, disabled, style, value_label, context = workbench_page.sync_candidate_horizon_slider(payload, "es", None, {})

    assert minimum == 0
    assert maximum == 0
    assert marks == {0: "0"}
    assert value == 0
    assert disabled is True
    assert style == {"display": "none"}
    assert value_label == ""
    assert context == {}


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

    _value_updates, disabled_values, card_classes, note_children, note_styles = workbench_page.sync_assumption_context_ui(
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

    _value_updates, disabled_values, card_classes, note_children, note_styles = workbench_page.sync_assumption_context_ui(
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


def test_workbench_assumption_context_callback_refreshes_visible_panel_values_for_selected_catalog_panel() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state, lang="es")
    field_values = {
        "panel_name": "PREM-620 Premium",
        "P_mod_W": 600.0,
        "Voc25": 50.0,
        "Vmp25": 41.0,
        "Isc": 14.0,
        "panel_technology_mode": "standard",
    }
    input_ids = [{"type": "assumption-input", "field": field} for field in field_values]
    card_ids = [{"type": "assumption-field-card", "field": field} for field in field_values]
    note_ids = [{"type": "assumption-context-note", "group": "Sol y módulos"}]

    value_updates, disabled_values, _card_classes, note_children, note_styles = workbench_page.sync_assumption_context_ui(
        payload,
        input_ids,
        list(field_values.values()),
        "es",
        card_ids,
        note_ids,
    )

    updated_by_field = dict(zip(field_values.keys(), value_updates))
    disabled_by_field = dict(zip(field_values.keys(), disabled_values))

    assert updated_by_field["panel_name"] == "PREM-620 Premium"
    assert updated_by_field["P_mod_W"] == pytest.approx(620.0)
    assert updated_by_field["Voc25"] == pytest.approx(52.0)
    assert updated_by_field["Vmp25"] == pytest.approx(43.0)
    assert updated_by_field["Isc"] == pytest.approx(14.4)
    assert updated_by_field["panel_technology_mode"] == "premium"
    assert disabled_by_field["P_mod_W"] is True
    assert disabled_by_field["Voc25"] is True
    assert disabled_by_field["Vmp25"] is True
    assert disabled_by_field["Isc"] is True
    assert disabled_by_field["panel_technology_mode"] is True
    assert "modelo seleccionado" in note_children[0].lower()
    assert note_styles == [{"display": "block"}]


def test_workbench_assumption_context_callback_returns_wildcard_no_update_list_when_values_do_not_change() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state, lang="es")
    field_values = {
        "panel_name": "__manual__",
        "P_mod_W": 600.0,
        "Voc25": 50.0,
    }
    input_ids = [{"type": "assumption-input", "field": field} for field in field_values]
    card_ids = [{"type": "assumption-field-card", "field": field} for field in field_values]
    note_ids = [{"type": "assumption-context-note", "group": "Sol y módulos"}]

    value_updates, _disabled_values, _card_classes, _note_children, _note_styles = workbench_page.sync_assumption_context_ui(
        payload,
        input_ids,
        list(field_values.values()),
        "es",
        card_ids,
        note_ids,
    )

    assert len(value_updates) == len(input_ids)
    assert all(item is no_update for item in value_updates)


def test_populate_assumptions_keeps_monte_carlo_out_of_client_safe_general_assumptions() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = _session_payload(state, lang="es")

    rendered = workbench_page.populate_assumptions(payload, [], "es")

    rendered_payload = " ".join(str(section.to_plotly_json()) for section in rendered)
    assert "Sol y módulos" in rendered_payload
    assert "Monte Carlo" not in rendered_payload


def test_risk_monte_carlo_context_callback_enables_manual_kwp_only_when_requested() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None

    payload = _session_payload(state, lang="en")
    field_values = {
        "mc_PR_std": 5.0,
        "mc_buy_std": 4.0,
        "mc_sell_std": 3.0,
        "mc_demand_std": 2.0,
        "mc_use_manual_kWp": True,
        "mc_manual_kWp": 16.5,
        "mc_battery_name": "BAT-10",
    }
    input_ids = [{"type": "risk-mc-input", "field": field} for field in field_values]
    card_ids = [{"type": "risk-mc-field-card", "field": field} for field in field_values]

    disabled_values, card_classes = risk_page.sync_risk_monte_carlo_context(
        payload,
        scenario.scenario_id,
        input_ids,
        list(field_values.values()),
        "en",
        card_ids,
    )

    disabled_by_field = dict(zip(field_values.keys(), disabled_values))
    class_by_field = dict(zip(field_values.keys(), card_classes))

    assert disabled_by_field["mc_manual_kWp"] is False
    assert "field-card-disabled" not in class_by_field["mc_manual_kWp"]


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
    assert ".assumption-editor-panel" in css_source
    assert "--assumption-control-height" in css_source
    assert ".assumption-editor-panel .Select-control" in css_source
    assert ".candidate-selection-helper" in css_source
    assert ".candidate-horizon-toolbar" in css_source
    assert ":root {" in css_source
    assert "--color-primary" in css_source
    assert "--color-primary-soft" in css_source
    assert "body {" in css_source
    assert ".active-summary-copy" in css_source
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css_source
    assert ".active-summary-top" in css_source
    assert ".active-summary-actions" in css_source
    assert ".nav-link-active" in css_source
    assert ".sidebar-start-card" in css_source
    assert ".upload-box-action" in css_source
    assert ".project-action-grid" in css_source
    assert ".stacked-button-label" in css_source
    assert ".profile-main-grid" in css_source
    assert "minmax(0, 1.35fr)" in css_source
    assert ".profile-secondary-grid" in css_source
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css_source
    assert ".profile-secondary-pricing-panel" in css_source
    assert ".profile-inline-btn" in css_source
    assert ".profile-table-activator" in css_source
    assert ".profile-chart-panel" in css_source
    assert ".profile-table-card-active" in css_source
    assert ".demand-profile-mode-panel" in css_source
    assert ".demand-profile-control-grid" in css_source
    assert ".demand-profile-mode-option-label" in css_source
    assert ".demand-profile-secondary-grid" in css_source
    assert ".demand-profile-module .profile-table-card-shell" in css_source
    assert "height: 380px !important;" in css_source
    assert "min-height: 380px;" in css_source
    assert ".profile-table-subsection" in css_source
    assert ".assumptions-subtabs" in css_source
    assert ".assumptions-subtab-selected" in css_source
    assert ".demand-relocated-card" in css_source
    assert ".workbench-state-strip" in css_source
    assert ".workbench-state-chip" in css_source
    assert ".page-admin" in css_source
    assert ".workbench-grid-admin" in css_source
    assert ".admin-auxiliary-details" in css_source
    assert ".economics-preview-status-strip" in css_source
    assert ".economics-candidate-identity-strip" in css_source
    assert ".economics-preview-advanced-details" in css_source
    assert ".economics-breakdown-advanced-details" in css_source
    assert ".economics-editors-shell-gated" in css_source
    assert ".economics-table-wrap" in css_source


def test_workspace_frame_accepts_admin_specific_layout_hooks() -> None:
    frame = workspace_frame(
        page_class_name="page-admin",
        grid_class_name="workbench-grid-admin",
        children=[],
    )
    grid = _find_component_with_class(frame, "workbench-grid-admin")

    assert "page-admin" in str(frame.className).split()
    assert grid is not None


def test_delete_project_button_removes_selected_project_and_unbinds_current_session(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("services.runtime_paths.REPO_ROOT", tmp_path)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = save_project(state, project_name="Demo", language="es")
    payload = _session_payload(state)

    monkeypatch.setattr(shared_callbacks, "ctx", SimpleNamespace(triggered_id="delete-project-btn"))

    next_payload, status = shared_callbacks.mutate_workspace_session(
        upload_contents=None,
        _new_scenario_clicks=0,
        _duplicate_clicks=0,
        _rename_clicks=0,
        _delete_clicks=0,
        _scenario_pill_clicks=[],
        _save_project_clicks=0,
        _save_project_as_clicks=0,
        _open_project_clicks=0,
        _delete_project_clicks=1,
        upload_filename=None,
        rename_value=None,
        project_name_value="Demo",
        project_dropdown_value=state.project_slug,
        session_payload=payload,
        language_value="es",
    )
    _, next_state = shared_callbacks._session(next_payload, "es")

    assert not Path(tmp_path / "proyectos" / "demo").exists()
    assert status == tr("workbench.project.deleted", "es", name="Demo")
    assert next_state.project_slug is None
    assert next_state.project_name is None
    assert next_state.project_dirty is True


def test_profile_visibility_and_bundle_rebuild_round_trip() -> None:
    bundle = _fast_bundle()
    visibility = demand_profile_visibility("perfil horario relativo")
    assert visibility["demand-profile-weights-panel"]["display"] == "block"
    assert visibility["demand-profile-panel"]["display"] == "none"
    assert visibility["demand-profile-general-preview-panel"]["display"] == "none"

    weekday_visibility = demand_profile_visibility("perfil hora dia de semana")
    assert weekday_visibility["demand-profile-panel"]["display"] == "block"
    assert weekday_visibility["demand-profile-general-preview-panel"]["display"] == "block"

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
    assert workbench_page.translate_profile_table_activators("en") == ["Preview chart"] * 2
    assert workbench_page.translate_profile_table_activators("es") == ["Ver gráfica"] * 2


def test_profile_table_header_click_toggles_the_active_chart(monkeypatch) -> None:
    monkeypatch.setattr(
        workbench_page,
        "ctx",
        SimpleNamespace(triggered_id={"type": "profile-table-activate", "table": "sun-profile-editor"}),
    )

    clicks = [0, 1]
    activated = workbench_page.sync_active_profile_table(clicks, None, None, {"table_id": None})
    cleared = workbench_page.sync_active_profile_table(clicks, None, None, {"table_id": "sun-profile-editor"})

    assert activated == {"table_id": "sun-profile-editor"}
    assert cleared == {"table_id": None}


def test_profile_table_header_mount_with_zero_clicks_does_not_auto_activate(monkeypatch) -> None:
    monkeypatch.setattr(
        workbench_page,
        "ctx",
        SimpleNamespace(triggered_id={"type": "profile-table-activate", "table": "month-profile-editor"}),
    )

    with pytest.raises(PreventUpdate):
        workbench_page.sync_active_profile_table([0, 0], None, None, {"table_id": None})


def test_profile_table_active_cell_activates_without_toggling_off(monkeypatch) -> None:
    monkeypatch.setattr(workbench_page, "ctx", SimpleNamespace(triggered_id="sun-profile-editor"))

    activated = workbench_page.sync_active_profile_table(
        [],
        None,
        {"row": 2, "column": 1},
        {"table_id": None},
    )

    assert activated == {"table_id": "sun-profile-editor"}

    with pytest.raises(PreventUpdate):
        workbench_page.sync_active_profile_table(
            [],
            None,
            {"row": 2, "column": 1},
            {"table_id": "sun-profile-editor"},
        )


def test_profile_chart_render_marks_one_active_resource_card() -> None:
    bundle = load_example_config()
    month_columns, _ = build_table_display_columns("month_profile", list(bundle.month_profile_table.columns), "en")
    sun_columns, _ = build_table_display_columns("sun_profile", list(bundle.sun_profile_table.columns), "en")

    main = workbench_page.render_active_profile_chart(
        {"table_id": "sun-profile-editor"},
        bundle.month_profile_table.to_dict("records"),
        month_columns,
        bundle.sun_profile_table.to_dict("records"),
        sun_columns,
        "en",
    )

    assert main[0]["display"] == "grid"
    assert main[1] == tr("workbench.profiles.sun", "en")
    assert sum("profile-table-card-active" in class_name for class_name in main[4:]) == 1


def test_inactive_profile_chart_hides_chart_shell_and_active_classes() -> None:
    bundle = load_example_config()
    month_columns, _ = build_table_display_columns("month_profile", list(bundle.month_profile_table.columns), "es")
    sun_columns, _ = build_table_display_columns("sun_profile", list(bundle.sun_profile_table.columns), "es")

    rendered = workbench_page.render_active_profile_chart(
        {"table_id": None},
        bundle.month_profile_table.to_dict("records"),
        month_columns,
        bundle.sun_profile_table.to_dict("records"),
        sun_columns,
        "es",
    )

    assert rendered[0]["display"] == "none"
    assert all("profile-table-card-active" not in class_name for class_name in rendered[4:])


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
    assert figure.layout.yaxis.title.text == "VPN [COP]"
    assert figure.layout.yaxis2.title.text == "Payback [años]"
    assert list(figure.layout.xaxis2.ticktext) == ["20", "30"]
    assert list(figure.layout.xaxis2.tickvals) == pytest.approx([12.0, 18.0])
    assert list(figure.data[0].customdata[0][:2]) == ["12.000::None", 20]
    assert any(trace.name == "Payback [años]" for trace in figure.data)
    assert any(trace.name == "Diseño seleccionado" for trace in figure.data)


def test_npv_chart_switches_to_project_price_axis_for_year_zero() -> None:
    table = pd.DataFrame(
        [
            {
                "candidate_key": "12.000::None",
                "kWp": 12.0,
                "battery": "None",
                "NPV_COP": 58_000_000,
                "payback_years": 5.5,
                "self_consumption_ratio": 0.45,
                "peak_ratio": 1.1,
                "scan_order": 0,
            },
            {
                "candidate_key": "18.000::BAT-10",
                "kWp": 18.0,
                "battery": "BAT-10",
                "NPV_COP": 72_000_000,
                "payback_years": 6.2,
                "self_consumption_ratio": 0.52,
                "peak_ratio": 1.25,
                "scan_order": 1,
            },
        ]
    )

    figure = build_npv_figure(
        table,
        selected_key="18.000::BAT-10",
        lang="es",
        horizon_years=0,
        display_metric_key="capex_client",
        module_power_w=600.0,
    )

    assert figure.layout.title.text.endswith("Horizonte financiero: 0 años</sup>")
    assert figure.layout.yaxis.title.text == tr("workbench.project_price.axis_label", "es")
    assert figure.layout.yaxis2.title.text == "Payback [años]"
    assert any(tr("workbench.project_price.axis_label", "es") in hover for hover in figure.data[0].hovertext)


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


def test_npv_chart_renders_discard_strip_without_fabricating_npv() -> None:
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

    figure = build_npv_figure(
        table,
        selected_key="18.000::BAT-10",
        lang="es",
        module_power_w=600.0,
        discarded_points=(
            {"scan_order": 2, "kWp": 24.0, "reason": "peak_ratio", "peak_ratio": 1.8, "limit_peak_ratio": 1.5},
            {"scan_order": 3, "kWp": 30.0, "reason": "inverter_string"},
        ),
    )

    assert figure.layout.xaxis3.title.text == "Número de paneles"
    assert figure.layout.yaxis.title.text == "VPN [COP]"
    assert figure.layout.yaxis2.title.text == "Payback [años]"
    assert figure.layout.yaxis3.showticklabels is False
    assert any(trace.name == "Diseño seleccionado" for trace in figure.data)
    assert any(trace.name == "Payback [años]" for trace in figure.data)
    discard_traces = [trace for trace in figure.data if trace.name in {"excede el límite de peak ratio", "no se encontró una combinación válida de inversor/string"}]
    assert len(discard_traces) == 2
    assert all(all(value == 0.5 for value in trace.y) for trace in discard_traces)
    assert any("Descartado" in trace.hovertemplate[0] for trace in discard_traces if isinstance(trace.hovertemplate, (list, tuple)))


def test_workbench_results_explain_all_discarded_scan() -> None:
    bundle = replace(
        _fast_bundle(),
        config={**_fast_bundle().config, "limit_peak_ratio_enable": True, "limit_peak_ratio": 0.01},
    )
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", bundle))
    state = run_scenario_scan(state, state.active_scenario_id)
    payload = _session_payload(state)

    (
        summary_strip,
        explainer,
        explainer_style,
        kpis,
        npv_figure,
        _banner,
        monthly_figure,
        _cash_flow,
        _annual,
        _battery,
        _typical_day,
        table_rows,
        _columns,
        selected_rows,
        _styles,
        _tooltips,
    ) = workbench_page.populate_results(payload, "es", 1)

    assert len(summary_strip) == 6
    assert "restricción dominante actual" in explainer
    assert explainer_style["display"] == "block"
    assert kpis == []
    assert table_rows == []
    assert selected_rows == []
    assert monthly_figure.layout.annotations[0].text == tr("workbench.scan_discard.no_viable_detail", "es")
    assert npv_figure.data


def test_populate_results_uses_horizon_adjusted_summary_without_losing_selection() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None
    non_best_key = next(key for key in scenario.scan_result.candidate_details if key != scenario.scan_result.best_candidate_key)
    state = update_selected_candidate(state, scenario.scenario_id, non_best_key)
    payload = _session_payload(state)

    short_horizon = workbench_page.populate_results(payload, "es", 1)
    full_horizon = workbench_page.populate_results(payload, "es", 5)

    short_table_rows = short_horizon[11]
    short_selected_rows = short_horizon[13]
    full_table_rows = full_horizon[11]
    full_selected_rows = full_horizon[13]

    assert short_selected_rows
    assert full_selected_rows
    assert short_table_rows[short_selected_rows[0]]["candidate_key"] == non_best_key
    assert full_table_rows[full_selected_rows[0]]["candidate_key"] == non_best_key
    assert short_horizon[4].layout.title.text.endswith("Horizonte financiero: 1 año</sup>")
    assert full_horizon[4].layout.title.text.endswith("Horizonte financiero: 5 años</sup>")

    short_row = next(row for row in short_table_rows if row["candidate_key"] == non_best_key)
    full_row = next(row for row in full_table_rows if row["candidate_key"] == non_best_key)
    assert short_row["NPV_COP"] != full_row["NPV_COP"]


def test_populate_results_year_zero_shows_project_price_in_main_ui() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    payload = _session_payload(state)

    year_zero = workbench_page.populate_results(payload, "es", 0)
    table_rows = year_zero[11]
    selected_rows = year_zero[13]
    selected_row = table_rows[selected_rows[0]]
    columns = year_zero[12]
    active = state.get_scenario()
    selected_snapshot = build_candidate_financial_snapshot(active, selected_row["candidate_key"])

    assert year_zero[4].layout.title.text.endswith("Horizonte financiero: 0 años</sup>")
    assert year_zero[4].layout.yaxis.title.text == tr("workbench.project_price.axis_label", "es")
    assert next(column["name"] for column in columns if column["id"] == "NPV_COP") == tr("workbench.project_price.axis_label", "es")
    assert all(column["id"] != "capex_client" for column in columns)
    assert selected_row["NPV_COP"] == pytest.approx(float(selected_snapshot.project_price_year0_COP))
    assert tr("workbench.project_price.label", "es") in str(year_zero[5][3].to_plotly_json())
    assert tr("workbench.project_price.axis_label", "es") in str(year_zero[3][2].to_plotly_json())


def test_populate_results_year_zero_selected_overlay_uses_selected_candidate_snapshot_not_curve_best() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None

    initial_outputs = workbench_page.populate_results(_session_payload(state), "es", 0)
    year_zero_table = pd.DataFrame(initial_outputs[11])
    same_kwp_rows = next(
        group
        for _, group in year_zero_table.groupby("kWp", sort=True)
        if len(group.index) >= 2
        and group["candidate_key"].map(
            lambda candidate_key: build_candidate_financial_snapshot(scenario, str(candidate_key)).project_price_year0_COP
        ).nunique()
        >= 2
    )
    ordered_rows = same_kwp_rows.sort_values(["NPV_COP", "scan_order"], ascending=[True, True], kind="mergesort").reset_index(drop=True)
    curve_key = str(ordered_rows.iloc[0]["candidate_key"])
    selected_overlay_key = str(ordered_rows.iloc[1]["candidate_key"])
    assert curve_key != selected_overlay_key

    state = update_selected_candidate(state, scenario.scenario_id, selected_overlay_key)
    active = state.get_scenario()
    assert active is not None
    outputs = workbench_page.populate_results(_session_payload(state), "es", 0)
    npv_figure = outputs[4]
    selected_trace = next(trace for trace in npv_figure.data if list(trace.customdata[0])[2] == "selected_overlay")
    curve_trace = next(trace for trace in npv_figure.data if list(trace.customdata[0])[2] == "npv_curve")
    curve_index = next(index for index, point in enumerate(curve_trace.customdata) if list(point)[0] == curve_key)
    selected_snapshot = build_candidate_financial_snapshot(active, selected_overlay_key)
    curve_snapshot = build_candidate_financial_snapshot(active, curve_key)

    assert list(selected_trace.customdata[0])[0] == selected_overlay_key
    assert float(selected_trace.y[0]) == pytest.approx(selected_snapshot.project_price_year0_COP)
    assert float(curve_trace.y[curve_index]) == pytest.approx(curve_snapshot.project_price_year0_COP)
    assert float(selected_trace.y[0]) != pytest.approx(float(curve_trace.y[curve_index]))


def test_populate_results_ignores_poisoned_legacy_finance_fields() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None
    candidate_key = scenario.selected_candidate_key or scenario.scan_result.best_candidate_key
    assert candidate_key is not None
    snapshot = build_candidate_financial_snapshot(scenario, candidate_key)
    detail = scenario.scan_result.candidate_details[candidate_key]
    detail["summary"]["capex_client"] = -111.0
    detail["summary"]["cum_disc_final"] = -222.0
    detail["summary"]["payback_month"] = 999
    detail["summary"]["payback_years"] = 83.25
    detail["monthly"]["NPV_COP"] = [-333.0] * len(detail["monthly"])
    payload = _session_payload(state)

    year_zero = workbench_page.populate_results(payload, "es", 0)
    full_horizon = workbench_page.populate_results(payload, "es", 5)

    year_zero_rows = year_zero[11]
    year_zero_selected = year_zero_rows[year_zero[13][0]]
    full_rows = full_horizon[11]
    full_selected = full_rows[full_horizon[13][0]]
    cash_flow_figure = full_horizon[7]

    assert year_zero_selected["candidate_key"] == candidate_key
    assert year_zero_selected["NPV_COP"] == pytest.approx(snapshot.project_price_year0_COP)
    assert full_selected["candidate_key"] == candidate_key
    assert full_selected["NPV_COP"] == pytest.approx(snapshot.visible_npv_COP)
    assert full_selected["payback_years"] == snapshot.payback_years
    assert list(cash_flow_figure.data[0].y) == list(snapshot.cumulative_discounted_cash_flow_series)


def test_populate_results_fails_closed_when_snapshot_attachment_is_missing(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    payload = _session_payload(state)

    def _raw_detail_map(active):
        assert active.scan_result is not None
        return active.scan_result.candidate_details

    monkeypatch.setattr(results_callbacks, "attach_candidate_financial_snapshots", _raw_detail_map)

    with pytest.raises(CandidateFinancialSnapshotUnavailableError, match="CandidateFinancialSnapshot"):
        workbench_page.populate_results(payload, "es", 5)


def test_populate_results_fails_closed_when_snapshot_attachment_builder_errors(monkeypatch) -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    payload = _session_payload(state)

    def _boom(_active):
        raise CandidateFinancialSnapshotUnavailableError("fallo forzado del snapshot")

    monkeypatch.setattr(results_callbacks, "attach_candidate_financial_snapshots", _boom)

    with pytest.raises(CandidateFinancialSnapshotUnavailableError, match="fallo forzado"):
        workbench_page.populate_results(payload, "es", 5)


def test_graph_click_selection_updates_store_table_and_selected_marker() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None

    initial_outputs = workbench_page.populate_results(_session_payload(state), "es", 5)
    horizon_table = pd.DataFrame(initial_outputs[11])
    same_kwp_rows = next(
        group
        for _, group in horizon_table.groupby("kWp", sort=True)
        if len(group.index) >= 2
    )
    ordered_rows = same_kwp_rows.sort_values(["NPV_COP", "scan_order"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    curve_key = str(ordered_rows.iloc[0]["candidate_key"])
    selected_overlay_key = str(ordered_rows.iloc[1]["candidate_key"])
    assert curve_key != selected_overlay_key

    state = update_selected_candidate(state, scenario.scenario_id, selected_overlay_key)
    payload = _session_payload(state)
    table_rows = workbench_page.populate_results(payload, "es", 5)[11]

    next_payload = results_callbacks.persist_selected_candidate(
        [],
        {
            "points": [
                {"customdata": [selected_overlay_key, None, "selected_overlay"]},
                {"customdata": [curve_key, None, "npv_curve"]},
            ]
        },
        table_rows,
        payload,
    )

    _, next_state = resolve_client_session(next_payload, language="es")
    active = next_state.get_scenario()
    assert active is not None
    assert active.selected_candidate_key == curve_key
    expected_bridge = prepare_economics_runtime_price_bridge(active)
    assert expected_bridge.applied is True
    assert active.runtime_price_bridge is None
    assert resolve_runtime_price_bridge_state(active) == "none"
    assert active.config_bundle.config["pricing_mode"] == scenario.config_bundle.config["pricing_mode"]
    assert float(active.config_bundle.config["price_total_COP"]) == pytest.approx(float(scenario.config_bundle.config["price_total_COP"]))
    assert active.config_bundle.config["include_hw_in_price"] == scenario.config_bundle.config["include_hw_in_price"]
    assert float(active.config_bundle.config["price_others_total"]) == pytest.approx(float(scenario.config_bundle.config["price_others_total"]))

    outputs = workbench_page.populate_results(next_payload, "es", 5)
    table_rows = outputs[11]
    selected_rows = outputs[13]
    npv_figure = outputs[4]

    assert selected_rows
    assert table_rows[selected_rows[0]]["candidate_key"] == curve_key
    selected_trace = next(trace for trace in npv_figure.data if trace.name == "Diseño seleccionado")
    assert list(selected_trace.customdata[0])[0] == curve_key
    assert selected_trace.marker.color == "#dc2626"


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
