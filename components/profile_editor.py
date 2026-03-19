from __future__ import annotations

from dash import dash_table, html

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


def _profile_panel(
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
) -> html.Div:
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
    class_name = " ".join(part for part in ["subpanel", panel_class_name] if part)
    head_children = [_profile_title(title_key, title_id, tooltip_key, tooltip_id)]
    if button is not None:
        head_children.append(button)
    div_kwargs = {"className": class_name}
    if panel_id is not None:
        div_kwargs["id"] = panel_id
    return html.Div(
        **div_kwargs,
        children=[
            html.Div(
                className="section-head profile-table-head",
                children=head_children,
            ),
            _profile_table(table_id, page_size=page_size),
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
                        "workbench.profiles.month",
                        "month-profile-title",
                        "workbench.profiles.tooltip.month",
                        "month-profile-tooltip",
                        "month-profile-editor",
                        panel_class_name="profile-main-panel",
                        page_size=12,
                    ),
                    _profile_panel(
                        "workbench.profiles.sun",
                        "sun-profile-title",
                        "workbench.profiles.tooltip.sun",
                        "sun-profile-tooltip",
                        "sun-profile-editor",
                        panel_class_name="profile-main-panel",
                        page_size=12,
                    ),
                    _profile_panel(
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
            html.Div(
                id="profile-secondary-grid",
                className="profile-secondary-grid",
                children=[
                    _profile_panel(
                        "workbench.profiles.price",
                        "price-kwp-title",
                        "workbench.profiles.tooltip.price",
                        "price-kwp-tooltip",
                        "price-kwp-editor",
                        panel_id="price-kwp-panel",
                        add_row_button_id="add-price-kwp-row-btn",
                    ),
                    _profile_panel(
                        "workbench.profiles.price_others",
                        "price-kwp-others-title",
                        "workbench.profiles.tooltip.price_others",
                        "price-kwp-others-tooltip",
                        "price-kwp-others-editor",
                        panel_id="price-kwp-others-panel",
                        add_row_button_id="add-price-kwp-others-row-btn",
                    ),
                    _profile_panel(
                        "workbench.profiles.demand_weekday",
                        "demand-profile-title",
                        "workbench.profiles.tooltip.demand_weekday",
                        "demand-profile-tooltip",
                        "demand-profile-editor",
                        panel_id="demand-profile-panel",
                    ),
                    _profile_panel(
                        "workbench.profiles.demand_general",
                        "demand-profile-general-title",
                        "workbench.profiles.tooltip.demand_general",
                        "demand-profile-general-tooltip",
                        "demand-profile-general-editor",
                        panel_id="demand-profile-general-panel",
                    ),
                ],
            ),
        ],
    )
