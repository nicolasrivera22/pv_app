from __future__ import annotations

from dash import dcc, dash_table, html

from services.i18n import tr


def _component_id(id_prefix: str | None, base_id: str) -> str:
    prefix = str(id_prefix or "").strip()
    return f"{prefix}-{base_id}" if prefix else base_id


def _profile_table(
    table_id: str,
    *,
    page_size: int = 8,
    row_deletable: bool = False,
    editable: bool = True,
    hidden_columns: list[str] | None = None,
    style_data_conditional: list[dict] | None = None,
) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=editable,
        row_deletable=row_deletable,
        sort_action="native",
        page_size=page_size,
        hidden_columns=hidden_columns or [],
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
        style_data_conditional=style_data_conditional or [],
        tooltip_delay=0,
        tooltip_duration=None,
        tooltip_header={},
    )


def _profile_title(title_key: str, title_id: str, tooltip_key: str | None = None, tooltip_id: str | None = None) -> html.Div:
    children = [html.H4(tr(title_key, "es"), id=title_id)]
    if tooltip_key and tooltip_id:
        children.append(
            html.Span(
                className="field-help",
                children=[
                    html.Span("ⓘ", className="field-help-trigger", tabIndex=0),
                    html.Span(tr(tooltip_key, "es"), id=tooltip_id, className="field-help-tooltip"),
                ],
            )
        )
    return html.Div(
        className="profile-table-title",
        children=children,
    )


def _profile_chart_panel(
    *,
    panel_id: str,
    title_id: str,
    subtitle_id: str,
    graph_id: str,
) -> html.Div:
    return html.Div(
        id=panel_id,
        className="subpanel profile-chart-panel",
        style={"display": "none"},
        children=[
            html.Div(
                className="profile-chart-head",
                children=[
                    html.H4("", id=title_id),
                    html.P("", id=subtitle_id, className="section-copy profile-chart-subtitle"),
                ],
            ),
            dcc.Graph(
                id=graph_id,
                className="profile-chart-graph",
                figure={},
                config={"displayModeBar": False, "responsive": True},
                responsive=True,
                style={"height": "380px", "minHeight": "380px"},
            ),
        ],
    )


def _profile_panel(
    card_id: str,
    title_key: str,
    title_id: str,
    tooltip_key: str | None,
    tooltip_id: str | None,
    table_id: str,
    *,
    panel_id: str | None = None,
    panel_class_name: str = "",
    page_size: int = 8,
    add_row_button_id: str | None = None,
    placeholder_id: str | None = None,
    row_deletable: bool = False,
    editable: bool = True,
    hidden_columns: list[str] | None = None,
    style_data_conditional: list[dict] | None = None,
    show_activator: bool = True,
    extra_children: list | None = None,
) -> html.Div:
    activator = (
        html.Button(
            tr("workbench.profiles.preview_chart", "es"),
            id={"type": "profile-table-activate", "table": table_id},
            n_clicks=0,
            className="action-btn tertiary profile-table-activator",
            type="button",
        )
        if show_activator
        else None
    )
    button = (
        html.Button(
            tr("workbench.profiles.add_row", "es"),
            id=add_row_button_id,
            n_clicks=0,
            className="action-btn tertiary profile-inline-btn",
        )
        if add_row_button_id
        else None
    )
    class_name = " ".join(part for part in ["subpanel", "profile-table-card", panel_class_name] if part)
    action_children = [activator] if activator is not None else []
    if button is not None:
        action_children.append(button)
    head_children = [
        _profile_title(title_key, title_id, tooltip_key, tooltip_id),
        html.Div(className="profile-table-actions", children=action_children),
    ]
    panel_children = [
        html.Div(
            className="section-head profile-table-head",
            children=head_children,
        ),
        _profile_table(
            table_id,
            page_size=page_size,
            row_deletable=row_deletable,
            editable=editable,
            hidden_columns=hidden_columns,
            style_data_conditional=style_data_conditional,
        ),
    ]
    if placeholder_id is not None:
        panel_children.append(
            html.Div(id=placeholder_id, className="profile-table-placeholder", style={"display": "none"})
        )
    if extra_children:
        panel_children.extend(extra_children)
    div_kwargs = {"className": class_name}
    if panel_id is not None:
        div_kwargs["id"] = panel_id
    return html.Div(
        id=card_id,
        className="profile-table-card-shell",
        children=[
            html.Div(
                **div_kwargs,
                children=panel_children,
            ),
        ],
    )


def _profile_subsection(title_id: str, table_id: str, *, copy_id: str | None = None, page_size: int = 8) -> html.Div:
    children = [html.H5("", id=title_id)]
    if copy_id is not None:
        children.append(html.P("", id=copy_id, className="section-copy profile-preview-copy"))
    children.append(_profile_table(table_id, page_size=page_size, editable=False))
    return html.Div(className="profile-table-subsection", children=children)


