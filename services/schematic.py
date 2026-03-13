from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pv_product.hardware import string_checks

from .i18n import tr
from .types import ScenarioRecord


@dataclass(frozen=True)
class StringGroupSummary:
    mppt_index: int
    strings: int
    modules_per_string: int
    total_modules: int


@dataclass(frozen=True)
class StringLayoutSummary:
    exact: bool
    total_modules: int | None
    groups: tuple[StringGroupSummary, ...]
    summary_text: str
    note: str | None = None


@dataclass(frozen=True)
class SchematicDetailRow:
    label: str
    value: str


@dataclass(frozen=True)
class SchematicLegendItem:
    role: str
    badge: str
    label: str
    connection_type: str | None
    style_class: str


@dataclass(frozen=True)
class SchematicInspector:
    title: str
    description: str
    details: tuple[SchematicDetailRow, ...]
    representative_note: str | None = None


@dataclass(frozen=True)
class SchematicNode:
    id: str
    role: str
    label: str
    position: dict[str, float]
    metadata: dict[str, object]


@dataclass(frozen=True)
class SchematicEdge:
    id: str
    source: str
    target: str
    role: str
    label: str = ""


@dataclass(frozen=True)
class SchematicModel:
    nodes: tuple[SchematicNode, ...]
    edges: tuple[SchematicEdge, ...]
    representative: bool
    note: str
    string_summary: str


def _lang(value: str | None) -> str:
    return value if value in {"en", "es"} else "es"


def _module_data(bundle) -> dict[str, float]:
    cfg = bundle.config
    return {
        "P_mod_W": float(cfg.get("P_mod_W", 0.0) or 0.0),
        "Voc25": float(cfg.get("Voc25", 0.0) or 0.0),
        "Vmp25": float(cfg.get("Vmp25", 0.0) or 0.0),
        "Isc": float(cfg.get("Isc", 0.0) or 0.0),
    }


def _battery_present(detail: dict[str, Any]) -> bool:
    battery = detail.get("battery") or {}
    return float(battery.get("nom_kWh", 0.0) or 0.0) > 0.0


def _distribute_strings(total_strings: int, active_mppts: int) -> tuple[int, ...]:
    base = total_strings // active_mppts
    remainder = total_strings % active_mppts
    return tuple(base + (1 if index < remainder else 0) for index in range(active_mppts))


def _layout_rank(ns_exact: int, stored_ns: int, active_counts: tuple[int, ...]) -> tuple[int, int, int]:
    symmetry_gap = (max(active_counts) - min(active_counts)) if active_counts else 0
    return (abs(ns_exact - stored_ns), symmetry_gap, len(active_counts))


def _voltage_and_current_ok(
    *,
    module: dict[str, float],
    inverter: dict[str, Any],
    tmin_c: float,
    a_voc_pct: float,
    ns_exact: int,
    max_strings_per_mppt: int,
    total_strings: int,
) -> bool:
    try:
        ok_voc, ok_mppt, _, _ = string_checks(
            module,
            inverter,
            tmin_c,
            a_voc_pct,
            ns_exact,
            total_strings,
        )
        i_mppt = float(module["Isc"]) * float(max_strings_per_mppt)
        return bool(ok_voc and ok_mppt and i_mppt <= float(inverter.get("Imax_mppt", 0.0) or 0.0))
    except Exception:
        return False


