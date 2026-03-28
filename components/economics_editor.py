from __future__ import annotations

from dash import dash_table, html

from services.i18n import tr


def _economics_table(table_id: str) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=True,
        row_deletable=True,
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


def _definition_card(title_key: str, copy_key: str, *, lang: str, card_id: str) -> html.Div:
    return html.Div(
        id=card_id,
        className="field-card economics-definition-card",
        children=[
            html.H4(tr(title_key, lang)),
            html.P(tr(copy_key, lang), className="section-copy"),
        ],
    )


def _flow_step(title_key: str, copy_key: str, *, lang: str, step_id: str) -> html.Div:
    return html.Div(
        id=step_id,
        className="subpanel economics-flow-card",
        children=[
            html.H4(tr(title_key, lang)),
            html.P(tr(copy_key, lang), className="section-copy"),
        ],
    )


def economics_editor_section(*, lang: str = "es") -> html.Div:
    return html.Div(
        className="panel secondary-panel",
        children=[
            html.Div(className="section-head", children=[html.H3(tr("workspace.admin.economics.title", lang), id="economics-editor-title")]),
            html.Div(tr("workspace.admin.economics.note", lang), id="economics-editor-note", className="section-copy section-copy-wide"),
            html.Div(
                id="economics-definition-grid",
                className="economics-definition-grid",
                children=[
                    _definition_card(
                        "workspace.admin.economics.definition.technical.title",
                        "workspace.admin.economics.definition.technical.copy",
                        lang=lang,
                        card_id="economics-definition-technical",
                    ),
                    _definition_card(
                        "workspace.admin.economics.definition.installed.title",
                        "workspace.admin.economics.definition.installed.copy",
                        lang=lang,
                        card_id="economics-definition-installed",
                    ),
                    _definition_card(
                        "workspace.admin.economics.definition.commercial.title",
                        "workspace.admin.economics.definition.commercial.copy",
                        lang=lang,
                        card_id="economics-definition-commercial",
                    ),
                    _definition_card(
                        "workspace.admin.economics.definition.final.title",
                        "workspace.admin.economics.definition.final.copy",
                        lang=lang,
                        card_id="economics-definition-final",
                    ),
                ],
            ),
            html.Div(
                id="economics-flow-shell",
                className="subpanel economics-flow-shell",
                children=[
                    html.Div(className="section-head", children=[html.H4(tr("workspace.admin.economics.flow.title", lang), id="economics-flow-title")]),
                    html.Div(
                        id="economics-flow-grid",
                        className="economics-flow-grid",
                        children=[
                            _flow_step(
                                "workspace.admin.economics.flow.technical.title",
                                "workspace.admin.economics.flow.technical.copy",
                                lang=lang,
                                step_id="economics-flow-technical",
                            ),
                            _flow_step(
                                "workspace.admin.economics.flow.installed.title",
                                "workspace.admin.economics.flow.installed.copy",
                                lang=lang,
                                step_id="economics-flow-installed",
                            ),
                            _flow_step(
                                "workspace.admin.economics.flow.commercial.title",
                                "workspace.admin.economics.flow.commercial.copy",
                                lang=lang,
                                step_id="economics-flow-commercial",
                            ),
                            _flow_step(
                                "workspace.admin.economics.flow.final.title",
                                "workspace.admin.economics.flow.final.copy",
                                lang=lang,
                                step_id="economics-flow-final",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="catalog-stack economics-table-stack",
                children=[
                    html.Div(
                        className="subpanel",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[
                                    html.H4(tr("workspace.admin.economics.cost_items.title", lang), id="economics-cost-items-title"),
                                    html.Div(
                                        className="profile-table-actions",
                                        children=[
                                            html.Button(
                                                tr("workspace.admin.economics.sync_hardware", lang),
                                                id="sync-economics-hardware-costs-btn",
                                                n_clicks=0,
                                                className="action-btn tertiary profile-inline-btn",
                                                disabled=True,
                                                style={"display": "none"},
                                            ),
                                            html.Button(
                                                tr("workbench.profiles.add_row", lang),
                                                id="add-economics-cost-row-btn",
                                                n_clicks=0,
                                                className="action-btn tertiary profile-inline-btn",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.P(tr("workspace.admin.economics.cost_items.copy", lang), id="economics-cost-items-copy", className="section-copy"),
                            _economics_table("economics-cost-items-editor"),
                        ],
                    ),
                    html.Div(
                        className="subpanel",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[
                                    html.H4(tr("workspace.admin.economics.price_items.title", lang), id="economics-price-items-title"),
                                    html.Button(
                                        tr("workbench.profiles.add_row", lang),
                                        id="add-economics-price-row-btn",
                                        n_clicks=0,
                                        className="action-btn tertiary profile-inline-btn",
                                    ),
                                ],
                            ),
                            html.P(tr("workspace.admin.economics.price_items.copy", lang), id="economics-price-items-copy", className="section-copy"),
                            _economics_table("economics-price-items-editor"),
                        ],
                    ),
                ],
            ),
        ],
    )
