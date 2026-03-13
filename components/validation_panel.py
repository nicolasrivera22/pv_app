from __future__ import annotations

from dash import html


def render_validation_panel(issues) -> html.Div:
    if not issues:
        return html.Div("No validation messages.", className="validation-empty")
    items = []
    for issue in issues:
        color = "#9f1239" if issue.level == "error" else "#92400e"
        items.append(html.Li(f"{issue.level.upper()} [{issue.field}] {issue.message}", style={"color": color}))
    return html.Div(html.Ul(items, style={"margin": 0, "paddingLeft": "1.2rem"}), className="validation-box")
