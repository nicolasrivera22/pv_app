from __future__ import annotations

from dash import Input, Output, callback, html, register_page

from services.i18n import tr
from services.runtime_paths import bundled_quick_guide_path


register_page(__name__, path="/help", name="Help")


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def layout():
    guide_available = bundled_quick_guide_path().exists()
    return html.Div(
        className="page",
        children=[
            html.Div(
                className="main-stack",
                children=[
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[html.H2(tr("help.title", "es"), id="help-page-title")],
                            ),
                            html.P(tr("help.intro", "es"), id="help-page-intro", className="section-copy"),
                        ],
                    ),
                    html.Div(
                        className="panel",
                        children=[
                            html.Iframe(
                                id="help-quick-guide-frame",
                                src="/help/guia-rapida",
                                className="help-frame",
                                style={"display": "block" if guide_available else "none"},
                            ),
                            html.Div(
                                tr("help.missing", "es"),
                                id="help-missing-message",
                                className="help-empty",
                                style={"display": "none" if guide_available else "block"},
                            ),
                        ],
                    ),
                ],
            )
        ],
    )


@callback(
    Output("help-page-title", "children"),
    Output("help-page-intro", "children"),
    Output("help-missing-message", "children"),
    Input("language-selector", "value"),
)
def translate_help_page(language_value):
    lang = _lang(language_value)
    return (
        tr("help.title", lang),
        tr("help.intro", lang),
        tr("help.missing", lang),
    )
