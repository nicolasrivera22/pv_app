from __future__ import annotations

from dash import dcc, dash_table, html

from services.economics_tables import economics_editor_dropdowns
from services.i18n import tr

from .collapsible_section import collapsible_section


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
        style_cell_conditional=[
            {"if": {"column_id": "amount_COP"}, "textAlign": "right"},
            {"if": {"column_id": "value"}, "textAlign": "right"},
        ],
        tooltip_delay=0,
        tooltip_duration=None,
        tooltip_header={},
    )


def _economics_layers_panel(
    *,
    section_id: str,
    title_id: str,
    lang: str,
    title: str,
    note: str,
    copy: str,
    add_button_id: str,
    add_button_label: str,
    table,
) -> html.Details:
    return collapsible_section(
        section_id=section_id,
        summary_id=f"{section_id}-summary",
        title_id=title_id,
        title=title,
        open=False,
        title_level="h4",
        variant="secondary",
        class_name="subpanel economics-editor-panel economics-layer-section",
        body_class_name="economics-editor-panel-body",
        body=[
            html.Div(
                className="section-head economics-editor-panel-head",
                children=[
                    html.Div(
                        className="economics-editor-panel-copy",
                        children=[
                            html.P(note, className="section-copy economics-editor-panel-note"),
                        ],
                    ),
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
            html.Div(className="economics-table-wrap economics-table-wrap-dense", children=[table]),
        ],
    )


def _economics_presets_panel(*, lang: str) -> html.Details:
    return collapsible_section(
        section_id="economics-presets-shell",
        summary_id="economics-presets-summary",
        title_id="economics-presets-title",
        title=tr("workspace.admin.economics.presets.title", lang),
        open=False,
        title_level="h4",
        variant="subdued",
        class_name="subpanel economics-presets-shell",
        body_class_name="economics-presets-body",
        body=[
            html.P(
                tr("workspace.admin.economics.presets.copy", lang),
                id="economics-presets-copy",
                className="section-copy economics-editor-panel-note",
            ),
            html.Div(
                className="economics-preset-chip-row",
                children=[
                    html.Span(
                        "",
                        id="economics-preset-origin-badge",
                        className="workbench-state-chip workbench-state-chip-info",
                    ),
                    html.Span(
                        "",
                        id="economics-preset-match-badge",
                        className="workbench-state-chip workbench-state-chip-neutral",
                    ),
                ],
            ),
            html.Div(
                className="economics-preset-grid",
                children=[
                    html.Div(
                        className="economics-candidate-control",
                        children=[
                            html.Label(
                                tr("workspace.admin.economics.presets.selector.label", lang),
                                htmlFor="economics-preset-dropdown",
                                className="input-label",
                            ),
                            dcc.Dropdown(
                                id="economics-preset-dropdown",
                                options=[],
                                value=None,
                                clearable=True,
                                placeholder=tr("workspace.admin.economics.presets.selector.placeholder", lang),
                            ),
                        ],
                    ),
                    html.Div(
                        className="economics-preset-name-control",
                        children=[
                            html.Label(
                                tr("workspace.admin.economics.presets.name.label", lang),
                                htmlFor="economics-preset-name-input",
                                className="input-label",
                            ),
                            dcc.Input(
                                id="economics-preset-name-input",
                                type="text",
                                value="",
                                placeholder=tr("workspace.admin.economics.presets.name.placeholder", lang),
                                className="text-input",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(id="economics-preset-summary", className="economics-preset-summary"),
            html.Div(id="economics-preset-helper", className="status-line economics-preset-helper"),
            html.Div(
                className="controls economics-preset-actions",
                children=[
                    html.Button(
                        tr("workspace.admin.economics.presets.apply", lang),
                        id="apply-economics-preset-btn",
                        n_clicks=0,
                        className="action-btn tertiary",
                    ),
                    html.Button(
                        tr("workspace.admin.economics.presets.save_current", lang),
                        id="save-economics-preset-btn",
                        n_clicks=0,
                        className="action-btn tertiary",
                    ),
                    html.Button(
                        tr("workspace.admin.economics.presets.duplicate", lang),
                        id="duplicate-economics-preset-btn",
                        n_clicks=0,
                        className="action-btn tertiary",
                    ),
                    html.Button(
                        tr("workspace.admin.economics.presets.rename", lang),
                        id="rename-economics-preset-btn",
                        n_clicks=0,
                        className="action-btn tertiary",
                    ),
                    html.Button(
                        tr("workspace.admin.economics.presets.delete", lang),
                        id="delete-economics-preset-btn",
                        n_clicks=0,
                        className="action-btn tertiary",
                    ),
                ],
            ),
            dcc.ConfirmDialog(
                id="economics-preset-delete-confirm",
                message=tr("workspace.admin.economics.presets.delete_confirm", lang),
            ),
        ],
    )


def economics_editor_section(*, lang: str = "es") -> html.Details:
    return collapsible_section(
        section_id="economics-editor-section",
        summary_id="economics-editor-summary",
        title_id="economics-editor-title",
        title=tr("workspace.admin.economics.title", lang),
        open=False,
        title_level="h3",
        variant="primary",
        class_name="panel secondary-panel economics-editor-section",
        body_class_name="economics-editor-body",
        body=[
            html.Div(
                tr("workspace.admin.economics.note", lang),
                id="economics-editor-note",
                className="section-copy section-copy-wide economics-editor-note",
            ),
            html.Div(
                className="catalog-stack economics-admin-stack",
                children=[
                    collapsible_section(
                        section_id="economics-preview-shell",
                        summary_id="economics-preview-summary",
                        title_id="economics-preview-title",
                        title=tr("workspace.admin.economics.preview.title", lang),
                        open=True,
                        title_level="h4",
                        variant="secondary",
                        class_name="subpanel economics-preview-shell",
                        body_class_name="economics-preview-body",
                        body=[
                            html.P(
                                tr("workspace.admin.economics.preview.copy", lang),
                                id="economics-preview-copy",
                                className="section-copy",
                            ),
                            html.Div(id="economics-preview-content", className="economics-preview-stack"),
                        ],
                    ),
                    collapsible_section(
                        section_id="admin-preview-candidate-shell",
                        summary_id="admin-preview-candidate-summary",
                        title_id="admin-preview-candidate-title",
                        title=tr("workspace.admin.economics.preview.selector.title", lang),
                        open=False,
                        title_level="h4",
                        variant="secondary",
                        class_name="subpanel economics-candidate-shell",
                        body_class_name="economics-candidate-body",
                        body=[
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
                    _economics_presets_panel(lang=lang),
                    html.Div(
                        id="economics-editors-shell",
                        className="economics-editors-shell",
                        children=[
                            html.Div(id="economics-editors-gate-note", className="status-line economics-editors-gate-note"),
                            html.Div(
                                id="economics-editors-panels",
                                className="economics-editors-panels",
                                children=[
                                    _economics_layers_panel(
                                        section_id="economics-cost-items-details",
                                        title_id="economics-cost-items-title",
                                        lang=lang,
                                        title=tr("workspace.admin.economics.cost_items.title", lang),
                                        note=tr("workspace.admin.economics.cost_items.note", lang),
                                        copy=tr("workspace.admin.economics.cost_items.copy", lang),
                                        add_button_id="add-economics-cost-row-btn",
                                        add_button_label=tr("workbench.profiles.add_row", lang),
                                        table=_economics_table("economics-cost-items-editor", table_kind="economics_cost_items", lang=lang),
                                    ),
                                    _economics_layers_panel(
                                        section_id="economics-tax-items-details",
                                        title_id="economics-tax-items-title",
                                        lang=lang,
                                        title=tr("workspace.admin.economics.tax_items.title", lang),
                                        note=tr("workspace.admin.economics.tax_items.note", lang),
                                        copy=tr("workspace.admin.economics.tax_items.copy", lang),
                                        add_button_id="add-economics-tax-row-btn",
                                        add_button_label=tr("workbench.profiles.add_row", lang),
                                        table=_economics_table("economics-tax-items-editor", table_kind="economics_price_items", lang=lang),
                                    ),
                                    _economics_layers_panel(
                                        section_id="economics-adjustment-items-details",
                                        title_id="economics-adjustment-items-title",
                                        lang=lang,
                                        title=tr("workspace.admin.economics.adjustment_items.title", lang),
                                        note=tr("workspace.admin.economics.adjustment_items.note", lang),
                                        copy=tr("workspace.admin.economics.adjustment_items.copy", lang),
                                        add_button_id="add-economics-adjustment-row-btn",
                                        add_button_label=tr("workbench.profiles.add_row", lang),
                                        table=_economics_table("economics-adjustment-items-editor", table_kind="economics_price_items", lang=lang),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    collapsible_section(
                        section_id="economics-compatibility-shell",
                        summary_id="economics-compatibility-summary",
                        title_id="economics-compatibility-title",
                        title=tr("workspace.admin.economics.bridge.compat.title", lang),
                        open=False,
                        title_level="h4",
                        variant="subdued",
                        class_name="economics-compatibility-shell economics-collapsible-section",
                        summary_class_name="economics-collapsible-summary economics-compatibility-summary",
                        body_id="economics-compatibility-body",
                        body_class_name="economics-collapsible-body economics-compatibility-body",
                        summary_text=tr("workspace.admin.economics.bridge.compat.summary", lang),
                        summary_text_id="economics-compatibility-summary-copy",
                        summary_accessory=html.Span(
                            tr("workspace.admin.economics.bridge.summary.none", lang),
                            id="economics-compatibility-compact-status",
                            className="workbench-state-chip workbench-state-chip-neutral economics-compatibility-status-chip",
                        ),
                        body=[
                            html.P(
                                tr("workspace.admin.economics.bridge.compat.copy", lang),
                                id="economics-compatibility-copy",
                                className="section-copy economics-compatibility-body-copy",
                            ),
                            html.Div(
                                id="economics-compatibility-cta-row",
                                className="economics-compatibility-cta-row",
                                children=[
                                    html.Button(
                                        tr("workspace.admin.economics.bridge.button", lang),
                                        id="economics-bridge-btn",
                                        n_clicks=0,
                                        className="action-btn tertiary profile-inline-btn",
                                    ),
                                ],
                            ),
                            html.Div(id="economics-bridge-cta-note", className="status-line economics-bridge-cta-note"),
                            html.Div(id="economics-bridge-status-shell", className="economics-bridge-status-shell"),
                        ],
                    ),
                ],
            ),
        ],
    )
