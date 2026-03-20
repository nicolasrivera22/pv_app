from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import dash

from services import build_assumption_sections, load_example_config, tr
from services.types import ValidationIssue
from services.validation import localize_validation_message

_APP = dash.Dash(__name__, use_pages=True, pages_folder="")
help_page = importlib.import_module("pages.help")
_validation_panel_spec = importlib.util.spec_from_file_location(
    "validation_panel_module",
    Path("components/validation_panel.py"),
)
validation_panel_module = importlib.util.module_from_spec(_validation_panel_spec)
assert _validation_panel_spec is not None and _validation_panel_spec.loader is not None
_validation_panel_spec.loader.exec_module(validation_panel_module)
render_validation_panel = validation_panel_module.render_validation_panel


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


def test_help_page_contains_real_bilingual_product_help() -> None:
    title_en, intro_en, sections_en = help_page.translate_help_page("en")
    title_es, intro_es, sections_es = help_page.translate_help_page("es")

    text_en = _flatten_text(sections_en)
    text_es = _flatten_text(sections_es)

    assert title_en == tr("help.title", "en")
    assert intro_en == tr("help.intro", "en")
    assert "Start here" in text_en
    assert "Core concepts" in text_en
    assert "Workbench workflow" in text_en
    assert "Compare workflow" in text_en
    assert "Risk workflow" in text_en
    assert "How to read results" in text_en
    assert "Exporting and saving" in text_en
    assert "Glossary / key terms" in text_en
    assert "Risk > Monte Carlo settings" in text_en
    assert "chart and candidate table show only viable designs" in text_en
    assert "discard counters and discard markers" in text_en
    assert "quick-start guide" not in text_en.lower()

    assert title_es == tr("help.title", "es")
    assert intro_es == tr("help.intro", "es")
    assert "Empieza aquí" in text_es
    assert "Conceptos clave" in text_es
    assert "Flujo de trabajo en Escenarios" in text_es
    assert "Flujo de trabajo en Comparar" in text_es
    assert "Flujo de trabajo en Riesgo" in text_es
    assert "Cómo leer los resultados" in text_es
    assert "Exportar y guardar" in text_es
    assert "Glosario / términos clave" in text_es
    assert "Riesgo > Parámetros de Monte Carlo" in text_es
    assert "solo diseños viables" in text_es
    assert "contadores y marcadores de descarte" in text_es


def test_validation_panel_uses_friendly_names_and_sections() -> None:
    issues = [
        ValidationIssue("error", "pricing_mode", "pricing_mode debe ser 'variable' o 'total'."),
        ValidationIssue("error", "battery_name", "battery_name no existe en el catálogo de baterías."),
    ]

    rendered_en = render_validation_panel(issues, lang="en")
    rendered_es = render_validation_panel(issues, lang="es")

    text_en = _flatten_text(rendered_en)
    text_es = _flatten_text(rendered_es)

    assert "pricing_mode" not in text_en
    assert "battery_name" not in text_en
    assert "Assumptions > Economics and pricing" in text_en
    assert "Assumptions > Battery and export" in text_en
    assert "Base project pricing" in text_en
    assert "Fixed battery" in text_en
    assert "Choose Variable (by kWp bands) or Fixed project total." in text_en
    assert "turn on battery optimization" in text_en

    assert "pricing_mode" not in text_es
    assert "battery_name" not in text_es
    assert "Supuestos > Economía y precios" in text_es
    assert "Supuestos > Batería y exportación" in text_es
    assert "Cómo fijar el costo base" in text_es
    assert "Batería fija" in text_es


def test_validation_panel_routes_monte_carlo_fields_to_risk_section() -> None:
    issues = [ValidationIssue("error", "mc_manual_kWp", "El valor de 'mc_manual_kWp' debe ser mayor que cero.")]

    rendered_en = render_validation_panel(issues, lang="en")
    rendered_es = render_validation_panel(issues, lang="es")

    text_en = _flatten_text(rendered_en)
    text_es = _flatten_text(rendered_es)

    assert "Risk > Monte Carlo" in text_en
    assert "Riesgo > Monte Carlo" in text_es


def test_validation_messages_are_human_and_actionable() -> None:
    solar_warning_en = localize_validation_message(
        ValidationIssue("warning", "SUN_HSP_PROFILE", "El perfil solar se normalizó para que sume 1."),
        lang="en",
    )
    solar_warning_es = localize_validation_message(
        ValidationIssue("warning", "SUN_HSP_PROFILE", "El perfil solar se normalizó para que sume 1."),
        lang="es",
    )
    scan_error_en = localize_validation_message(
        ValidationIssue("error", "scan_range", "La configuración actual no genera ningún candidato de kWp."),
        lang="en",
    )

    assert "normalized it automatically" in solar_warning_en
    assert "Revísalo si eso no era intencional" in solar_warning_es
    assert "Widen the scan range" in scan_error_en


def test_assumption_copy_guides_first_time_users_better() -> None:
    sections_en = build_assumption_sections(load_example_config(), lang="en", show_all=True)
    sections_es = build_assumption_sections(load_example_config(), lang="es", show_all=True)

    alpha_mix = _find_field(sections_en, "alpha_mix")
    mc_n = _find_field(sections_en, "mc_n_simulations")
    peak_ratio = _find_field(sections_en, "limit_peak_ratio")
    include_battery = _find_field(sections_en, "include_battery")

    assert alpha_mix["label"] == "Daytime demand share"
    assert "solar hours" in alpha_mix["help"]
    assert mc_n["label"] == "Default simulation count"
    assert "stabilize percentiles and probabilities" in mc_n["help"]
    assert peak_ratio["label"] == "Maximum PV-to-load ratio"
    assert "1.5 means 150%" in peak_ratio["help"]
    assert include_battery["label"] == "Evaluate battery"

    groups_es = {section["group"]: section["help"] for section in sections_es}
    assert "Barrido de diseños" in groups_es
    assert "Monte Carlo" in groups_es
    assert "pico fv" in groups_es["Límite de pico FV"].lower()
