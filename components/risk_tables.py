from __future__ import annotations

from dash import dash_table, html
import pandas as pd


def risk_tables_section() -> html.Div:
    return html.Div(
        className="compare-grid",
        children=[
            html.Div(
                className="panel",
                children=[
                    html.H3(id="risk-metadata-title"),
                    html.Div(id="risk-metadata-table"),
                    html.Div(id="risk-warnings"),
                    html.P(id="risk-payback-note", className="scenario-meta"),
                    html.P(id="risk-payback-band-note", className="scenario-meta"),
                ],
            ),
            html.Div(
                className="panel",
                children=[
                    html.H3(id="risk-percentiles-title"),
                    dash_table.DataTable(
                        id="risk-percentile-table",
                        data=[],
                        columns=[],
                        sort_action="native",
                        page_size=10,
                        style_table={"overflowX": "auto"},
                        style_cell={"padding": "0.45rem", "fontFamily": "monospace", "fontSize": 12},
                        style_header={"backgroundColor": "#e2e8f0", "fontWeight": "bold"},
                    ),
                ],
            ),
        ],
    )


def render_metadata_table(frame: pd.DataFrame) -> html.Div:
    if frame.empty:
        return html.Div(className="validation-empty")
    rows = []
    for row in frame.to_dict("records"):
        rows.append(
            html.Div(
                className="rename-row",
                children=[
                    html.Div(row["label"], className="scenario-meta"),
                    html.Div(str(row["value"])),
                ],
            )
        )
    return html.Div(rows)


def render_message_list(messages: list[str], *, empty_message: str | None = None) -> html.Div:
    if not messages:
        return html.Div(empty_message or "", className="validation-empty")
    return html.Ul([html.Li(message) for message in messages], style={"margin": 0, "paddingLeft": "1.2rem"})
