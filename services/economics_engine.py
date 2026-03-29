from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from pv_product.panel_catalog import PANEL_SELECTION_CATALOG, resolve_selected_panel

from .economics_tables import ECONOMICS_COST_COLUMNS, ECONOMICS_PRICE_COLUMNS
from .types import ScenarioRecord

PREVIEW_STATE_READY = "ready"
PREVIEW_STATE_RERUN_REQUIRED = "rerun_required"
PREVIEW_STATE_NO_SCAN = "no_scan"
PREVIEW_STATE_CANDIDATE_MISSING = "candidate_missing"

BREAKDOWN_COST_SOURCE = "Economics_Cost_Items"
BREAKDOWN_PRICE_SOURCE = "Economics_Price_Items"
BATTERY_ENERGY_FIELDS = ("nom_kWh", "nominal_kWh", "capacity_kWh", "energy_kWh", "usable_kWh")
BATTERY_POWER_FIELDS = ("max_kW", "max_ch_kW", "max_dis_kW")


@dataclass(frozen=True)
class EconomicsQuantities:
    candidate_key: str
    kWp: float
    panel_count: int
    inverter_count: int
    battery_kwh: float
    battery_name: str
    inverter_name: str
    panel_name: str = ""
    battery_energy_missing_with_power: bool = False


@dataclass(frozen=True)
class EconomicsBreakdownRow:
    source_table: str
    source_row: int
    group: str
    stage_or_layer: str
    name: str
    rule: str
    multiplier: float
    unit_rate_COP: float
    base_amount_COP: float | None
    line_amount_COP: float
    notes: str
    value_source: str = "manual"
    hardware_binding: str = "none"
    hardware_name: str = ""


@dataclass(frozen=True)
class EconomicsResult:
    quantities: EconomicsQuantities
    cost_rows: tuple[EconomicsBreakdownRow, ...]
    price_rows: tuple[EconomicsBreakdownRow, ...]
    technical_subtotal_COP: float
    installed_subtotal_COP: float
    cost_total_COP: float
    commercial_adjustment_COP: float
    commercial_offer_COP: float
    sale_adjustment_COP: float
    final_price_COP: float
    final_price_per_kwp_COP: float | None


@dataclass(frozen=True)
class EconomicsPreviewResult:
    state: str
    candidate_key: str | None = None
    candidate_source: str | None = None
    message_key: str | None = None
    result: EconomicsResult | None = None


@dataclass(frozen=True)
class ResolvedHardwarePrice:
    value_source: str
    hardware_binding: str
    hardware_name: str
    unit_rate_COP: float


@dataclass(frozen=True)
class ResolvedBatteryEnergy:
    battery_kwh: float
    source_field: str = ""
    missing_with_power: bool = False


def _as_frame(
    source: pd.DataFrame | list[dict[str, Any]] | None,
    *,
    columns: list[str],
) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        frame = source.copy()
    else:
        frame = pd.DataFrame(source or [])
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[columns].copy()


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def _positive_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if numeric > 0 else 0.0


def _positive_price(value: Any) -> float | None:
    numeric = _positive_float(value)
    return numeric if numeric > 0 else None


def _casefold_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {str(key).strip().casefold(): value for key, value in data.items()}


def _catalog_price_by_name(catalog: pd.DataFrame, name: Any) -> float | None:
    raw_name = str(name or "").strip()
    if not raw_name or catalog.empty or "name" not in catalog.columns:
        return None
    names = catalog["name"].astype(str).str.strip()
    matches = catalog.loc[names == raw_name]
    if matches.empty or "price_COP" not in matches.columns:
        return None
    return _positive_price(matches.iloc[0].get("price_COP"))


def resolve_panel_count(detail: dict[str, Any], config: dict[str, Any]) -> int:
    inv_sel = detail.get("inv_sel") or {}
    explicit = _positive_int(inv_sel.get("N_mod"))
    if explicit is not None:
        return explicit
    module_power_w = _positive_float(config.get("P_mod_W"))
    if module_power_w <= 0:
        return 0
    estimated = round(_positive_float(detail.get("kWp")) / (module_power_w / 1000.0))
    return int(estimated) if estimated > 0 else 0