def demand_profile_module(
    *,
    id_prefix: str | None = None,
    include_overview_chart: bool = False,
    include_inline_relative_chart: bool = True,
    show_activators: bool = True,
) -> html.Div:
    mode_panel_id = _component_id(id_prefix, "demand-profile-mode-panel")
    mode_title_id = _component_id(id_prefix, "demand-profile-mode-title")
    mode_copy_id = _component_id(id_prefix, "demand-profile-mode-copy")
    mode_selector_id = _component_id(id_prefix, "demand-profile-mode-selector")
    mode_note_id = _component_id(id_prefix, "demand-profile-mode-note")
    control_strip_id = _component_id(id_prefix, "demand-profile-control-strip")
    energy_shell_id = _component_id(id_prefix, "demand-profile-energy-shell")

    weights_panel_id = _component_id(id_prefix, "demand-profile-weights-panel")
    weights_card_id = _component_id(id_prefix, "demand-profile-weights-card")
    weights_title_id = _component_id(id_prefix, "demand-profile-weights-title")
    weights_tooltip_id = _component_id(id_prefix, "demand-profile-weights-tooltip")
    weights_table_id = _component_id(id_prefix, "demand-profile-weights-editor")
    relative_grid_id = _component_id(id_prefix, "demand-profile-relative-grid")
    weights_preview_card_id = _component_id(id_prefix, "demand-profile-weights-preview-card")
    weights_preview_panel_id = _component_id(id_prefix, "demand-profile-weights-preview-panel")
    type_label_id = _component_id(id_prefix, "demand-profile-type-label")
    type_shell_id = _component_id(id_prefix, "demand-profile-type-shell")
    type_selector_id = _component_id(id_prefix, "demand-profile-type-selector")
    alpha_shell_id = _component_id(id_prefix, "demand-profile-alpha-shell")
    alpha_label_id = _component_id(id_prefix, "demand-profile-alpha-label")
    alpha_slider_id = _component_id(id_prefix, "demand-profile-alpha-slider")
    energy_label_id = _component_id(id_prefix, "demand-profile-energy-label")
    energy_input_id = _component_id(id_prefix, "demand-profile-energy-input")
    weights_preview_title_id = _component_id(id_prefix, "demand-profile-weights-preview-title")
    weights_preview_copy_id = _component_id(id_prefix, "demand-profile-weights-preview-copy")
    weights_preview_table_id = _component_id(id_prefix, "demand-profile-weights-preview-editor")
    relative_chart_shell_id = _component_id(id_prefix, "demand-profile-relative-chart-shell")
    relative_chart_title_id = _component_id(id_prefix, "demand-profile-relative-chart-title")
    relative_chart_copy_id = _component_id(id_prefix, "demand-profile-relative-chart-copy")
    relative_chart_id = _component_id(id_prefix, "demand-profile-relative-chart")

    weekday_card_id = _component_id(id_prefix, "demand-profile-card")
    weekday_panel_id = _component_id(id_prefix, "demand-profile-panel")
    weekday_title_id = _component_id(id_prefix, "demand-profile-title")
    weekday_tooltip_id = _component_id(id_prefix, "demand-profile-tooltip")
    weekday_table_id = _component_id(id_prefix, "demand-profile-editor")

    total_card_id = _component_id(id_prefix, "demand-profile-general-card")
    total_panel_id = _component_id(id_prefix, "demand-profile-general-panel")
    total_title_id = _component_id(id_prefix, "demand-profile-general-title")
    total_tooltip_id = _component_id(id_prefix, "demand-profile-general-tooltip")
    total_table_id = _component_id(id_prefix, "demand-profile-general-editor")

    preview_card_id = _component_id(id_prefix, "demand-profile-general-preview-card")
    preview_panel_id = _component_id(id_prefix, "demand-profile-general-preview-panel")
    preview_title_id = _component_id(id_prefix, "demand-profile-general-preview-title")
    preview_table_id = _component_id(id_prefix, "demand-profile-general-preview-editor")
    secondary_grid_id = _component_id(id_prefix, "demand-profile-secondary-grid")

    overview_chart_panel_id = _component_id(id_prefix, "demand-profile-chart-panel")
    overview_chart_title_id = _component_id(id_prefix, "demand-profile-chart-title")
    overview_chart_subtitle_id = _component_id(id_prefix, "demand-profile-chart-subtitle")
    overview_chart_graph_id = _component_id(id_prefix, "demand-profile-chart-graph")

    relative_children: list = []
    if include_inline_relative_chart:
        relative_children.append(
            html.Div(
                id=relative_chart_shell_id,
                className="profile-chart-panel demand-profile-inline-chart",
                children=[
                    html.Div(
                        className="profile-chart-head",
                        children=[
                            html.H4("", id=relative_chart_title_id),
                            html.P("", id=relative_chart_copy_id, className="section-copy profile-chart-subtitle"),
                        ],
                    ),
                    dcc.Graph(
                        id=relative_chart_id,
                        className="profile-chart-graph",
                        figure={},
                        config={"displayModeBar": False, "responsive": True},
                        responsive=True,
                        style={"height": "380px", "minHeight": "380px"},
                    ),
                ],
            )
        )

    children: list = [
        html.Div(
            id=mode_panel_id,
            className="subpanel demand-profile-mode-panel",
            children=[
                html.Div(
                    className="section-head demand-profile-mode-head",
                    children=[html.H4(tr("workbench.profiles.mode.title", "es"), id=mode_title_id)],
                ),
                html.P(tr("workbench.profiles.mode.copy", "es"), id=mode_copy_id, className="section-copy"),
                dcc.RadioItems(
                    id=mode_selector_id,
                    className="demand-profile-mode-selector",
                    labelClassName="demand-profile-mode-option",
                    inputClassName="demand-profile-mode-input",
                    options=[],
                    value="perfil general",
                ),
                html.Div(tr("workbench.profiles.mode.note.total", "es"), id=mode_note_id, className="profile-mode-note"),
            ],
        ),
        html.Div(
            id=control_strip_id,
            className="demand-profile-relative-controls",
            children=[
                html.Div(
                    className="demand-profile-control-grid",
                    children=[
                        html.Div(
                            id=energy_shell_id,
                            className="field-card demand-profile-control-card",
                            children=[
                                html.Label(tr("workbench.profiles.relative.energy", "es"), id=energy_label_id, className="input-label"),
                                dcc.Input(
                                    id=energy_input_id,
                                    type="number",
                                    value=0,
                                    min=0,
                                    step=1,
                                    className="text-input",
                                ),
                            ],
                        ),
                        html.Div(
                            id=alpha_shell_id,
                            className="field-card demand-profile-control-card",
                            children=[
                                html.Label(tr("workbench.profiles.relative.alpha", "es"), id=alpha_label_id, className="input-label"),
                                dcc.Slider(
                                    id=alpha_slider_id,
                                    min=0,
                                    max=1,
                                    step=0.05,
                                    value=0.5,
                                    marks=None,
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                            ],
                        ),
                        html.Div(
                            id=type_shell_id,
                            className="field-card demand-profile-control-card",
                            children=[
                                html.Label(tr("workbench.profiles.relative.type", "es"), id=type_label_id, className="input-label"),
                                dcc.RadioItems(
                                    id=type_selector_id,
                                    className="demand-profile-type-selector",
                                    labelClassName="demand-profile-type-option",
                                    inputClassName="demand-profile-type-input",
                                    options=[],
                                    value="mixta",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        html.Div(
            id=relative_grid_id,
            className="profile-secondary-grid demand-profile-secondary-grid",
            children=[
                _profile_panel(
                    weights_card_id,
                    "workbench.profiles.demand_weights",
                    weights_title_id,
                    "workbench.profiles.tooltip.demand_weights",
                    weights_tooltip_id,
                    weights_table_id,
                    panel_id=weights_panel_id,
                    panel_class_name="profile-main-panel",
                    page_size=24,
                    hidden_columns=["W_RES_BASE", "W_IND_BASE", "W_TOTAL", "TOTAL_kWh"],
                    show_activator=show_activators,
                    extra_children=relative_children,
                ),
                _profile_panel(
                    weights_preview_card_id,
                    "workbench.profiles.relative.preview",
                    weights_preview_title_id,
                    None,
                    None,
                    weights_preview_table_id,
                    panel_id=weights_preview_panel_id,
                    editable=False,
                    page_size=24,
                    show_activator=False,
                    extra_children=[
                        html.P("", id=weights_preview_copy_id, className="section-copy profile-preview-copy"),
                    ],
                ),
            ],
        ),
        html.Div(
            id=secondary_grid_id,
            className="profile-secondary-grid demand-profile-secondary-grid",
            children=[
                _profile_panel(
                    weekday_card_id,
                    "workbench.profiles.demand_weekday",
                    weekday_title_id,
                        "workbench.profiles.tooltip.demand_weekday",
                        weekday_tooltip_id,
                        weekday_table_id,
                        panel_id=weekday_panel_id,
                        page_size=24,
                        hidden_columns=["DOW"],
                        show_activator=show_activators,
                        style_data_conditional=[
                            {
                                "if": {"column_id": "TOTAL_kWh"},
                                "backgroundColor": "var(--color-surface-soft)",
                                "color": "var(--color-text-secondary)",
                                "fontWeight": "600",
                            }
                        ],
                ),
                _profile_panel(
                    total_card_id,
                    "workbench.profiles.demand_general",
                    total_title_id,
                        "workbench.profiles.tooltip.demand_general",
                        total_tooltip_id,
                        total_table_id,
                        panel_id=total_panel_id,
                        page_size=24,
                        show_activator=show_activators,
                        style_data_conditional=[
                            {
                                "if": {"column_id": "TOTAL_kWh"},
                                "backgroundColor": "var(--color-surface-soft)",
                                "color": "var(--color-text-secondary)",
                                "fontWeight": "600",
                            }
                        ],
                ),
                _profile_panel(
                    preview_card_id,
                    "workbench.profiles.demand_general_preview",
                    preview_title_id,
                    None,
                        None,
                        preview_table_id,
                        panel_id=preview_panel_id,
                        editable=False,
                        page_size=24,
                        show_activator=False,
                    ),
            ],
        ),
    ]
    if include_overview_chart:
        children.append(
            _profile_chart_panel(
                panel_id=overview_chart_panel_id,
                title_id=overview_chart_title_id,
                subtitle_id=overview_chart_subtitle_id,
                graph_id=overview_chart_graph_id,
            )
        )
    return html.Div(className="demand-profile-module", children=children)


def profile_editor_section() -> html.Div:
    return html.Div(
        className="panel secondary-panel",
        children=[
            html.Div(className="section-head", children=[html.H3(tr("workbench.profiles", "es"), id="profile-editor-title")]),
            html.Div(tr("workbench.profiles.note", "es"), id="profile-editor-note", className="section-copy section-copy-wide"),
            html.Div(
                id="profile-main-grid",
                className="profile-main-grid",
                children=[
                    _profile_panel(
                        "month-profile-card",
                        "workbench.profiles.month",
                        "month-profile-title",
                        "workbench.profiles.tooltip.month",
                        "month-profile-tooltip",
                        "month-profile-editor",
                        panel_class_name="profile-main-panel",
                        page_size=12,
                    ),
                    _profile_panel(
                        "sun-profile-card",
                        "workbench.profiles.sun",
                        "sun-profile-title",
                        "workbench.profiles.tooltip.sun",
                        "sun-profile-tooltip",
                        "sun-profile-editor",
                        panel_class_name="profile-main-panel",
                        page_size=12,
                    ),
                ],
            ),
            _profile_chart_panel(
                panel_id="profile-main-chart-panel",
                title_id="profile-main-chart-title",
                subtitle_id="profile-main-chart-subtitle",
                graph_id="profile-main-chart-graph",
            ),
            html.Div(
                id="profile-secondary-grid",
                className="profile-secondary-grid",
                children=[
                    _profile_panel(
                        "price-kwp-card",
                        "workbench.profiles.price",
                        "price-kwp-title",
                        "workbench.profiles.tooltip.price",
                        "price-kwp-tooltip",
                        "price-kwp-editor",
                        panel_id="price-kwp-panel",
                        panel_class_name="profile-secondary-pricing-panel",
                        add_row_button_id="add-price-kwp-row-btn",
                        placeholder_id="price-kwp-placeholder",
                        row_deletable=True,
                    ),
                    _profile_panel(
                        "price-kwp-others-card",
                        "workbench.profiles.price_others",
                        "price-kwp-others-title",
                        "workbench.profiles.tooltip.price_others",
                        "price-kwp-others-tooltip",
                        "price-kwp-others-editor",
                        panel_id="price-kwp-others-panel",
                        panel_class_name="profile-secondary-pricing-panel",
                        add_row_button_id="add-price-kwp-others-row-btn",
                        placeholder_id="price-kwp-others-placeholder",
                        row_deletable=True,
                    ),
                ],
            ),
            html.Div(
                id="profile-demand-relocated-card",
                className="subpanel demand-relocated-card",
                children=[
                    html.H4(tr("workspace.assumptions.demand.title", "es"), id="profile-demand-relocated-title"),
                    html.P(tr("workspace.admin.demand_moved.copy", "es"), id="profile-demand-relocated-copy", className="section-copy"),
                    dcc.Link(
                        tr("workspace.admin.demand_moved.link", "es"),
                        id="profile-demand-relocated-link",
                        href="/assumptions",
                        className="action-btn tertiary",
                    ),
                ],
            ),
            _profile_chart_panel(
                panel_id="profile-secondary-chart-panel",
                title_id="profile-secondary-chart-title",
                subtitle_id="profile-secondary-chart-subtitle",
                graph_id="profile-secondary-chart-graph",
            ),
        ],
    )
