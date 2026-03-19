from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

import dash
import pandas as pd
import pytest

from services import build_assumption_sections, load_config_from_excel, load_example_config, run_monte_carlo, run_scan, tr
from services.result_views import build_battery_load_figure, build_npv_figure, build_pv_destination_figure
from services.validation import localize_validation_message

_APP = dash.Dash(__name__, use_pages=True, pages_folder="")
help_page = importlib.import_module("pages.help")
stochastic_runner = importlib.import_module("services.stochastic_runner")
design_compare = importlib.import_module("services.design_compare")


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


def _find_field(sections: list[dict], field_key: str) -> dict:
    for section in sections:
        for bucket in ("basic", "advanced"):
            for field in section.get(bucket, []):
                if field["field"] == field_key:
                    return field
    raise AssertionError(f"Field {field_key!r} not found")


def _flatten_text(node) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return " ".join(part for child in node if (part := _flatten_text(child)))
    children = getattr(node, "children", None)
    if children is None:
        return ""
    if isinstance(children, (list, tuple)):
        return " ".join(part for child in children if (part := _flatten_text(child)))
    return _flatten_text(children)


def test_help_page_english_renders_real_product_help() -> None:
    title, intro, sections = help_page.translate_help_page("en")
    text = _flatten_text(sections)

    assert title == tr("help.title", "en")
    assert intro == tr("help.intro", "en")
    assert "Start here" in text
    assert "Workbench workflow" in text
    assert "Risk workflow" in text
    assert "Exporting and saving" in text


def test_schema_help_stays_english_without_falling_back_to_spanish_descriptions() -> None:
    bundle = load_config_from_excel(Path("PV_inputs.xlsx"))
    sections = build_assumption_sections(bundle, lang="en", show_all=False)

    monthly_demand = _find_field(sections, "E_month_kWh")
    daytime_mix = _find_field(sections, "alpha_mix")
    pricing_mode = _find_field(sections, "pricing_mode")

    assert monthly_demand["label"] == "Reference monthly demand"
    assert monthly_demand["help"] == "Use the site's typical monthly consumption. This value anchors system size and savings."
    assert daytime_mix["help"] == "How much demand happens during solar hours. Higher values usually favor self-consumption."
    assert [option["label"] for option in pricing_mode["options"]] == [
        "Variable (by kWp bands)",
        "Fixed project total",
    ]


def test_workbench_figures_use_english_chart_labels() -> None:
    bundle = _fast_bundle()
    scan = run_scan(bundle)
    detail = scan.candidate_details[scan.best_candidate_key]

    npv_table = scan.candidates[["candidate_key", "kWp", "battery", "NPV_COP", "payback_years", "self_consumption_ratio", "peak_ratio", "scan_order"]].copy()
    npv_figure = build_npv_figure(npv_table, selected_key=scan.best_candidate_key, lang="en", module_power_w=600.0)
    battery_figure = build_battery_load_figure(detail, bundle.config, lang="en")
    pv_destination_figure = build_pv_destination_figure(detail, bundle.config, lang="en")

    assert npv_figure.layout.xaxis.title.text == "Installed kWp"
    assert npv_figure.layout.xaxis2.title.text == "Panel count"
    assert any(trace.name == "Selected design" for trace in npv_figure.data)
    assert [trace.name for trace in battery_figure.data] == ["PV to load", "Battery to load", "Grid import"]
    assert battery_figure.layout.xaxis.title.text == "Month"
    assert battery_figure.layout.yaxis.title.text == "Energy [kWh]"
    assert {trace.name for trace in pv_destination_figure.data}.issuperset({"PV to load", "PV to battery", "Export"})
    assert pv_destination_figure.layout.xaxis.title.text == "Month"


def test_compare_npv_projection_hover_uses_npv_in_english() -> None:
    frame = pd.DataFrame(
        [
            {
                "design_label": "Design A",
                "candidate_key": "12.000::None",
                "Año_mes": "01-01",
                "NPV_COP": -10_000.0,
                "month_index": 1,
                "calendar_year": 2027,
                "project_year": 1,
                "kWp": 12.0,
                "panel_count": 20,
                "battery": "None",
                "inverter_name": "INV-1",
            }
        ]
    )

    figure = design_compare.build_npv_projection_figure(frame, lang="en", empty_message="empty", base_year=2026)

    assert "NPV [COP]" in figure.data[0].hovertemplate
    assert "VPN" not in figure.data[0].hovertemplate


def test_risk_warnings_and_errors_respect_english_mode(monkeypatch) -> None:
    bundle = _fast_bundle()
    baseline = run_scan(bundle)

    monkeypatch.setattr(stochastic_runner, "MONTE_CARLO_WARNING_THRESHOLD", 5)
    result = run_monte_carlo(
        bundle,
        selected_candidate_key=baseline.best_candidate_key,
        seed=0,
        n_simulations=6,
        return_samples=False,
        baseline_scan=baseline,
        lang="en",
    )

    assert any("recommended threshold" in warning for warning in result.warnings)

    with pytest.raises(ValueError, match="selected design"):
        run_monte_carlo(
            bundle,
            selected_candidate_key="missing",
            seed=0,
            n_simulations=6,
            return_samples=False,
            baseline_scan=baseline,
            lang="en",
        )


def test_validation_messages_can_be_localized_to_english() -> None:
    duplicate_issue = localize_validation_message(
        type("Issue", (), {"message": "Los nombres deben ser únicos. Duplicados: INV-A.", "field": "Inversor_Catalog", "level": "error"})(),
        lang="en",
    )
    pricing_issue = localize_validation_message(
        type("Issue", (), {"message": "pricing_mode debe ser 'variable' o 'total'.", "field": "pricing_mode", "level": "error"})(),
        lang="en",
    )
    warning_issue = localize_validation_message(
        type("Issue", (), {"message": "El perfil solar se normalizó para que sume 1.", "field": "SUN_HSP_PROFILE", "level": "warning"})(),
        lang="en",
    )

    assert duplicate_issue == "Each item must have a unique name. Duplicate names: INV-A."
    assert pricing_issue == "Choose Variable (by kWp bands) or Fixed project total."
    assert "normalized it automatically" in warning_issue