def infer_string_layout(detail: dict[str, Any], config_bundle, *, lang: str = "es") -> StringLayoutSummary:
    lang = _lang(lang)
    inv_sel = detail.get("inv_sel") or {}
    inverter = inv_sel.get("inverter") or {}
    n_mppt = max(1, int(inverter.get("n_mppt", 1) or 1))
    total_modules = int(inv_sel.get("N_mod", 0) or 0)
    stored_ns = max(1, int(inv_sel.get("Ns", 1) or 1))
    stored_np = max(1, int(inv_sel.get("Np", 1) or 1))
    module = _module_data(config_bundle)
    tmin_c = float(config_bundle.config.get("Tmin_C", 25.0) or 25.0)
    a_voc_pct = float(config_bundle.config.get("a_Voc_pct", 0.0) or 0.0)

    feasible: list[tuple[tuple[int, int, int], tuple[StringGroupSummary, ...], int]] = []
    for ns_exact in range(1, max(total_modules, 1) + 1):
        if total_modules % ns_exact != 0:
            continue
        total_strings = total_modules // ns_exact
        for active_mppts in range(1, min(n_mppt, total_strings) + 1):
            counts = _distribute_strings(total_strings, active_mppts)
            if max(counts, default=0) <= 0:
                continue
            if not _voltage_and_current_ok(
                module=module,
                inverter=inverter,
                tmin_c=tmin_c,
                a_voc_pct=a_voc_pct,
                ns_exact=ns_exact,
                max_strings_per_mppt=max(counts),
                total_strings=total_strings,
            ):
                continue
            groups = tuple(
                StringGroupSummary(
                    mppt_index=index + 1,
                    strings=strings,
                    modules_per_string=ns_exact,
                    total_modules=strings * ns_exact,
                )
                for index, strings in enumerate(counts)
                if strings > 0
            )
            feasible.append((_layout_rank(ns_exact, stored_ns, counts), groups, ns_exact))

    if feasible:
        _, groups, _ = sorted(feasible, key=lambda item: item[0])[0]
        summary = " · ".join(
            tr(
                "workbench.schematic.group_exact",
                lang,
                mppt=group.mppt_index,
                strings=group.strings,
                modules=group.modules_per_string,
            )
            for group in groups
        )
        return StringLayoutSummary(
            exact=True,
            total_modules=total_modules,
            groups=groups,
            summary_text=tr("workbench.schematic.summary_exact", lang, groups=summary),
        )

    active_mppts = max(1, min(n_mppt, stored_np))
    counts = _distribute_strings(max(1, stored_np), active_mppts)
    remaining_modules = total_modules
    groups: list[StringGroupSummary] = []
    for index, strings in enumerate(counts):
        provisional = min(remaining_modules, strings * stored_ns)
        groups.append(
            StringGroupSummary(
                mppt_index=index + 1,
                strings=strings,
                modules_per_string=stored_ns,
                total_modules=max(provisional, 0),
            )
        )
        remaining_modules -= provisional
    summary = tr(
        "workbench.schematic.summary_representative",
        lang,
        total_modules=total_modules,
        modules_per_string=stored_ns,
    )
    return StringLayoutSummary(
        exact=False,
        total_modules=total_modules,
        groups=tuple(groups),
        summary_text=summary,
        note=tr("workbench.schematic.note.representative_detail", lang),
    )


def _badge(component_kind: str, lang: str) -> str:
    return tr(f"workbench.schematic.badge.{component_kind}", lang)


def _pv_node_label(group: StringGroupSummary, module_power_kw: float, *, exact: bool, lang: str) -> str:
    kwp_group = group.total_modules * module_power_kw
    lines = [
        f"[{_badge('pv', lang)}]",
        tr("workbench.schematic.pv_label", lang, mppt=group.mppt_index),
    ]
    if exact:
        lines.extend(
            [
                tr(
                    "workbench.schematic.group_exact_short",
                    lang,
                    strings=group.strings,
                    modules=group.modules_per_string,
                ),
                tr("workbench.schematic.group_kwp", lang, kwp=kwp_group),
            ]
        )
    else:
        lines.extend(
            [
                tr(
                    "workbench.schematic.group_representative_short",
                    lang,
                    strings=group.strings,
                    modules=group.modules_per_string,
                ),
                tr("workbench.schematic.group_modules_total", lang, modules=group.total_modules),
            ]
        )
    return "\n".join(lines)


def _inverter_label(detail: dict[str, Any], *, lang: str) -> str:
    inverter = (detail.get("inv_sel") or {}).get("inverter") or {}
    name = str(inverter.get("name", tr("workbench.schematic.inverter_node", lang)))
    ac_kw = inverter.get("AC_kW")
    lines = [f"[{_badge('inverter', lang)}]", name]
    if ac_kw not in (None, ""):
        lines.append(tr("workbench.schematic.inverter_power", lang, kw=float(ac_kw)))
    return "\n".join(lines)


def _battery_label(detail: dict[str, Any], config_bundle, *, lang: str) -> str:
    battery = detail.get("battery") or {}
    name = str(battery.get("name", detail.get("battery_name", tr("workbench.schematic.battery_node", lang))))
    nom_kwh = float(battery.get("nom_kWh", 0.0) or 0.0)
    usable = nom_kwh * float(config_bundle.config.get("bat_DoD", 1.0) or 1.0)
    coupling = str(config_bundle.config.get("bat_coupling", "ac") or "ac").lower()
    return "\n".join(
        [
            f"[{_badge('battery', lang)}]",
            name,
            tr("workbench.schematic.battery_energy_short", lang, nominal=nom_kwh, usable=usable),
            tr("workbench.schematic.battery_coupling_short", lang, coupling=coupling.upper()),
        ]
    )


