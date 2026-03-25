from __future__ import annotations

import pytest

import pandas as pd

from services import load_example_config, tr
from services.demand_profile_logic import (
    PROFILE_TYPE_INDUSTRIAL,
    PROFILE_TYPE_MIXED,
    PROFILE_TYPE_RESIDENTIAL,
    canonicalize_total_source,
    canonicalize_weekday_source,
    derive_relative_profile,
    derive_total_preview_from_weekday,
)
from services.workspace_demand import build_demand_profile_ui_state, demand_mode_options


def test_weekday_source_derives_total_kwh_from_res_and_ind() -> None:
    frame = canonicalize_weekday_source(
        [
            {"Dia": "Lunes", "DOW": 1, "HOUR": 8, "RES": 1.25, "IND": 2.75, "TOTAL_kWh": 999},
            {"Dia": "Martes", "DOW": 2, "HOUR": 9, "RES": "", "IND": 1.5, "TOTAL_kWh": ""},
        ]
    )

    assert float(frame.loc[0, "TOTAL_kWh"]) == pytest.approx(4.0)
    assert float(frame.loc[1, "TOTAL_kWh"]) == pytest.approx(1.5)


def test_total_preview_aggregates_weekday_rows_by_hour_mean() -> None:
    preview = derive_total_preview_from_weekday(
        [
            {"Dia": "Lunes", "DOW": 1, "HOUR": 8, "RES": 2.0, "IND": 1.0},
            {"Dia": "Martes", "DOW": 2, "HOUR": 8, "RES": 4.0, "IND": 3.0},
            {"Dia": "Lunes", "DOW": 1, "HOUR": 9, "RES": 1.0, "IND": 2.0},
        ]
    )

    hour_8 = preview.loc[preview["HOUR"] == 8].iloc[0]
    hour_9 = preview.loc[preview["HOUR"] == 9].iloc[0]

    assert float(hour_8["RES"]) == pytest.approx(3.0)
    assert float(hour_8["IND"]) == pytest.approx(2.0)
    assert float(hour_8["TOTAL_kWh"]) == pytest.approx(5.0)
    assert float(hour_9["TOTAL_kWh"]) == pytest.approx(3.0)


def test_total_source_derives_total_kwh_without_crashing_on_blanks() -> None:
    frame = canonicalize_total_source(
        [
            {"HOUR": "10", "RES": "3.5", "IND": "", "TOTAL_kWh": ""},
            {"HOUR": "11", "RES": "", "IND": "", "TOTAL_kWh": ""},
        ]
    )

    assert float(frame.loc[0, "TOTAL_kWh"]) == pytest.approx(3.5)
    assert pd.isna(frame.loc[1, "TOTAL_kWh"])


def test_relative_profile_normalizes_bases_and_applies_mixed_alpha() -> None:
    frame = derive_relative_profile(
        [
            {"HOUR": 0, "W_RES": 2.0, "W_IND": 1.0},
            {"HOUR": 1, "W_RES": 6.0, "W_IND": 3.0},
        ],
        profile_type=PROFILE_TYPE_MIXED,
        alpha_mix=0.25,
        e_month_kwh=3000,
    )

    assert float(frame.loc[0, "W_RES_BASE"]) == pytest.approx(0.25)
    assert float(frame.loc[1, "W_RES_BASE"]) == pytest.approx(0.75)
    assert float(frame.loc[0, "W_IND_BASE"]) == pytest.approx(0.25)
    assert float(frame.loc[1, "W_IND_BASE"]) == pytest.approx(0.75)
    assert float(frame.loc[0, "W_TOTAL"]) == pytest.approx(0.25)
    assert float(frame.loc[1, "W_TOTAL"]) == pytest.approx(0.75)
    assert float(frame.loc[0, "TOTAL_kWh"]) == pytest.approx((3000 / (365 / 12)) * 0.25)


