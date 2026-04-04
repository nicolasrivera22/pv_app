from __future__ import annotations

from dash import dash_table, html

from services.i18n import tr

from .collapsible_section import collapsible_section


def _catalog_table(table_id: str) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=True,
        row_deletable=True,
        filter_action="native",
        sort_action="native",
        page_size=8,
        style_table={"overflowX": "auto"},
        style_cell={
            "padding": "0.4rem",
            "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif",
            "fontSize": 12,
            "color": "var(--color-text-primary)",
        },
        style_header={
            "backgroundColor": "var(--color-primary-soft)",
            "color": "var(--color-text-primary)",
            "fontWeight": "bold",
        },
        tooltip_delay=0,
        tooltip_duration=None,
        tooltip_header={},
    )


def catalog_editor_section(*, lang: str = "es") -> html.Details:
    return collapsible_section(
        section_id="catalog-editor-section",
        summary_id="catalog-editor-summary",
        title_id="catalog-editor-title",
        title=tr("workbench.catalogs", lang),
        open=False,
        title_level="h3",
        variant="primary",
        class_name="panel secondary-panel catalog-editor-section",
        body_class_name="catalog-editor-body",
        body=html.Div(
            className="catalog-stack",
            children=[
                html.Div(
                    className="subpanel",
                    children=[
                        html.Div(className="section-head", children=[html.H4(tr("workbench.catalogs.inverters", lang), id="inverter-editor-title"), html.Button(tr("workbench.add_row", lang), id="add-inverter-row-btn", n_clicks=0, className="action-btn tertiary")]),
                        _catalog_table("inverter-table-editor"),
                    ],
                ),
                html.Div(
                    className="subpanel",
                    children=[
                        html.Div(className="section-head", children=[html.H4(tr("workbench.catalogs.batteries", lang), id="battery-editor-title"), html.Button(tr("workbench.add_row", lang), id="add-battery-row-btn", n_clicks=0, className="action-btn tertiary")]),
                        _catalog_table("battery-table-editor"),
                    ],
                ),
                html.Div(
                    className="subpanel",
                    children=[
                        html.Div(className="section-head", children=[html.H4(tr("workbench.catalogs.panels", lang), id="panel-editor-title"), html.Button(tr("workbench.add_row", lang), id="add-panel-row-btn", n_clicks=0, className="action-btn tertiary")]),
                        _catalog_table("panel-table-editor"),
                    ],
                ),
            ],
        ),
    )
