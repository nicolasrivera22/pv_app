from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import unicodedata

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .demand_profile_logic import (
    canonicalize_total_source,
    canonicalize_weekday_source,
)
from .i18n import tr
from .result_views import abbreviated_month_labels


TABLE_ID_MONTH = "month-profile-editor"
TABLE_ID_SUN = "sun-profile-editor"
TABLE_ID_DEMAND_WEIGHTS = "demand-profile-weights-editor"
TABLE_ID_DEMAND_WEEKDAY = "demand-profile-editor"
TABLE_ID_DEMAND_GENERAL = "demand-profile-general-editor"


@dataclass(frozen=True)
class ProfileChartRender:
    row_target: str
    title: str
    subtitle: str
    figure: go.Figure


@dataclass(frozen=True)
class ProfileChartSpec:
    table_id: str
    row_target: str
    title_key: str
    subtitle_key: str
    builder: Callable[[list[dict] | None, list[dict] | None, str], go.Figure]


def _column_name_map(columns: list[dict] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for column in columns or []:
        key = str(column.get("id", "")).strip()
        if not key:
            continue
        name = column.get("name", key)
        if isinstance(name, (list, tuple)):
            label = " / ".join(str(part).strip() for part in name if str(part).strip())
        else:
            label = str(name).strip()
        mapping[key] = label or key
    return mapping


def _label(column_map: dict[str, str], key: str, fallback: str | None = None) -> str:
    return column_map.get(key) or fallback or key


def _frame(rows: list[dict] | None) -> pd.DataFrame:
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


def _drop_rows_blank_for(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.loc[~frame[columns].isna().all(axis=1)].copy()


def _empty_profile_figure(lang: str, *, message: str | None = None) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        template="plotly_white",
        margin={"l": 44, "r": 18, "t": 20, "b": 36},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": message or tr("workbench.profile_chart.empty", lang),
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 13, "color": "#475569"},
            }
        ],
    )
    return figure


def _apply_chart_layout(
    figure: go.Figure,
    *,
    lang: str,
    xaxis_title: str | None = None,
    yaxis_title: str | None = None,
    secondary_yaxis_title: str | None = None,
    hovermode: str | None = "x unified",
) -> go.Figure:
    figure.update_layout(
        template="plotly_white",
        height=320,
        margin={"l": 48, "r": 28 if secondary_yaxis_title else 18, "t": 18, "b": 42},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode=hovermode,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.03, "xanchor": "left", "x": 0},
    )
    if xaxis_title:
        figure.update_xaxes(title_text=xaxis_title)
    if secondary_yaxis_title:
        if yaxis_title:
            figure.update_yaxes(title_text=yaxis_title, secondary_y=False)
        figure.update_yaxes(title_text=secondary_yaxis_title, secondary_y=True)
    elif yaxis_title:
        figure.update_yaxes(title_text=yaxis_title)
    return figure


def _weekday_label(day_number: int, lang: str) -> str:
    return tr(f"workbench.profile_chart.weekday.{int(day_number)}", lang)


def _normalized_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _resolve_weekday_numbers(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)

    dow_source = frame["DOW"] if "DOW" in frame else pd.Series(pd.NA, index=frame.index, dtype=object)
    resolved = pd.to_numeric(dow_source, errors="coerce")

    text_source = dow_source.astype("string")
    if "Dia" in frame:
        text_source = text_source.fillna(frame["Dia"].astype("string"))

    weekday_map = {
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
        "miercoles": 3,
        "miércoles": 3,
        "mie": 3,
        "miec": 3,
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
        "sabado": 6,
        "sábado": 6,
        "sab": 6,
        "7": 7,
        "sun": 7,
        "sunday": 7,
        "domingo": 7,
        "dom": 7,
    }
    text_numbers = text_source.map(lambda value: weekday_map.get(_normalized_text(value)))
    return resolved.fillna(pd.to_numeric(text_numbers, errors="coerce"))


def _build_month_profile_figure(rows: list[dict] | None, columns: list[dict] | None, lang: str) -> go.Figure:
    column_map = _column_name_map(columns)
    frame = _coerce_numeric(_frame(rows), ["MONTH", "Demand_month", "HSP_month"])
    frame = frame.loc[frame["MONTH"].notna() & ~(frame[["Demand_month", "HSP_month"]].isna().all(axis=1))].copy()
    if frame.empty:
        return _empty_profile_figure(lang)
    frame = frame.sort_values(["MONTH"], kind="mergesort")
    labels = abbreviated_month_labels(frame["MONTH"], lang=lang)
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    if frame["Demand_month"].notna().any():
        figure.add_bar(
            x=labels,
            y=frame["Demand_month"],
            name=_label(column_map, "Demand_month"),
            marker_color="#0f766e",
            opacity=0.86,
            secondary_y=False,
        )
    if frame["HSP_month"].notna().any():
        figure.add_scatter(
            x=labels,
            y=frame["HSP_month"],
            name=_label(column_map, "HSP_month"),
            mode="lines+markers",
            line={"color": "#2563eb", "width": 2.5},
            marker={"size": 7, "color": "#1d4ed8"},
            secondary_y=True,
        )
    if not figure.data:
        return _empty_profile_figure(lang)
    return _apply_chart_layout(
        figure,
        lang=lang,
        xaxis_title=tr("common.chart.month", lang),
        yaxis_title=_label(column_map, "Demand_month"),
        secondary_yaxis_title=_label(column_map, "HSP_month"),
    )


