from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .economics_tables import ECONOMICS_COST_COLUMNS, ECONOMICS_PRICE_COLUMNS
from .types import ScenarioRecord

PREVIEW_STATE_READY = "ready"
PREVIEW_STATE_RERUN_REQUIRED = "rerun_required"
PREVIEW_STATE_NO_SCAN = "no_scan"
PREVIEW_STATE_CANDIDATE_MISSING = "candidate_missing"

BREAKDOWN_COST_SOURCE = "Economics_Cost_Items"
BREAKDOWN_PRICE_SOURCE = "Economics_Price_Items"


@dataclass(frozen=True)
class EconomicsQuantities:
    candidate_key: str
    kWp: float
    panel_count: int
    inverter_count: int
    battery_kwh: float
    battery_name: str
    inverter_name: str


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
    message_key: str | None = None
    result: EconomicsResult | None = None


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


def resolve_battery_kwh(detail: dict[str, Any]) -> float:
    battery = detail.get("battery") or {}
    return _positive_float(battery.get("nom_kWh"))


def resolve_economics_quantities(
    *,
    candidate_key: str,
    detail: dict[str, Any],
    config: dict[str, Any],
) -> EconomicsQuantities:
    inverter = ((detail.get("inv_sel") or {}).get("inverter") or {})
    battery = detail.get("battery") or {}
    return EconomicsQuantities(
        candidate_key=candidate_key,
        kWp=float(detail.get("kWp", 0.0) or 0.0),
        panel_count=resolve_panel_count(detail, config),
        inverter_count=resolve_inverter_count(detail),
        battery_kwh=resolve_battery_kwh(detail),
        battery_name=str(battery.get("name", "") or ""),
        inverter_name=str(inverter.get("name", "") or ""),
    )


def _cost_multiplier(basis: str, quantities: EconomicsQuantities) -> float:
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
        multiplier = _cost_multiplier(basis, quantities)
        line_amount = amount * multiplier
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
                unit_rate_COP=float(amount),
                base_amount_COP=None,
                line_amount_COP=float(line_amount),
                notes=str(row.get("notes") or ""),
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
            message_key="workspace.admin.economics.preview.state.no_scan",
        )
    if scenario.dirty:
        return EconomicsPreviewResult(
            state=PREVIEW_STATE_RERUN_REQUIRED,
            message_key="workspace.admin.economics.preview.state.rerun_required",
        )

    candidate_key: str | None = None
    if scenario.selected_candidate_key in scenario.scan_result.candidate_details:
        candidate_key = str(scenario.selected_candidate_key)
    elif scenario.scan_result.best_candidate_key in scenario.scan_result.candidate_details:
        candidate_key = str(scenario.scan_result.best_candidate_key)

    if not candidate_key:
        return EconomicsPreviewResult(
            state=PREVIEW_STATE_CANDIDATE_MISSING,
            message_key="workspace.admin.economics.preview.state.candidate_missing",
        )

    detail = scenario.scan_result.candidate_details.get(candidate_key)
    if detail is None:
        return EconomicsPreviewResult(
            state=PREVIEW_STATE_CANDIDATE_MISSING,
            message_key="workspace.admin.economics.preview.state.candidate_missing",
        )

    quantities = resolve_economics_quantities(
        candidate_key=candidate_key,
        detail=detail,
        config=scenario.config_bundle.config,
    )
    result = calculate_economics_result(
        economics_cost_items=economics_cost_items,
        economics_price_items=economics_price_items,
        quantities=quantities,
    )
    return EconomicsPreviewResult(
        state=PREVIEW_STATE_READY,
        candidate_key=candidate_key,
        message_key="workspace.admin.economics.preview.state.ready",
        result=result,
    )
