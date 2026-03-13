from __future__ import annotations

from dash import html

from services.i18n import tr


def _pretty_field(field: str) -> str:
    if not field:
        return ""
    return field.replace("_", " ").strip()


def render_validation_panel(issues, *, lang: str = "es") -> html.Div:
    if not issues:
        return html.Div(tr("common.no_validation", lang), className="validation-empty")
    items = []
    for issue in issues:
        color = "#9f1239" if issue.level == "error" else "#92400e"
        level = "ERROR" if lang == "en" and issue.level == "error" else ("WARNING" if lang == "en" else ("ERROR" if issue.level == "error" else "ADVERTENCIA"))
        field = _pretty_field(issue.field)
        prefix = f"{level} [{field}] " if field else f"{level} "
        items.append(html.Li(f"{prefix}{issue.message}", style={"color": color}))
    return html.Div(html.Ul(items, style={"margin": 0, "paddingLeft": "1.2rem"}), className="validation-box")
