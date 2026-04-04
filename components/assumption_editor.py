from __future__ import annotations

from dash import dcc, html

from services.i18n import tr
from .collapsible_section import collapsible_section


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


def _assumption_input(field: dict, *, input_id_type: str):
    component_id = {"type": input_id_type, "field": field["field"]}
    kind = field["kind"]
    if kind == "dropdown":
        return dcc.Dropdown(
            id=component_id,
            options=field["options"],
            value=field["value"],
            clearable=False,
            className="text-input",
            disabled=field.get("disabled", False),
        )
    if field.get("currency_input"):
        input_control = dcc.Input(
            id=component_id,
            type="text",
            value=_format_thousands(field["value"]),
            className="text-input text-input-affixed currency-text-input",
            inputMode="numeric",
            debounce=True,
            disabled=field.get("disabled", False),
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
            disabled=field.get("disabled", False),
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
    return dcc.Input(
        id=component_id,
        type="text",
        value=field["value"],
        className="text-input",
        disabled=field.get("disabled", False),
    )


def _field_card(field: dict, *, field_card_type: str, input_id_type: str, extra_class: str = "") -> html.Div:
    help_icon = html.Span(
        className="field-help",
        children=[
            html.Span("ⓘ", className="field-help-trigger", tabIndex=0),
            html.Span(field["help"], className="field-help-tooltip"),
        ],
    )
    children = [
        html.Label([field["label"], help_icon], className="input-label"),
        _assumption_input(field, input_id_type=input_id_type),
    ]
    unit = html.Div(field["unit"], className="scenario-meta") if field.get("kind") != "number" and field.get("unit") else None
    if unit is not None:
        children.append(unit)
    classes = ["field-card"]
    if extra_class:
        classes.append(extra_class)
    if field.get("disabled"):
        classes.append("field-card-disabled")
    if field.get("emphasize") and not field.get("disabled"):
        classes.append("field-card-highlight")
    css = " ".join(dict.fromkeys(classes))
    return html.Div(id={"type": field_card_type, "field": field["field"]}, className=css, children=children)


_PRECIOS_ROW1_FIELDS = ["pricing_mode", "include_hw_in_price", "include_var_others"]
_PRECIOS_ROW2_FIELDS = ["price_total_COP", "price_others_total"]


def _section_slug(section: dict) -> str:
    return (
        str(section.get("group_key") or section.get("group") or "section")
        .strip()
        .lower()
        .replace(" ", "-")
        .replace("_", "-")
    )


def _advanced_fields_block(
    section: dict,
    advanced_fields: list[dict],
    *,
    show_all: bool,
    advanced_label: str,
    input_id_type: str,
    field_card_type: str,
) -> html.Div | html.Details:
    advanced_grid = html.Div(
        className="assumption-grid",
        children=[
            _field_card(
                field,
                field_card_type=field_card_type,
                input_id_type=input_id_type,
            )
            for field in advanced_fields
        ],
    )
    if show_all:
        return advanced_grid
    slug = _section_slug(section)
    return collapsible_section(
        section_id=f"{slug}-advanced-details",
        summary_id=f"{slug}-advanced-summary",
        title_id=f"{slug}-advanced-title",
        title=advanced_label,
        open=False,
        title_level="h5",
        variant="secondary",
        class_name="subpanel advanced-details assumption-advanced-details",
        body_class_name="assumption-advanced-body",
        body=[advanced_grid],
    )


def _section_content_blocks(
    section: dict,
    *,
    show_all: bool,
    advanced_label: str,
    input_id_type: str,
    field_card_type: str,
    context_note_type: str,
) -> list:
    basic_fields = section.get("basic", [])
    advanced_fields = section.get("advanced", [])
    blocks: list = []
    if section.get("help"):
        blocks.append(html.P(section["help"], className="section-copy"))
    if section.get("context_note_id"):
        note_group = section.get("group_key", section.get("group", ""))
        blocks.append(
            html.Div(
                section.get("context_note", ""),
                id={"type": context_note_type, "group": note_group},
                className="assumption-context-note",
                style={"display": "block"} if section.get("context_note") else {"display": "none"},
            )
        )
    if basic_fields:
        blocks.append(
            html.Div(
                className="assumption-grid",
                children=[
                    _field_card(
                        field,
                        field_card_type=field_card_type,
                        input_id_type=input_id_type,
                    )
                    for field in basic_fields
                ],
            )
        )
    if advanced_fields:
        blocks.append(
            _advanced_fields_block(
                section,
                advanced_fields,
                show_all=show_all,
                advanced_label=advanced_label,
                input_id_type=input_id_type,
                field_card_type=field_card_type,
            )
        )
    return blocks


def _render_precios_section(
    section: dict,
    *,
    show_all: bool,
    advanced_label: str,
    input_id_type: str,
    field_card_type: str,
    context_note_type: str,
    collapsible_groups: bool,
    group_open_defaults: dict[str, bool] | None,
    section_id_prefix: str,
) -> html.Div:
    """Render the Precios section with a custom two-row layout."""
    all_fields = section.get("basic", []) + section.get("advanced", [])
    row1_fields = []
    row2_fields = []
    other_fields = []

    for field in all_fields:
        if field["field"] in _PRECIOS_ROW1_FIELDS:
            row1_fields.append(field)
        elif field["field"] in _PRECIOS_ROW2_FIELDS:
            row2_fields.append(field)
        else:
            other_fields.append(field)

    row1_fields.sort(key=lambda f: _PRECIOS_ROW1_FIELDS.index(f["field"]) if f["field"] in _PRECIOS_ROW1_FIELDS else 99)
    row2_fields.sort(key=lambda f: _PRECIOS_ROW2_FIELDS.index(f["field"]) if f["field"] in _PRECIOS_ROW2_FIELDS else 99)

    blocks: list = []
    if section.get("help"):
        blocks.append(html.P(section["help"], className="section-copy"))
    if section.get("context_note_id"):
        note_group = section.get("group_key", section.get("group", ""))
        blocks.append(
                    html.Div(
                        section.get("context_note", ""),
                        id={"type": context_note_type, "group": note_group},
                        className="assumption-context-note",
                        style={"display": "block"} if section.get("context_note") else {"display": "none"},
                    )
                )
    if row1_fields:
        blocks.append(
            html.Div(
                className="precios-row precios-row-1",
                children=[
                    _field_card(
                        f,
                        field_card_type=field_card_type,
                        input_id_type=input_id_type,
                        extra_class="precios-card",
                    )
                    for f in row1_fields
                ],
            )
        )
    if row2_fields:
        row2_cards = []
        for f in row2_fields:
            row2_cards.append(
                _field_card(
                    f,
                    field_card_type=field_card_type,
                    input_id_type=input_id_type,
                    extra_class="precios-card",
                )
            )
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
                children=[
                    _field_card(
                        f,
                        field_card_type=field_card_type,
                        input_id_type=input_id_type,
                    )
                    for f in other_fields
                ],
            )
        )
    if not collapsible_groups:
        return html.Div(className="subpanel", children=[html.H4(section["group"]), *blocks])
    slug = _section_slug(section)
    open_default = bool((group_open_defaults or {}).get(str(section.get("group_key") or section.get("group")), False))
    return collapsible_section(
        section_id=f"{section_id_prefix}-{slug}-section",
        summary_id=f"{section_id_prefix}-{slug}-summary",
        title_id=f"{section_id_prefix}-{slug}-title",
        title=section["group"],
        open=open_default,
        title_level="h4",
        variant="secondary",
        class_name="subpanel assumption-group-section",
        body_class_name="assumption-group-body",
        body=blocks,
    )


