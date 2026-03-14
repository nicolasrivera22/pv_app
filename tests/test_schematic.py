from __future__ import annotations

import importlib
from dataclasses import replace

import pandas as pd
import pytest

from app import create_app
from components.unifilar_diagram import CYTOSCAPE_STYLESHEET, unifilar_diagram_section
from services import (
    LoadedConfigBundle,
    ScanRunResult,
    ScenarioRecord,
    build_schematic_legend,
    build_unifilar_model,
    default_schematic_inspector,
    infer_string_layout,
    load_example_config,
    resolve_schematic_focus,
    resolve_schematic_inspector,
    resolve_schematic_icon_url,
    to_cytoscape_elements,
)
from services.schematic import MIN_VERTICAL_GAP, NODE_HEIGHT, VERTICAL_MARGIN


def _base_bundle(**config_updates) -> LoadedConfigBundle:
    bundle = load_example_config()
    return replace(bundle, config={**bundle.config, **config_updates})


def _detail(
    *,
    candidate_key: str,
    k_wp: float,
    n_mod: int,
    ns: int,
    np_: int,
    inverter: dict,
    battery: dict | None = None,
    battery_name: str = "None",
) -> dict:
    return {
        "scan_order": 0,
        "candidate_key": candidate_key,
        "kWp": k_wp,
        "battery_name": battery_name,
        "battery": battery or {"name": "BAT-0", "nom_kWh": 0.0, "max_kW": 0.0, "max_ch_kW": 0.0, "max_dis_kW": 0.0, "price_COP": 0.0},
        "inv_sel": {"N_mod": n_mod, "Ns": ns, "Np": np_, "inverter": inverter, "checks": {}},
        "summary": {},
        "value": 0.0,
        "peak_ratio": 1.0,
        "best_battery": True,
        "monthly": pd.DataFrame(),
        "self_consumption_ratio": 0.0,
        "self_sufficiency_ratio": 0.0,
    }


def _scenario(bundle: LoadedConfigBundle, details: dict[str, dict], best_key: str) -> ScenarioRecord:
    scan = ScanRunResult(
        candidates=pd.DataFrame(
            {
                "candidate_key": list(details.keys()),
                "kWp": [detail["kWp"] for detail in details.values()],
                "battery": [detail["battery_name"] for detail in details.values()],
            }
        ),
        best_candidate_key=best_key,
        candidate_details=details,
        seed_kwp=best_key and float(details[best_key]["kWp"]),
    )
    return ScenarioRecord(
        scenario_id="scenario-test",
        name="Prueba",
        source_name="PV_inputs.xlsx",
        config_bundle=bundle,
        scan_result=scan,
        selected_candidate_key=best_key,
        dirty=False,
        last_run_at="2026-03-13T12:00:00",
    )


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


def _node(model, node_id: str):
    return next(node for node in model.nodes if node.id == node_id)


def test_unifilar_model_builds_required_core_nodes_without_battery() -> None:
    bundle = _base_bundle()
    inverter = {"name": "INV-10", "AC_kW": 10.0, "Vmppt_min": 150.0, "Vmppt_max": 800.0, "Vdc_max": 1000.0, "Imax_mppt": 20.0, "n_mppt": 2}
    detail = _detail(candidate_key="12.000::None", k_wp=12.0, n_mod=24, ns=12, np_=2, inverter=inverter)
    scenario = _scenario(bundle, {"12.000::None": detail}, "12.000::None")

    model = build_unifilar_model(scenario, "12.000::None", lang="es")
    roles = {node.role for node in model.nodes}
    edge_pairs = {(edge.source, edge.target, edge.label) for edge in model.edges}
    pv_node = next(node for node in model.nodes if node.role == "pv")

    assert roles == {"pv", "inverter", "load", "grid"}
    assert ("inverter", "load", "AC") in edge_pairs
    assert ("grid", "load", "AC") in edge_pairs
    assert ("pv-1", "inverter", "DC") in edge_pairs
    assert model.string_summary.startswith("Arreglo FV:")
    assert pv_node.metadata["component_kind"] == "pv"
    assert pv_node.metadata["title"].startswith("FV · MPPT")
    assert "[FV]" not in pv_node.display_label
    assert pv_node.display_label.startswith("MPPT 1")
    assert pv_node.metadata["details"]


