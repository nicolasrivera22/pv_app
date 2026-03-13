from __future__ import annotations

from dash import html

from services.i18n import tr


def render_validation_panel(issues, *, lang: str = "es") -> html.Div:
    if not issues:
        return html.Div(tr("common.no_validation", lang), className="validation-empty")
    items = []
    for issue in issues:
        color = "#9f1239" if issue.level == "error" else "#92400e"
        items.append(html.Li(f"{issue.level.upper()} [{issue.field}] {issue.message}", style={"color": color}))
    return html.Div(html.Ul(items, style={"margin": 0, "paddingLeft": "1.2rem"}), className="validation-box")
