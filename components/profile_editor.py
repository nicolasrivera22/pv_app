from __future__ import annotations

from dash import dcc, dash_table, html

from services.i18n import tr


def _profile_table(table_id: str, *, page_size: int = 8) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        editable=True,
        row_deletable=False,
        sort_action="native",
        page_size=page_size,
        style_table={"overflowX": "auto"},
        style_cell={"padding": "0.4rem", "fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": 12},
        style_header={"backgroundColor": "#ede9fe", "fontWeight": "bold"},
        tooltip_delay=0,
        tooltip_duration=None,
        tooltip_header={},
    )


def _profile_title(title_key: str, title_id: str, tooltip_key: str, tooltip_id: str) -> html.Div:
    return html.Div(
        className="profile-table-title",
        children=[
            html.H4(tr(title_key, "es"), id=title_id),
            html.Span(
                className="field-help",
                children=[
                    html.Span("ⓘ", className="field-help-trigger", tabIndex=0),
                    html.Span(tr(tooltip_key, "es"), id=tooltip_id, className="field-help-tooltip"),
                ],
            ),
        ],
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
            ),
        ],
    )


def _profile_panel(
    card_id: str,
    title_key: str,
    title_id: str,
    tooltip_key: str,
    tooltip_id: str,
    table_id: str,
    *,
    panel_id: str | None = None,
    panel_class_name: str = "",
    page_size: int = 8,
    add_row_button_id: str | None = None,
    placeholder_id: str | None = None,
) -> html.Div:
    activator = html.Button(
        tr("workbench.profiles.preview_chart", "es"),
        id={"type": "profile-table-activate", "table": table_id},
        n_clicks=0,
        className="action-btn tertiary profile-table-activator",
        type="button",
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
    action_children = [activator]
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
        _profile_table(table_id, page_size=page_size),
    ]
    if placeholder_id is not None:
        panel_children.append(
            html.Div(id=placeholder_id, className="profile-table-placeholder", style={"display": "none"})
        )
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
                    _profile_panel(
                        "demand-profile-weights-card",
                        "workbench.profiles.demand_weights",
                        "demand-profile-weights-title",
                        "workbench.profiles.tooltip.demand_weights",
                        "demand-profile-weights-tooltip",
                        "demand-profile-weights-editor",
                        panel_id="demand-profile-weights-panel",
                        panel_class_name="profile-main-panel profile-main-panel-wide",
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
                        add_row_button_id="add-price-kwp-row-btn",
                        placeholder_id="price-kwp-placeholder",
                    ),
                    _profile_panel(
                        "price-kwp-others-card",
                        "workbench.profiles.price_others",
                        "price-kwp-others-title",
                        "workbench.profiles.tooltip.price_others",
                        "price-kwp-others-tooltip",
                        "price-kwp-others-editor",
                        panel_id="price-kwp-others-panel",
                        add_row_button_id="add-price-kwp-others-row-btn",
                        placeholder_id="price-kwp-others-placeholder",
                    ),
                    _profile_panel(
                        "demand-profile-card",
                        "workbench.profiles.demand_weekday",
                        "demand-profile-title",
                        "workbench.profiles.tooltip.demand_weekday",
                        "demand-profile-tooltip",
                        "demand-profile-editor",
                        panel_id="demand-profile-panel",
                    ),
                    _profile_panel(
                        "demand-profile-general-card",
                        "workbench.profiles.demand_general",
                        "demand-profile-general-title",
                        "workbench.profiles.tooltip.demand_general",
                        "demand-profile-general-tooltip",
                        "demand-profile-general-editor",
                        panel_id="demand-profile-general-panel",
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