def resolve_inverter_count(detail: dict[str, Any]) -> int:
    inv_sel = detail.get("inv_sel") or {}
    for key in ("inverter_count", "n_inverters", "count", "qty"):
        explicit = _positive_int(inv_sel.get(key))
        if explicit is not None:
            return explicit
    # V1 simplification: the deterministic scan currently exposes one selected inverter,
    # but not a full inverter quantity model. Count that as one design-level inverter.
    return 1 if (inv_sel.get("inverter") or {}) else 0


def resolve_battery_energy(detail: dict[str, Any]) -> ResolvedBatteryEnergy:
    battery = detail.get("battery") or {}
    if not isinstance(battery, dict):
        return ResolvedBatteryEnergy(battery_kwh=0.0)
    battery_lookup = _casefold_dict(battery)
    for field in BATTERY_ENERGY_FIELDS:
        raw_value = battery.get(field)
        if raw_value in (None, ""):
            raw_value = battery_lookup.get(field.casefold())
        numeric = _positive_float(raw_value)
        if numeric > 0:
            return ResolvedBatteryEnergy(battery_kwh=numeric, source_field=field)
    has_power_fields = any(_positive_float(battery_lookup.get(field.casefold())) > 0 for field in BATTERY_POWER_FIELDS)
    return ResolvedBatteryEnergy(
        battery_kwh=0.0,
        missing_with_power=has_power_fields,
    )


def resolve_battery_kwh(detail: dict[str, Any]) -> float:
    return resolve_battery_energy(detail).battery_kwh


def resolve_economics_quantities(
    *,
    candidate_key: str,
    detail: dict[str, Any],
    config: dict[str, Any],
    panel_catalog: pd.DataFrame | None = None,
) -> EconomicsQuantities:
    inverter = ((detail.get("inv_sel") or {}).get("inverter") or {})
    battery = detail.get("battery") or {}
    resolved_battery_energy = resolve_battery_energy(detail)
    panel_name = ""
    if panel_catalog is not None:
        panel_selection = resolve_selected_panel(config, panel_catalog)
        if panel_selection.selection_mode == PANEL_SELECTION_CATALOG and panel_selection.selected_panel_name:
            panel_name = str(panel_selection.selected_panel_name)
    return EconomicsQuantities(
        candidate_key=candidate_key,
        kWp=float(detail.get("kWp", 0.0) or 0.0),
        panel_count=resolve_panel_count(detail, config),
        inverter_count=resolve_inverter_count(detail),
        battery_kwh=resolved_battery_energy.battery_kwh,
        battery_name=str(battery.get("name") or detail.get("battery_name") or ""),
        inverter_name=str(inverter.get("name", "") or ""),
        panel_name=panel_name,
        battery_energy_missing_with_power=resolved_battery_energy.missing_with_power,
    )


def resolve_panel_hardware_price(config: dict[str, Any], panel_catalog: pd.DataFrame) -> ResolvedHardwarePrice:
    selection = resolve_selected_panel(config, panel_catalog)
    if selection.selection_mode != PANEL_SELECTION_CATALOG or not selection.selected_panel_name:
        return ResolvedHardwarePrice(
            value_source="unavailable",
            hardware_binding="panel",
            hardware_name="",
            unit_rate_COP=0.0,
        )
    panel_row = selection.panel_row or {}
    unit_rate = _positive_price(panel_row.get("price_COP"))
    return ResolvedHardwarePrice(
        value_source="selected_panel_catalog" if unit_rate is not None else "unavailable",
        hardware_binding="panel",
        hardware_name=str(selection.selected_panel_name or ""),
        unit_rate_COP=float(unit_rate or 0.0),
    )


