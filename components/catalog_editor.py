from __future__ import annotations

from dash import dash_table, html

from services.i18n import tr


def _catalog_table(table_id: str) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=True,
        row_deletable=True,
        filter_action="native",
        sort_action="native",
        page_size=8,
        style_table={"overflowX": "auto"},
        style_cell={"padding": "0.4rem", "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": 12},
        style_header={"backgroundColor": "#dbeafe", "fontWeight": "bold"},
        tooltip_delay=0,
        tooltip_duration=None,
        tooltip_header={},
    )


def catalog_editor_section() -> html.Div:
    return html.Div(
        className="panel secondary-panel",
        children=[
            html.Div(className="section-head", children=[html.H3(tr("workbench.catalogs", "es"), id="catalog-editor-title")]),
            html.Div(
                className="catalog-stack",
                children=[
                    html.Div(
                        className="subpanel",
                        children=[
                            html.Div(className="section-head", children=[html.H4(tr("workbench.catalogs.inverters", "es"), id="inverter-editor-title"), html.Button(tr("workbench.add_row", "es"), id="add-inverter-row-btn", n_clicks=0, className="action-btn tertiary")]),
                            _catalog_table("inverter-table-editor"),
                        ],
                    ),
                    html.Div(
                        className="subpanel",
                        children=[
                            html.Div(className="section-head", children=[html.H4(tr("workbench.catalogs.batteries", "es"), id="battery-editor-title"), html.Button(tr("workbench.add_row", "es"), id="add-battery-row-btn", n_clicks=0, className="action-btn tertiary")]),
                            _catalog_table("battery-table-editor"),
                        ],
                    ),
                ],
            ),
        ],
    )
