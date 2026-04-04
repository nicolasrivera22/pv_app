from __future__ import annotations

from dash import html


_TITLE_COMPONENTS = {
    "h3": html.H3,
    "h4": html.H4,
    "h5": html.H5,
}


def collapsible_section(
    *,
    section_id: str,
    summary_id: str,
    title_id: str,
    title: str,
    body,
    open: bool = False,
    title_level: str = "h3",
    variant: str = "primary",
    class_name: str = "",
    summary_class_name: str = "",
    body_id: str | None = None,
    body_class_name: str = "",
    summary_text: str | None = None,
    summary_text_id: str | None = None,
    summary_accessory=None,
):
    title_tag = _TITLE_COMPONENTS.get(title_level, html.H3)
    classes = " ".join(
        part
        for part in (
            class_name,
            "ui-collapsible-section",
            f"ui-collapsible-{variant}",
        )
        if part
    )
    summary_classes = " ".join(
        part
        for part in (
            "ui-collapsible-summary",
            summary_class_name,
        )
        if part
    )
    body_classes = " ".join(
        part
        for part in (
            "ui-collapsible-body",
            body_class_name,
        )
        if part
    )
    summary_copy_children = [title_tag(title, id=title_id)]
    if summary_text:
        summary_copy_children.append(
            html.P(
                summary_text,
                id=summary_text_id,
                className="ui-collapsible-summary-text",
            )
        )
    return html.Details(
        id=section_id,
        className=classes,
        open=open,
        children=[
            html.Summary(
                id=summary_id,
                className=summary_classes,
                children=[
                    html.Div(
                        className="ui-collapsible-summary-main",
                        children=[
                            html.Span(
                                className="ui-collapsible-caret",
                                **{"aria-hidden": "true"},
                            ),
                            html.Div(
                                className="ui-collapsible-summary-copy",
                                children=summary_copy_children,
                            ),
                            *(
                                [
                                    html.Div(
                                        className="ui-collapsible-summary-accessory",
                                        children=[summary_accessory],
                                    )
                                ]
                                if summary_accessory is not None
                                else []
                            ),
                        ],
                    )
                ],
            ),
            html.Div(
                **({"id": body_id} if body_id is not None else {}),
                className=body_classes,
                children=body,
            ),
        ],
    )
