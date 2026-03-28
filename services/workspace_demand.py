from __future__ import annotations

from typing import Any

from dash import html
import pandas as pd

from .demand_profile_logic import (
    PROFILE_MODE_RELATIVE,
    PROFILE_MODE_TOTAL,
    PROFILE_MODE_WEEKDAY,
    PROFILE_TYPE_MIXED,
    RELATIVE_BASE_COLUMNS,
    RELATIVE_TABLE_COLUMNS,
    TOTAL_TABLE_COLUMNS,
    WEEKDAY_NAMES_ES,
    WEEKDAY_TABLE_COLUMNS,
    canonicalize_total_source,
    canonicalize_weekday_source,
    clamp_alpha_mix,
    coerce_month_energy,
    derive_relative_profile,
    derive_total_preview_from_weekday,
    frame_to_records,
    infer_relative_profile_type,
    normalize_profile_mode,
    normalize_profile_type,
    relative_preview_from_source,
)
from .i18n import tr
from .profile_charts import build_profile_chart
from .ui_schema import build_table_display_columns
from .workbench_ui import collect_config_updates, demand_profile_visibility


DEMAND_PROFILE_CONFIG_FIELDS = {"use_excel_profile", "alpha_mix", "E_month_kWh"}


def mark_columns_readonly(columns: list[dict] | None, readonly_ids: set[str]) -> list[dict]:
    next_columns: list[dict] = []
    for column in columns or []:
        next_column = dict(column)
        if str(next_column.get("id", "")) in readonly_ids:
            next_column["editable"] = False
        next_columns.append(next_column)
    return next_columns


def mark_all_columns_readonly(columns: list[dict] | None) -> list[dict]:
    return mark_columns_readonly(columns, {str(column.get("id", "")) for column in columns or []})


def _mode_tooltip(mode: str, lang: str) -> str:
    normalized = normalize_profile_mode(mode)
    if normalized == PROFILE_MODE_WEEKDAY:
        return tr("workbench.profiles.mode.note.weekday", lang)
    if normalized == PROFILE_MODE_RELATIVE:
        return tr("workbench.profiles.mode.note.relative", lang)
    return tr("workbench.profiles.mode.note.total", lang)


def _mode_option(label: str, *, tooltip: str, value: str) -> dict[str, object]:
    return {
        "label": html.Span(label, title=tooltip, className="demand-profile-mode-option-label"),
        "value": value,
    }


def demand_mode_options(lang: str) -> list[dict[str, object]]:
    return [
        _mode_option(
            tr("workbench.profiles.mode.weekday", lang),
            tooltip=_mode_tooltip(PROFILE_MODE_WEEKDAY, lang),
            value=PROFILE_MODE_WEEKDAY,
        ),
        _mode_option(
            tr("workbench.profiles.mode.total", lang),
            tooltip=_mode_tooltip(PROFILE_MODE_TOTAL, lang),
            value=PROFILE_MODE_TOTAL,
        ),
        _mode_option(
            tr("workbench.profiles.mode.relative", lang),
            tooltip=_mode_tooltip(PROFILE_MODE_RELATIVE, lang),
            value=PROFILE_MODE_RELATIVE,
        ),
    ]


def relative_profile_type_options(lang: str) -> list[dict[str, str]]:
    return [
        {"label": tr("workbench.profiles.relative.type.residential", lang), "value": "residencial"},
        {"label": tr("workbench.profiles.relative.type.industrial", lang), "value": "industrial"},
        {"label": tr("workbench.profiles.relative.type.mixed", lang), "value": "mixta"},
    ]


def demand_profile_mode_note(profile_mode: str, lang: str) -> str:
    return _mode_tooltip(profile_mode, lang)


def demand_profile_control_updates(
    base_config: dict[str, object],
    *,
    assumption_input_ids,
    assumption_values,
    mode_value,
    alpha_mix_value,
    e_month_value,
) -> dict[str, object]:
    updates = collect_config_updates(assumption_input_ids, assumption_values, base_config)
    profile_mode = normalize_profile_mode(mode_value if mode_value is not None else updates.get("use_excel_profile"))
    updates["use_excel_profile"] = profile_mode
    if profile_mode == PROFILE_MODE_RELATIVE:
        updates["alpha_mix"] = clamp_alpha_mix(alpha_mix_value if alpha_mix_value is not None else updates.get("alpha_mix"))
        updates["E_month_kWh"] = coerce_month_energy(e_month_value if e_month_value is not None else updates.get("E_month_kWh"))
    else:
        updates["alpha_mix"] = clamp_alpha_mix(base_config.get("alpha_mix"))
        updates["E_month_kWh"] = coerce_month_energy(base_config.get("E_month_kWh"))
    return updates