def test_relative_profile_supports_residential_and_industrial_modes() -> None:
    rows = [
        {"HOUR": 0, "W_RES": 1.0, "W_IND": 3.0},
        {"HOUR": 1, "W_RES": 3.0, "W_IND": 1.0},
    ]

    residential = derive_relative_profile(rows, profile_type=PROFILE_TYPE_RESIDENTIAL, alpha_mix=0.8, e_month_kwh=1200)
    industrial = derive_relative_profile(rows, profile_type=PROFILE_TYPE_INDUSTRIAL, alpha_mix=0.2, e_month_kwh=1200)

    assert float(residential.loc[0, "W_TOTAL"]) == pytest.approx(float(residential.loc[0, "W_RES_BASE"]))
    assert float(residential.loc[1, "W_TOTAL"]) == pytest.approx(float(residential.loc[1, "W_RES_BASE"]))
    assert float(industrial.loc[0, "W_TOTAL"]) == pytest.approx(float(industrial.loc[0, "W_IND_BASE"]))
    assert float(industrial.loc[1, "W_TOTAL"]) == pytest.approx(float(industrial.loc[1, "W_IND_BASE"]))


def test_relative_profile_handles_zero_weight_sums_without_division_errors() -> None:
    frame = derive_relative_profile(
        [
            {"HOUR": 0, "W_RES": 0.0, "W_IND": 0.0},
            {"HOUR": 1, "W_RES": 0.0, "W_IND": 0.0},
        ],
        profile_type=PROFILE_TYPE_MIXED,
        alpha_mix=0.6,
        e_month_kwh=1800,
    )

    assert all(float(value) == pytest.approx(0.0) for value in frame["W_RES_BASE"])
    assert all(float(value) == pytest.approx(0.0) for value in frame["W_IND_BASE"])
    assert all(float(value) == pytest.approx(0.0) for value in frame["W_TOTAL"])
    assert all(float(value) == pytest.approx(0.0) for value in frame["TOTAL_kWh"])


def test_workspace_demand_state_total_mode_fills_24_hours_and_month_display() -> None:
    bundle = load_example_config()

    state = build_demand_profile_ui_state(
        bundle=bundle,
        lang="es",
        profile_mode_value="perfil general",
        total_rows=[{"HOUR": 0, "RES": 2.0, "IND": 1.0}],
    )

    assert len(state["total_source_rows"]) == 24
    assert state["total_source_rows"][0]["TOTAL_kWh"] == pytest.approx(3.0)
    assert state["total_source_rows"][-1]["HOUR"] == 23
    assert state["e_month_kwh"] == pytest.approx(90.0)
    assert state["energy_disabled"] is True
    assert state["visibility"]["demand-profile-general-panel"]["display"] == "block"


def test_workspace_demand_state_weekday_mode_keeps_full_week_and_month_display() -> None:
    bundle = load_example_config()

    state = build_demand_profile_ui_state(
        bundle=bundle,
        lang="es",
        profile_mode_value="perfil hora dia de semana",
        weekday_rows=[{"Dia": "Lunes", "DOW": 1, "HOUR": 0, "RES": 4.0, "IND": 1.0}],
    )

    assert len(state["weekday_source_rows"]) == 168
    assert state["weekday_source_rows"][0]["HOUR"] == 0
    assert state["weekday_source_rows"][23]["HOUR"] == 23
    assert state["weekday_source_rows"][24]["DOW"] == 2
    assert state["e_month_kwh"] == pytest.approx(21.43)
    assert state["visibility"]["demand-profile-general-preview-panel"]["display"] == "block"


def test_workspace_demand_state_relative_mode_keeps_controls_visible_and_complete() -> None:
    bundle = load_example_config()

    state = build_demand_profile_ui_state(
        bundle=bundle,
        lang="es",
        profile_mode_value="perfil horario relativo",
        relative_profile_type_value="industrial",
        alpha_mix_value=0.35,
        e_month_value=2400,
        relative_rows=[{"HOUR": 1, "W_RES": 2.0, "W_IND": 4.0}],
    )

    assert len(state["relative_source_rows"]) == 24
    assert state["relative_source_rows"][0]["HOUR"] == 0
    assert state["relative_source_rows"][-1]["HOUR"] == 23
    assert state["weights_preview_style"]["display"] == "block"
    assert state["relative_grid_style"]["display"] == "grid"
    assert state["secondary_grid_style"]["display"] == "none"
    assert state["alpha_disabled"] is True
    assert state["energy_disabled"] is False


def test_demand_mode_options_expose_option_tooltips() -> None:
    options = demand_mode_options("es")

    assert options[0]["label"].title == tr("workbench.profiles.mode.note.weekday", "es")
    assert options[1]["label"].title == tr("workbench.profiles.mode.note.total", "es")
    assert options[2]["label"].title == tr("workbench.profiles.mode.note.relative", "es")
