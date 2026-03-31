from __future__ import annotations

from dash import dcc, dash_table, html

from services.economics_tables import economics_editor_dropdowns
from services.i18n import tr


def _economics_table(
    table_id: str,
    *,
    table_kind: str,
    lang: str,
    editable: bool = True,
    row_deletable: bool = True,
) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=editable,
        row_deletable=row_deletable,
        dropdown=economics_editor_dropdowns(table_kind, lang=lang),
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


def _economics_layers_details(
    *,
    details_id: str,
    summary_id: str,
    lang: str,
    title: str,
    note: str,
    copy: str,
    add_button_id: str,
    add_button_label: str,
    table,
) -> html.Details:
    return html.Details(
        id=details_id,
        open=True,
        className="subpanel economics-editor-details",
        children=[
            html.Summary(
                id=summary_id,
                className="economics-editor-details-summary",
                children=[
                    html.Div(
                        className="economics-editor-details-head",
                        children=[
                            html.Div(
                                className="economics-editor-details-title-wrap",
                                children=[
                                    html.H4(title),
                                    html.P(note, className="section-copy economics-editor-details-note"),
                                ],
                            ),
                            html.Span(tr("workspace.admin.economics.layers.toggle", lang), className="economics-editor-details-pill"),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="economics-editor-details-body",
                children=[
                    html.Div(
                        className="section-head",
                        children=[
                            html.H4(title),
                            html.Div(
                                className="profile-table-actions",
                                children=[
                                    html.Button(
                                        add_button_label,
                                        id=add_button_id,
                                        n_clicks=0,
                                        className="action-btn tertiary profile-inline-btn",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.P(copy, className="section-copy"),
                    table,
                ],
            ),
        ],
    )


def economics_editor_section(*, lang: str = "es") -> html.Div:
    return html.Div(
        className="panel secondary-panel",
        children=[
            html.Div(className="section-head", children=[html.H3(tr("workspace.admin.economics.title", lang), id="economics-editor-title")]),
            html.Div(tr("workspace.admin.economics.note", lang), id="economics-editor-note", className="section-copy section-copy-wide economics-editor-note"),
            html.Div(
                className="catalog-stack economics-admin-stack",
                children=[
                    html.Div(
                        id="economics-preview-shell",
                        className="subpanel economics-preview-shell",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[html.H4(tr("workspace.admin.economics.preview.title", lang), id="economics-preview-title")],
                            ),
                            html.P(tr("workspace.admin.economics.preview.copy", lang), id="economics-preview-copy", className="section-copy"),
                            html.Div(
                                id="admin-preview-candidate-shell",
                                className="subpanel economics-candidate-shell",
                                children=[
                                    html.Div(
                                        className="section-head",
                                        children=[html.H5(tr("workspace.admin.economics.preview.selector.title", lang), id="admin-preview-candidate-title")],
                                    ),
                                    html.P(
                                        tr("workspace.admin.economics.preview.selector.copy", lang),
                                        id="admin-preview-candidate-copy",
                                        className="section-copy",
                                    ),
                                    html.Div(
                                        className="economics-candidate-grid",
                                        children=[
                                            html.Div(
                                                className="economics-candidate-control",
                                                children=[
                                                    html.Label(
                                                        tr("workspace.admin.economics.preview.selector.label", lang),
                                                        htmlFor="admin-preview-candidate-dropdown",
                                                        className="input-label",
                                                    ),
                                                    dcc.Dropdown(
                                                        id="admin-preview-candidate-dropdown",
                                                        options=[],
                                                        value=None,
                                                        clearable=False,
                                                        placeholder=tr("workspace.admin.economics.preview.selector.placeholder", lang),
                                                    ),
                                                ],
                                            ),
                                            html.Div(id="admin-preview-candidate-meta", className="economics-candidate-meta"),
                                        ],
                                    ),
                                    html.Div(
                                        id="admin-preview-candidate-helper",
                                        className="status-line economics-candidate-helper",
                                    ),
                                ],
                            ),
                            html.Div(id="economics-preview-content", className="economics-preview-stack"),
                        ],
                    ),
                    _economics_layers_details(
                        details_id="economics-cost-items-details",
                        summary_id="economics-cost-items-summary",
                        lang=lang,
                        title=tr("workspace.admin.economics.cost_items.title", lang),
                        note=tr("workspace.admin.economics.cost_items.note", lang),
                        copy=tr("workspace.admin.economics.cost_items.copy", lang),
                        add_button_id="add-economics-cost-row-btn",
                        add_button_label=tr("workbench.profiles.add_row", lang),
                        table=_economics_table("economics-cost-items-editor", table_kind="economics_cost_items", lang=lang),
                    ),
                    _economics_layers_details(
                        details_id="economics-tax-items-details",
                        summary_id="economics-tax-items-summary",
                        lang=lang,
                        title=tr("workspace.admin.economics.tax_items.title", lang),
                        note=tr("workspace.admin.economics.tax_items.note", lang),
                        copy=tr("workspace.admin.economics.tax_items.copy", lang),
                        add_button_id="add-economics-tax-row-btn",
                        add_button_label=tr("workbench.profiles.add_row", lang),
                        table=_economics_table("economics-tax-items-editor", table_kind="economics_price_items", lang=lang),
                    ),
                    _economics_layers_details(
                        details_id="economics-adjustment-items-details",
                        summary_id="economics-adjustment-items-summary",
                        lang=lang,
                        title=tr("workspace.admin.economics.adjustment_items.title", lang),
                        note=tr("workspace.admin.economics.adjustment_items.note", lang),
                        copy=tr("workspace.admin.economics.adjustment_items.copy", lang),
                        add_button_id="add-economics-adjustment-row-btn",
                        add_button_label=tr("workbench.profiles.add_row", lang),
                        table=_economics_table("economics-adjustment-items-editor", table_kind="economics_price_items", lang=lang),
                    ),
                    html.Div(
                        id="economics-compatibility-shell",
                        className="subpanel economics-compatibility-shell",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[
                                    html.H4(
                                        tr("workspace.admin.economics.bridge.compat.title", lang),
                                        id="economics-compatibility-title",
                                    ),
                                    html.Div(
                                        className="profile-table-actions",
                                        children=[
                                            html.Button(
                                                tr("workspace.admin.economics.bridge.button", lang),
                                                id="economics-bridge-btn",
                                                n_clicks=0,
                                                className="action-btn tertiary profile-inline-btn",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.P(
                                tr("workspace.admin.economics.bridge.compat.copy", lang),
                                id="economics-compatibility-copy",
                                className="section-copy",
                            ),
                            html.Div(id="economics-bridge-cta-note", className="status-line economics-bridge-cta-note"),
                            html.Div(id="economics-bridge-status-shell", className="economics-bridge-status-shell"),
                        ],
                    ),
                ],
            ),
        ],
    )
