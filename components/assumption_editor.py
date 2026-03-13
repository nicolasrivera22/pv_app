from __future__ import annotations

from dash import dcc, html


ASSUMPTION_FIELDS = [
    {"field": "E_month_kWh", "label": "Monthly demand (kWh)", "kind": "number"},
    {"field": "PR", "label": "Performance ratio", "kind": "number"},
    {"field": "buy_tariff_COP_kWh", "label": "Buy tariff (COP/kWh)", "kind": "number"},
    {"field": "sell_tariff_COP_kWh", "label": "Sell tariff (COP/kWh)", "kind": "number"},
    {"field": "discount_rate", "label": "Discount rate", "kind": "number"},
    {"field": "years", "label": "Years", "kind": "number"},
    {"field": "pricing_mode", "label": "Pricing mode", "kind": "dropdown", "options": [{"label": "Variable", "value": "variable"}, {"label": "Total", "value": "total"}]},
    {"field": "price_per_kWp_COP", "label": "Price per kWp (COP)", "kind": "number"},
    {"field": "price_total_COP", "label": "Total price (COP)", "kind": "number"},
    {"field": "include_var_others", "label": "Include variable others", "kind": "dropdown", "options": [{"label": "Yes", "value": True}, {"label": "No", "value": False}]},
    {"field": "price_others_total", "label": "Fixed others (COP)", "kind": "number"},
    {"field": "include_hw_in_price", "label": "Add hardware on top", "kind": "dropdown", "options": [{"label": "Yes", "value": True}, {"label": "No", "value": False}]},
    {"field": "export_allowed", "label": "Grid export allowed", "kind": "dropdown", "options": [{"label": "Yes", "value": True}, {"label": "No", "value": False}]},
    {"field": "include_battery", "label": "Include battery", "kind": "dropdown", "options": [{"label": "Yes", "value": True}, {"label": "No", "value": False}]},
    {"field": "optimize_battery", "label": "Optimize battery", "kind": "dropdown", "options": [{"label": "Yes", "value": True}, {"label": "No", "value": False}]},
    {"field": "battery_name", "label": "Fixed battery name", "kind": "text"},
    {"field": "bat_coupling", "label": "Battery coupling", "kind": "dropdown", "options": [{"label": "AC", "value": "ac"}, {"label": "DC", "value": "dc"}]},
    {"field": "bat_DoD", "label": "Battery DoD", "kind": "number"},
    {"field": "bat_eta_rt", "label": "Battery round-trip efficiency", "kind": "number"},
    {"field": "kWp_seed_mode", "label": "Seed mode", "kind": "dropdown", "options": [{"label": "Auto", "value": "auto"}, {"label": "Manual", "value": "manual"}]},
    {"field": "kWp_seed_manual_kWp", "label": "Manual seed kWp", "kind": "number"},
    {"field": "kWp_min", "label": "Min kWp", "kind": "number"},
    {"field": "kWp_max", "label": "Max kWp", "kind": "number"},
    {"field": "modules_span_each_side", "label": "Modules around seed", "kind": "number"},
    {"field": "limit_peak_ratio_enable", "label": "Peak-ratio limit enabled", "kind": "dropdown", "options": [{"label": "Yes", "value": True}, {"label": "No", "value": False}]},
    {"field": "limit_peak_ratio", "label": "Peak-ratio limit", "kind": "number"},
    {"field": "limit_peak_month_mode", "label": "Peak month mode", "kind": "dropdown", "options": [{"label": "Max", "value": "max"}, {"label": "Fixed", "value": "fixed"}]},
    {"field": "limit_peak_month_fixed", "label": "Fixed peak month", "kind": "number"},
    {"field": "limit_peak_basis", "label": "Peak basis", "kind": "dropdown", "options": [{"label": "Weighted mean", "value": "weighted_mean"}, {"label": "Max", "value": "max"}, {"label": "Weekday", "value": "weekday"}, {"label": "P95", "value": "p95"}]},
]


def assumption_values_from_config(config: dict) -> list:
    return [config.get(item["field"]) for item in ASSUMPTION_FIELDS]


def _assumption_input(item: dict):
    component_id = {"type": "assumption-input", "field": item["field"]}
    if item["kind"] == "dropdown":
        return dcc.Dropdown(id=component_id, options=item["options"], clearable=False)
    if item["kind"] == "number":
        return dcc.Input(id=component_id, type="number", className="text-input")
    return dcc.Input(id=component_id, type="text", className="text-input")


def assumption_editor_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.Div(className="section-head", children=[html.H3("Assumptions"), html.Button("Apply edits", id="apply-edits-btn", n_clicks=0, className="action-btn")]),
            html.Div(
                className="assumption-grid",
                children=[
                    html.Div(className="field-card", children=[html.Label(item["label"], className="input-label"), _assumption_input(item)])
                    for item in ASSUMPTION_FIELDS
                ],
            ),
        ],
    )
