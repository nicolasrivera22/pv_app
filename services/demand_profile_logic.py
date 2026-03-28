from __future__ import annotations

from typing import Any

import pandas as pd


PROFILE_MODE_WEEKDAY = "perfil hora dia de semana"
PROFILE_MODE_TOTAL = "perfil general"
PROFILE_MODE_RELATIVE = "perfil horario relativo"

PROFILE_TYPE_RESIDENTIAL = "residencial"
PROFILE_TYPE_INDUSTRIAL = "industrial"
PROFILE_TYPE_MIXED = "mixta"

WEEKDAY_NAMES_ES = {
    1: "Lunes",
    2: "Martes",
    3: "Miercoles",
    4: "Jueves",
    5: "Viernes",
    6: "Sabado",
    7: "Domingo",
}

_WEEKDAY_ALIASES = {
    "1": 1,
    "mon": 1,
    "monday": 1,
    "lunes": 1,
    "2": 2,
    "tue": 2,
    "tues": 2,
    "tuesday": 2,
    "martes": 2,
    "3": 3,
    "wed": 3,
    "wednesday": 3,
    "mie": 3,
    "miercoles": 3,
    "miércoles": 3,
    "4": 4,
    "thu": 4,
    "thur": 4,
    "thurs": 4,
    "thursday": 4,
    "jueves": 4,
    "jue": 4,
    "5": 5,
    "fri": 5,
    "friday": 5,
    "viernes": 5,
    "vie": 5,
    "6": 6,
    "sat": 6,
    "saturday": 6,
    "sab": 6,
    "sabado": 6,
    "sábado": 6,
    "7": 7,
    "sun": 7,
    "sunday": 7,
    "dom": 7,
    "domingo": 7,
}

WEEKDAY_TABLE_COLUMNS = ["Dia", "DOW", "HOUR", "RES", "IND", "TOTAL_kWh"]
TOTAL_TABLE_COLUMNS = ["HOUR", "RES", "IND", "TOTAL_kWh"]
RELATIVE_TABLE_COLUMNS = ["HOUR", "W_RES", "W_IND", "W_RES_BASE", "W_IND_BASE", "W_TOTAL", "TOTAL_kWh"]
RELATIVE_BASE_COLUMNS = ["HOUR", "W_RES", "W_IND"]
RELATIVE_PREVIEW_COLUMNS = ["HOUR", "W_RES_BASE", "W_IND_BASE", "W_TOTAL", "TOTAL_kWh"]


def normalize_profile_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == PROFILE_MODE_WEEKDAY:
        return PROFILE_MODE_WEEKDAY
    if text == PROFILE_MODE_RELATIVE:
        return PROFILE_MODE_RELATIVE
    return PROFILE_MODE_TOTAL


def normalize_profile_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == PROFILE_TYPE_RESIDENTIAL:
        return PROFILE_TYPE_RESIDENTIAL
    if text == PROFILE_TYPE_INDUSTRIAL:
        return PROFILE_TYPE_INDUSTRIAL
    return PROFILE_TYPE_MIXED


def clamp_alpha_mix(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, numeric))


def coerce_month_energy(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, numeric)


def _frame(rows: list[dict[str, Any]] | pd.DataFrame | None) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame(rows or [])


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    next_frame = frame.copy()
    for column in columns:
        if column not in next_frame.columns:
            next_frame[column] = pd.NA
    return next_frame


