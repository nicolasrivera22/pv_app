from __future__ import annotations

import sys
import types
from dataclasses import replace

import pytest

if "dash_cytoscape" not in sys.modules:
    stub = types.ModuleType("dash_cytoscape")

    class Cytoscape:
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.children = kwargs.get("children")
            self.id = kwargs.get("id")

    stub.Cytoscape = Cytoscape
    sys.modules["dash_cytoscape"] = stub

from components.candidate_explorer import candidate_explorer_section
from app import app as _app
from pages import workbench as workbench_page
from services import (
    ScenarioSessionState,
    add_scenario,
    bootstrap_client_session,
    commit_client_session,
    create_scenario_record,
    load_example_config,
    run_scenario_scan,
    tr,
    update_selected_candidate,
)


def _fast_bundle():
    bundle = load_example_config()
    return replace(
        bundle,
        config={
            **bundle.config,
            "years": 5,
            "modules_span_each_side": 4,
            "kWp_min": 12.0,
            "kWp_max": 18.0,
        },
    )


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


def _find_payback_card(cards: list) -> object:
    return next(card for card in cards if card.children[0].children == tr("workbench.payback.project_label", "es"))


def test_candidate_explorer_renders_horizon_helper_copy() -> None:
    section = candidate_explorer_section()

    assert _find_component(section, "candidate-horizon-helper").children == tr("workbench.horizon.helper", "es")


def test_populate_results_keeps_project_payback_and_shows_conditional_note() -> None:
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    scenario = state.get_scenario()
    assert scenario is not None and scenario.scan_result is not None
    selected_key, selected_detail = next(
        (key, detail)
        for key, detail in scenario.scan_result.candidate_details.items()
        if (detail.get("summary") or {}).get("payback_years") not in (None, "")
        and float((detail.get("summary") or {})["payback_years"]) > 1.0
    )
    state = update_selected_candidate(state, scenario.scenario_id, selected_key)
    payload = _session_payload(state)

    short_horizon = workbench_page.populate_results(payload, "es", 1)
    full_horizon = workbench_page.populate_results(payload, "es", 5)

    short_payback_card = _find_payback_card(short_horizon[3])
    full_payback_card = _find_payback_card(full_horizon[3])
    short_row = next(row for row in short_horizon[11] if row["candidate_key"] == selected_key)

    assert short_horizon[4].layout.title.text.endswith("Horizonte financiero: 1 año</sup>")
    assert short_horizon[4].layout.yaxis2.title.text == tr("workbench.payback.project_axis_label", "es")
    assert short_horizon[15]["payback_years"] == tr("workbench.horizon.helper", "es")
    assert short_row["payback_years"] == pytest.approx(float(selected_detail["summary"]["payback_years"]))
    assert short_payback_card.children[2].children == tr("workbench.payback.note.visible_horizon", "es")
    assert len(full_payback_card.children) == 2