def test_battery_node_is_conditional_and_respects_coupling_target() -> None:
    inverter = {"name": "INV-10", "AC_kW": 10.0, "Vmppt_min": 150.0, "Vmppt_max": 800.0, "Vdc_max": 1000.0, "Imax_mppt": 20.0, "n_mppt": 2}
    battery = {"name": "BAT-10", "nom_kWh": 10.0, "max_kW": 5.0, "max_ch_kW": 5.0, "max_dis_kW": 5.0, "price_COP": 1_000_000}
    detail = _detail(candidate_key="12.000::BAT-10", k_wp=12.0, n_mod=24, ns=12, np_=2, inverter=inverter, battery=battery, battery_name="BAT-10")

    ac_scenario = _scenario(_base_bundle(bat_coupling="ac"), {"12.000::BAT-10": detail}, "12.000::BAT-10")
    dc_scenario = _scenario(_base_bundle(bat_coupling="dc"), {"12.000::BAT-10": detail}, "12.000::BAT-10")

    ac_model = build_unifilar_model(ac_scenario, "12.000::BAT-10", lang="es")
    dc_model = build_unifilar_model(dc_scenario, "12.000::BAT-10", lang="es")

    assert any(node.role == "battery" for node in ac_model.nodes)
    assert any(edge.source == "battery" and edge.target == "load" and edge.label == "AC" for edge in ac_model.edges)
    assert any(edge.source == "battery" and edge.target == "inverter" and edge.label == "DC" for edge in dc_model.edges)


def test_unifilar_layout_uses_even_horizontal_spacing_and_full_vertical_distribution() -> None:
    bundle = _base_bundle()
    inverter = {"name": "INV-15", "AC_kW": 15.0, "Vmppt_min": 200.0, "Vmppt_max": 850.0, "Vdc_max": 1000.0, "Imax_mppt": 26.0, "n_mppt": 3}
    detail = _detail(candidate_key="18.000::None", k_wp=18.0, n_mod=36, ns=12, np_=3, inverter=inverter)
    scenario = _scenario(bundle, {"18.000::None": detail}, "18.000::None")

    model = build_unifilar_model(scenario, "18.000::None", lang="es")
    pv_nodes = sorted((node for node in model.nodes if node.role == "pv"), key=lambda node: node.id)
    inverter_node = _node(model, "inverter")
    load_node = _node(model, "load")
    grid_node = _node(model, "grid")

    deltas = [
        inverter_node.position["x"] - pv_nodes[0].position["x"],
        load_node.position["x"] - inverter_node.position["x"],
        grid_node.position["x"] - load_node.position["x"],
    ]
    assert all(delta > 0 for delta in deltas)
    assert deltas[0] == pytest.approx(deltas[1])
    assert deltas[1] == pytest.approx(deltas[2])

    assert model.diagram_height == int(2 * VERTICAL_MARGIN + 3 * NODE_HEIGHT + 2 * MIN_VERTICAL_GAP)
    top_center = VERTICAL_MARGIN + NODE_HEIGHT / 2.0
    bottom_center = model.diagram_height - VERTICAL_MARGIN - NODE_HEIGHT / 2.0
    pv_ys = [node.position["y"] for node in pv_nodes]
    assert pv_ys[0] == pytest.approx(top_center)
    assert pv_ys[-1] == pytest.approx(bottom_center)
    assert pv_ys[1] - pv_ys[0] == pytest.approx(pv_ys[2] - pv_ys[1])
    assert pv_ys[1] - pv_ys[0] >= NODE_HEIGHT + MIN_VERTICAL_GAP


def test_battery_column_uses_same_vertical_spacing_rule_for_dc_and_ac_coupling() -> None:
    inverter = {"name": "INV-10", "AC_kW": 10.0, "Vmppt_min": 150.0, "Vmppt_max": 800.0, "Vdc_max": 1000.0, "Imax_mppt": 20.0, "n_mppt": 2}
    battery = {"name": "BAT-10", "nom_kWh": 10.0, "max_kW": 5.0, "max_ch_kW": 5.0, "max_dis_kW": 5.0, "price_COP": 1_000_000}
    detail = _detail(candidate_key="12.000::BAT-10", k_wp=12.0, n_mod=24, ns=12, np_=2, inverter=inverter, battery=battery, battery_name="BAT-10")

    ac_scenario = _scenario(_base_bundle(bat_coupling="ac"), {"12.000::BAT-10": detail}, "12.000::BAT-10")
    dc_scenario = _scenario(_base_bundle(bat_coupling="dc"), {"12.000::BAT-10": detail}, "12.000::BAT-10")

    ac_model = build_unifilar_model(ac_scenario, "12.000::BAT-10", lang="es")
    dc_model = build_unifilar_model(dc_scenario, "12.000::BAT-10", lang="es")
    expected_centers = [
        VERTICAL_MARGIN + NODE_HEIGHT / 2.0,
        ac_model.diagram_height - VERTICAL_MARGIN - NODE_HEIGHT / 2.0,
    ]

    ac_load = _node(ac_model, "load")
    ac_battery = _node(ac_model, "battery")
    assert ac_battery.position["x"] == pytest.approx(ac_load.position["x"])
    assert sorted([ac_load.position["y"], ac_battery.position["y"]]) == pytest.approx(expected_centers)

    dc_inverter = _node(dc_model, "inverter")
    dc_battery = _node(dc_model, "battery")
    assert dc_battery.position["x"] == pytest.approx(dc_inverter.position["x"])
    assert sorted([dc_inverter.position["y"], dc_battery.position["y"]]) == pytest.approx(expected_centers)