def _simple_node_label(component_kind: str, title_key: str, *, lang: str) -> str:
    return "\n".join([f"[{_badge(component_kind, lang)}]", tr(title_key, lang)])


def _detail_row(label_key: str, value: str, lang: str) -> SchematicDetailRow:
    return SchematicDetailRow(label=tr(label_key, lang), value=value)


def _format_kwh(value: float) -> str:
    return f"{value:,.1f} kWh"


def _format_kw(value: float) -> str:
    return f"{value:,.1f} kW"


def _format_kwp(value: float) -> str:
    return f"{value:,.2f} kWp"


def _pv_metadata(
    group: StringGroupSummary,
    module_power_kw: float,
    *,
    representative: bool,
    layout_note: str | None,
    lang: str,
) -> dict[str, object]:
    kwp_group = group.total_modules * module_power_kw
    details = [
        _detail_row("workbench.schematic.detail.component_kind", tr("workbench.schematic.kind.pv", lang), lang),
        _detail_row("workbench.schematic.detail.mppt", str(group.mppt_index), lang),
        _detail_row("workbench.schematic.detail.strings", str(group.strings), lang),
        _detail_row("workbench.schematic.detail.modules_per_string", str(group.modules_per_string), lang),
        _detail_row("workbench.schematic.detail.total_modules", str(group.total_modules), lang),
        _detail_row("workbench.schematic.detail.kwp_share", _format_kwp(kwp_group), lang),
    ]
    return {
        "component_kind": "pv",
        "title": tr("workbench.schematic.pv_label", lang, mppt=group.mppt_index),
        "description": tr("workbench.schematic.description.pv", lang),
        "details": [{"label": row.label, "value": row.value} for row in details],
        "tooltip": tr(
            "workbench.schematic.tooltip.pv",
            lang,
            mppt=group.mppt_index,
            strings=group.strings,
            modules=group.modules_per_string,
        ),
        "representative": representative,
        "representative_note": layout_note if representative else None,
    }


def _inverter_metadata(detail: dict[str, Any], *, lang: str) -> dict[str, object]:
    inverter = (detail.get("inv_sel") or {}).get("inverter") or {}
    details = [
        _detail_row("workbench.schematic.detail.component_kind", tr("workbench.schematic.kind.inverter", lang), lang),
        _detail_row("workbench.schematic.detail.model", str(inverter.get("name", "-")), lang),
    ]
    ac_kw = inverter.get("AC_kW")
    if ac_kw not in (None, ""):
        details.append(_detail_row("workbench.schematic.detail.ac_power", _format_kw(float(ac_kw)), lang))
    n_mppt = inverter.get("n_mppt")
    if n_mppt not in (None, ""):
        details.append(_detail_row("workbench.schematic.detail.mppt_count", str(int(n_mppt)), lang))
    return {
        "component_kind": "inverter",
        "title": tr("workbench.schematic.inverter_node", lang),
        "description": tr("workbench.schematic.description.inverter", lang),
        "details": [{"label": row.label, "value": row.value} for row in details],
        "tooltip": tr("workbench.schematic.tooltip.inverter", lang, name=str(inverter.get("name", "-"))),
        "representative": False,
        "representative_note": None,
    }


def _battery_metadata(detail: dict[str, Any], config_bundle, *, lang: str) -> dict[str, object]:
    battery = detail.get("battery") or {}
    nom_kwh = float(battery.get("nom_kWh", 0.0) or 0.0)
    usable = nom_kwh * float(config_bundle.config.get("bat_DoD", 1.0) or 1.0)
    coupling = str(config_bundle.config.get("bat_coupling", "ac") or "ac").upper()
    details = [
        _detail_row("workbench.schematic.detail.component_kind", tr("workbench.schematic.kind.battery", lang), lang),
        _detail_row("workbench.schematic.detail.model", str(battery.get("name", detail.get("battery_name", "-"))), lang),
        _detail_row("workbench.schematic.detail.nominal_energy", _format_kwh(nom_kwh), lang),
        _detail_row("workbench.schematic.detail.usable_energy", _format_kwh(usable), lang),
        _detail_row("workbench.schematic.detail.coupling", coupling, lang),
    ]
    return {
        "component_kind": "battery",
        "title": tr("workbench.schematic.battery_node", lang),
        "description": tr("workbench.schematic.description.battery", lang),
        "details": [{"label": row.label, "value": row.value} for row in details],
        "tooltip": tr("workbench.schematic.tooltip.battery", lang, name=str(battery.get("name", "-"))),
        "representative": False,
        "representative_note": None,
    }