def render_assumption_sections(
    sections: list[dict],
    *,
    show_all: bool = False,
    empty_message: str,
    advanced_label: str,
    input_id_type: str = "assumption-input",
    field_card_type: str = "assumption-field-card",
    context_note_type: str = "assumption-context-note",
    collapsible_groups: bool = False,
    group_open_defaults: dict[str, bool] | None = None,
    section_id_prefix: str = "assumption-group",
) -> list[html.Div]:
    if not sections:
        return [html.Div(className="validation-empty", children=empty_message)]

    children: list[html.Div] = []
    for section in sections:
        if section.get("group_key") == "Precios":
            children.append(
                _render_precios_section(
                    section,
                    show_all=show_all,
                    advanced_label=advanced_label,
                    input_id_type=input_id_type,
                    field_card_type=field_card_type,
                    context_note_type=context_note_type,
                    collapsible_groups=collapsible_groups,
                    group_open_defaults=group_open_defaults,
                    section_id_prefix=section_id_prefix,
                )
            )
            continue

        blocks = _section_content_blocks(
            section,
            show_all=show_all,
            advanced_label=advanced_label,
            input_id_type=input_id_type,
            field_card_type=field_card_type,
            context_note_type=context_note_type,
        )
        if not collapsible_groups:
            children.append(html.Div(className="subpanel", children=[html.H4(section["group"]), *blocks]))
            continue
        slug = _section_slug(section)
        open_default = bool((group_open_defaults or {}).get(str(section.get("group_key") or section.get("group")), False))
        children.append(
            collapsible_section(
                section_id=f"{section_id_prefix}-{slug}-section",
                summary_id=f"{section_id_prefix}-{slug}-summary",
                title_id=f"{section_id_prefix}-{slug}-title",
                title=section["group"],
                open=open_default,
                title_level="h4",
                variant="secondary",
                class_name="subpanel assumption-group-section",
                body_class_name="assumption-group-body",
                body=blocks,
            )
        )
    return children


def assumption_editor_section() -> html.Div:
    return html.Div(
        className="panel assumption-editor-panel",
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