def test_exact_string_layout_distributes_evenly_across_mppts() -> None:
    bundle = _base_bundle()
    inverter = {"name": "INV-10", "AC_kW": 10.0, "Vmppt_min": 150.0, "Vmppt_max": 800.0, "Vdc_max": 1000.0, "Imax_mppt": 20.0, "n_mppt": 2}
    detail = _detail(candidate_key="12.000::None", k_wp=12.0, n_mod=24, ns=12, np_=2, inverter=inverter)

    layout = infer_string_layout(detail, bundle, lang="es")

    assert layout.exact is True
    assert len(layout.groups) == 2
    assert all(group.strings == 1 for group in layout.groups)
    assert all(group.modules_per_string == 12 for group in layout.groups)
    assert sum(group.total_modules for group in layout.groups) == 24


def test_representative_fallback_renders_without_prime_shortcut() -> None:
    bundle = _base_bundle()
    inverter = {"name": "INV-8", "AC_kW": 8.0, "Vmppt_min": 120.0, "Vmppt_max": 220.0, "Vdc_max": 300.0, "Imax_mppt": 20.0, "n_mppt": 2}
    detail = _detail(candidate_key="6.500::None", k_wp=6.5, n_mod=13, ns=6, np_=3, inverter=inverter)
    scenario = _scenario(bundle, {"6.500::None": detail}, "6.500::None")

    layout = infer_string_layout(detail, bundle, lang="es")
    model = build_unifilar_model(scenario, "6.500::None", lang="es")
    pv_node = next(node for node in model.nodes if node.role == "pv")

    assert layout.exact is False
    assert "representativo" in layout.summary_text.lower()
    assert model.representative is True
    assert pv_node.metadata["representative"] is True
    assert "aproximación simplificada" in str(pv_node.metadata["representative_note"])


def test_cytoscape_elements_include_inspector_metadata() -> None:
    bundle = _base_bundle()
    inverter = {"name": "INV-15", "AC_kW": 15.0, "Vmppt_min": 200.0, "Vmppt_max": 850.0, "Vdc_max": 1000.0, "Imax_mppt": 26.0, "n_mppt": 3}
    detail = _detail(candidate_key="18.000::None", k_wp=18.0, n_mod=36, ns=12, np_=3, inverter=inverter)
    scenario = _scenario(bundle, {"18.000::None": detail}, "18.000::None")

    model = build_unifilar_model(scenario, "18.000::None", lang="es")
    elements = to_cytoscape_elements(model)
    inverter_node = next(element for element in elements if element["data"]["id"] == "inverter")

    assert inverter_node["data"]["component_kind"] == "inverter"
    assert inverter_node["data"]["title"] == "Inversor"
    assert inverter_node["data"]["description"].startswith("Convierte la energía DC")
    assert inverter_node["data"]["details"]
    assert inverter_node["data"]["icon_url"].endswith("/assets/icons/inverter.svg")
    assert "[" not in inverter_node["data"]["label"]


def test_default_inspector_and_legend_are_spanish_first() -> None:
    legend = build_schematic_legend("es")
    inspector = default_schematic_inspector(None, "es")

    assert [item.label for item in legend[:5]] == [
        "Strings FV / grupos MPPT",
        "Inversor",
        "Batería",
        "Casa / carga",
        "Red",
    ]
    assert inspector.title == "Cómo leer este esquema"
    assert inspector.description.startswith("Haz clic o toca")
    assert inspector.status == "Guía rápida"
    assert legend[0].icon_url and legend[0].icon_url.endswith("/assets/icons/pv.svg")
    assert legend[4].icon_url and legend[4].icon_url.endswith("/assets/icons/grid.svg")


