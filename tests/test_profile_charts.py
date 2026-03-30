from __future__ import annotations

from services import build_profile_chart, build_table_display_columns, load_example_config, tr


def _columns(table_kind: str, frame, *, lang: str = "es") -> list[dict]:
    columns, _ = build_table_display_columns(table_kind, list(frame.columns), lang)
    return columns


def test_month_profile_chart_builds_combo_chart_with_secondary_axis() -> None:
    bundle = load_example_config()
    render = build_profile_chart(
        "month-profile-editor",
        bundle.month_profile_table.to_dict("records"),
        _columns("month_profile", bundle.month_profile_table, lang="en"),
        "en",
    )

    assert render.row_target == "main"
    assert render.title == tr("workbench.profiles.month", "en")
    assert any(trace.type == "bar" for trace in render.figure.data)
    assert any(trace.type == "scatter" for trace in render.figure.data)
    assert render.figure.layout.yaxis2.overlaying == "y"


def test_sun_profile_chart_renders_sorted_hourly_area_line() -> None:
    bundle = load_example_config()
    render = build_profile_chart(
        "sun-profile-editor",
        bundle.sun_profile_table.to_dict("records"),
        _columns("sun_profile", bundle.sun_profile_table, lang="en"),
        "en",
    )

    trace = render.figure.data[0]
    assert render.row_target == "main"
    assert trace.type == "scatter"
    assert trace.fill == "tozeroy"
    assert list(trace.x) == sorted(trace.x)


def test_demand_weights_chart_includes_optional_base_traces_only_when_valid() -> None:
    bundle = load_example_config()
    full_render = build_profile_chart(
        "demand-profile-weights-editor",
        bundle.demand_profile_weights_table.to_dict("records"),
        _columns("demand_profile_weights", bundle.demand_profile_weights_table, lang="en"),
        "en",
    )
    no_base_rows = [
        {
            "HOUR": 0,
            "W_RES": 0.5,
            "W_IND": 0.2,
            "W_TOTAL": 0.7,
            "W_RES_BASE": "",
            "W_IND_BASE": "",
        }
    ]
    no_base_render = build_profile_chart(
        "demand-profile-weights-editor",
        no_base_rows,
        _columns("demand_profile_weights", bundle.demand_profile_weights_table, lang="en"),
        "en",
    )

    assert len(full_render.figure.data) == 4
    assert len(no_base_render.figure.data) == 1
    assert all("base" not in str(trace.name).lower() for trace in no_base_render.figure.data)


def test_weekday_heatmap_builds_7x24_matrix_and_derives_total_when_missing() -> None:
    bundle = load_example_config()
    rows = []
    for row in bundle.demand_profile_table.to_dict("records"):
        next_row = dict(row)
        next_row["TOTAL_kWh"] = ""
        rows.append(next_row)

    render = build_profile_chart(
        "demand-profile-editor",
        rows,
        _columns("demand_profile", bundle.demand_profile_table, lang="es"),
        "es",
    )

    trace = render.figure.data[0]
    assert render.row_target == "secondary"
    assert trace.type == "heatmap"
    assert len(trace.x) == 24
    assert len(trace.y) == 7
    assert len(trace.z) == 7
    assert len(trace.z[0]) == 24
    assert trace.y[0] == tr("workbench.profile_chart.weekday.1", "es")


def test_weekday_heatmap_accepts_textual_weekdays_from_dow_or_dia() -> None:
    bundle = load_example_config()
    rows = []
    for row in bundle.demand_profile_table.to_dict("records"):
        next_row = dict(row)
        next_row["DOW"] = next_row["Dia"]
        rows.append(next_row)

    render = build_profile_chart(
        "demand-profile-editor",
        rows,
        _columns("demand_profile", bundle.demand_profile_table, lang="es"),
        "es",
    )

    trace = render.figure.data[0]
    assert trace.type == "heatmap"
    assert len(trace.x) == 24
    assert len(trace.y) == 7
    assert trace.y[0] == tr("workbench.profile_chart.weekday.1", "es")


def test_general_demand_chart_derives_total_when_needed() -> None:
    bundle = load_example_config()
    rows = []
    for row in bundle.demand_profile_general_table.to_dict("records"):
        next_row = dict(row)
        next_row["TOTAL_kWh"] = ""
        rows.append(next_row)

    render = build_profile_chart(
        "demand-profile-general-editor",
        rows,
        _columns("demand_profile_general", bundle.demand_profile_general_table, lang="en"),
        "en",
    )

    assert render.row_target == "secondary"
    assert [trace.type for trace in render.figure.data] == ["scatter", "scatter", "scatter"]
    assert any("total" in str(trace.name).lower() for trace in render.figure.data)


def test_unknown_profile_chart_ids_return_localized_empty_figure() -> None:
    bundle = load_example_config()

    render = build_profile_chart(
        "price-kwp-editor",
        bundle.cop_kwp_table.to_dict("records"),
        _columns("cop_kwp", bundle.cop_kwp_table, lang="en"),
        "en",
    )

    assert render.row_target == "main"
    assert render.title == ""
    assert not render.figure.data


def test_empty_or_partial_rows_return_a_localized_empty_figure() -> None:
    bundle = load_example_config()
    render = build_profile_chart(
        "sun-profile-editor",
        [{"HOUR": "", "SOL": ""}, {"HOUR": "x", "SOL": "y"}],
        _columns("sun_profile", bundle.sun_profile_table, lang="es"),
        "es",
    )

    assert not render.figure.data
    assert render.figure.layout.annotations[0].text == tr("workbench.profile_chart.empty", "es")
