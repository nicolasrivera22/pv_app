from __future__ import annotations

from dash import dcc, html

from services.i18n import tr


def _format_thousands(value) -> str:
    """Format a numeric value with thousand separators for display."""
    if value is None:
        return ""
    try:
        num = float(str(value).replace(",", ""))
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.0f}"
    except (ValueError, TypeError):
        return str(value)


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
    if field.get("currency_input"):
        input_control = dcc.Input(
            id=component_id,
            type="text",
            value=_format_thousands(field["value"]),
            className="text-input text-input-affixed currency-text-input",
            inputMode="numeric",
            debounce=True,
        )
        if field.get("suffix"):
            return html.Div(
                className="assumption-input-shell",
                children=[
                    input_control,
                    html.Span(field["suffix"], className="input-affix"),
                ],
            )
        return input_control
    if kind == "number":
        input_control = dcc.Input(
            id=component_id,
            type="number",
            value=field["value"],
            step=field.get("input_step"),
            min=field.get("min"),
            max=field.get("max"),
            className="text-input text-input-affixed" if field.get("suffix") else "text-input",
        )
        if field.get("suffix"):
            return html.Div(
                className="assumption-input-shell",
                children=[
                    input_control,
                    html.Span(field["suffix"], className="input-affix"),
                ],
            )
        return input_control
    return dcc.Input(id=component_id, type="text", value=field["value"], className="text-input")


def _field_card(field: dict, *, extra_class: str = "") -> html.Div:
    help_icon = html.Span(
        className="field-help",
        children=[
            html.Span("ⓘ", className="field-help-trigger", tabIndex=0),
            html.Span(field["help"], className="field-help-tooltip"),
        ],
    )
    children = [
        html.Label([field["label"], help_icon], className="input-label"),
        _assumption_input(field),
    ]
    unit = html.Div(field["unit"], className="scenario-meta") if field.get("kind") != "number" and field.get("unit") else None
    if unit is not None:
        children.append(unit)
    css = "field-card"
    if extra_class:
        css = f"field-card {extra_class}"
    return html.Div(className=css, children=children)


_PRECIOS_ROW1_FIELDS = ["pricing_mode", "include_hw_in_price", "include_var_others"]
_PRECIOS_ROW2_FIELDS = ["price_total_COP", "price_others_total"]


def _render_precios_section(section: dict, *, show_all: bool, advanced_label: str) -> html.Div:
    """Render the Precios section with a custom two-row layout."""
    all_fields = section.get("basic", []) + section.get("advanced", [])
    row1_fields = []
    row2_fields = []
    other_fields = []

    pricing_mode = "variable"
    for field in all_fields:
        if field["field"] == "pricing_mode":
            pricing_mode = str(field.get("value", "variable")).strip().lower()
        if field["field"] in _PRECIOS_ROW1_FIELDS:
            row1_fields.append(field)
        elif field["field"] in _PRECIOS_ROW2_FIELDS:
            row2_fields.append(field)
        else:
            other_fields.append(field)

    row1_fields.sort(key=lambda f: _PRECIOS_ROW1_FIELDS.index(f["field"]) if f["field"] in _PRECIOS_ROW1_FIELDS else 99)
    row2_fields.sort(key=lambda f: _PRECIOS_ROW2_FIELDS.index(f["field"]) if f["field"] in _PRECIOS_ROW2_FIELDS else 99)

    blocks: list = [html.H4(section["group"])]
    if section.get("help"):
        blocks.append(html.P(section["help"], className="section-copy"))
    if row1_fields:
        blocks.append(
            html.Div(
                className="precios-row precios-row-1",
                children=[_field_card(f, extra_class="precios-card") for f in row1_fields],
            )
        )
    if row2_fields:
        disabled_total = pricing_mode == "variable"
        row2_cards = []
        for f in row2_fields:
            extra = "precios-card"
            if f["field"] == "price_total_COP" and disabled_total:
                extra = "precios-card field-card-disabled"
            row2_cards.append(_field_card(f, extra_class=extra))
        blocks.append(
            html.Div(
                className="precios-row precios-row-2",
                children=row2_cards,
            )
        )
    if other_fields:
        blocks.append(
            html.Div(
                className="assumption-grid",
                children=[_field_card(f) for f in other_fields],
            )
        )
    return html.Div(className="subpanel", children=blocks)


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
        if section.get("group_key") == "Precios":
            children.append(_render_precios_section(section, show_all=show_all, advanced_label=advanced_label))
            continue

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
