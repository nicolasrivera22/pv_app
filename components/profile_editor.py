from __future__ import annotations

from dash import dash_table, html

from services.i18n import tr


def _profile_table(table_id: str) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=True,
        row_deletable=False,
        sort_action="native",
        page_size=8,
        style_table={"overflowX": "auto"},
        style_cell={"padding": "0.4rem", "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": 12},
        style_header={"backgroundColor": "#ede9fe", "fontWeight": "bold"},
        tooltip_delay=0,
        tooltip_duration=None,
        tooltip_header={},
    )


def profile_editor_section() -> html.Div:
    return html.Div(
        className="panel secondary-panel",
        children=[
            html.Div(className="section-head", children=[html.H3(tr("workbench.profiles", "es"), id="profile-editor-title")]),
            html.Div(tr("workbench.profiles.note", "es"), id="profile-editor-note", className="section-copy section-copy-wide"),
            html.Div(
                className="catalog-grid",
                children=[
                    html.Div(className="subpanel", children=[html.H4(tr("workbench.profiles.month", "es"), id="month-profile-title"), _profile_table("month-profile-editor")]),
                    html.Div(className="subpanel", children=[html.H4(tr("workbench.profiles.sun", "es"), id="sun-profile-title"), _profile_table("sun-profile-editor")]),
                    html.Div(className="subpanel", children=[html.H4(tr("workbench.profiles.price", "es"), id="price-kwp-title"), _profile_table("price-kwp-editor")]),
                    html.Div(className="subpanel", children=[html.H4(tr("workbench.profiles.price_others", "es"), id="price-kwp-others-title"), _profile_table("price-kwp-others-editor")]),
                    html.Div(className="subpanel", id="demand-profile-panel", children=[html.H4(tr("workbench.profiles.demand_weekday", "es"), id="demand-profile-title"), _profile_table("demand-profile-editor")]),
                    html.Div(className="subpanel", id="demand-profile-general-panel", children=[html.H4(tr("workbench.profiles.demand_general", "es"), id="demand-profile-general-title"), _profile_table("demand-profile-general-editor")]),
                    html.Div(className="subpanel", id="demand-profile-weights-panel", children=[html.H4(tr("workbench.profiles.demand_weights", "es"), id="demand-profile-weights-title"), _profile_table("demand-profile-weights-editor")]),
                ],
            ),
        ],
    )