def _full_total_editor_source(rows: list[dict[str, Any]] | pd.DataFrame | None) -> pd.DataFrame:
    frame = canonicalize_total_source(rows)
    valid = frame.loc[frame["HOUR"].notna(), ["HOUR", "RES", "IND"]].copy()
    if not valid.empty:
        valid["HOUR"] = valid["HOUR"].astype(int)
        valid = valid.drop_duplicates(subset=["HOUR"], keep="last")
    template = pd.DataFrame({"HOUR": list(range(24))})
    merged = template.merge(valid, on="HOUR", how="left")
    for column in ("RES", "IND"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    merged["TOTAL_kWh"] = merged["RES"] + merged["IND"]
    merged["HOUR"] = merged["HOUR"].astype("Int64")
    return merged[TOTAL_TABLE_COLUMNS].copy()


def _full_weekday_editor_source(rows: list[dict[str, Any]] | pd.DataFrame | None) -> pd.DataFrame:
    frame = canonicalize_weekday_source(rows)
    valid = frame.loc[frame["DOW"].notna() & frame["HOUR"].notna(), ["DOW", "HOUR", "RES", "IND"]].copy()
    if not valid.empty:
        valid["DOW"] = valid["DOW"].astype(int)
        valid["HOUR"] = valid["HOUR"].astype(int)
        valid = valid.drop_duplicates(subset=["DOW", "HOUR"], keep="last")
    template = pd.MultiIndex.from_product([range(1, 8), range(24)], names=["DOW", "HOUR"]).to_frame(index=False)
    merged = template.merge(valid, on=["DOW", "HOUR"], how="left")
    for column in ("RES", "IND"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    merged["Dia"] = merged["DOW"].map(WEEKDAY_NAMES_ES)
    merged["TOTAL_kWh"] = merged["RES"] + merged["IND"]
    merged["DOW"] = merged["DOW"].astype("Int64")
    merged["HOUR"] = merged["HOUR"].astype("Int64")
    return merged[WEEKDAY_TABLE_COLUMNS].copy()


def _full_relative_editor_source(
    rows: list[dict[str, Any]] | pd.DataFrame | None,
    *,
    profile_type: str,
    alpha_mix: Any,
    e_month_kwh: Any,
) -> pd.DataFrame:
    frame = pd.DataFrame([] if rows is None else rows).copy()
    for column in RELATIVE_BASE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    valid = frame[RELATIVE_BASE_COLUMNS].copy()
    valid["HOUR"] = pd.to_numeric(valid["HOUR"], errors="coerce")
    valid["HOUR"] = valid["HOUR"].where(valid["HOUR"].isna(), valid["HOUR"].round().clip(lower=0, upper=23))
    valid["W_RES"] = pd.to_numeric(valid["W_RES"], errors="coerce")
    valid["W_IND"] = pd.to_numeric(valid["W_IND"], errors="coerce")
    valid = valid.loc[valid["HOUR"].notna()].copy()
    if not valid.empty:
        valid["HOUR"] = valid["HOUR"].astype(int)
        valid = valid.drop_duplicates(subset=["HOUR"], keep="last")
    template = pd.DataFrame({"HOUR": list(range(24))}).merge(valid, on="HOUR", how="left")
    for column in ("W_RES", "W_IND"):
        template[column] = pd.to_numeric(template[column], errors="coerce").fillna(0.0)
    return derive_relative_profile(
        template[RELATIVE_BASE_COLUMNS],
        profile_type=profile_type,
        alpha_mix=alpha_mix,
        e_month_kwh=e_month_kwh,
    )[RELATIVE_TABLE_COLUMNS].copy()


def _relative_preview_rows(
    relative_source: pd.DataFrame,
    *,
    profile_type: str,
    alpha_mix: Any,
    e_month_kwh: Any,
) -> pd.DataFrame:
    preview = relative_preview_from_source(
        relative_source,
        profile_type=profile_type,
        alpha_mix=alpha_mix,
        e_month_kwh=e_month_kwh,
    )
    if preview.empty:
        return preview
    return preview.sort_values(["HOUR"], kind="mergesort").reset_index(drop=True)


def _month_display_value(profile_mode: str, *, weekday_source: pd.DataFrame, total_source: pd.DataFrame, relative_e_month: float) -> float:
    if profile_mode == PROFILE_MODE_RELATIVE:
        return relative_e_month
    if profile_mode == PROFILE_MODE_WEEKDAY:
        return round(float(weekday_source["TOTAL_kWh"].fillna(0).sum()) * 4.286, 2)
    return round(float(total_source["TOTAL_kWh"].fillna(0).sum()) * 30.0, 2)


def build_demand_profile_ui_state(
    *,
    bundle,
    lang: str,
    profile_mode_value=None,
    relative_profile_type_value=None,
    alpha_mix_value=None,
    e_month_value=None,
    weekday_rows=None,
    total_rows=None,
    relative_rows=None,
) -> dict[str, object]:
    profile_mode = normalize_profile_mode(
        profile_mode_value if profile_mode_value is not None else bundle.config.get("use_excel_profile", PROFILE_MODE_TOTAL)
    )
    alpha_mix = clamp_alpha_mix(
        alpha_mix_value if profile_mode == PROFILE_MODE_RELATIVE and alpha_mix_value is not None else bundle.config.get("alpha_mix", 0.5)
    )
    relative_e_month = coerce_month_energy(
        e_month_value if profile_mode == PROFILE_MODE_RELATIVE and e_month_value is not None else bundle.config.get("E_month_kWh", 0.0)
    )

    resolved_profile_type = normalize_profile_type(
        relative_profile_type_value
        if relative_profile_type_value is not None
        else infer_relative_profile_type(relative_rows if relative_rows is not None else bundle.demand_profile_weights_table, alpha_mix=alpha_mix)
    )

    weekday_source = _full_weekday_editor_source(weekday_rows if weekday_rows is not None else bundle.demand_profile_table)
    total_source = _full_total_editor_source(total_rows if total_rows is not None else bundle.demand_profile_general_table)
    relative_source = _full_relative_editor_source(
        relative_rows if relative_rows is not None else bundle.demand_profile_weights_table,
        profile_type=resolved_profile_type,
        alpha_mix=alpha_mix,
        e_month_kwh=relative_e_month,
    )
    total_preview = derive_total_preview_from_weekday(weekday_source)
    relative_preview = _relative_preview_rows(
        relative_source,
        profile_type=resolved_profile_type,
        alpha_mix=alpha_mix,
        e_month_kwh=relative_e_month,
    )
    visibility = demand_profile_visibility(profile_mode)
    if profile_mode == PROFILE_MODE_TOTAL:
        visibility["demand-profile-general-panel"] = {"display": "block", "gridColumn": "1 / -1"}

    weekday_columns, weekday_tooltips = build_table_display_columns("demand_profile", list(weekday_source.columns), lang)
    total_columns, total_tooltips = build_table_display_columns("demand_profile_general", list(total_source.columns), lang)
    relative_columns, relative_tooltips = build_table_display_columns("demand_profile_weights", list(relative_source.columns), lang)
    total_preview_columns, total_preview_tooltips = build_table_display_columns("demand_profile_general", list(total_preview.columns), lang)
    relative_preview_columns, relative_preview_tooltips = build_table_display_columns("demand_profile_weights", list(relative_preview.columns), lang)

    is_relative = profile_mode == PROFILE_MODE_RELATIVE
    month_value = _month_display_value(
        profile_mode,
        weekday_source=weekday_source,
        total_source=total_source,
        relative_e_month=relative_e_month,
    )

    return {
        "profile_mode": profile_mode,
        "profile_type": resolved_profile_type,
        "alpha_mix": alpha_mix,
        "e_month_kwh": month_value,
        "weekday_source_rows": frame_to_records(weekday_source),
        "total_source_rows": frame_to_records(total_source),
        "relative_source_rows": frame_to_records(relative_source),
        "total_preview_rows": frame_to_records(total_preview),
        "relative_preview_rows": frame_to_records(relative_preview),
        "weekday_columns": mark_columns_readonly(weekday_columns, {"TOTAL_kWh"}),
        "weekday_tooltips": weekday_tooltips,
        "total_columns": mark_columns_readonly(total_columns, {"TOTAL_kWh"}),
        "total_tooltips": total_tooltips,
        "relative_columns": mark_columns_readonly(relative_columns, {"W_RES_BASE", "W_IND_BASE", "W_TOTAL", "TOTAL_kWh"}),
        "relative_tooltips": relative_tooltips,
        "total_preview_columns": mark_all_columns_readonly(total_preview_columns),
        "total_preview_tooltips": total_preview_tooltips,
        "relative_preview_columns": mark_all_columns_readonly(relative_preview_columns),
        "relative_preview_tooltips": relative_preview_tooltips,
        "visibility": visibility,
        "relative_grid_style": {"display": "grid"} if is_relative else {"display": "none"},
        "secondary_grid_style": {"display": "grid"} if not is_relative else {"display": "none"},
        "weights_preview_style": {"display": "block"} if is_relative else {"display": "none"},
        "mode_note": demand_profile_mode_note(profile_mode, lang),
        "alpha_shell_style": {"display": "block"} if is_relative else {"display": "none"},
        "type_shell_style": {"display": "block"} if is_relative else {"display": "none"},
        "energy_shell_style": {"display": "block"} if is_relative else {"display": "block", "gridColumn": "1 / -1"},
        "alpha_disabled": not (is_relative and resolved_profile_type == PROFILE_TYPE_MIXED),
        "energy_disabled": not is_relative,
    }


def build_active_demand_chart(
    *,
    lang: str,
    demand_state: dict[str, object],
) -> dict[str, object]:
    profile_mode = normalize_profile_mode(str(demand_state.get("profile_mode") or ""))
    if profile_mode == PROFILE_MODE_WEEKDAY:
        render = build_profile_chart(
            "demand-profile-editor",
            demand_state.get("weekday_source_rows"),
            demand_state.get("weekday_columns"),
            lang,
        )
    elif profile_mode == PROFILE_MODE_TOTAL:
        render = build_profile_chart(
            "demand-profile-general-editor",
            demand_state.get("total_source_rows"),
            demand_state.get("total_columns"),
            lang,
        )
    else:
        render = build_profile_chart(
            "demand-profile-weights-editor",
            demand_state.get("relative_source_rows"),
            demand_state.get("relative_columns"),
            lang,
        )
    return {
        "style": {"display": "grid"},
        "title": render.title,
        "copy": render.subtitle,
        "figure": render.figure,
    }
