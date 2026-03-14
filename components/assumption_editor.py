from __future__ import annotations

from dash import dcc, html

from services.i18n import tr


def _assumption_input(field: dict):
    component_id = {"type": "assumption-input", "field": field["field"]}
    kind = field["kind"]
    if kind == "dropdown":
        return dcc.Dropdown(
            id=component_id,
            options=field["options"],
            value=field["value"],
            clearable=False,
            className="text-input",
        )
    if kind == "number":
        return dcc.Input(id=component_id, type="number", value=field["value"], className="text-input")
    return dcc.Input(id=component_id, type="text", value=field["value"], className="text-input")


def _field_card(field: dict) -> html.Div:
    help_icon = html.Span(
        className="field-help",
        children=[
            html.Span("ⓘ", className="field-help-trigger", tabIndex=0),
            html.Span(field["help"], className="field-help-tooltip"),
        ],
    )
    unit = html.Div(field["unit"], className="scenario-meta") if field.get("unit") else None
    children = [
        html.Label([field["label"], help_icon], className="input-label"),
        _assumption_input(field),
    ]
    if unit is not None:
        children.append(unit)
    return html.Div(className="field-card", children=children)


def render_assumption_sections(
    sections: list[dict],
    *,
    show_all: bool = False,
    empty_message: str,
    advanced_label: str,
) -> list[html.Div]:
    if not sections:
        return [html.Div(className="validation-empty", children=empty_message)]

    children: list[html.Div] = []
    for section in sections:
        basic_fields = section.get("basic", [])
        advanced_fields = section.get("advanced", [])
        blocks = [html.H4(section["group"])]
        if section.get("help"):
            blocks.append(html.P(section["help"], className="section-copy"))
        if basic_fields:
            blocks.append(
                html.Div(
                    className="assumption-grid",
                    children=[_field_card(field) for field in basic_fields],
                )
            )
        if advanced_fields:
            advanced_grid = html.Div(
                className="assumption-grid",
                children=[_field_card(field) for field in advanced_fields],
            )
            if show_all:
                blocks.append(advanced_grid)
            else:
                blocks.append(
                    html.Details(
                        className="subpanel advanced-details",
                        children=[
                            html.Summary(advanced_label),
                            advanced_grid,
                        ],
                    )
                )
        children.append(html.Div(className="subpanel", children=blocks))
    return children


def assumption_editor_section() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.Div(
                className="section-head",
                children=[
                    html.H3(tr("workbench.assumptions", "es"), id="assumption-editor-title"),
                    html.Div(
                        className="controls",
                        children=[
                            dcc.Checklist(
                                id="assumption-show-all",
                                value=[],
                                options=[{"label": tr("workbench.assumptions.show_all", "es"), "value": "all"}],
                            ),
                            html.Button(tr("workbench.assumptions.apply", "es"), id="apply-edits-btn", n_clicks=0, className="action-btn"),
                        ],
                    ),
                ],
            ),
            html.Div(id="assumption-sections", children=[html.Div(className="validation-empty", children=tr("workbench.assumptions.none", "es"))]),
        ],
    )
