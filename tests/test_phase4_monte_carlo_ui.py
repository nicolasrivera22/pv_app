from __future__ import annotations

from dataclasses import replace

from services import build_config_fields, create_scenario_record, load_example_config
from services.result_views import build_typical_day_figure


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
    }
    return replace(bundle, config=config)


def test_risk_monte_carlo_fields_use_localized_uncertainty_labels() -> None:
    bundle = _fast_bundle()

    fields = build_config_fields(
        bundle,
        ("mc_PR_std", "mc_buy_std", "mc_sell_std", "mc_demand_std"),
        lang="en",
    )
    labels = [field["label"] for field in fields]

    assert labels == [
        "PR variation in Risk",
        "Import tariff variation",
        "Export tariff variation",
        "Demand variation in Risk",
    ]


def test_typical_day_chart_adds_battery_flows_when_battery_is_present() -> None:
    bundle = _fast_bundle()
    inverter = bundle.inverter_catalog.iloc[0].to_dict()
    battery = bundle.battery_catalog.loc[bundle.battery_catalog["nom_kWh"] > 0].iloc[0].to_dict()
    scenario = create_scenario_record("Typical Day", bundle)

    with_battery = build_typical_day_figure(
        {
            "kWp": 15.0,
            "inv_sel": {"inverter": inverter},
            "battery": battery,
        },
        scenario,
        lang="en",
    )
    without_battery = build_typical_day_figure(
        {
            "kWp": 15.0,
            "inv_sel": {"inverter": inverter},
            "battery": None,
        },
        scenario,
        lang="en",
    )

    with_names = [trace.name for trace in with_battery.data]
    without_names = [trace.name for trace in without_battery.data]

    assert "Battery to load" in with_names
    assert "PV to battery" in with_names
    assert "Battery to load" not in without_names
    assert "PV to battery" not in without_names
