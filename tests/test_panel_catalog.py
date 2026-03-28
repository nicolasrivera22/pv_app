from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from pv_product.panel_catalog import (
    DEFAULT_BASELINE_PANEL_NAME,
    MANUAL_PANEL_TOKEN,
    default_panel_catalog_frame,
    normalize_panel_name,
)
from pv_product.utils import DEFAULT_CONFIG
from services import build_assumption_sections, fingerprint_deterministic_input, load_config_from_excel, load_example_config
from services.io_excel import _normalize_config_value, rebuild_config_bundle
from services.validation import normalize_panel_catalog_rows


def _baseline_row(panel_catalog: pd.DataFrame) -> pd.Series:
    row = panel_catalog.loc[panel_catalog["name"].astype(str).str.strip() == DEFAULT_BASELINE_PANEL_NAME]
    assert len(row) == 1
    return row.iloc[0]


def test_example_bundle_defaults_to_baseline_panel_with_current_module_behavior() -> None:
    bundle = load_example_config()
    baseline = _baseline_row(bundle.panel_catalog)

    assert bundle.config["panel_name"] == DEFAULT_BASELINE_PANEL_NAME
    assert float(baseline["P_mod_W"]) == pytest.approx(float(DEFAULT_CONFIG["P_mod_W"]))
    assert float(baseline["Voc25"]) == pytest.approx(float(DEFAULT_CONFIG["Voc25"]))
    assert float(baseline["Vmp25"]) == pytest.approx(float(DEFAULT_CONFIG["Vmp25"]))
    assert float(baseline["Isc"]) == pytest.approx(float(DEFAULT_CONFIG["Isc"]))
    assert str(baseline["panel_technology_mode"]).strip() == str(DEFAULT_CONFIG["panel_technology_mode"])
    assert bundle.config["P_mod_W"] == pytest.approx(float(DEFAULT_CONFIG["P_mod_W"]))
    assert bundle.config["Voc25"] == pytest.approx(float(DEFAULT_CONFIG["Voc25"]))
    assert bundle.config["Vmp25"] == pytest.approx(float(DEFAULT_CONFIG["Vmp25"]))
    assert bundle.config["Isc"] == pytest.approx(float(DEFAULT_CONFIG["Isc"]))
    assert bundle.config["panel_technology_mode"] == DEFAULT_CONFIG["panel_technology_mode"]


def test_legacy_workbook_without_panel_name_normalizes_to_manual_mode() -> None:
    bundle = load_config_from_excel("PV_inputs.xlsx")

    assert bundle.config["panel_name"] == MANUAL_PANEL_TOKEN


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, MANUAL_PANEL_TOKEN),
        ("", MANUAL_PANEL_TOKEN),
        ("   ", MANUAL_PANEL_TOKEN),
        ("__unknown__", MANUAL_PANEL_TOKEN),
        ("__MANUAL__", MANUAL_PANEL_TOKEN),
        ("Panel Real", "Panel Real"),
    ],
)
def test_panel_name_normalization_handles_manual_and_real_selection_cases(raw_value, expected) -> None:
    normalized, error = _normalize_config_value("panel_name", raw_value)

    assert normalized == expected
    assert error is None
    assert normalize_panel_name(raw_value) == expected


def test_manual_mode_uses_raw_config_fields_instead_of_catalog_values() -> None:
    bundle = load_example_config()
    manual_bundle = rebuild_config_bundle(
        bundle,
        config={
            **bundle.config,
            "panel_name": MANUAL_PANEL_TOKEN,
            "P_mod_W": 777.0,
            "Voc25": 58.0,
            "Vmp25": 47.0,
            "Isc": 15.5,
            "panel_technology_mode": "premium",
        },
    )

    assert manual_bundle.config["panel_name"] == MANUAL_PANEL_TOKEN
    assert manual_bundle.config["P_mod_W"] == pytest.approx(777.0)
    assert manual_bundle.config["Voc25"] == pytest.approx(58.0)
    assert manual_bundle.config["Vmp25"] == pytest.approx(47.0)
    assert manual_bundle.config["Isc"] == pytest.approx(15.5)
    assert manual_bundle.config["panel_technology_mode"] == "premium"
    assert "panel_area_m2" not in manual_bundle.config