def _load_metadata(*, lang: str) -> dict[str, object]:
    details = [
        _detail_row("workbench.schematic.detail.component_kind", tr("workbench.schematic.kind.load", lang), lang),
        _detail_row("workbench.schematic.detail.connection_side", tr("workbench.schematic.detail.connection_side.ac_bus", lang), lang),
    ]
    return {
        "component_kind": "load",
        "title": tr("workbench.schematic.load_node", lang),
        "description": tr("workbench.schematic.description.load", lang),
        "details": [{"label": row.label, "value": row.value} for row in details],
        "tooltip": tr("workbench.schematic.tooltip.load", lang),
        "representative": False,
        "representative_note": None,
    }


def _grid_metadata(*, lang: str) -> dict[str, object]:
    details = [
        _detail_row("workbench.schematic.detail.component_kind", tr("workbench.schematic.kind.grid", lang), lang),
        _detail_row("workbench.schematic.detail.connection_side", tr("workbench.schematic.detail.connection_side.ac_bus", lang), lang),
    ]
    return {
        "component_kind": "grid",
        "title": tr("workbench.schematic.grid_node", lang),
        "description": tr("workbench.schematic.description.grid", lang),
        "details": [{"label": row.label, "value": row.value} for row in details],
        "tooltip": tr("workbench.schematic.tooltip.grid", lang),
        "representative": False,
        "representative_note": None,
    }


def build_schematic_legend(lang: str = "es") -> tuple[SchematicLegendItem, ...]:
    lang = _lang(lang)
    return (
        SchematicLegendItem(role="pv", badge=_badge("pv", lang), label=tr("workbench.schematic.legend.pv", lang), connection_type=None, style_class="legend-role-pv"),
        SchematicLegendItem(role="inverter", badge=_badge("inverter", lang), label=tr("workbench.schematic.legend.inverter", lang), connection_type=None, style_class="legend-role-inverter"),
        SchematicLegendItem(role="battery", badge=_badge("battery", lang), label=tr("workbench.schematic.legend.battery", lang), connection_type=None, style_class="legend-role-battery"),
        SchematicLegendItem(role="load", badge=_badge("load", lang), label=tr("workbench.schematic.legend.load", lang), connection_type=None, style_class="legend-role-load"),
        SchematicLegendItem(role="grid", badge=_badge("grid", lang), label=tr("workbench.schematic.legend.grid", lang), connection_type=None, style_class="legend-role-grid"),
        SchematicLegendItem(role="ac", badge="AC", label=tr("workbench.schematic.legend.ac", lang), connection_type="ac", style_class="legend-connection-ac"),
        SchematicLegendItem(role="dc", badge="DC", label=tr("workbench.schematic.legend.dc", lang), connection_type="dc", style_class="legend-connection-dc"),
    )


def default_schematic_inspector(model: SchematicModel | None, lang: str = "es") -> SchematicInspector:
    lang = _lang(lang)
    details: tuple[SchematicDetailRow, ...] = ()
    representative_note = None
    if model is not None and model.string_summary:
        details = (
            SchematicDetailRow(
                label=tr("workbench.schematic.inspector.detail.layout", lang),
                value=model.string_summary,
            ),
        )
        representative_note = model.note if model.representative else None
    return SchematicInspector(
        title=tr("workbench.schematic.inspector.default_title", lang),
        description=tr("workbench.schematic.inspector.default_description", lang),
        details=details,
        representative_note=representative_note,
    )


def resolve_schematic_inspector(node_data: dict[str, Any] | None, model: SchematicModel, lang: str = "es") -> SchematicInspector:
    lang = _lang(lang)
    if not node_data:
        return default_schematic_inspector(model, lang)
    node_id = str(node_data.get("id", "")).strip()
    node = next((candidate for candidate in model.nodes if candidate.id == node_id), None)
    if node is None:
        return default_schematic_inspector(model, lang)
    metadata = (node.metadata if node is not None else {}) or {}
    title = str(metadata.get("title") or node_data.get("title") or tr("workbench.schematic.inspector.default_title", lang))
    description = str(metadata.get("description") or node_data.get("description") or tr("workbench.schematic.inspector.default_description", lang))
    detail_rows = tuple(
        SchematicDetailRow(label=str(item.get("label", "")), value=str(item.get("value", "")))
        for item in (metadata.get("details") or node_data.get("details") or [])
        if item.get("label") and item.get("value") not in (None, "")
    )
    representative_note = metadata.get("representative_note") or node_data.get("representative_note")
    return SchematicInspector(
        title=title,
        description=description,
        details=detail_rows,
        representative_note=str(representative_note) if representative_note else None,
    )