def resolve_inverter_hardware_price(detail: dict[str, Any], inverter_catalog: pd.DataFrame) -> ResolvedHardwarePrice:
    inverter = ((detail.get("inv_sel") or {}).get("inverter") or {})
    hardware_name = str(inverter.get("name") or "").strip()
    unit_rate = _positive_price(inverter.get("price_COP"))
    if unit_rate is None and hardware_name:
        unit_rate = _catalog_price_by_name(inverter_catalog, hardware_name)
    return ResolvedHardwarePrice(
        value_source="selected_inverter_catalog" if unit_rate is not None else "unavailable",
        hardware_binding="inverter",
        hardware_name=hardware_name,
        unit_rate_COP=float(unit_rate or 0.0),
    )


def resolve_battery_hardware_price(detail: dict[str, Any], battery_catalog: pd.DataFrame) -> ResolvedHardwarePrice:
    battery = detail.get("battery") or {}
    hardware_name = str(battery.get("name") or detail.get("battery_name") or "").strip()
    unit_rate = _positive_price(battery.get("price_COP"))
    if unit_rate is None and hardware_name:
        unit_rate = _catalog_price_by_name(battery_catalog, hardware_name)
    return ResolvedHardwarePrice(
        value_source="selected_battery_catalog" if unit_rate is not None else "unavailable",
        hardware_binding="battery",
        hardware_name=hardware_name,
        unit_rate_COP=float(unit_rate or 0.0),
    )


def _resolve_cost_line_rate(
    *,
    source_mode: str,
    hardware_binding: str,
    manual_amount: float,
    hardware_prices: dict[str, ResolvedHardwarePrice] | None,
) -> ResolvedHardwarePrice:
    if source_mode != "selected_hardware":
        return ResolvedHardwarePrice(
            value_source="manual",
            hardware_binding=hardware_binding or "none",
            hardware_name="",
            unit_rate_COP=float(manual_amount),
        )
    if not hardware_prices:
        return ResolvedHardwarePrice(
            value_source="unavailable",
            hardware_binding=hardware_binding or "none",
            hardware_name="",
            unit_rate_COP=0.0,
        )
    return hardware_prices.get(
        hardware_binding or "none",
        ResolvedHardwarePrice(
            value_source="unavailable",
            hardware_binding=hardware_binding or "none",
            hardware_name="",
            unit_rate_COP=0.0,
        ),
    )


def _cost_multiplier(
    basis: str,
    quantities: EconomicsQuantities,
    *,
    source_mode: str = "manual",
    hardware_binding: str = "none",
) -> float:
    # Selected battery hardware resolves a whole-battery catalog price, not a per-kWh rate.
    # Multiply that total battery price by one design-level battery selection.
    if source_mode == "selected_hardware" and hardware_binding == "battery":
        return 1.0
    if basis == "fixed_project":
        return 1.0
    if basis == "per_kwp":
        return float(quantities.kWp)
    if basis == "per_panel":
        return float(quantities.panel_count)
    if basis == "per_inverter":
        return float(quantities.inverter_count)
    if basis == "per_battery_kwh":
        return float(quantities.battery_kwh)
    raise ValueError(f"Unsupported economics cost basis: {basis}")


def _price_line_amount(method: str, value: float, *, quantities: EconomicsQuantities, layer_base: float) -> tuple[float, float | None]:
    if method == "markup_pct":
        return float(value) * float(layer_base), float(layer_base)
    if method == "fixed_project":
        return float(value), None
    if method == "per_kwp":
        return float(value) * float(quantities.kWp), None
    raise ValueError(f"Unsupported economics price method: {method}")


