from __future__ import annotations

import dash_cytoscape as cyto
from dash import html

from services.i18n import tr
from services.schematic import (
    SchematicInspector,
    SchematicLegendItem,
    build_schematic_legend,
    default_schematic_inspector,
)


CYTOSCAPE_STYLESHEET = [
    {
        "selector": "node",
        "style": {
            "width": 190,
            "height": 110,
            "padding": "14px",
            "font-family": "IBM Plex Sans, Segoe UI, sans-serif",
            "font-size": 11,
            "font-weight": 600,
            "text-wrap": "wrap",
            "text-max-width": 165,
            "text-valign": "center",
            "text-halign": "center",
            "color": "#0f172a",
            "border-width": 3,
            "border-color": "#cbd5e1",
            "background-color": "#ffffff",
        },
    },
    {"selector": ".role-pv", "style": {"shape": "hexagon", "background-color": "#fef3c7", "border-color": "#f59e0b"}},
    {"selector": ".role-inverter", "style": {"shape": "round-rectangle", "background-color": "#dbeafe", "border-color": "#2563eb"}},
    {"selector": ".role-battery", "style": {"shape": "ellipse", "background-color": "#ede9fe", "border-color": "#7c3aed"}},
    {"selector": ".role-load", "style": {"shape": "round-rectangle", "background-color": "#dcfce7", "border-color": "#16a34a"}},
    {"selector": ".role-grid", "style": {"shape": "diamond", "background-color": "#e2e8f0", "border-color": "#475569"}},
    {
        "selector": "edge",
        "style": {
            "curve-style": "straight",
            "width": 3,
            "line-color": "#64748b",
            "target-arrow-color": "#64748b",
            "target-arrow-shape": "triangle",
            "arrow-scale": 1.1,
            "font-size": 10,
            "font-weight": 700,
            "label": "data(label)",
            "text-background-opacity": 1,
            "text-background-color": "#ffffff",
            "text-background-padding": "3px",
            "color": "#334155",
        },
    },
    {"selector": ".edge-pv-link", "style": {"line-color": "#f59e0b", "target-arrow-color": "#f59e0b"}},
    {"selector": ".edge-battery-dc", "style": {"line-color": "#7c3aed", "target-arrow-color": "#7c3aed"}},
    {"selector": ".edge-battery-ac", "style": {"line-color": "#0f766e", "target-arrow-color": "#0f766e", "line-style": "dashed"}},
    {"selector": ".edge-ac-link", "style": {"line-color": "#2563eb", "target-arrow-color": "#2563eb"}},
    {"selector": ".edge-grid-link", "style": {"line-color": "#475569", "target-arrow-color": "#475569"}},
    {
        "selector": ":selected",
        "style": {
            "border-color": "#b91c1c",
            "border-width": 4,
        },
    },
]


def render_schematic_legend(items: tuple[SchematicLegendItem, ...]) -> list[html.Div]:
    children: list[html.Div] = []
    for item in items:
        swatch_class = item.style_class
        if item.connection_type is None:
            swatch = html.Span(item.badge, className=f"legend-swatch legend-node {swatch_class}")
        else:
            swatch = html.Span(item.badge, className=f"legend-swatch legend-line {swatch_class}")
        children.append(
            html.Div(
                className="legend-item",
                children=[
                    swatch,
                    html.Span(item.label),
                ],
            )
        )
    return children


def render_schematic_inspector(inspector: SchematicInspector) -> list[html.Div]:
    rows = [
        html.Div(
            className="inspector-row",
            children=[
                html.Span(row.label, className="inspector-label"),
                html.Span(row.value, className="inspector-value"),
            ],
        )
        for row in inspector.details
    ]
    children: list[html.Div] = [
        html.Div(inspector.title, className="inspector-focus-title"),
        html.P(inspector.description, className="inspector-description"),
    ]
    if rows:
        children.append(html.Div(className="inspector-list", children=rows))
    if inspector.representative_note:
        children.append(html.Div(inspector.representative_note, className="inspector-note"))
    return children


def unifilar_diagram_section() -> html.Div:
    default_legend = render_schematic_legend(build_schematic_legend("es"))
    default_inspector = render_schematic_inspector(default_schematic_inspector(None, "es"))
    return html.Div(
        className="panel",
        children=[
            html.Div(
                className="section-head",
                children=[html.H3(tr("workbench.schematic.title", "es"), id="unifilar-diagram-title")],
            ),
            html.Div(id="unifilar-diagram-summary", className="status-line schematic-summary-chip"),
            html.P(tr("workbench.schematic.empty", "es"), id="unifilar-diagram-empty", className="section-copy"),
            html.Div(
                className="subpanel",
                id="unifilar-diagram-shell",
                style={"display": "none"},
                children=[
                    html.Div(
                        className="schematic-layout",
                        children=[
                            html.Div(
                                className="schematic-main",
                                children=[
                                    cyto.Cytoscape(
                                        id="active-unifilar-diagram",
                                        layout={"name": "preset", "fit": True, "padding": 18},
                                        elements=[],
                                        stylesheet=CYTOSCAPE_STYLESHEET,
                                        style={"width": "100%", "height": "420px"},
                                        userZoomingEnabled=False,
                                        userPanningEnabled=False,
                                        boxSelectionEnabled=False,
                                        autoungrabify=True,
                                    ),
                                    html.P("", id="unifilar-diagram-note", className="section-copy schematic-note"),
                                ],
                            ),
                            html.Div(
                                className="schematic-side",
                                children=[
                                    html.Div(
                                        className="subpanel secondary-panel",
                                        children=[
                                            html.H4(tr("workbench.schematic.legend.title", "es"), id="unifilar-legend-title"),
                                            html.Div(id="unifilar-legend-items", className="legend-list", children=default_legend),
                                        ],
                                    ),
                                    html.Div(
                                        className="subpanel",
                                        children=[
                                            html.H4(tr("workbench.schematic.inspector.title", "es"), id="unifilar-inspector-title"),
                                            html.Div(id="unifilar-inspector-body", className="inspector-body", children=default_inspector),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            ),
        ],
    )