def test_real_panel_selection_resolves_module_fields_and_technology_from_catalog() -> None:
    bundle = load_example_config()
    premium_name = "PREM-620 Premium"
    resolved = rebuild_config_bundle(bundle, config={**bundle.config, "panel_name": premium_name})

    assert resolved.config["panel_name"] == premium_name
    assert resolved.config["P_mod_W"] == pytest.approx(620.0)
    assert resolved.config["Voc25"] == pytest.approx(52.0)
    assert resolved.config["Vmp25"] == pytest.approx(43.0)
    assert resolved.config["Isc"] == pytest.approx(14.4)
    assert resolved.config["panel_technology_mode"] == "premium"
    assert resolved.config["panel_area_m2"] == pytest.approx(2.384 * 1.303)


def test_invalid_explicit_panel_selection_is_a_validation_error_not_silent_fallback() -> None:
    bundle = load_example_config()
    invalid = rebuild_config_bundle(bundle, config={**bundle.config, "panel_name": "No existe"})

    assert invalid.config["panel_name"] == "No existe"
    assert any(issue.field == "panel_name" and issue.level == "error" for issue in invalid.issues)


def test_panel_catalog_validation_rejects_reserved_token_and_case_insensitive_duplicates() -> None:
    _, issues = normalize_panel_catalog_rows(
        [
            {
                "name": "__manual__",
                "P_mod_W": 600,
                "Voc25": 50,
                "Vmp25": 41,
                "Isc": 14,
                "length_m": 2.2,
                "width_m": 1.1,
                "panel_technology_mode": "standard",
            },
            {
                "name": "Premium 1",
                "P_mod_W": 620,
                "Voc25": 52,
                "Vmp25": 43,
                "Isc": 14.4,
                "length_m": 2.3,
                "width_m": 1.2,
                "panel_technology_mode": "premium",
            },
            {
                "name": " premium 1 ",
                "P_mod_W": 620,
                "Voc25": 52,
                "Vmp25": 43,
                "Isc": 14.4,
                "length_m": 2.3,
                "width_m": 1.2,
                "panel_technology_mode": "premium",
            },
        ]
    )

    messages = [issue.message for issue in issues]
    assert any("__manual__" in message for message in messages)
    assert any("Duplicados" in message for message in messages)


def test_catalog_mode_keeps_derived_fields_visible_but_disabled_with_context_note() -> None:
    base_bundle = load_example_config()
    bundle = rebuild_config_bundle(base_bundle, config={**base_bundle.config, "panel_name": "PREM-620 Premium"})
    sections = build_assumption_sections(bundle, lang="es", show_all=True)
    solar_section = next(section for section in sections if section["group_key"] == "Sol y módulos")
    field_map = {
        field["field"]: field
        for bucket in ("basic", "advanced")
        for field in solar_section.get(bucket, [])
    }

    assert field_map["panel_name"]["disabled"] is False
    assert field_map["P_mod_W"]["disabled"] is True
    assert field_map["Voc25"]["disabled"] is True
    assert field_map["Vmp25"]["disabled"] is True
    assert field_map["Isc"]["disabled"] is True
    assert field_map["panel_technology_mode"]["disabled"] is True
    assert "modelo seleccionado" in solar_section["context_note"].lower()


def test_unrelated_panel_catalog_rows_do_not_change_deterministic_fingerprint() -> None:
    bundle = load_example_config()
    baseline = fingerprint_deterministic_input(bundle)

    modified_catalog = bundle.panel_catalog.copy()
    modified_catalog.loc[modified_catalog["name"] == "TRACK-600 Simplified", "length_m"] = 99.0
    unchanged = rebuild_config_bundle(bundle, panel_catalog=modified_catalog)

    assert fingerprint_deterministic_input(unchanged) == baseline


def test_selected_panel_effective_inputs_do_change_deterministic_fingerprint() -> None:
    bundle = load_example_config()
    baseline = fingerprint_deterministic_input(bundle)
    premium = rebuild_config_bundle(bundle, config={**bundle.config, "panel_name": "PREM-620 Premium"})

    assert fingerprint_deterministic_input(premium) != baseline
