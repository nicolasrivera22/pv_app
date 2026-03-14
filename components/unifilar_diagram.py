from __future__ import annotations

import dash_cytoscape as cyto
from dash import dcc, html

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
            "label": "data(label)",
            "width": 196,
            "height": 138,
            "padding": "16px",
            "font-family": "IBM Plex Sans, Segoe UI, sans-serif",
            "font-size": 11,
            "font-weight": 600,
            "text-wrap": "wrap",
            "text-max-width": 150,
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": "-6px",
            "color": "#0f172a",
            "border-width": 2.5,
            "border-color": "#cbd5e1",
            "background-color": "#ffffff",
            "background-image": "data(icon_url)",
            "background-fit": "contain",
            "background-repeat": "no-repeat",
            "background-width": "48px",
            "background-height": "48px",
            "background-position-y": "28%",
            "overlay-opacity": 0,
        },
    },
    {"selector": ".role-pv", "style": {"shape": "round-rectangle", "background-color": "#fffbeb", "border-color": "#f59e0b"}},
    {"selector": ".role-inverter", "style": {"shape": "round-rectangle", "background-color": "#eff6ff", "border-color": "#2563eb"}},
    {"selector": ".role-battery", "style": {"shape": "round-rectangle", "background-color": "#f5f3ff", "border-color": "#7c3aed"}},
    {"selector": ".role-load", "style": {"shape": "round-rectangle", "background-color": "#f0fdf4", "border-color": "#16a34a"}},
    {"selector": ".role-grid", "style": {"shape": "round-rectangle", "background-color": "#e2e8f0", "border-color": "#1e293b", "border-width": 3.5}},
    {
        "selector": "edge",
        "style": {
            "curve-style": "straight",
            "width": 4,
            "line-color": "#64748b",
            "target-arrow-color": "#64748b",
            "target-arrow-shape": "triangle",
            "arrow-scale": 1.05,
            "font-size": 10,
            "font-weight": 700,
            "label": "data(label)",
            "text-background-opacity": 1,
            "text-background-color": "#ffffff",
            "text-background-padding": "3px",
            "color": "#334155",
            "text-rotation": "autorotate",
            "line-cap": "round",
        },
    },
    {"selector": ".edge-pv-link", "style": {"line-color": "#7c3aed", "target-arrow-color": "#7c3aed"}},
    {"selector": ".edge-battery-dc", "style": {"line-color": "#7c3aed", "target-arrow-color": "#7c3aed"}},
    {"selector": ".edge-battery-ac", "style": {"line-color": "#0f766e", "target-arrow-color": "#0f766e", "line-style": "dashed"}},
    {"selector": ".edge-ac-link", "style": {"line-color": "#2563eb", "target-arrow-color": "#2563eb"}},
    {"selector": ".edge-grid-link", "style": {"line-color": "#475569", "target-arrow-color": "#475569"}},
    {
        "selector": ":selected",
        "style": {
            "border-color": "#b91c1c",
            "border-width": 4,
            "shadow-blur": 18,
            "shadow-color": "rgba(185, 28, 28, 0.25)",
            "shadow-opacity": 1,
        },
    },
]


def render_schematic_legend(items: tuple[SchematicLegendItem, ...]) -> list[html.Div]:
    children: list[html.Div] = []
    for item in items:
        swatch_class = item.style_class
        if item.connection_type is None:
            swatch = html.Span(
                item.badge if not item.icon_url else None,
                className=f"legend-swatch legend-node {swatch_class}",
                style={"backgroundImage": f"url({item.icon_url})"} if item.icon_url else {},
            )
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
    icon = html.Span(
        inspector.badge if not inspector.icon_url else None,
        className="inspector-icon",
        style={"backgroundImage": f"url({inspector.icon_url})"} if inspector.icon_url else {},
    )
    header_bits: list[object] = []
    if inspector.kind_label:
        header_bits.append(html.Span(inspector.kind_label, className="inspector-kind"))
    if inspector.status:
        header_bits.append(html.Span(inspector.status, className="inspector-status"))
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
        html.Div(
            className="inspector-header",
            children=[
                icon,
                html.Div(
                    className="inspector-header-copy",
                    children=[
                        html.Div(header_bits, className="inspector-kind-row") if header_bits else html.Div(className="inspector-kind-row"),
                        html.Div(inspector.title, className="inspector-focus-title"),
                    ],
                ),
            ],
        ),
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
            dcc.Store(id="unifilar-inspector-lock", storage_type="memory"),
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
                                        className="subpanel",
                                        children=[
                                            html.H4(tr("workbench.schematic.inspector.title", "es"), id="unifilar-inspector-title"),
                                            html.Div(id="unifilar-inspector-body", className="inspector-body", children=default_inspector),
                                        ],
                                    ),
                                    html.Div(
                                        className="subpanel secondary-panel",
                                        children=[
                                            html.H4(tr("workbench.schematic.legend.title", "es"), id="unifilar-legend-title"),
                                            html.Div(id="unifilar-legend-items", className="legend-list", children=default_legend),
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