def _build_sun_profile_figure(rows: list[dict] | None, columns: list[dict] | None, lang: str) -> go.Figure:
    column_map = _column_name_map(columns)
    frame = _coerce_numeric(_frame(rows), ["HOUR", "SOL"])
    frame = frame.loc[frame["HOUR"].notna() & frame["SOL"].notna()].copy()
    if frame.empty:
        return _empty_profile_figure(lang)
    frame = frame.sort_values(["HOUR"], kind="mergesort")
    figure = go.Figure()
    figure.add_scatter(
        x=frame["HOUR"],
        y=frame["SOL"],
        name=_label(column_map, "SOL"),
        mode="lines",
        fill="tozeroy",
        line={"color": "#f59e0b", "width": 2.5},
    )
    return _apply_chart_layout(
        figure,
        lang=lang,
        xaxis_title=tr("common.chart.hour", lang),
        yaxis_title=_label(column_map, "SOL"),
    )


def _build_demand_weights_figure(rows: list[dict] | None, columns: list[dict] | None, lang: str) -> go.Figure:
    column_map = _column_name_map(columns)
    numeric_columns = ["HOUR", "W_RES", "W_IND", "W_TOTAL", "W_RES_BASE", "W_IND_BASE", "TOTAL_kWh"]
    frame = _coerce_numeric(_frame(rows), numeric_columns)
    frame = frame.loc[
        frame["HOUR"].notna()
        & ~(frame[["W_RES", "W_IND", "W_TOTAL", "W_RES_BASE", "W_IND_BASE", "TOTAL_kWh"]].isna().all(axis=1))
    ].copy()
    if frame.empty:
        return _empty_profile_figure(lang)
    frame = frame.sort_values(["HOUR"], kind="mergesort")
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    traces = [
        ("W_RES_BASE", "#0f766e", "dash", "scatter", False),
        ("W_IND_BASE", "#2563eb", "dash", "scatter", False),
        ("W_TOTAL", "#7c3aed", "solid", "scatter", False),
        ("TOTAL_kWh", "rgba(235, 37, 60, 0.41)", "dash", "bar", True),
    ]
    for key, color, dash, mode, secondary_y in traces:
        if key not in frame or not frame[key].notna().any():
            continue
        if mode == "bar":
            figure.add_bar(
                x=frame["HOUR"],
                y=frame[key],
                name=_label(column_map, key),
                marker_color=color,
                opacity=0.72,
                secondary_y=bool(secondary_y),
            )
        else:
            figure.add_scatter(
                x=frame["HOUR"],
                y=frame[key],
                name=_label(column_map, key),
                mode="lines",
                line={"color": color, "width": 2.4 if dash == "solid" else 1.6, "dash": dash},
                opacity=0.95 if dash == "solid" else 0.55,
                secondary_y=bool(secondary_y),
            )
    if not figure.data:
        return _empty_profile_figure(lang)
    return _apply_chart_layout(
        figure,
        lang=lang,
        xaxis_title=tr("common.chart.hour", lang),
        secondary_yaxis_title=_label(column_map, "TOTAL_kWh") if frame["TOTAL_kWh"].notna().any() else None,
    )


