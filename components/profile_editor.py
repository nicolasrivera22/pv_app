from __future__ import annotations

from dash import dash_table, html


def _profile_table(table_id: str) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=True,
        row_deletable=False,
        sort_action="native",
        page_size=8,
        style_table={"overflowX": "auto"},
        style_cell={"padding": "0.4rem", "fontFamily": "monospace", "fontSize": 12},
        style_header={"backgroundColor": "#ede9fe", "fontWeight": "bold"},
    )


def profile_editor_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.Div(className="section-head", children=[html.H3(id="profile-editor-title")]),
            html.Div(id="profile-editor-note", className="scenario-meta"),
            html.Div(
                className="catalog-grid",
                children=[
                    html.Div(className="subpanel", children=[html.H4(id="month-profile-title"), _profile_table("month-profile-editor")]),
                    html.Div(className="subpanel", children=[html.H4(id="sun-profile-title"), _profile_table("sun-profile-editor")]),
                    html.Div(className="subpanel", children=[html.H4(id="price-kwp-title"), _profile_table("price-kwp-editor")]),
                    html.Div(className="subpanel", children=[html.H4(id="price-kwp-others-title"), _profile_table("price-kwp-others-editor")]),
                    html.Div(className="subpanel", id="demand-profile-panel", children=[html.H4(id="demand-profile-title"), _profile_table("demand-profile-editor")]),
                    html.Div(className="subpanel", id="demand-profile-general-panel", children=[html.H4(id="demand-profile-general-title"), _profile_table("demand-profile-general-editor")]),
                    html.Div(className="subpanel", id="demand-profile-weights-panel", children=[html.H4(id="demand-profile-weights-title"), _profile_table("demand-profile-weights-editor")]),
                ],
            ),
        ],
    )