def calculate_economics_result(
    *,
    economics_cost_items: pd.DataFrame | list[dict[str, Any]] | None,
    economics_price_items: pd.DataFrame | list[dict[str, Any]] | None,
    quantities: EconomicsQuantities,
    hardware_prices: dict[str, ResolvedHardwarePrice] | None = None,
) -> EconomicsResult:
    cost_frame = _as_frame(economics_cost_items, columns=ECONOMICS_COST_COLUMNS)
    price_frame = _as_frame(economics_price_items, columns=ECONOMICS_PRICE_COLUMNS)

    cost_rows: list[EconomicsBreakdownRow] = []
    technical_subtotal = 0.0
    installed_subtotal = 0.0
    for source_row, row in enumerate(cost_frame.to_dict("records"), start=1):
        if not bool(row.get("enabled")):
            continue
        stage = str(row.get("stage") or "").strip()
        basis = str(row.get("basis") or "").strip()
        amount = float(row.get("amount_COP", 0.0) or 0.0)
        source_mode = str(row.get("source_mode") or "manual").strip() or "manual"
        hardware_binding = str(row.get("hardware_binding") or "none").strip() or "none"
        resolved_rate = _resolve_cost_line_rate(
            source_mode=source_mode,
            hardware_binding=hardware_binding,
            manual_amount=amount,
            hardware_prices=hardware_prices,
        )
        multiplier = _cost_multiplier(
            basis,
            quantities,
            source_mode=source_mode,
            hardware_binding=hardware_binding,
        )
        line_amount = resolved_rate.unit_rate_COP * multiplier
        if stage == "technical":
            technical_subtotal += line_amount
        elif stage == "installed":
            installed_subtotal += line_amount
        cost_rows.append(
            EconomicsBreakdownRow(
                source_table=BREAKDOWN_COST_SOURCE,
                source_row=source_row,
                group="cost",
                stage_or_layer=stage,
                name=str(row.get("name") or ""),
                rule=basis,
                multiplier=float(multiplier),
                unit_rate_COP=float(resolved_rate.unit_rate_COP),
                base_amount_COP=None,
                line_amount_COP=float(line_amount),
                notes=str(row.get("notes") or ""),
                value_source=resolved_rate.value_source,
                hardware_binding=resolved_rate.hardware_binding,
                hardware_name=resolved_rate.hardware_name,
            )
        )

    cost_total = technical_subtotal + installed_subtotal
    price_rows: list[EconomicsBreakdownRow] = []
    commercial_adjustment = 0.0
    commercial_offer = cost_total
    sale_adjustment = 0.0
    for source_row, row in enumerate(price_frame.to_dict("records"), start=1):
        if not bool(row.get("enabled")):
            continue
        layer = str(row.get("layer") or "").strip()
        method = str(row.get("method") or "").strip()
        value = float(row.get("value", 0.0) or 0.0)
        layer_base = cost_total if layer == "commercial" else commercial_offer
        if method == "markup_pct":
            multiplier = float(layer_base)
        elif method == "per_kwp":
            multiplier = float(quantities.kWp)
        else:
            multiplier = 1.0
        line_amount, base_amount = _price_line_amount(
            method,
            value,
            quantities=quantities,
            layer_base=layer_base,
        )
        if layer == "commercial":
            commercial_adjustment += line_amount
        elif layer == "sale":
            sale_adjustment += line_amount
        price_rows.append(
            EconomicsBreakdownRow(
                source_table=BREAKDOWN_PRICE_SOURCE,
                source_row=source_row,
                group="price",
                stage_or_layer=layer,
                name=str(row.get("name") or ""),
                rule=method,
                multiplier=float(multiplier),
                unit_rate_COP=float(value),
                base_amount_COP=base_amount,
                line_amount_COP=float(line_amount),
                notes=str(row.get("notes") or ""),
                value_source="",
                hardware_binding="",
                hardware_name="",
            )
        )
        if layer == "commercial":
            commercial_offer = cost_total + commercial_adjustment

    final_price = commercial_offer + sale_adjustment
    final_price_per_kwp = (final_price / quantities.kWp) if quantities.kWp > 0 else None
    return EconomicsResult(
        quantities=quantities,
        cost_rows=tuple(cost_rows),
        price_rows=tuple(price_rows),
        technical_subtotal_COP=float(technical_subtotal),
        installed_subtotal_COP=float(installed_subtotal),
        cost_total_COP=float(cost_total),
        commercial_adjustment_COP=float(commercial_adjustment),
        commercial_offer_COP=float(commercial_offer),
        sale_adjustment_COP=float(sale_adjustment),
        final_price_COP=float(final_price),
        final_price_per_kwp_COP=None if final_price_per_kwp is None else float(final_price_per_kwp),
    )


