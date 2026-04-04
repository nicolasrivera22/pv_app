from __future__ import annotations

from dash import dcc, html, register_page

from components import demand_profile_module, run_scan_choice_dialog
from components.workspace_frame import workspace_frame
import services.workspace_admin_callbacks as _workspace_admin_callbacks  # noqa: F401
import services.workspace_assumptions_callbacks as _workspace_assumptions_callbacks  # noqa: F401
import services.workspace_shared_callbacks as _workspace_shared_callbacks  # noqa: F401


register_page(__name__, path="/assumptions", name="Supuestos")


ASSUMPTIONS_SUBTAB_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "minHeight": "3rem",
    "padding": "0.85rem 1.2rem",
    "borderRadius": "16px",
    "border": "1px solid rgba(203, 213, 225, 0.95)",
    "background": "rgba(255, 255, 255, 0.82)",
    "color": "#475569",
    "fontWeight": 700,
    "letterSpacing": "0.01em",
    "boxShadow": "inset 0 1px 0 rgba(255, 255, 255, 0.88)",
    "transition": "transform 140ms ease, border-color 140ms ease, background-color 140ms ease, color 140ms ease, box-shadow 140ms ease",
}

ASSUMPTIONS_SUBTAB_SELECTED_STYLE = {
    **ASSUMPTIONS_SUBTAB_STYLE,
    "background": "linear-gradient(180deg, rgba(37, 99, 235, 0.2) 0%, rgba(219, 234, 254, 0.98) 100%)",
    "color": "#1d4ed8",
    "fontWeight": 800,
    "border": "1px solid rgba(37, 99, 235, 0.92)",
    "boxShadow": "0 0 0 2px rgba(37, 99, 235, 0.14), 0 14px 28px rgba(37, 99, 235, 0.18)",
    "transform": "translateY(-1px)",
}


layout = workspace_frame(
    page_class_name="page-advanced-host",
    grid_class_name="workbench-grid-advanced-host",
    stores=[
        dcc.Store(id="run-scan-choice-state", storage_type="memory", data={"open": False, "suggested_project_name": ""}),
        dcc.Store(id="assumptions-draft-meta", storage_type="memory", data={}),
        dcc.Store(id="active-profile-table-state", storage_type="memory", data={"table_id": None}),
        dcc.Store(
            id="admin-preview-candidate-key",
            storage_type="memory",
            data={"scenario_id": None, "candidate_key": None, "source": None},
        ),
        dcc.Store(
            id="admin-financial-preset-selection",
            storage_type="memory",
            data={"preset_id": None},
        ),
        dcc.Store(
            id="admin-financial-preset-meta",
            storage_type="memory",
            data={"revision": 0, "message_key": None, "tone": "neutral"},
        ),
        dcc.Store(id="admin-draft-meta", storage_type="memory", data={}),
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
            id="assumptions-advanced-tools-entry-shell",
            className="assumptions-advanced-tools-entry-shell",
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
                            style=ASSUMPTIONS_SUBTAB_STYLE,
                            selected_style=ASSUMPTIONS_SUBTAB_SELECTED_STYLE,
                            children=[html.Div(id="assumptions-sections", className="assumptions-tab-body")],
                        ),
                        dcc.Tab(
                            id="assumptions-demand-tab",
                            label="Demanda",
                            value="demand",
                            className="assumptions-subtab",
                            selected_className="assumptions-subtab-selected",
                            style=ASSUMPTIONS_SUBTAB_STYLE,
                            selected_style=ASSUMPTIONS_SUBTAB_SELECTED_STYLE,
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
        html.Div(
            id="advanced-tools",
            className="panel secondary-panel assumptions-advanced-section",
            children=[
                html.Div(
                    className="section-head",
                    children=[html.H3("Herramientas avanzadas", id="assumptions-advanced-tools-title")],
                ),
                html.P("", id="assumptions-advanced-tools-copy", className="section-copy section-copy-wide"),
                html.Div(id="assumptions-advanced-tools-shell", className="assumptions-advanced-tools-shell"),
            ],
        ),
    ],
)
