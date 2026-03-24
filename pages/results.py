from __future__ import annotations

from dash import dcc, html, register_page

from components import candidate_explorer_section, selected_candidate_deep_dive_section
from components.workspace_frame import workspace_frame
import services.workspace_results_callbacks as _workspace_results_callbacks  # noqa: F401
import services.workspace_shared_callbacks as _workspace_shared_callbacks  # noqa: F401


register_page(__name__, path="/", name="Resultados")


layout = workspace_frame(
    stores=[
        dcc.Download(id="scenario-download"),
        dcc.Store(id="workbench-latest-export-folder", storage_type="memory", data=""),
        dcc.Store(id="candidate-horizon-context", storage_type="memory", data={}),
    ],
    children=[
        html.Div(
            className="panel",
            children=[
                html.Div(
                    className="section-head",
                    children=[html.H2("Resultados", id="results-page-title")],
                ),
                html.P("", id="results-page-copy", className="section-copy section-copy-wide"),
            ],
        ),
        html.Div(id="results-status-digest", className="panel results-status-digest", style={"display": "none"}),
        html.Div(
            id="results-main-content",
            children=[
                html.Div(
                    id="deterministic-results-area",
                    children=[candidate_explorer_section(), selected_candidate_deep_dive_section()],
                ),
            ],
        ),
    ],
)