def build_unifilar_model(
    scenario_record: ScenarioRecord,
    selected_candidate_key: str,
    *,
    lang: str = "es",
) -> SchematicModel:
    lang = _lang(lang)
    if scenario_record.scan_result is None:
        raise ValueError(f"El escenario '{scenario_record.name}' no tiene resultados determinísticos.")
    if selected_candidate_key not in scenario_record.scan_result.candidate_details:
        raise KeyError(f"No existe el candidato '{selected_candidate_key}' en el escenario.")

    detail = scenario_record.scan_result.candidate_details[selected_candidate_key]
    layout = infer_string_layout(detail, scenario_record.config_bundle, lang=lang)
    module_power_kw = float(scenario_record.config_bundle.config.get("P_mod_W", 0.0) or 0.0) / 1000.0
    pv_count = max(1, len(layout.groups))
    center_y = 80.0 + (pv_count - 1) * 55.0

    nodes: list[SchematicNode] = []
    edges: list[SchematicEdge] = []

    for index, group in enumerate(layout.groups):
        y = 80.0 + index * 110.0
        nodes.append(
            SchematicNode(
                id=f"pv-{group.mppt_index}",
                role="pv",
                label=_pv_node_label(group, module_power_kw, exact=layout.exact, lang=lang),
                position={"x": 80.0, "y": y},
                metadata=_pv_metadata(
                    group,
                    module_power_kw,
                    representative=not layout.exact,
                    layout_note=layout.note,
                    lang=lang,
                ),
            )
        )
        edges.append(
            SchematicEdge(
                id=f"pv-{group.mppt_index}-to-inverter",
                source=f"pv-{group.mppt_index}",
                target="inverter",
                role="pv-link",
                label="DC",
            )
        )

    nodes.append(
        SchematicNode(
            id="inverter",
            role="inverter",
            label=_inverter_label(detail, lang=lang),
            position={"x": 370.0, "y": center_y},
            metadata=_inverter_metadata(detail, lang=lang),
        )
    )
    nodes.append(
        SchematicNode(
            id="load",
            role="load",
            label=_simple_node_label("load", "workbench.schematic.load_node", lang=lang),
            position={"x": 690.0, "y": center_y},
            metadata=_load_metadata(lang=lang),
        )
    )
    nodes.append(
        SchematicNode(
            id="grid",
            role="grid",
            label=_simple_node_label("grid", "workbench.schematic.grid_node", lang=lang),
            position={"x": 970.0, "y": center_y},
            metadata=_grid_metadata(lang=lang),
        )
    )
    edges.extend(
        [
            SchematicEdge(id="inverter-to-load", source="inverter", target="load", role="ac-link", label="AC"),
            SchematicEdge(id="grid-to-load", source="grid", target="load", role="grid-link", label="AC"),
        ]
    )

    if _battery_present(detail):
        coupling = str(scenario_record.config_bundle.config.get("bat_coupling", "ac") or "ac").lower()
        battery_target = "inverter" if coupling == "dc" else "load"
        battery_y = center_y + 165.0
        battery_x = 370.0 if coupling == "dc" else 690.0
        nodes.append(
            SchematicNode(
                id="battery",
                role="battery",
                label=_battery_label(detail, scenario_record.config_bundle, lang=lang),
                position={"x": battery_x, "y": battery_y},
                metadata=_battery_metadata(detail, scenario_record.config_bundle, lang=lang),
            )
        )
        edges.append(
            SchematicEdge(
                id="battery-link",
                source="battery",
                target=battery_target,
                role=f"battery-{coupling}",
                label=coupling.upper(),
            )
        )

    note_parts = [tr("workbench.schematic.note.base", lang)]
    if layout.note:
        note_parts.append(layout.note)
    return SchematicModel(
        nodes=tuple(nodes),
        edges=tuple(edges),
        representative=not layout.exact,
        note=" ".join(part for part in note_parts if part),
        string_summary=layout.summary_text,
    )


def to_cytoscape_elements(model: SchematicModel) -> list[dict[str, object]]:
    elements: list[dict[str, object]] = []
    for node in model.nodes:
        data = {"id": node.id, "label": node.label}
        data.update(node.metadata)
        elements.append(
            {
                "data": data,
                "position": node.position,
                "classes": f"role-{node.role}",
            }
        )
    for edge in model.edges:
        elements.append(
            {
                "data": {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "label": edge.label,
                },
                "classes": f"edge-{edge.role}",
            }
        )
    return elements