def test_resolve_schematic_inspector_returns_practical_rows() -> None:
    bundle = _base_bundle()
    inverter = {"name": "INV-10", "AC_kW": 10.0, "Vmppt_min": 150.0, "Vmppt_max": 800.0, "Vdc_max": 1000.0, "Imax_mppt": 20.0, "n_mppt": 2}
    battery = {"name": "BAT-10", "nom_kWh": 10.0, "max_kW": 5.0, "max_ch_kW": 5.0, "max_dis_kW": 5.0, "price_COP": 1_000_000}
    detail = _detail(candidate_key="12.000::BAT-10", k_wp=12.0, n_mod=24, ns=12, np_=2, inverter=inverter, battery=battery, battery_name="BAT-10")
    scenario = _scenario(_base_bundle(bat_coupling="dc"), {"12.000::BAT-10": detail}, "12.000::BAT-10")
    model = build_unifilar_model(scenario, "12.000::BAT-10", lang="es")
    battery_node = next(node for node in model.nodes if node.role == "battery")

    inspector = resolve_schematic_inspector({"id": battery_node.id}, model, "es", locked=True)

    assert inspector.title == "Batería"
    assert inspector.description.startswith("Almacena excedentes")
    assert inspector.status == "Detalle fijado"
    assert {row.label for row in inspector.details}.issuperset({"Componente", "Modelo", "Energía nominal", "Energía útil", "Acoplamiento"})


def test_incomplete_hardware_data_and_component_defaults_are_graceful() -> None:
    bundle = _base_bundle()
    inverter = {"name": "INV-INCOMPLETO", "n_mppt": 1}
    detail = _detail(candidate_key="5.000::None", k_wp=5.0, n_mod=11, ns=5, np_=3, inverter=inverter)
    scenario = _scenario(bundle, {"5.000::None": detail}, "5.000::None")

    model = build_unifilar_model(scenario, "5.000::None", lang="es")
    section = unifilar_diagram_section()
    section_title = _find_component(section, "unifilar-diagram-title")
    legend_title = _find_component(section, "unifilar-legend-title")
    inspector_title = _find_component(section, "unifilar-inspector-title")

    assert model.nodes
    assert model.note.startswith("Este es un esquema unifilar")
    assert section_title.children == "Esquema unifilar"
    assert legend_title.children == "Leyenda"
    assert inspector_title.children == "Detalle del componente"


def test_unifilar_section_stacks_diagram_inspector_legend_and_note() -> None:
    section = unifilar_diagram_section()
    shell = _find_component(section, "unifilar-diagram-shell")
    legend_items = _find_component(section, "unifilar-legend-items")
    note = _find_component(section, "unifilar-diagram-note")

    assert shell is not None
    stack = shell.children[0]
    assert stack.className == "schematic-stack"
    assert stack.children[0].className == "schematic-diagram-card"
    assert _find_component(stack.children[0], "active-unifilar-diagram") is not None
    assert "schematic-detail-card" in stack.children[1].className
    assert _find_component(stack.children[1], "unifilar-inspector-body") is not None
    assert "schematic-legend-card" in stack.children[2].className
    assert stack.children[3].id == "unifilar-diagram-note"
    assert note is not None
    assert legend_items is not None
    assert "legend-list-inline" in legend_items.className
    assert len(legend_items.children) == len(build_schematic_legend("es"))


def test_unifilar_styles_shift_labels_and_callback_uses_model_height(monkeypatch) -> None:
    node_style = next(rule["style"] for rule in CYTOSCAPE_STYLESHEET if rule["selector"] == "node")
    assert node_style["text-margin-y"] == "-14px"

    bundle = _base_bundle()
    inverter = {"name": "INV-15", "AC_kW": 15.0, "Vmppt_min": 200.0, "Vmppt_max": 850.0, "Vdc_max": 1000.0, "Imax_mppt": 26.0, "n_mppt": 3}
    detail = _detail(candidate_key="18.000::None", k_wp=18.0, n_mod=36, ns=12, np_=3, inverter=inverter)
    scenario = _scenario(bundle, {"18.000::None": detail}, "18.000::None")
    model = build_unifilar_model(scenario, "18.000::None", lang="es")

    create_app()
    workbench = importlib.import_module("pages.workbench")
    monkeypatch.setattr(workbench, "_session_with_scan", lambda payload, language_value: (None, None, scenario))

    outputs = workbench.populate_unifilar_diagram({}, "es")
    assert outputs[7]["height"] == f"{model.diagram_height}px"


def test_resolve_schematic_focus_prioritizes_locked_selection() -> None:
    focus, locked = resolve_schematic_focus(
        locked_node_id="battery",
        hover_node_data={"id": "pv-1"},
    )

    assert locked is True
    assert focus == {"id": "battery"}


def test_missing_icon_role_falls_back_cleanly() -> None:
    assert resolve_schematic_icon_url("missing-role") is None