def _replace_blank_with_na(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    next_frame = _ensure_columns(frame, columns)
    next_frame[columns] = next_frame[columns].replace(r"^\s*$", pd.NA, regex=True)
    return next_frame


def _coerce_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    next_frame = _replace_blank_with_na(frame, columns)
    for column in columns:
        next_frame[column] = pd.to_numeric(next_frame[column], errors="coerce")
    return next_frame


def _coerce_hour_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    bounded = numeric.where(numeric.isna(), numeric.round().clip(lower=0, upper=23))
    return bounded.astype("Int64")


def _normalize_weekday_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _resolve_dow(frame: pd.DataFrame) -> pd.Series:
    next_frame = _ensure_columns(frame, ["DOW", "Dia"])
    numeric = pd.to_numeric(next_frame["DOW"], errors="coerce")
    text = next_frame["DOW"].astype("string")
    text = text.fillna(next_frame["Dia"].astype("string"))
    resolved = text.map(lambda value: _WEEKDAY_ALIASES.get(_normalize_weekday_text(value)))
    combined = numeric.fillna(pd.to_numeric(resolved, errors="coerce"))
    combined = combined.where(combined.isna(), combined.round().clip(lower=1, upper=7))
    return combined.astype("Int64")


def _fill_weekday_names(dow_series: pd.Series, current_values: pd.Series) -> pd.Series:
    labels = dow_series.map(lambda value: WEEKDAY_NAMES_ES.get(int(value)) if pd.notna(value) else pd.NA)
    return current_values.astype("string").fillna(labels).replace("<NA>", pd.NA)


def _sum_series(left: pd.Series, right: pd.Series) -> pd.Series:
    left_valid = left.notna()
    right_valid = right.notna()
    total = left.fillna(0) + right.fillna(0)
    return total.where(left_valid | right_valid, pd.NA)


def frame_to_records(frame: pd.DataFrame, *, columns: list[str] | None = None) -> list[dict[str, Any]]:
    target = frame.copy()
    if columns is not None:
        target = _ensure_columns(target, columns)[columns]
    target = target.where(pd.notna(target), None)
    return target.to_dict("records")


def canonicalize_weekday_source(
    rows: list[dict[str, Any]] | pd.DataFrame | None,
) -> pd.DataFrame:
    frame = _replace_blank_with_na(_frame(rows), WEEKDAY_TABLE_COLUMNS)
    frame = _coerce_numeric(frame, ["HOUR", "RES", "IND"])
    frame["DOW"] = _resolve_dow(frame)
    frame["Dia"] = _fill_weekday_names(frame["DOW"], frame["Dia"])
    frame["HOUR"] = _coerce_hour_series(frame["HOUR"])
    frame["TOTAL_kWh"] = _sum_series(frame["RES"], frame["IND"])
    return frame[WEEKDAY_TABLE_COLUMNS].copy()


def canonicalize_total_source(
    rows: list[dict[str, Any]] | pd.DataFrame | None,
) -> pd.DataFrame:
    frame = _replace_blank_with_na(_frame(rows), TOTAL_TABLE_COLUMNS)
    frame = _coerce_numeric(frame, ["HOUR", "RES", "IND"])
    frame["HOUR"] = _coerce_hour_series(frame["HOUR"])
    frame["TOTAL_kWh"] = _sum_series(frame["RES"], frame["IND"])
    return frame[TOTAL_TABLE_COLUMNS].copy()


def derive_total_preview_from_weekday(
    rows: list[dict[str, Any]] | pd.DataFrame | None,
) -> pd.DataFrame:
    frame = canonicalize_weekday_source(rows)
    valid = frame.loc[frame["HOUR"].notna()].copy()
    if valid.empty:
        return pd.DataFrame(columns=TOTAL_TABLE_COLUMNS)
    valid["HOUR"] = valid["HOUR"].astype(int)
    aggregated = (
        valid.groupby("HOUR", dropna=False)[["RES", "IND"]]
        .mean()
        .reindex(list(range(24)))
        .reset_index()
        .rename(columns={"index": "HOUR"})
    )
    aggregated["TOTAL_kWh"] = _sum_series(aggregated["RES"], aggregated["IND"])
    aggregated["HOUR"] = aggregated["HOUR"].astype("Int64")
    return aggregated[TOTAL_TABLE_COLUMNS].copy()


def derive_relative_profile(
    rows: list[dict[str, Any]] | pd.DataFrame | None,
    *,
    profile_type: str,
    alpha_mix: Any,
    e_month_kwh: Any,
) -> pd.DataFrame:
    frame = _replace_blank_with_na(_frame(rows), RELATIVE_TABLE_COLUMNS)
    frame = _coerce_numeric(frame, ["HOUR", "W_RES", "W_IND"])
    frame["HOUR"] = _coerce_hour_series(frame["HOUR"])

    w_res = frame["W_RES"]
    w_ind = frame["W_IND"]
    sum_res = float(w_res.fillna(0).sum())
    sum_ind = float(w_ind.fillna(0).sum())

    if sum_res > 0:
        frame["W_RES_BASE"] = w_res.fillna(0) / sum_res
    else:
        frame["W_RES_BASE"] = w_res.fillna(0) * 0

    if sum_ind > 0:
        frame["W_IND_BASE"] = w_ind.fillna(0) / sum_ind
    else:
        frame["W_IND_BASE"] = w_ind.fillna(0) * 0

    normalized_profile_type = normalize_profile_type(profile_type)
    normalized_alpha = clamp_alpha_mix(alpha_mix)
    if normalized_profile_type == PROFILE_TYPE_RESIDENTIAL:
        frame["W_TOTAL"] = frame["W_RES_BASE"]
    elif normalized_profile_type == PROFILE_TYPE_INDUSTRIAL:
        frame["W_TOTAL"] = frame["W_IND_BASE"]
    else:
        frame["W_TOTAL"] = (frame["W_RES_BASE"] * (1.0 - normalized_alpha)) + (frame["W_IND_BASE"] * normalized_alpha)

    daily_energy = coerce_month_energy(e_month_kwh) / (365.0 / 12.0)
    valid_weight = frame["HOUR"].notna() | frame[["W_RES", "W_IND"]].notna().any(axis=1)
    frame["TOTAL_kWh"] = (frame["W_TOTAL"] * daily_energy).where(valid_weight, pd.NA)
    return frame[RELATIVE_TABLE_COLUMNS].copy()


def relative_preview_from_source(
    rows: list[dict[str, Any]] | pd.DataFrame | None,
    *,
    profile_type: str,
    alpha_mix: Any,
    e_month_kwh: Any,
) -> pd.DataFrame:
    derived = derive_relative_profile(
        rows,
        profile_type=profile_type,
        alpha_mix=alpha_mix,
        e_month_kwh=e_month_kwh,
    )
    preview = derived[RELATIVE_PREVIEW_COLUMNS].copy()
    valid = preview.loc[preview["HOUR"].notna()].copy()
    if valid.empty:
        return preview.iloc[0:0].copy()
    valid["HOUR"] = valid["HOUR"].astype(int)
    valid = valid.sort_values(["HOUR"], kind="mergesort").reset_index(drop=True)
    valid["HOUR"] = valid["HOUR"].astype("Int64")
    return valid[RELATIVE_PREVIEW_COLUMNS].copy()


def infer_relative_profile_type(
    rows: list[dict[str, Any]] | pd.DataFrame | None,
    *,
    alpha_mix: Any = 0.5,
) -> str:
    frame = _replace_blank_with_na(_frame(rows), RELATIVE_TABLE_COLUMNS)
    frame = _coerce_numeric(frame, ["W_RES_BASE", "W_IND_BASE", "W_TOTAL"])
    comparable = frame.loc[frame[["W_RES_BASE", "W_IND_BASE", "W_TOTAL"]].notna().all(axis=1)].copy()
    if not comparable.empty:
        residential_delta = float((comparable["W_TOTAL"] - comparable["W_RES_BASE"]).abs().max())
        industrial_delta = float((comparable["W_TOTAL"] - comparable["W_IND_BASE"]).abs().max())
        tolerance = 1e-9
        if residential_delta <= tolerance and industrial_delta > tolerance:
            return PROFILE_TYPE_RESIDENTIAL
        if industrial_delta <= tolerance and residential_delta > tolerance:
            return PROFILE_TYPE_INDUSTRIAL
    normalized_alpha = clamp_alpha_mix(alpha_mix)
    if normalized_alpha <= 1e-9:
        return PROFILE_TYPE_RESIDENTIAL
    if normalized_alpha >= 1.0 - 1e-9:
        return PROFILE_TYPE_INDUSTRIAL
    return PROFILE_TYPE_MIXED

