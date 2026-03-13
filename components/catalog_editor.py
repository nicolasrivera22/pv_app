from __future__ import annotations

from dash import dash_table, html


def _catalog_table(table_id: str) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=True,
        row_deletable=True,
        filter_action="native",
        sort_action="native",
        page_size=8,
        style_table={"overflowX": "auto"},
        style_cell={"padding": "0.4rem", "fontFamily": "monospace", "fontSize": 12},
        style_header={"backgroundColor": "#dbeafe", "fontWeight": "bold"},
    )


def catalog_editor_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.Div(className="section-head", children=[html.H3("Hardware catalogs")]),
            html.Div(
                className="catalog-grid",
                children=[
                    html.Div(
                        className="subpanel",
                        children=[
                            html.Div(className="section-head", children=[html.H4("Inverters"), html.Button("Add row", id="add-inverter-row-btn", n_clicks=0, className="action-btn tertiary")]),
                            _catalog_table("inverter-table-editor"),
                        ],
                    ),
                    html.Div(
                        className="subpanel",
                        children=[
                            html.Div(className="section-head", children=[html.H4("Batteries"), html.Button("Add row", id="add-battery-row-btn", n_clicks=0, className="action-btn tertiary")]),
                            _catalog_table("battery-table-editor"),
                        ],
                    ),
                ],
            ),
        ],
    )
