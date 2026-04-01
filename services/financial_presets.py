from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .economics_tables import (
    compute_economics_runtime_signature,
    default_economics_cost_items_rows,
    default_economics_price_items_rows,
    normalize_economics_cost_items_frame,
    normalize_economics_price_items_frame,
)
from .i18n import tr
from .types import FinancialPresetRecord


SYSTEM_PRESET_IDS = (
    "system:residential_conservative",
    "system:commercial_standard",
    "system:industrial_aggressive",
)


@dataclass(frozen=True)
class SystemFinancialPreset:
    preset_id: str
    label_key: str
    description_key: str | None
    economics_cost_items_rows: tuple[dict[str, Any], ...]
    economics_price_items_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ResolvedFinancialPreset:
    preset_id: str
    display_name: str
    origin: str
    label_key: str | None
    description_key: str | None
    economics_cost_items_rows: tuple[dict[str, Any], ...]
    economics_price_items_rows: tuple[dict[str, Any], ...]


def _normalized_cost_rows(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    frame = normalize_economics_cost_items_frame(rows)
    return tuple(dict(row) for row in frame.to_dict("records"))


def _normalized_price_rows(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    frame = normalize_economics_price_items_frame(rows)
    return tuple(dict(row) for row in frame.to_dict("records"))


def _replace_cost_amounts(
    *,
    bos_electrico: float,
    estructura: float,
    mano_de_obra: float,
    ingenieria: float,
    logistica: float,
) -> tuple[dict[str, Any], ...]:
    rows = [dict(row) for row in default_economics_cost_items_rows()]
    amounts = {
        "BOS eléctrico": float(bos_electrico),
        "Estructura": float(estructura),
        "Mano de obra": float(mano_de_obra),
        "Ingeniería": float(ingenieria),
        "Logística": float(logistica),
    }
    for row in rows:
        name = str(row.get("name") or "").strip()
        if name in amounts:
            row["amount_COP"] = amounts[name]
            row["enabled"] = True
    return _normalized_cost_rows(rows)


def _replace_price_amounts(
    *,
    tax_pct: float,
    contingency_pct: float,
    margin_pct: float,
) -> tuple[dict[str, Any], ...]:
    rows = [dict(row) for row in default_economics_price_items_rows()]
    for row in rows:
        name = str(row.get("name") or "").strip()
        if name == "IVA":
            row["value"] = float(tax_pct)
            row["enabled"] = True
        elif name == "Contingencia":
            row["value"] = float(contingency_pct)
            row["enabled"] = True
        elif name == "Margen comercial":
            row["value"] = float(margin_pct)
            row["enabled"] = True
        elif name == "Ajuste final":
            row["value"] = 0.0
            row["enabled"] = False
    return _normalized_price_rows(rows)


def _system_preset(
    preset_id: str,
    *,
    label_key: str,
    description_key: str | None = None,
    bos_electrico: float,
    estructura: float,
    mano_de_obra: float,
    ingenieria: float,
    logistica: float,
    tax_pct: float,
    contingency_pct: float,
    margin_pct: float,
) -> SystemFinancialPreset:
    return SystemFinancialPreset(
        preset_id=preset_id,
        label_key=label_key,
        description_key=description_key,
        economics_cost_items_rows=_replace_cost_amounts(
            bos_electrico=bos_electrico,
            estructura=estructura,
            mano_de_obra=mano_de_obra,
            ingenieria=ingenieria,
            logistica=logistica,
        ),
        economics_price_items_rows=_replace_price_amounts(
            tax_pct=tax_pct,
            contingency_pct=contingency_pct,
            margin_pct=margin_pct,
        ),
    )


def system_financial_presets() -> tuple[SystemFinancialPreset, ...]:
    return (
        _system_preset(
            "system:residential_conservative",
            label_key="workspace.admin.economics.presets.system.residential_conservative.label",
            description_key="workspace.admin.economics.presets.system.residential_conservative.description",
            bos_electrico=520_000,
            estructura=280_000,
            mano_de_obra=340_000,
            ingenieria=1_800_000,
            logistica=900_000,
            tax_pct=0.19,
            contingency_pct=0.06,
            margin_pct=0.18,
        ),
        _system_preset(
            "system:commercial_standard",
            label_key="workspace.admin.economics.presets.system.commercial_standard.label",
            description_key="workspace.admin.economics.presets.system.commercial_standard.description",
            bos_electrico=420_000,
            estructura=220_000,
            mano_de_obra=240_000,
            ingenieria=2_500_000,
            logistica=1_200_000,
            tax_pct=0.19,
            contingency_pct=0.05,
            margin_pct=0.12,
        ),
        _system_preset(
            "system:industrial_aggressive",
            label_key="workspace.admin.economics.presets.system.industrial_aggressive.label",
            description_key="workspace.admin.economics.presets.system.industrial_aggressive.description",
            bos_electrico=320_000,
            estructura=160_000,
            mano_de_obra=180_000,
            ingenieria=3_200_000,
            logistica=1_600_000,
            tax_pct=0.19,
            contingency_pct=0.03,
            margin_pct=0.07,
        ),
    )


def normalize_financial_preset_record(record: FinancialPresetRecord) -> FinancialPresetRecord:
    normalized_cost_rows = _normalized_cost_rows(record.economics_cost_items_rows)
    normalized_price_rows = _normalized_price_rows(record.economics_price_items_rows)
    if not normalized_cost_rows or not normalized_price_rows:
        raise ValueError(f"Preset '{record.preset_id}' is incomplete.")
    return FinancialPresetRecord(
        preset_id=record.preset_id,
        name=str(record.name or "").strip(),
        economics_cost_items_rows=normalized_cost_rows,
        economics_price_items_rows=normalized_price_rows,
    )


def sanitize_financial_presets(
    presets: tuple[FinancialPresetRecord, ...] | list[FinancialPresetRecord],
) -> tuple[tuple[FinancialPresetRecord, ...], tuple[str, ...]]:
    valid: list[FinancialPresetRecord] = []
    invalid: list[str] = []
    for preset in presets or ():
        try:
            normalized = normalize_financial_preset_record(preset)
        except Exception:
            invalid.append(str(getattr(preset, "preset_id", "") or getattr(preset, "name", "") or "invalid"))
            continue
        if not normalized.name:
            invalid.append(normalized.preset_id)
            continue
        valid.append(normalized)
    return tuple(valid), tuple(invalid)


def resolve_system_preset(preset_id: str) -> SystemFinancialPreset | None:
    normalized = str(preset_id or "").strip()
    for preset in system_financial_presets():
        if preset.preset_id == normalized:
            return preset
    return None


def resolve_financial_preset(
    preset_id: str | None,
    custom_presets: tuple[FinancialPresetRecord, ...] | list[FinancialPresetRecord],
    *,
    lang: str,
) -> ResolvedFinancialPreset | None:
    normalized_id = str(preset_id or "").strip()
    if not normalized_id:
        return None
    system_preset = resolve_system_preset(normalized_id)
    if system_preset is not None:
        return ResolvedFinancialPreset(
            preset_id=system_preset.preset_id,
            display_name=tr(system_preset.label_key, lang),
            origin="system",
            label_key=system_preset.label_key,
            description_key=system_preset.description_key,
            economics_cost_items_rows=system_preset.economics_cost_items_rows,
            economics_price_items_rows=system_preset.economics_price_items_rows,
        )
    valid_custom, _invalid = sanitize_financial_presets(tuple(custom_presets or ()))
    for preset in valid_custom:
        if preset.preset_id == normalized_id:
            return ResolvedFinancialPreset(
                preset_id=preset.preset_id,
                display_name=preset.name,
                origin="custom",
                label_key=None,
                description_key=None,
                economics_cost_items_rows=preset.economics_cost_items_rows,
                economics_price_items_rows=preset.economics_price_items_rows,
            )
    return None


def build_financial_preset_catalog(
    custom_presets: tuple[FinancialPresetRecord, ...] | list[FinancialPresetRecord],
    *,
    lang: str,
) -> tuple[ResolvedFinancialPreset, ...]:
    resolved: list[ResolvedFinancialPreset] = []
    for preset in system_financial_presets():
        resolved.append(
            ResolvedFinancialPreset(
                preset_id=preset.preset_id,
                display_name=tr(preset.label_key, lang),
                origin="system",
                label_key=preset.label_key,
                description_key=preset.description_key,
                economics_cost_items_rows=preset.economics_cost_items_rows,
                economics_price_items_rows=preset.economics_price_items_rows,
            )
        )
    valid_custom, _invalid = sanitize_financial_presets(tuple(custom_presets or ()))
    resolved.extend(
        ResolvedFinancialPreset(
            preset_id=preset.preset_id,
            display_name=preset.name,
            origin="custom",
            label_key=None,
            description_key=None,
            economics_cost_items_rows=preset.economics_cost_items_rows,
            economics_price_items_rows=preset.economics_price_items_rows,
        )
        for preset in valid_custom
    )
    return tuple(resolved)


def preset_signature(
    *,
    economics_cost_items_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    economics_price_items_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> str:
    return compute_economics_runtime_signature(economics_cost_items_rows, economics_price_items_rows)


def preset_record_signature(record: ResolvedFinancialPreset | FinancialPresetRecord | SystemFinancialPreset) -> str:
    return preset_signature(
        economics_cost_items_rows=record.economics_cost_items_rows,
        economics_price_items_rows=record.economics_price_items_rows,
    )


def preset_summary_counts(record: ResolvedFinancialPreset | FinancialPresetRecord | SystemFinancialPreset) -> dict[str, int]:
    price_rows = normalize_economics_price_items_frame(record.economics_price_items_rows).to_dict("records")
    return {
        "cost_count": len(normalize_economics_cost_items_frame(record.economics_cost_items_rows).index),
        "tax_count": sum(1 for row in price_rows if str(row.get("layer") or "").strip() == "tax"),
        "adjustment_count": sum(1 for row in price_rows if str(row.get("layer") or "").strip() in {"commercial", "sale"}),
    }


def normalized_preset_name_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def duplicate_preset_name(base_name: str, existing_names: list[str] | tuple[str, ...], *, lang: str) -> str:
    seed = tr("workspace.admin.economics.presets.copy_suffix", lang)
    candidate = f"{str(base_name or '').strip()} {seed}".strip()
    if not candidate:
        candidate = seed
    existing = {normalized_preset_name_key(name) for name in existing_names}
    if normalized_preset_name_key(candidate) not in existing:
        return candidate
    index = 2
    while True:
        next_candidate = f"{candidate} {index}"
        if normalized_preset_name_key(next_candidate) not in existing:
            return next_candidate
        index += 1


def financial_preset_name_conflict(
    name: str,
    custom_presets: tuple[FinancialPresetRecord, ...] | list[FinancialPresetRecord],
    *,
    lang: str,
    exclude_preset_id: str | None = None,
) -> str | None:
    normalized_name = normalized_preset_name_key(name)
    if not normalized_name:
        return None
    for preset in system_financial_presets():
        if normalized_name == normalized_preset_name_key(tr(preset.label_key, lang)):
            return preset.preset_id
    valid_custom, _invalid = sanitize_financial_presets(tuple(custom_presets or ()))
    for preset in valid_custom:
        if preset.preset_id == exclude_preset_id:
            continue
        if normalized_name == normalized_preset_name_key(preset.name):
            return preset.preset_id
    return None
