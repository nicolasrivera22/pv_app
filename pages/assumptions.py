from __future__ import annotations

from dash import dcc, html, register_page

from components import demand_profile_module, run_scan_choice_dialog
from components.workspace_frame import workspace_frame
import services.workspace_assumptions_callbacks as _workspace_assumptions_callbacks  # noqa: F401
import services.workspace_shared_callbacks as _workspace_shared_callbacks  # noqa: F401


register_page(__name__, path="/assumptions", name="Supuestos")


layout = workspace_frame(
    stores=[
        dcc.Store(id="run-scan-choice-state", storage_type="memory", data={"open": False}),
        dcc.Store(id="assumptions-draft-meta", storage_type="memory", data={}),
    ],
    children=[
        run_scan_choice_dialog(),
        html.Div(
            className="panel",
            children=[
                html.Div(
                    className="section-head",
                    children=[html.H2("Supuestos", id="assumptions-page-title")],
                ),
                html.P("", id="assumptions-page-copy", className="section-copy section-copy-wide"),
                html.Div(
                    className="controls",
                    children=[
                        dcc.Checklist(id="assumptions-show-all", value=[]),
                        html.Button("", id="apply-assumptions-btn", n_clicks=0, className="action-btn"),
                        html.Button("", id="run-assumptions-scan-btn", n_clicks=0, className="action-btn secondary"),
                    ],
                ),
                html.Div("", id="assumptions-run-progress", className="status-line", style={"display": "none"}),
            ],
        ),
        html.Div(
            className="panel",
            children=[
                html.H3("", id="assumptions-validation-title"),
                html.Div(id="assumptions-validation"),
            ],
        ),
        html.Div(
            className="panel assumption-editor-panel",
            children=[
                dcc.Tabs(
                    id="assumptions-subtabs",
                    value="general",
                    className="assumptions-subtabs",
                    parent_className="assumptions-subtabs-shell",
                    children=[
                        dcc.Tab(
                            id="assumptions-general-tab",
                            label="Generales",
                            value="general",
                            className="assumptions-subtab",
                            selected_className="assumptions-subtab-selected",
                            children=[html.Div(id="assumptions-sections", className="assumptions-tab-body")],
                        ),
                        dcc.Tab(
                            id="assumptions-demand-tab",
                            label="Demanda",
                            value="demand",
                            className="assumptions-subtab",
                            selected_className="assumptions-subtab-selected",
                            children=[
                                html.Div(
                                    className="assumptions-tab-body assumptions-demand-body",
                                    children=[
                                        html.Div(
                                            className="section-head",
                                            children=[html.H3("Demanda", id="assumptions-demand-title")],
                                        ),
                                        html.P("", id="assumptions-demand-copy", className="section-copy section-copy-wide"),
                                        demand_profile_module(
                                            id_prefix="assumptions",
                                            include_overview_chart=True,
                                            include_inline_relative_chart=False,
                                            show_activators=False,
                                        ),
                                    ],
                                )
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ],
)