def _build_demand_weekday_figure(rows: list[dict] | None, columns: list[dict] | None, lang: str) -> go.Figure:
    column_map = _column_name_map(columns)
    frame = canonicalize_weekday_source(rows)
    frame["DOW_RESOLVED"] = pd.to_numeric(frame["DOW"], errors="coerce")
    frame["TOTAL_RESOLVED"] = frame["TOTAL_kWh"]
    frame = frame.loc[frame["DOW_RESOLVED"].notna() & frame["HOUR"].notna() & frame["TOTAL_RESOLVED"].notna()].copy()
    if frame.empty:
        return _empty_profile_figure(lang)
    frame["DOW_RESOLVED"] = frame["DOW_RESOLVED"].astype(int)
    frame["HOUR"] = frame["HOUR"].astype(int)
    matrix = (
        frame.pivot_table(index="DOW_RESOLVED", columns="HOUR", values="TOTAL_RESOLVED", aggfunc="mean")
        .reindex(index=list(range(1, 8)), columns=list(range(24)))
    )
    if matrix.isna().all().all():
        return _empty_profile_figure(lang)
    y_labels = [_weekday_label(day_number, lang) for day_number in matrix.index]
    zmax = float(matrix.max().max()) if matrix.notna().any().any() else None
    figure = go.Figure(
        data=[
            go.Heatmap(
                x=list(matrix.columns),
                y=y_labels,
                z=matrix.values,
                colorscale="YlGnBu",
                colorbar={"title": _label(column_map, "TOTAL_kWh", tr("common.chart.energy_kwh", lang))},
                zmin=0,
                zmax=zmax,
                hovertemplate="%{y}<br>"
                + f"{_label(column_map, 'HOUR', tr('common.chart.hour', lang))}: "
                + "%{x}<br>"
                + f"{_label(column_map, 'TOTAL_kWh', tr('common.chart.energy_kwh', lang))}: "
                + "%{z:.3f}<extra></extra>",
            )
        ]
    )
    figure.update_yaxes(autorange="reversed")
    return _apply_chart_layout(
        figure,
        lang=lang,
        xaxis_title=tr("common.chart.hour", lang),
        hovermode=None,
    )


def _build_demand_general_figure(rows: list[dict] | None, columns: list[dict] | None, lang: str) -> go.Figure:
    column_map = _column_name_map(columns)
    frame = canonicalize_total_source(rows)
    frame["TOTAL_RESOLVED"] = frame["TOTAL_kWh"]
    frame = frame.loc[frame["HOUR"].notna() & ~(frame[["RES", "IND", "TOTAL_RESOLVED"]].isna().all(axis=1))].copy()
    if frame.empty:
        return _empty_profile_figure(lang)
    frame = frame.sort_values(["HOUR"], kind="mergesort")
    figure = go.Figure()
    for key, source_key, color in [
        ("RES", "RES", "#0f766e"),
        ("IND", "IND", "#2563eb"),
        ("TOTAL_RESOLVED", "TOTAL_kWh", "#7c3aed"),
    ]:
        if key not in frame or not frame[key].notna().any():
            continue
        figure.add_scatter(
            x=frame["HOUR"],
            y=frame[key],
            name=_label(column_map, source_key),
            mode="lines",
            line={"color": color, "width": 2.4},
        )
    if not figure.data:
        return _empty_profile_figure(lang)
    return _apply_chart_layout(
        figure,
        lang=lang,
        xaxis_title=tr("common.chart.hour", lang),
    )


PROFILE_CHARTS: dict[str, ProfileChartSpec] = {
    TABLE_ID_MONTH: ProfileChartSpec(
        table_id=TABLE_ID_MONTH,
        row_target="main",
        title_key="workbench.profiles.month",
        subtitle_key="workbench.profile_chart.subtitle.month",
        builder=_build_month_profile_figure,
    ),
    TABLE_ID_SUN: ProfileChartSpec(
        table_id=TABLE_ID_SUN,
        row_target="main",
        title_key="workbench.profiles.sun",
        subtitle_key="workbench.profile_chart.subtitle.sun",
        builder=_build_sun_profile_figure,
    ),
    TABLE_ID_DEMAND_WEIGHTS: ProfileChartSpec(
        table_id=TABLE_ID_DEMAND_WEIGHTS,
        row_target="main",
        title_key="workbench.profiles.demand_weights",
        subtitle_key="workbench.profile_chart.subtitle.demand_weights",
        builder=_build_demand_weights_figure,
    ),
    TABLE_ID_DEMAND_WEEKDAY: ProfileChartSpec(
        table_id=TABLE_ID_DEMAND_WEEKDAY,
        row_target="secondary",
        title_key="workbench.profiles.demand_weekday",
        subtitle_key="workbench.profile_chart.subtitle.demand_weekday",
        builder=_build_demand_weekday_figure,
    ),
    TABLE_ID_DEMAND_GENERAL: ProfileChartSpec(
        table_id=TABLE_ID_DEMAND_GENERAL,
        row_target="secondary",
        title_key="workbench.profiles.demand_general",
        subtitle_key="workbench.profile_chart.subtitle.demand_general",
        builder=_build_demand_general_figure,
    ),
}


def build_profile_chart(table_id: str, rows: list[dict] | None, columns: list[dict] | None, lang: str = "es") -> ProfileChartRender:
    spec = PROFILE_CHARTS.get(str(table_id or "").strip())
    if spec is None:
        return ProfileChartRender(
            row_target="main",
            title="",
            subtitle="",
            figure=_empty_profile_figure(lang),
        )
    try:
        figure = spec.builder(rows, columns, lang)
    except Exception:
        figure = _empty_profile_figure(lang)
    return ProfileChartRender(
        row_target=spec.row_target,
        title=tr(spec.title_key, lang),
        subtitle=tr(spec.subtitle_key, lang),
        figure=figure,
    )