def resolve_economics_preview(
    scenario: ScenarioRecord,
    *,
    economics_cost_items: pd.DataFrame | list[dict[str, Any]] | None,
    economics_price_items: pd.DataFrame | list[dict[str, Any]] | None,
) -> EconomicsPreviewResult:
    if scenario.scan_result is None:
        return EconomicsPreviewResult(
            state=PREVIEW_STATE_NO_SCAN,
            candidate_source=None,
            message_key="workspace.admin.economics.preview.state.no_scan",
        )
    if scenario.dirty:
        return EconomicsPreviewResult(
            state=PREVIEW_STATE_RERUN_REQUIRED,
            candidate_source=None,
            message_key="workspace.admin.economics.preview.state.rerun_required",
        )

    candidate_key: str | None = None
    candidate_source: str | None = None
    if scenario.selected_candidate_key in scenario.scan_result.candidate_details:
        candidate_key = str(scenario.selected_candidate_key)
        candidate_source = "selected"
    elif scenario.scan_result.best_candidate_key in scenario.scan_result.candidate_details:
        candidate_key = str(scenario.scan_result.best_candidate_key)
        candidate_source = "best_fallback"

    if not candidate_key:
        return EconomicsPreviewResult(
            state=PREVIEW_STATE_CANDIDATE_MISSING,
            candidate_source=None,
            message_key="workspace.admin.economics.preview.state.candidate_missing",
        )

    detail = scenario.scan_result.candidate_details.get(candidate_key)
    if detail is None:
        return EconomicsPreviewResult(
            state=PREVIEW_STATE_CANDIDATE_MISSING,
            candidate_source=None,
            message_key="workspace.admin.economics.preview.state.candidate_missing",
        )

    quantities = resolve_economics_quantities(
        candidate_key=candidate_key,
        detail=detail,
        config=scenario.config_bundle.config,
        panel_catalog=scenario.config_bundle.panel_catalog,
    )
    hardware_prices = {
        "none": ResolvedHardwarePrice(
            value_source="unavailable",
            hardware_binding="none",
            hardware_name="",
            unit_rate_COP=0.0,
        ),
        "panel": resolve_panel_hardware_price(scenario.config_bundle.config, scenario.config_bundle.panel_catalog),
        "inverter": resolve_inverter_hardware_price(detail, scenario.config_bundle.inverter_catalog),
        "battery": resolve_battery_hardware_price(detail, scenario.config_bundle.battery_catalog),
    }
    result = calculate_economics_result(
        economics_cost_items=economics_cost_items,
        economics_price_items=economics_price_items,
        quantities=quantities,
        hardware_prices=hardware_prices,
    )
    return EconomicsPreviewResult(
        state=PREVIEW_STATE_READY,
        candidate_key=candidate_key,
        candidate_source=candidate_source,
        message_key="workspace.admin.economics.preview.state.ready",
        result=result,
    )


def economics_preview_warning_messages(preview: EconomicsPreviewResult) -> tuple[str, ...]:
    if preview.result is None:
        return ()
    warnings: list[str] = []
    for row in preview.result.cost_rows:
        if row.rule == "per_battery_kwh" and preview.result.quantities.battery_energy_missing_with_power:
            warnings.append(
                f"Economics_Cost_Items fila {row.source_row}: la batería seleccionada tiene campos de potencia pero no una energía válida ('nom_kWh' o alias soportado); la cantidad energética quedará en 0 kWh."
            )
        if row.value_source != "unavailable":
            continue
        if row.hardware_binding == "none":
            warnings.append(
                f"Economics_Cost_Items fila {row.source_row}: 'selected_hardware' requiere un 'hardware_binding' distinto de 'none'."
            )
            continue
        if str(row.hardware_name or "").strip():
            warnings.append(
                f"Economics_Cost_Items fila {row.source_row}: falta 'price_COP' para el hardware seleccionado '{row.hardware_name}'."
            )
            continue
        warnings.append(
            f"Economics_Cost_Items fila {row.source_row}: no se pudo resolver el hardware seleccionado para '{row.hardware_binding}'."
        )
    deduped: dict[str, None] = {}
    for message in warnings:
        deduped[message] = None
    return tuple(deduped)
