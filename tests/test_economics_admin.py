from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from components.admin_view import admin_secure_content
from components.economics_editor import economics_editor_section
import services.workspace_admin_callbacks as admin_callbacks
import services.workspace_results_callbacks as results_callbacks
from services.candidate_financials import build_candidate_financial_snapshot
from services import (
    ScenarioSessionState,
    ValidationIssue,
    add_scenario,
    add_financial_preset,
    bootstrap_client_session,
    clear_all_admin_session_access,
    clear_session_states,
    clear_workspace_drafts,
    commit_client_session,
    create_financial_preset_record,
    create_scenario_record,
    fingerprint_deterministic_input,
    get_workspace_draft,
    grant_admin_session_access,
    load_example_config,
    open_project,
    refresh_bundle_issues,
    resolve_client_session,
    resolve_deterministic_scan,
    run_scenario_scan,
    save_project,
    set_admin_pin,
    tr,
    update_config_table_values,
    update_scenario_bundle,
)
from services.financial_presets import build_financial_preset_catalog, resolve_financial_preset
from services.economics_tables import RICH_MIGRATION_NOTE_PREFIX, normalize_economics_cost_items_with_issues
from services.economics_tables import (
    economics_cost_items_rows_from_editor,
    economics_cost_items_rows_to_editor,
    economics_price_items_rows_from_editor,
    economics_price_items_rows_from_split_editors,
    economics_price_items_rows_to_editor,
    economics_price_items_rows_to_section_editor,
)
from services.economics_engine import EconomicsPreviewResult, EconomicsQuantities, EconomicsResult
from services.project_io import projects_root, read_project_manifest
from services.scenario_session import (
    PreparedEconomicsRuntimePriceBridge,
    build_runtime_price_bridge_record,
    compute_economics_runtime_signature,
    prepare_economics_runtime_price_bridge,
    resolve_runtime_price_bridge_state,
)
from services.ui_schema import build_table_display_columns
from services.validation import localize_validation_message, validate_economics_tables
from services.workspace_admin_callbacks import (
    apply_economics_runtime_price_bridge,
    apply_admin_edits,
    apply_financial_preset,
    delete_financial_preset_action,
    duplicate_financial_preset_action,
    render_financial_preset_controls,
    rename_financial_preset_action,
    request_financial_preset_delete,
    render_economics_preview,
    render_runtime_price_bridge_ui,
    save_current_financial_preset,
    sync_admin_draft,
    sync_financial_preset_name_input,
    sync_economics_bridge_cta,
)

COST_COLUMNS = ["stage", "name", "basis", "amount_COP", "source_mode", "hardware_binding", "enabled", "notes"]
PRICE_COLUMNS = ["layer", "name", "method", "value", "enabled", "notes"]


def _fast_bundle():
    bundle = load_example_config()
    return replace(
        bundle,
        config={
            **bundle.config,
            "years": 5,
            "modules_span_each_side": 4,
            "kWp_min": 12.0,
            "kWp_max": 18.0,
        },
    )


def _admin_client_state(lang: str = "es"):
    return replace(bootstrap_client_session(lang), ui_mode="admin")


def _patch_user_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PVW_PRIVATE_CONFIG_ROOT", str(tmp_path / "private"))
    monkeypatch.setattr("services.runtime_paths.user_root", lambda: tmp_path)


def _find_component(node, component_id: str):
    if node is None:
        return None
    if isinstance(node, (list, tuple)):
        for child in node:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    if getattr(node, "id", None) == component_id:
        return node
    children = getattr(node, "children", None)
    return _find_component(children, component_id)


def _bridge_args(
    active,
    *,
    economics_cost_rows=None,
    economics_price_rows=None,
    economics_price_rows_are_editor: bool = False,
    assumption_input_ids=None,
    assumption_values=None,
    lang: str = "es",
):
    if economics_price_rows is None:
        tax_rows = economics_price_items_rows_to_section_editor(
            active.config_bundle.economics_price_items_table,
            layers=("tax",),
            lang=lang,
        )
        adjustment_rows = economics_price_items_rows_to_section_editor(
            active.config_bundle.economics_price_items_table,
            layers=("commercial", "sale"),
            lang=lang,
        )
    else:
        tax_rows, adjustment_rows = _split_price_rows(
            economics_price_rows,
            lang=lang,
            rows_are_editor=economics_price_rows_are_editor,
        )
    return (
        [] if assumption_input_ids is None else assumption_input_ids,
        [] if assumption_values is None else assumption_values,
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang=lang)
        if economics_cost_rows is None
        else economics_cost_rows,
        tax_rows,
        adjustment_rows,
        lang,
    )


def _split_price_rows(
    rows_or_frame,
    *,
    lang: str = "es",
    rows_are_editor: bool = False,
) -> tuple[list[dict[str, object]] | None, list[dict[str, object]] | None]:
    if rows_or_frame is None:
        return None, None
    source = economics_price_items_rows_from_editor(rows_or_frame) if rows_are_editor else rows_or_frame
    tax_rows = economics_price_items_rows_to_section_editor(source, layers=("tax",), lang=lang)
    adjustment_rows = economics_price_items_rows_to_section_editor(source, layers=("commercial", "sale"), lang=lang)
    return tax_rows, adjustment_rows


def _render_preview_call(
    session_payload,
    *,
    economics_cost_rows=None,
    economics_price_rows=None,
    economics_price_rows_are_editor: bool = False,
    lang: str = "es",
    admin_preview_candidate_state=None,
):
    economics_tax_rows, economics_adjustment_rows = _split_price_rows(
        economics_price_rows,
        lang=lang,
        rows_are_editor=economics_price_rows_are_editor,
    )
    return render_economics_preview(
        session_payload,
        economics_cost_rows,
        economics_tax_rows,
        economics_adjustment_rows,
        lang,
        admin_preview_candidate_state,
    )


def _sync_admin_draft_call(
    session_payload,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_price_rows,
    *,
    economics_price_rows_are_editor: bool = False,
    lang: str = "es",
):
    economics_tax_rows, economics_adjustment_rows = _split_price_rows(
        economics_price_rows,
        lang=lang,
        rows_are_editor=economics_price_rows_are_editor,
    )
    return sync_admin_draft(
        session_payload,
        assumption_input_ids,
        assumption_values,
        inverter_rows,
        battery_rows,
        panel_rows,
        month_profile_rows,
        sun_profile_rows,
        economics_cost_rows,
        economics_tax_rows,
        economics_adjustment_rows,
    )


def _resolve_state_from_payload(session_payload, *, lang: str = "es"):
    _client_state, state = resolve_client_session(session_payload, language=lang)
    return state


def _render_preset_controls_call(
    session_payload,
    *,
    preset_selection_state=None,
    preset_meta=None,
    economics_cost_rows=None,
    economics_price_rows=None,
    economics_price_rows_are_editor: bool = False,
    lang: str = "es",
):
    economics_tax_rows, economics_adjustment_rows = _split_price_rows(
        economics_price_rows,
        lang=lang,
        rows_are_editor=economics_price_rows_are_editor,
    )
    return render_financial_preset_controls(
        session_payload,
        lang,
        preset_selection_state or {"preset_id": None},
        preset_meta or {"revision": 0, "message_key": None, "tone": "neutral"},
        economics_cost_rows,
        economics_tax_rows,
        economics_adjustment_rows,
    )


def _apply_admin_edits_call(
    n_clicks,
    session_payload,
    project_name_value,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_price_rows,
    language_value,
    *,
    economics_price_rows_are_editor: bool = False,
):
    economics_tax_rows, economics_adjustment_rows = _split_price_rows(
        economics_price_rows,
        lang=language_value,
        rows_are_editor=economics_price_rows_are_editor,
    )
    return apply_admin_edits(
        n_clicks,
        session_payload,
        project_name_value,
        assumption_input_ids,
        assumption_values,
        inverter_rows,
        battery_rows,
        panel_rows,
        month_profile_rows,
        sun_profile_rows,
        economics_cost_rows,
        economics_tax_rows,
        economics_adjustment_rows,
        language_value,
    )


def _sync_economics_bridge_cta_call(
    session_payload,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_price_rows,
    language_value,
    admin_preview_candidate_state=None,
    *,
    economics_price_rows_are_editor: bool = False,
):
    economics_tax_rows, economics_adjustment_rows = _split_price_rows(
        economics_price_rows,
        lang=language_value,
        rows_are_editor=economics_price_rows_are_editor,
    )
    return sync_economics_bridge_cta(
        session_payload,
        assumption_input_ids,
        assumption_values,
        inverter_rows,
        battery_rows,
        panel_rows,
        month_profile_rows,
        sun_profile_rows,
        economics_cost_rows,
        economics_tax_rows,
        economics_adjustment_rows,
        language_value,
        admin_preview_candidate_state,
    )


def _apply_economics_runtime_price_bridge_call(
    n_clicks,
    session_payload,
    project_name_value,
    assumption_input_ids,
    assumption_values,
    inverter_rows,
    battery_rows,
    panel_rows,
    month_profile_rows,
    sun_profile_rows,
    economics_cost_rows,
    economics_price_rows,
    language_value,
    admin_preview_candidate_state=None,
    *,
    economics_price_rows_are_editor: bool = False,
):
    economics_tax_rows, economics_adjustment_rows = _split_price_rows(
        economics_price_rows,
        lang=language_value,
        rows_are_editor=economics_price_rows_are_editor,
    )
    return apply_economics_runtime_price_bridge(
        n_clicks,
        session_payload,
        project_name_value,
        assumption_input_ids,
        assumption_values,
        inverter_rows,
        battery_rows,
        panel_rows,
        month_profile_rows,
        sun_profile_rows,
        economics_cost_rows,
        economics_tax_rows,
        economics_adjustment_rows,
        language_value,
        admin_preview_candidate_state,
    )


@pytest.fixture(autouse=True)
def _clear_runtime_state():
    clear_all_admin_session_access()
    clear_session_states()
    clear_workspace_drafts()
    yield
    clear_all_admin_session_access()
    clear_session_states()
    clear_workspace_drafts()


def _admin_payload(monkeypatch, tmp_path: Path):
    _patch_user_root(monkeypatch, tmp_path)
    client_state = _admin_client_state("es")
    set_admin_pin("2468")
    grant_admin_session_access(client_state.session_id)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None
    return client_state, state, active, payload


def _scanned_admin_payload(monkeypatch, tmp_path: Path):
    client_state, state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    state = run_scenario_scan(state, active.scenario_id)
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None
    assert active.scan_result is not None
    return client_state, state, active, payload


def _replace_selected_battery_detail(state, active, battery: dict[str, object]):
    assert active.scan_result is not None
    candidate_key = active.selected_candidate_key or active.scan_result.best_candidate_key
    assert candidate_key is not None
    updated_detail = {
        **active.scan_result.candidate_details[candidate_key],
        "battery_name": str(battery.get("name") or ""),
        "battery": dict(battery),
    }
    updated_scan = replace(
        active.scan_result,
        candidate_details={**active.scan_result.candidate_details, candidate_key: updated_detail},
    )
    updated_active = replace(active, scan_result=updated_scan, selected_candidate_key=candidate_key)
    updated_state = replace(
        state,
        scenarios=tuple(updated_active if scenario.scenario_id == active.scenario_id else scenario for scenario in state.scenarios),
    )
    return updated_state, updated_active


def _prepared_bridge_result(
    active,
    *,
    candidate_key: str,
    final_price_COP: float,
    normalized_cost_rows: list[dict[str, object]],
    normalized_price_rows: list[dict[str, object]],
    applied_at: str = "2026-03-29T12:00:00",
) -> PreparedEconomicsRuntimePriceBridge:
    next_config = dict(active.config_bundle.config)
    next_config.update(
        {
            "pricing_mode": "total",
            "price_total_COP": float(final_price_COP),
            "include_hw_in_price": False,
            "price_others_total": 0.0,
        }
    )
    bundle = replace(
        active.config_bundle,
        config=next_config,
        config_table=update_config_table_values(active.config_bundle.config_table, next_config),
        economics_cost_items_table=pd.DataFrame(normalized_cost_rows, columns=active.config_bundle.economics_cost_items_table.columns),
        economics_price_items_table=pd.DataFrame(
            normalized_price_rows,
            columns=active.config_bundle.economics_price_items_table.columns,
        ),
    )
    economics_signature = compute_economics_runtime_signature(
        bundle.economics_cost_items_table,
        bundle.economics_price_items_table,
    )
    bridge_record = build_runtime_price_bridge_record(
        candidate_key=candidate_key,
        final_price_COP=final_price_COP,
        resolved_preview_state="ready",
        applied_scan_fingerprint=active.scan_fingerprint,
        applied_economics_signature=economics_signature,
        applied_at=applied_at,
    )
    return PreparedEconomicsRuntimePriceBridge(
        applied=True,
        candidate_key=candidate_key,
        preview_state="ready",
        final_price_COP=final_price_COP,
        economics_signature=economics_signature,
        bundle=bundle,
        bridge_record=bridge_record,
    )


def test_example_bundle_uses_simple_seeded_economics_and_panel_price_is_not_authoritative() -> None:
    bundle = load_example_config()

    assert list(bundle.economics_cost_items_table.columns) == COST_COLUMNS
    assert list(bundle.economics_price_items_table.columns) == PRICE_COLUMNS
    assert bundle.economics_cost_items_table.empty is False
    assert bundle.economics_price_items_table.empty is False
    assert "price_COP" in bundle.panel_catalog.columns
    assert float(bundle.panel_catalog.loc[0, "price_COP"]) >= 0.0

    panel_cost_row = next(
        row for row in bundle.economics_cost_items_table.to_dict("records") if str(row.get("name")) == "Panel hardware"
    )
    assert panel_cost_row["stage"] == "technical"
    assert panel_cost_row["basis"] == "per_panel"
    assert panel_cost_row["source_mode"] == "selected_hardware"
    assert panel_cost_row["hardware_binding"] == "panel"
    assert float(panel_cost_row["amount_COP"]) == pytest.approx(0.0)


def test_economics_editor_round_trips_friendly_enum_labels_to_raw_values() -> None:
    bundle = load_example_config()

    cost_editor_rows = economics_cost_items_rows_to_editor(bundle.economics_cost_items_table, lang="es")
    price_editor_rows = economics_price_items_rows_to_editor(bundle.economics_price_items_table, lang="es")

    assert cost_editor_rows[0]["stage"] == "Costo técnico"
    assert cost_editor_rows[0]["basis"] == "Por panel"
    assert cost_editor_rows[0]["source_mode"] == "Hardware seleccionado"
    assert cost_editor_rows[0]["hardware_binding"] == "Panel"
    assert cost_editor_rows[0]["enabled"] == "Sí"
    assert price_editor_rows[0]["layer"] == "Impuestos"
    assert price_editor_rows[0]["method"] == "Impuesto porcentual"
    assert price_editor_rows[0]["enabled"] == "No"
    assert price_editor_rows[1]["layer"] == "Oferta comercial"
    assert price_editor_rows[1]["method"] == "Ajuste porcentual"
    assert price_editor_rows[1]["enabled"] == "Sí"

    round_trip_cost = economics_cost_items_rows_from_editor(cost_editor_rows)
    round_trip_price = economics_price_items_rows_from_editor(price_editor_rows)

    assert round_trip_cost[0]["stage"] == "technical"
    assert round_trip_cost[0]["basis"] == "per_panel"
    assert round_trip_cost[0]["source_mode"] == "selected_hardware"
    assert round_trip_cost[0]["hardware_binding"] == "panel"
    assert bool(round_trip_cost[0]["enabled"]) is True
    assert round_trip_price[0]["layer"] == "tax"
    assert round_trip_price[0]["method"] == "tax_pct"
    assert bool(round_trip_price[0]["enabled"]) is False
    assert round_trip_price[1]["layer"] == "commercial"
    assert round_trip_price[1]["method"] == "markup_pct"
    assert bool(round_trip_price[1]["enabled"]) is True


@pytest.mark.parametrize(
    ("editor_value", "expected_internal"),
    [
        ("Sí", True),
        ("No", False),
    ],
)
def test_economics_enabled_localized_boolean_round_trip(editor_value: str, expected_internal: bool) -> None:
    cost_rows = [
        {
            "stage": "Costo técnico",
            "name": "Panel hardware",
            "basis": "Por panel",
            "amount_COP": 0.0,
            "source_mode": "Hardware seleccionado",
            "hardware_binding": "Panel",
            "enabled": editor_value,
            "notes": "",
        }
    ]
    price_rows = [
        {
            "layer": "Oferta comercial",
            "name": "Margen comercial",
            "method": "Ajuste porcentual",
            "value": 12,
            "enabled": editor_value,
            "notes": "",
        }
    ]

    normalized_cost = economics_cost_items_rows_from_editor(cost_rows)
    normalized_price = economics_price_items_rows_from_editor(price_rows)
    round_trip_cost = economics_cost_items_rows_to_editor(normalized_cost, lang="es")
    round_trip_price = economics_price_items_rows_to_editor(normalized_price, lang="es")

    assert bool(normalized_cost[0]["enabled"]) is expected_internal
    assert bool(normalized_price[0]["enabled"]) is expected_internal
    assert round_trip_cost[0]["enabled"] == editor_value
    assert round_trip_price[0]["enabled"] == editor_value


@pytest.mark.parametrize(
    ("layer_label", "name", "method_label", "expected_method", "editor_value", "expected_internal"),
    [
        ("Oferta comercial", "Margen comercial", "Ajuste porcentual", "markup_pct", 1, 0.01),
        ("Oferta comercial", "Margen comercial", "Ajuste porcentual", "markup_pct", 1.0, 0.01),
        ("Oferta comercial", "Margen comercial", "Ajuste porcentual", "markup_pct", 1.1, 0.011),
        ("Oferta comercial", "Margen comercial", "Ajuste porcentual", "markup_pct", 20, 0.20),
        ("Impuestos", "IVA", "Impuesto porcentual", "tax_pct", 1, 0.01),
        ("Impuestos", "IVA", "Impuesto porcentual", "tax_pct", 19, 0.19),
    ],
)
def test_economics_price_percent_editor_values_normalize_to_internal_fractions(
    layer_label: str,
    name: str,
    method_label: str,
    expected_method: str,
    editor_value: float,
    expected_internal: float,
) -> None:
    rows = [
        {
            "layer": layer_label,
            "name": name,
            "method": method_label,
            "value": editor_value,
            "enabled": True,
            "notes": "",
        }
    ]

    normalized = economics_price_items_rows_from_editor(rows)

    assert normalized[0]["method"] == expected_method
    assert float(normalized[0]["value"]) == pytest.approx(expected_internal)


@pytest.mark.parametrize(
    ("layer_label", "name", "method_label", "editor_value"),
    [
        ("Oferta comercial", "Margen comercial", "Ajuste porcentual", 1),
        ("Oferta comercial", "Margen comercial", "Ajuste porcentual", 20),
        ("Impuestos", "IVA", "Impuesto porcentual", 1),
        ("Impuestos", "IVA", "Impuesto porcentual", 19),
    ],
)
def test_economics_price_percent_round_trip_preserves_editor_percent_semantics(
    layer_label: str,
    name: str,
    method_label: str,
    editor_value: float,
) -> None:
    rows = [
        {
            "layer": layer_label,
            "name": name,
            "method": method_label,
            "value": editor_value,
            "enabled": True,
            "notes": "",
        }
    ]

    normalized = economics_price_items_rows_from_editor(rows)
    round_trip_rows = economics_price_items_rows_to_editor(normalized, lang="es")

    assert round_trip_rows[0]["layer"] == layer_label
    assert round_trip_rows[0]["method"] == method_label
    assert float(round_trip_rows[0]["value"]) == pytest.approx(float(editor_value))


def test_financial_preset_catalog_exposes_stable_system_ids_and_localized_labels() -> None:
    catalog_es = build_financial_preset_catalog((), lang="es")
    catalog_en = build_financial_preset_catalog((), lang="en")

    assert [preset.preset_id for preset in catalog_es[:3]] == [
        "system:residential_conservative",
        "system:commercial_standard",
        "system:industrial_aggressive",
    ]
    assert catalog_es[0].display_name == "Residencial conservador"
    assert catalog_en[0].display_name == "Residential conservative"


def test_financial_preset_controls_disable_destructive_actions_for_system_presets(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    clear_all_admin_session_access()
    clear_session_states()

    client_state = _admin_client_state("es")
    grant_admin_session_access(client_state.session_id)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    session_payload = commit_client_session(client_state, state).to_payload()

    rendered = _render_preset_controls_call(
        session_payload,
        preset_selection_state={"preset_id": "system:commercial_standard"},
        lang="es",
    )

    options, value, _dropdown_disabled, origin, _origin_class, _match, _match_class, _summary, _helper, _apply_disabled, _save_disabled, duplicate_disabled, rename_disabled, delete_disabled = rendered
    assert any(option["value"] == "system:commercial_standard" for option in options)
    assert value == "system:commercial_standard"
    assert origin == "Sistema"
    assert duplicate_disabled is False
    assert rename_disabled is True
    assert delete_disabled is True


def test_apply_financial_preset_loads_editor_rows_without_mutating_stored_preset(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    clear_all_admin_session_access()
    clear_session_states()

    bundle = _fast_bundle()
    custom_preset = create_financial_preset_record(
        "Comercial propio",
        economics_cost_items_rows=bundle.economics_cost_items_table.to_dict("records"),
        economics_price_items_rows=bundle.economics_price_items_table.to_dict("records"),
    )
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", bundle))
    state = add_financial_preset(state, custom_preset)
    client_state = _admin_client_state("es")
    grant_admin_session_access(client_state.session_id)
    session_payload = commit_client_session(client_state, state).to_payload()

    cost_rows, tax_rows, adjustment_rows, _meta, _status = apply_financial_preset(
        1,
        session_payload,
        {"preset_id": custom_preset.preset_id},
        "es",
    )
    resolved = resolve_financial_preset(custom_preset.preset_id, state.financial_presets, lang="es")

    assert resolved is not None
    assert cost_rows == economics_cost_items_rows_to_editor(resolved.economics_cost_items_rows, lang="es")
    assert tax_rows == economics_price_items_rows_to_section_editor(resolved.economics_price_items_rows, layers=("tax",), lang="es")
    assert adjustment_rows == economics_price_items_rows_to_section_editor(
        resolved.economics_price_items_rows,
        layers=("commercial", "sale"),
        lang="es",
    )
    assert state.financial_presets[0].economics_cost_items_rows == custom_preset.economics_cost_items_rows
    assert state.financial_presets[0].economics_price_items_rows == custom_preset.economics_price_items_rows


def test_financial_preset_divergence_is_visible_after_manual_editor_change(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    clear_all_admin_session_access()
    clear_session_states()

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    client_state = _admin_client_state("es")
    grant_admin_session_access(client_state.session_id)
    session_payload = commit_client_session(client_state, state).to_payload()
    selection = {"preset_id": "system:commercial_standard"}

    cost_rows, tax_rows, adjustment_rows, _meta, _status = apply_financial_preset(1, session_payload, selection, "es")
    exact = _render_preset_controls_call(
        session_payload,
        preset_selection_state=selection,
        economics_cost_rows=cost_rows,
        economics_price_rows=[*tax_rows, *adjustment_rows],
        economics_price_rows_are_editor=True,
        lang="es",
    )
    edited_cost_rows = [dict(row) for row in cost_rows]
    edited_cost_rows[3]["amount_COP"] = float(edited_cost_rows[3]["amount_COP"]) + 1000.0
    modified = _render_preset_controls_call(
        session_payload,
        preset_selection_state=selection,
        economics_cost_rows=edited_cost_rows,
        economics_price_rows=[*tax_rows, *adjustment_rows],
        economics_price_rows_are_editor=True,
        lang="es",
    )

    assert exact[5] == tr("workspace.admin.economics.presets.match.exact", "es")
    assert modified[5] == tr("workspace.admin.economics.presets.match.modified", "es")


def test_save_financial_preset_rejects_collision_with_visible_system_label(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    clear_all_admin_session_access()
    clear_session_states()

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    client_state = _admin_client_state("es")
    grant_admin_session_access(client_state.session_id)
    session_payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    result_payload, _selection, preset_meta, status = save_current_financial_preset(
        1,
        session_payload,
        None,
        "Comercial estándar",
        economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es"),
        economics_price_items_rows_to_section_editor(active.config_bundle.economics_price_items_table, layers=("tax",), lang="es"),
        economics_price_items_rows_to_section_editor(active.config_bundle.economics_price_items_table, layers=("commercial", "sale"), lang="es"),
        "es",
    )

    assert status == tr("workspace.admin.economics.presets.error.name_conflict", "es")
    assert preset_meta["tone"] == "error"
    assert _resolve_state_from_payload(result_payload, lang="es").financial_presets == ()


def test_save_duplicate_rename_and_delete_financial_preset_persist_when_project_is_bound(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    clear_all_admin_session_access()
    clear_session_states()

    base_state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    base_state = save_project(base_state, project_name="Proyecto Presets", language="es")
    client_state = _admin_client_state("es")
    grant_admin_session_access(client_state.session_id)
    session_payload = commit_client_session(client_state, base_state).to_payload()
    active = base_state.get_scenario()
    assert active is not None

    saved_payload, selection, _meta, _status = save_current_financial_preset(
        1,
        session_payload,
        "Proyecto Presets",
        "Mi preset comercial",
        economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es"),
        economics_price_items_rows_to_section_editor(active.config_bundle.economics_price_items_table, layers=("tax",), lang="es"),
        economics_price_items_rows_to_section_editor(active.config_bundle.economics_price_items_table, layers=("commercial", "sale"), lang="es"),
        "es",
    )
    saved_state = _resolve_state_from_payload(saved_payload, lang="es")
    assert len(saved_state.financial_presets) == 1
    assert read_project_manifest(saved_state.project_slug).format_version == 2
    assert len(read_project_manifest(saved_state.project_slug).financial_presets) == 1

    duplicated_payload, duplicated_selection, _meta, _status = duplicate_financial_preset_action(
        1,
        saved_payload,
        "Proyecto Presets",
        selection,
        "",
        "es",
    )
    duplicated_state = _resolve_state_from_payload(duplicated_payload, lang="es")
    assert len(duplicated_state.financial_presets) == 2
    duplicated_preset_id = duplicated_selection["preset_id"]
    assert duplicated_preset_id != selection["preset_id"]

    renamed_payload, renamed_selection, _meta, _status = rename_financial_preset_action(
        1,
        duplicated_payload,
        "Proyecto Presets",
        duplicated_selection,
        "Mi preset duplicado",
        "es",
    )
    renamed_state = _resolve_state_from_payload(renamed_payload, lang="es")
    renamed_preset = next(preset for preset in renamed_state.financial_presets if preset.preset_id == renamed_selection["preset_id"])
    assert renamed_preset.name == "Mi preset duplicado"

    assert request_financial_preset_delete(1, renamed_payload, renamed_selection, "es") is True
    deleted_payload, deleted_selection, _meta, _status = delete_financial_preset_action(
        1,
        renamed_payload,
        "Proyecto Presets",
        renamed_selection,
        "es",
    )
    deleted_state = _resolve_state_from_payload(deleted_payload, lang="es")

    assert deleted_selection == {"preset_id": None}
    assert len(deleted_state.financial_presets) == 1
    reopened = open_project(deleted_state.project_slug)
    assert len(reopened.financial_presets) == 1
    assert reopened.financial_presets[0].name == "Mi preset comercial"

def test_economics_columns_mark_enum_fields_as_dropdowns() -> None:
    cost_columns, _ = build_table_display_columns(
        "economics_cost_items",
        ["stage", "basis", "source_mode", "hardware_binding", "enabled", "amount_COP"],
        "es",
    )
    price_columns, _ = build_table_display_columns("economics_price_items", ["layer", "method", "enabled", "value"], "es")

    assert {column["id"]: column.get("presentation") for column in cost_columns} == {
        "stage": "dropdown",
        "basis": "dropdown",
        "source_mode": "dropdown",
        "hardware_binding": "dropdown",
        "enabled": "dropdown",
        "amount_COP": None,
    }
    assert {column["id"]: column.get("presentation") for column in price_columns} == {
        "layer": "dropdown",
        "method": "dropdown",
        "enabled": "dropdown",
        "value": None,
    }


def test_economics_editor_section_uses_cleaner_copy_and_dropdown_labels() -> None:
    section = economics_editor_section(lang="es")

    note = _find_component(section, "economics-editor-note")
    preview_copy = _find_component(section, "economics-preview-copy")
    candidate_shell = _find_component(section, "admin-preview-candidate-shell")
    editors_shell = _find_component(section, "economics-editors-shell")
    editors_panels = _find_component(section, "economics-editors-panels")
    cost_details = _find_component(section, "economics-cost-items-details")
    tax_details = _find_component(section, "economics-tax-items-details")
    adjustment_details = _find_component(section, "economics-adjustment-items-details")
    compatibility_shell = _find_component(section, "economics-compatibility-shell")
    cost_table = _find_component(section, "economics-cost-items-editor")
    tax_table = _find_component(section, "economics-tax-items-editor")
    adjustment_table = _find_component(section, "economics-adjustment-items-editor")

    assert note is not None
    assert "flujo principal de pricing" in str(note.children).lower()
    assert "compatibilidad" in str(note.children).lower()
    assert preview_copy is not None
    assert "diseño activo del escenario" in str(preview_copy.children).lower()
    assert candidate_shell is not None
    assert editors_shell is not None
    assert editors_panels is not None
    assert cost_details is not None
    assert tax_details is not None
    assert adjustment_details is not None
    assert compatibility_shell is not None
    assert getattr(compatibility_shell, "open", None) is False
    assert cost_table is not None
    assert tax_table is not None
    assert adjustment_table is not None
    assert "Costo técnico" in {option["label"] for option in cost_table.dropdown["stage"]["options"]}
    assert "Hardware seleccionado" in {option["label"] for option in cost_table.dropdown["source_mode"]["options"]}
    assert "Panel" in {option["label"] for option in cost_table.dropdown["hardware_binding"]["options"]}
    assert {"Sí", "No"} == {option["label"] for option in cost_table.dropdown["enabled"]["options"]}
    assert "Impuesto porcentual" in {option["label"] for option in tax_table.dropdown["method"]["options"]}
    assert "Ajuste porcentual" in {option["label"] for option in adjustment_table.dropdown["method"]["options"]}
    assert {"Sí", "No"} == {option["label"] for option in tax_table.dropdown["enabled"]["options"]}
    assert {"Sí", "No"} == {option["label"] for option in adjustment_table.dropdown["enabled"]["options"]}


def test_admin_secure_content_places_economics_before_collapsed_assumptions() -> None:
    content = admin_secure_content(lang="es")
    assumptions_details = _find_component(content, "admin-assumptions-details")
    assumptions_sections = _find_component(content, "admin-assumption-sections")
    economics_index = next(
        index for index, child in enumerate(content.children) if _find_component(child, "economics-editor-title") is not None
    )
    assumptions_index = next(
        index for index, child in enumerate(content.children) if getattr(child, "id", None) == "admin-assumptions-details"
    )

    assert assumptions_index > economics_index
    assert assumptions_details is not None
    assert getattr(assumptions_details, "open", None) is False
    assert assumptions_sections is not None


def test_sync_admin_draft_tracks_economics_tables_with_simple_schema(monkeypatch, tmp_path) -> None:
    client_state, _state, active, payload = _admin_payload(monkeypatch, tmp_path)

    economics_cost_rows = active.config_bundle.economics_cost_items_table.to_dict("records")
    economics_price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    economics_cost_rows[0] = {**economics_cost_rows[0], "amount_COP": 777_000}
    economics_price_rows[1] = {**economics_price_rows[1], "value": 12}

    meta = _sync_admin_draft_call(
        payload,
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        economics_cost_rows,
        economics_price_rows,
        economics_price_rows_are_editor=True,
    )

    draft = get_workspace_draft(client_state.session_id, active.scenario_id)
    assert meta["revision"] > 0
    assert draft is not None
    assert draft.table_rows["economics_cost_items"][0]["amount_COP"] == pytest.approx(777_000)
    assert draft.table_rows["economics_price_items"][1]["method"] == "markup_pct"
    assert draft.table_rows["economics_price_items"][1]["value"] == pytest.approx(0.12)


def test_apply_admin_edits_persists_economics_tables_and_normalizes_markup_percent(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Economics Admin", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    economics_cost_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    economics_price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    economics_cost_rows[0] = {**economics_cost_rows[0], "amount_COP": 777_000}
    economics_price_rows[1] = {**economics_price_rows[1], "value": 19}

    next_payload, _status = _apply_admin_edits_call(
        1,
        payload,
        "Proyecto Economics Admin",
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        economics_cost_rows,
        economics_price_rows,
        "es",
        economics_price_rows_are_editor=True,
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    assert float(updated_active.config_bundle.economics_cost_items_table.iloc[0]["amount_COP"]) == pytest.approx(777_000)
    assert float(updated_active.config_bundle.economics_price_items_table.iloc[1]["value"]) == pytest.approx(0.19)
    assert list(updated_active.config_bundle.economics_cost_items_table.columns) == COST_COLUMNS
    assert list(updated_active.config_bundle.economics_price_items_table.columns) == PRICE_COLUMNS

    reopened = open_project(updated_state.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert float(reopened_active.config_bundle.economics_cost_items_table.iloc[0]["amount_COP"]) == pytest.approx(777_000)
    assert float(reopened_active.config_bundle.economics_price_items_table.iloc[1]["value"]) == pytest.approx(0.19)
    reopened_editor_cost_rows = economics_cost_items_rows_to_editor(reopened_active.config_bundle.economics_cost_items_table, lang="es")
    reopened_editor_price_rows = economics_price_items_rows_to_editor(reopened_active.config_bundle.economics_price_items_table, lang="es")
    assert reopened_editor_cost_rows[0]["stage"] == "Costo técnico"
    assert reopened_editor_cost_rows[0]["basis"] == "Por panel"
    assert reopened_editor_cost_rows[0]["source_mode"] == "Hardware seleccionado"
    assert reopened_editor_cost_rows[0]["hardware_binding"] == "Panel"
    assert reopened_editor_price_rows[0]["layer"] == "Impuestos"
    assert reopened_editor_price_rows[0]["method"] == "Impuesto porcentual"
    assert reopened_editor_price_rows[1]["layer"] == "Oferta comercial"
    assert reopened_editor_price_rows[1]["method"] == "Ajuste porcentual"


def test_open_project_without_economics_csv_defaults_new_tables(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    saved = save_project(state, project_name="Proyecto Legacy Economics", language="es")
    root = projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id
    (root / "Economics_Cost_Items.csv").unlink()
    (root / "Economics_Price_Items.csv").unlink()

    reopened = open_project(saved.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert list(reopened_active.config_bundle.economics_cost_items_table.columns) == COST_COLUMNS
    assert list(reopened_active.config_bundle.economics_price_items_table.columns) == PRICE_COLUMNS
    assert "Panel hardware" in reopened_active.config_bundle.economics_cost_items_table["name"].astype(str).tolist()
    assert "Margen comercial" in reopened_active.config_bundle.economics_price_items_table["name"].astype(str).tolist()


def test_open_rich_economics_schema_migrates_in_memory_only_and_rewrites_on_save(monkeypatch, tmp_path) -> None:
    _patch_user_root(monkeypatch, tmp_path)
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    saved = save_project(state, project_name="Proyecto Economics Rich", language="es")
    root = projects_root() / saved.project_slug / "inputs" / saved.active_scenario_id
    cost_path = root / "Economics_Cost_Items.csv"
    price_path = root / "Economics_Price_Items.csv"

    pd.DataFrame(
        [
            {"stage": "technical_cost", "name": "Panel hardware", "calculation_method": "per_panel", "value": 555_000, "enabled": True, "notes": ""},
            {"stage": "installed_cost", "name": "Legacy contingency", "calculation_method": "pct_of_running_subtotal", "value": 0.12, "enabled": True, "notes": "legacy"},
        ],
        columns=["stage", "name", "calculation_method", "value", "enabled", "notes"],
    ).to_csv(cost_path, index=False)
    pd.DataFrame(
        [
            {"stage": "commercial_offer", "name": "Commercial margin", "calculation_method": "markup_pct", "value": 0.19, "enabled": True, "notes": ""},
            {"stage": "final_sale_price", "name": "Taxes", "calculation_method": "tax_pct", "value": 0.16, "enabled": True, "notes": "legacy tax"},
        ],
        columns=["stage", "name", "calculation_method", "value", "enabled", "notes"],
    ).to_csv(price_path, index=False)

    original_cost_text = cost_path.read_text(encoding="utf-8")
    original_price_text = price_path.read_text(encoding="utf-8")

    reopened = open_project(saved.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    assert cost_path.read_text(encoding="utf-8") == original_cost_text
    assert price_path.read_text(encoding="utf-8") == original_price_text
    assert list(reopened_active.config_bundle.economics_cost_items_table.columns) == COST_COLUMNS
    assert list(reopened_active.config_bundle.economics_price_items_table.columns) == PRICE_COLUMNS
    assert reopened_active.config_bundle.economics_cost_items_table.iloc[0]["stage"] == "technical"
    assert reopened_active.config_bundle.economics_cost_items_table.iloc[0]["basis"] == "per_panel"
    assert reopened_active.config_bundle.economics_cost_items_table.iloc[0]["source_mode"] == "manual"
    assert reopened_active.config_bundle.economics_cost_items_table.iloc[0]["hardware_binding"] == "none"
    assert float(reopened_active.config_bundle.economics_cost_items_table.iloc[0]["amount_COP"]) == pytest.approx(555_000)
    assert bool(reopened_active.config_bundle.economics_cost_items_table.iloc[1]["enabled"]) is False
    assert "pct_of_running_subtotal" in str(reopened_active.config_bundle.economics_cost_items_table.iloc[1]["notes"])
    assert reopened_active.config_bundle.economics_price_items_table.iloc[0]["layer"] == "commercial"
    assert reopened_active.config_bundle.economics_price_items_table.iloc[0]["method"] == "markup_pct"
    assert float(reopened_active.config_bundle.economics_price_items_table.iloc[0]["value"]) == pytest.approx(0.19)
    assert reopened_active.config_bundle.economics_price_items_table.iloc[1]["layer"] == "tax"
    assert reopened_active.config_bundle.economics_price_items_table.iloc[1]["method"] == "tax_pct"
    assert float(reopened_active.config_bundle.economics_price_items_table.iloc[1]["value"]) == pytest.approx(0.16)
    assert bool(reopened_active.config_bundle.economics_price_items_table.iloc[1]["enabled"]) is True
    assert str(reopened_active.config_bundle.economics_price_items_table.iloc[1]["notes"]) == "legacy tax"
    cost_messages = [issue.message for issue in reopened_active.config_bundle.issues if issue.field == "economics_cost_items"]
    price_messages = [issue.message for issue in reopened_active.config_bundle.issues if issue.field == "economics_price_items"]
    assert "Economics_Cost_Items fila 2: migrada desde schema rico y desactivada por método no soportado 'pct_of_running_subtotal'." in cost_messages
    assert "Economics_Cost_Items: 1 filas migradas desde schema rico siguen deshabilitadas." in cost_messages
    assert cost_messages.count(
        "Economics_Cost_Items fila 2: migrada desde schema rico y desactivada por método no soportado 'pct_of_running_subtotal'."
    ) == 1
    assert price_messages == []

    save_project(reopened, language="es")
    rewritten_cost = pd.read_csv(cost_path)
    rewritten_price = pd.read_csv(price_path)

    assert list(rewritten_cost.columns) == COST_COLUMNS
    assert list(rewritten_price.columns) == PRICE_COLUMNS
    assert "calculation_method" not in rewritten_cost.columns
    assert "calculation_method" not in rewritten_price.columns
    reopened_after_save = open_project(saved.project_slug)
    reopened_after_save_active = reopened_after_save.get_scenario()

    assert reopened_after_save_active is not None
    post_save_cost_messages = [issue.message for issue in reopened_after_save_active.config_bundle.issues if issue.field == "economics_cost_items"]
    post_save_price_messages = [issue.message for issue in reopened_after_save_active.config_bundle.issues if issue.field == "economics_price_items"]
    assert "Economics_Cost_Items: 1 filas migradas desde schema rico siguen deshabilitadas." in post_save_cost_messages
    assert not any("fila 2: migrada desde schema rico" in message for message in post_save_cost_messages)
    assert not any("fila 2: migrada desde schema rico" in message for message in post_save_price_messages)
    assert post_save_price_messages == []


def test_normalize_invalid_economics_rows_preserves_disabled_row_and_source_row_number() -> None:
    frame, issues = normalize_economics_cost_items_with_issues(
        [
            {"stage": "", "name": "", "basis": "", "amount_COP": "", "enabled": "", "notes": ""},
            {"stage": "technical", "name": "   ", "basis": "per_kwp", "amount_COP": "oops", "enabled": True, "notes": "manual import"},
            {"stage": "installed", "name": "Mano de obra", "basis": "per_kwp", "amount_COP": 12000, "enabled": True, "notes": ""},
        ]
    )

    assert len(frame) == 2
    invalid_row = frame.iloc[0]
    assert invalid_row["name"] == ""
    assert bool(invalid_row["enabled"]) is False
    assert float(invalid_row["amount_COP"]) == pytest.approx(0.0)
    assert "manual import" in str(invalid_row["notes"])
    assert "Recovered invalid row (name=empty)." in str(invalid_row["notes"])
    assert "Recovered invalid row (amount_COP='oops')." in str(invalid_row["notes"])
    assert issues == [
        "Economics_Cost_Items fila 2: se desactivó por nombre vacío.",
        "Economics_Cost_Items fila 2: se desactivó por valor inválido en 'amount_COP'.",
    ]


def test_validate_economics_tables_only_emits_aggregated_operational_warnings() -> None:
    bundle = _fast_bundle()
    cost_frame = pd.DataFrame(
        [
            {
                "stage": "technical",
                "name": "Panel hardware",
                "basis": "per_panel",
                "amount_COP": 0.0,
                "source_mode": "selected_hardware",
                "hardware_binding": "panel",
                "enabled": True,
                "notes": "",
            },
            {
                "stage": "technical",
                "name": "  panel hardware  ",
                "basis": "per_panel",
                "amount_COP": 0.0,
                "source_mode": "manual",
                "hardware_binding": "none",
                "enabled": True,
                "notes": "",
            },
            {
                "stage": "installed",
                "name": "",
                "basis": "fixed_project",
                "amount_COP": 0.0,
                "source_mode": "manual",
                "hardware_binding": "none",
                "enabled": False,
                "notes": "Recovered invalid row (name='').",
            },
            {
                "stage": "installed",
                "name": "Legacy contingency",
                "basis": "fixed_project",
                "amount_COP": 0.0,
                "source_mode": "manual",
                "hardware_binding": "none",
                "enabled": False,
                "notes": f"{RICH_MIGRATION_NOTE_PREFIX} (stage=installed_cost, method=pct_of_running_subtotal, value=0.12).",
            },
        ],
        columns=COST_COLUMNS,
    )
    price_frame = pd.DataFrame(
        [
            {"layer": "sale", "name": "Ajuste final", "method": "fixed_project", "value": 0.0, "enabled": True, "notes": ""},
            {
                "layer": "sale",
                "name": "Taxes",
                "method": "fixed_project",
                "value": 0.0,
                "enabled": False,
                "notes": f"{RICH_MIGRATION_NOTE_PREFIX} (stage=final_sale_price, method=tax_pct, value=0.16).",
            },
        ],
        columns=["layer", "name", "method", "value", "enabled", "notes"],
    )

    issues = validate_economics_tables(
        replace(
            bundle,
            economics_cost_items_table=cost_frame,
            economics_price_items_table=price_frame,
        )
    )
    messages = [issue.message for issue in issues]

    assert "Economics_Cost_Items: nombres habilitados duplicados: Panel hardware." in messages
    assert "Economics_Cost_Items: no hay filas habilitadas en 'installed'." in messages
    assert "Economics_Cost_Items: 1 filas migradas desde schema rico siguen deshabilitadas." in messages
    assert "Economics_Price_Items: 1 filas migradas desde schema rico siguen deshabilitadas." in messages
    assert "Economics_Price_Items: no hay filas habilitadas en 'commercial'." not in messages
    assert not any("nombre vacío" in message for message in messages)
    assert not any("valor inválido" in message for message in messages)
    assert not any("enum inválido" in message for message in messages)


def test_refresh_bundle_issues_dedupes_economics_warnings() -> None:
    bundle = _fast_bundle()
    changed_costs = bundle.economics_cost_items_table.copy()
    changed_costs.loc[changed_costs["stage"] == "installed", "enabled"] = False
    seed_message = "Economics_Cost_Items: no hay filas habilitadas en 'installed'."

    refreshed = refresh_bundle_issues(
        replace(
            bundle,
            economics_cost_items_table=changed_costs,
            issues=(ValidationIssue("warning", "economics_cost_items", seed_message),),
        )
    )
    messages = [issue.message for issue in refreshed.issues if issue.field == "economics_cost_items"]

    assert messages.count(seed_message) == 1


def test_apply_admin_edits_preserves_invalid_economics_rows_and_warnings_after_reopen(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Economics Invalid Row", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    economics_cost_rows = active.config_bundle.economics_cost_items_table.to_dict("records")
    economics_price_rows = active.config_bundle.economics_price_items_table.to_dict("records")
    economics_cost_rows.append(
        {
            "stage": "technical",
            "name": "   ",
            "basis": "per_kwp",
            "amount_COP": "oops",
            "enabled": True,
            "notes": "draft invalid",
        }
    )

    next_payload, _status = _apply_admin_edits_call(
        1,
        payload,
        "Proyecto Economics Invalid Row",
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        economics_cost_rows,
        economics_price_rows,
        "es",
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    invalid_rows = updated_active.config_bundle.economics_cost_items_table.loc[
        updated_active.config_bundle.economics_cost_items_table["notes"].astype(str).str.contains("draft invalid", regex=False)
    ]
    assert len(invalid_rows) == 1
    assert invalid_rows.iloc[0]["name"] == ""
    assert bool(invalid_rows.iloc[0]["enabled"]) is False
    updated_messages = [issue.message for issue in updated_active.config_bundle.issues if issue.field == "economics_cost_items"]
    assert updated_messages.count("Economics_Cost_Items fila 9: se desactivó por nombre vacío.") == 1

    reopened = open_project(updated_state.project_slug)
    reopened_active = reopened.get_scenario()

    assert reopened_active is not None
    reopened_messages = [issue.message for issue in reopened_active.config_bundle.issues if issue.field == "economics_cost_items"]
    assert reopened_messages.count("Economics_Cost_Items fila 9: se desactivó por nombre vacío.") == 1


def test_economics_sync_button_is_removed_from_shell_and_callback_graph() -> None:
    section = economics_editor_section(lang="es")
    assert _find_component(section, "sync-economics-hardware-costs-btn") is None
    assert hasattr(admin_callbacks, "sync_economics_hardware_costs") is False


def test_localize_economics_validation_messages_are_stable_in_es_and_en() -> None:
    row_issue = ValidationIssue(
        "warning",
        "economics_cost_items",
        "Economics_Cost_Items fila 3: se desactivó por valor inválido en 'amount_COP'.",
    )
    aggregate_issue = ValidationIssue(
        "warning",
        "economics_price_items",
        "Economics_Price_Items: no hay filas habilitadas en 'commercial'.",
    )

    assert (
        localize_validation_message(row_issue, lang="en")
        == "Row 3 in economics cost items was disabled because Amount is invalid."
    )
    assert (
        localize_validation_message(row_issue, lang="es")
        == "Fila 3 en las partidas de costo de economics: se desactivó porque Monto es inválido."
    )
    assert (
        localize_validation_message(aggregate_issue, lang="en")
        == "economics price items has no enabled rows in 'commercial'."
    )
    assert (
        localize_validation_message(aggregate_issue, lang="es")
        == "No hay filas activas en 'commercial' dentro de las partidas de precio de economics."
    )


def test_economics_changes_do_not_affect_deterministic_fingerprint_or_scan() -> None:
    bundle = _fast_bundle()
    baseline_fingerprint = fingerprint_deterministic_input(bundle)
    baseline_scan = resolve_deterministic_scan(bundle, allow_parallel=False)

    changed_costs = bundle.economics_cost_items_table.copy()
    changed_prices = bundle.economics_price_items_table.copy()
    changed_costs.at[0, "amount_COP"] = 999_999.0
    changed_prices.at[0, "value"] = 0.22
    changed_bundle = replace(
        bundle,
        economics_cost_items_table=changed_costs,
        economics_price_items_table=changed_prices,
    )

    assert fingerprint_deterministic_input(changed_bundle) == baseline_fingerprint

    changed_scan = resolve_deterministic_scan(changed_bundle, allow_parallel=False)
    assert changed_scan.best_candidate_key == baseline_scan.best_candidate_key
    pdt.assert_frame_equal(changed_scan.candidates, baseline_scan.candidates)


def test_render_economics_preview_uses_normalized_editor_rows(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    cost_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    price_rows[1] = {**price_rows[1], "value": 12}
    captured: dict[str, object] = {}

    def _fake_preview(scenario, *, economics_cost_items, economics_price_items, **_kwargs):
        captured["scenario_id"] = scenario.scenario_id
        captured["cost_items"] = economics_cost_items
        captured["price_items"] = economics_price_items
        return admin_callbacks.EconomicsPreviewResult(
            state="no_scan",
            message_key="workspace.admin.economics.preview.state.no_scan",
        )

    monkeypatch.setattr(admin_callbacks, "resolve_economics_preview", _fake_preview)

    children = _render_preview_call(
        payload,
        economics_cost_rows=cost_rows,
        economics_price_rows=price_rows,
        economics_price_rows_are_editor=True,
        lang="es",
    )

    assert children
    assert captured["scenario_id"] == active.scenario_id
    assert captured["cost_items"] == economics_cost_items_rows_from_editor(cost_rows)
    normalized_price_rows = captured["price_items"]
    assert isinstance(normalized_price_rows, list)
    assert normalized_price_rows[1]["method"] == "markup_pct"
    assert normalized_price_rows[1]["value"] == pytest.approx(0.12)


def test_admin_preview_candidate_selector_updates_global_scenario_selection(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    assert active.scan_result is not None
    global_selected = active.selected_candidate_key or active.scan_result.best_candidate_key
    assert global_selected is not None
    selected_candidate = next(
        candidate_key for candidate_key in active.scan_result.candidate_details if candidate_key != global_selected
    )

    synced_state = admin_callbacks.sync_admin_preview_candidate_state(payload, {})
    options, dropdown_value, disabled, helper, meta = admin_callbacks.render_admin_preview_candidate_selector(
        payload,
        synced_state,
        "es",
    )
    assert dropdown_value == global_selected
    assert synced_state["source"] == admin_callbacks.ADMIN_PREVIEW_SOURCE_SCENARIO
    assert options
    assert disabled is False
    assert "sincron" in helper.lower()
    assert meta != ""
    assert _find_component(meta, "admin-preview-candidate-meta-panel") is not None
    assert _find_component(meta, "admin-preview-candidate-meta-inverter") is not None

    next_payload = admin_callbacks.update_admin_preview_candidate_state(selected_candidate, payload)
    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()
    assert updated_active is not None
    assert updated_active.selected_candidate_key == selected_candidate
    assert updated_active.dirty is False
    assert updated_state.project_dirty is True

    next_synced_state = admin_callbacks.sync_admin_preview_candidate_state(next_payload, {})
    assert next_synced_state["candidate_key"] == selected_candidate
    assert next_synced_state["source"] == admin_callbacks.ADMIN_PREVIEW_SOURCE_SCENARIO

    children = _render_preview_call(next_payload, lang="es", admin_preview_candidate_state=next_synced_state)
    preview_candidate = _find_component(children, "economics-preview-quantity-candidate")
    candidate_source = _find_component(children, "economics-preview-quantity-candidate-source")
    assert preview_candidate is not None
    assert selected_candidate in str(preview_candidate.children)
    assert candidate_source is not None
    assert "selección activa del escenario" in str(candidate_source.children).lower()


def test_results_selection_syncs_admin_selector_and_preview(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    assert active.scan_result is not None
    selected_candidate = next(
        candidate_key for candidate_key in active.scan_result.candidate_details if candidate_key != active.selected_candidate_key
    )
    table_rows = results_callbacks.populate_results(payload, "es", 5)[11]
    selected_index = next(index for index, row in enumerate(table_rows) if row["candidate_key"] == selected_candidate)

    next_payload = results_callbacks.persist_selected_candidate([selected_index], None, table_rows, payload)
    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    assert updated_active.selected_candidate_key == selected_candidate
    assert updated_active.dirty is False

    synced_state = admin_callbacks.sync_admin_preview_candidate_state(next_payload, {})
    options, dropdown_value, disabled, helper, meta = admin_callbacks.render_admin_preview_candidate_selector(
        next_payload,
        synced_state,
        "es",
    )
    preview_children = _render_preview_call(next_payload, lang="es", admin_preview_candidate_state=synced_state)
    preview_candidate = _find_component(preview_children, "economics-preview-quantity-candidate")

    assert options
    assert dropdown_value == selected_candidate
    assert disabled is False
    assert "sincron" in helper.lower()
    assert meta != ""
    assert preview_candidate is not None
    assert selected_candidate in str(preview_candidate.children)


def test_admin_preview_candidate_selector_reports_non_ready_states_without_mutating_state(monkeypatch, tmp_path) -> None:
    _client_state, state, active, payload = _admin_payload(monkeypatch, tmp_path)

    options, dropdown_value, disabled, helper, meta = admin_callbacks.render_admin_preview_candidate_selector(payload, {}, "es")
    assert options == []
    assert dropdown_value is None
    assert disabled is True
    assert "escaneo determinístico" in helper.lower()
    assert meta == ""

    scanned_state = run_scenario_scan(state, active.scenario_id)
    scanned_active = scanned_state.get_scenario()
    assert scanned_active is not None
    dirty_bundle = replace(scanned_active.config_bundle, config={**scanned_active.config_bundle.config, "PR": 0.85})
    rerun_state = update_scenario_bundle(scanned_state, scanned_active.scenario_id, dirty_bundle)
    rerun_payload = commit_client_session(_client_state, rerun_state).to_payload()
    options, dropdown_value, disabled, helper, meta = admin_callbacks.render_admin_preview_candidate_selector(
        rerun_payload,
        {},
        "es",
    )
    assert options == []
    assert dropdown_value is None
    assert disabled is True
    assert "escaneo determinístico" in helper.lower()
    assert meta == ""


def test_admin_preview_candidate_selector_handles_candidate_missing_state(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    assert active.scan_result is not None
    candidate_missing_scan = replace(
        active.scan_result,
        candidates=active.scan_result.candidates.iloc[0:0].copy(),
        best_candidate_key=None,
        candidate_details={},
    )
    broken_active = replace(active, scan_result=candidate_missing_scan, selected_candidate_key=None)
    broken_state = replace(
        state,
        scenarios=tuple(broken_active if scenario.scenario_id == active.scenario_id else scenario for scenario in state.scenarios),
    )
    payload = commit_client_session(client_state, broken_state).to_payload()

    options, dropdown_value, disabled, helper, meta = admin_callbacks.render_admin_preview_candidate_selector(
        payload,
        {},
        "es",
    )

    assert options == []
    assert dropdown_value is None
    assert disabled is True
    assert "no hay un diseño determinístico" in helper.lower()
    assert meta == ""


def test_pre_scan_economics_editors_stay_visible_while_preview_reports_no_scan(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _admin_payload(monkeypatch, tmp_path)
    synced_state = admin_callbacks.sync_admin_preview_candidate_state(payload, {})
    options, dropdown_value, disabled, helper, meta = admin_callbacks.render_admin_preview_candidate_selector(
        payload,
        synced_state,
        "es",
    )
    preview_children = _render_preview_call(payload, lang="es", admin_preview_candidate_state=synced_state)
    preview_status = _find_component(preview_children, "economics-preview-status")
    preview_summary = _find_component(preview_children, "economics-summary-cards")
    preview_closing = _find_component(preview_children, "economics-closing-shell")
    preview_breakdown = _find_component(preview_children, "economics-breakdown-shell")
    editors_class, editors_note, editors_note_style, editors_panels_style = admin_callbacks.sync_economics_editor_visibility(
        payload,
        economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es"),
        economics_price_items_rows_to_section_editor(active.config_bundle.economics_price_items_table, layers=("tax",), lang="es"),
        economics_price_items_rows_to_section_editor(
            active.config_bundle.economics_price_items_table,
            layers=("commercial", "sale"),
            lang="es",
        ),
        "es",
        synced_state,
    )

    assert options == []
    assert dropdown_value is None
    assert disabled is True
    assert "escaneo determinístico" in helper.lower()
    assert meta == ""
    assert preview_status is not None
    assert "Ejecuta el escaneo determinístico" in str(preview_status.children)
    assert preview_summary is None
    assert preview_closing is None
    assert preview_breakdown is None
    assert editors_class == "economics-editors-shell"
    assert editors_note == ""
    assert editors_note_style == {"display": "none"}
    assert editors_panels_style == {}


def test_render_economics_preview_ready_state_shows_cards_and_breakdown(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    cost_rows = active.config_bundle.economics_cost_items_table.to_dict("records")
    price_rows = active.config_bundle.economics_price_items_table.to_dict("records")
    cost_rows[0] = {**cost_rows[0], "amount_COP": 100_000.0}
    price_rows[0] = {**price_rows[0], "enabled": True, "value": 10}
    price_rows[2] = {**price_rows[2], "enabled": True, "value": 500_000.0}
    snapshot = build_candidate_financial_snapshot(
        active,
        active.selected_candidate_key or active.scan_result.best_candidate_key,
        economics_cost_items=cost_rows,
        economics_price_items=price_rows,
        use_cache=False,
    )

    children = _render_preview_call(
        payload,
        economics_cost_rows=cost_rows,
        economics_price_rows=price_rows,
        lang="es",
    )

    status = _find_component(children, "economics-preview-status")
    summary_shell = _find_component(children, "economics-summary-shell")
    quantities_shell = _find_component(children, "economics-preview-quantities-shell")
    flow_shell = _find_component(children, "economics-preview-flow-shell")
    advanced_preview = _find_component(children, "economics-preview-advanced-details")
    summary_cards = _find_component(children, "economics-summary-cards")
    breakdown_title = _find_component(children, "economics-breakdown-title")
    breakdown_copy = _find_component(children, "economics-breakdown-copy")
    breakdown_advanced = _find_component(children, "economics-breakdown-advanced-details")
    technical_shell = _find_component(children, "economics-breakdown-technical-shell")
    installed_shell = _find_component(children, "economics-breakdown-installed-shell")
    tax_shell = _find_component(children, "economics-breakdown-tax-shell")
    adjustments_shell = _find_component(children, "economics-breakdown-adjustments-shell")
    technical_table = _find_component(children, "economics-breakdown-technical-table")
    tax_table = _find_component(children, "economics-breakdown-tax-table")
    adjustments_table = _find_component(children, "economics-breakdown-adjustments-table")
    advanced_tax_table = _find_component(children, "economics-breakdown-advanced-tax-table")
    technical_subtotal = _find_component(children, "economics-breakdown-technical-subtotal")
    closing_shell = _find_component(children, "economics-closing-shell")
    closing_table = _find_component(children, "economics-closing-table")
    candidate_source = _find_component(children, "economics-preview-quantity-candidate-source")
    panel_name = _find_component(children, "economics-preview-quantity-panel-name")
    inverter_name = _find_component(children, "economics-preview-quantity-inverter-name")
    battery_name = _find_component(children, "economics-preview-quantity-battery-name")
    technical_copy = _find_component(children, "economics-breakdown-technical-copy")
    child_ids = [getattr(child, "id", None) for child in children]

    assert status is not None
    assert "diseño determinístico vigente" in str(status.children)
    assert child_ids.index("economics-summary-shell") < child_ids.index("economics-closing-shell")
    assert child_ids.index("economics-closing-shell") < child_ids.index("economics-breakdown-shell")
    assert child_ids.index("economics-breakdown-shell") < child_ids.index("economics-preview-advanced-details")
    assert summary_shell is not None
    assert quantities_shell is not None
    assert flow_shell is not None
    assert advanced_preview is not None
    assert "final_price_per_kwp_COP" not in str(flow_shell)
    assert "markup_pct" not in str(flow_shell)
    assert summary_cards is not None
    assert len(summary_cards.children) == 5
    assert "Precio final por kWp" in str(summary_shell)
    assert breakdown_title is not None
    assert breakdown_copy is not None
    assert breakdown_advanced is not None
    assert str(breakdown_title.children) == "Desglose del cálculo"
    assert technical_shell is not None
    assert installed_shell is not None
    assert tax_shell is not None
    assert adjustments_shell is not None
    assert technical_subtotal is not None
    assert closing_shell is not None
    assert closing_table is not None
    assert technical_table is not None
    assert tax_table is not None
    assert adjustments_table is not None
    assert advanced_tax_table is not None
    assert candidate_source is not None
    assert "Selección activa del escenario" in str(candidate_source.children)
    assert panel_name is not None
    assert inverter_name is not None
    assert battery_name is not None
    assert technical_copy is not None
    assert "subtotal técnico" in str(technical_copy.children)
    assert len(technical_table.data) >= 1
    assert len(tax_table.data) >= 1
    assert len(adjustments_table.data) >= 1
    assert "Base monetaria [COP]" not in {column["name"] for column in technical_table.columns}
    assert "Base monetaria [COP]" not in {column["name"] for column in tax_table.columns}
    assert "Base monetaria [COP]" in {column["name"] for column in advanced_tax_table.columns}
    assert "Etapa" not in {column["name"] for column in technical_table.columns}
    assert "Etapa" in {column["name"] for column in adjustments_table.columns}
    assert technical_table.data[0]["rule"] == "Por panel"
    assert tax_table.data[0]["rule"] == "Impuesto porcentual"
    assert "calculation" in technical_table.data[0]
    assert "x" in str(technical_table.data[0]["calculation"])
    assert float(technical_table.data[0]["line_amount_COP"]) == pytest.approx(snapshot.economics_result.cost_rows[0].line_amount_COP)
    assert len(technical_table.data) == len([row for row in snapshot.economics_result.cost_rows if row.stage_or_layer == "technical"])
    assert len(tax_table.data) == len([row for row in snapshot.economics_result.price_rows if row.stage_or_layer == "tax"])
    assert len(adjustments_table.data) == len(
        [row for row in snapshot.economics_result.price_rows if row.stage_or_layer in {"commercial", "sale"}]
    )
    assert "Precio final por kWp" not in {
        row["metric"] for row in closing_table.data
    }


def test_render_economics_preview_reports_no_scan_after_scan_invalidating_change(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    dirty_bundle = replace(active.config_bundle, config={**active.config_bundle.config, "PR": 0.85})
    state = update_scenario_bundle(state, active.scenario_id, dirty_bundle)
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None
    assert active.dirty is True

    children = _render_preview_call(payload, lang="es")

    status = _find_component(children, "economics-preview-status")
    summary_cards = _find_component(children, "economics-summary-cards")
    breakdown_table = _find_component(children, "economics-breakdown-technical-table")

    assert status is not None
    assert "Ejecuta el escaneo determinístico" in str(status.children)
    assert summary_cards is None
    assert breakdown_table is None


def test_render_economics_preview_reports_no_scan_when_scenario_has_no_scan(monkeypatch, tmp_path) -> None:
    _client_state, _state, _active, payload = _admin_payload(monkeypatch, tmp_path)

    children = _render_preview_call(payload, lang="es")

    status = _find_component(children, "economics-preview-status")
    summary_cards = _find_component(children, "economics-summary-cards")

    assert status is not None
    assert "Ejecuta el escaneo determinístico" in str(status.children)
    assert summary_cards is None


def test_render_economics_preview_reports_candidate_missing(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    assert active is not None
    broken_active = replace(
        active,
        scan_result=replace(active.scan_result, best_candidate_key=None),
        selected_candidate_key=None,
        dirty=False,
    )
    state = replace(state, scenarios=(broken_active,), active_scenario_id=broken_active.scenario_id)
    payload = commit_client_session(client_state, state).to_payload()

    children = _render_preview_call(payload, lang="es")

    status = _find_component(children, "economics-preview-status")
    assert status is not None
    assert "No hay un diseño determinístico disponible" in str(status.children)


def test_apply_admin_edits_preserves_scan_for_economics_only_changes_and_preview_stays_ready(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Economics Preview", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None
    assert active.scan_result is not None

    economics_cost_rows = active.config_bundle.economics_cost_items_table.to_dict("records")
    economics_price_rows = active.config_bundle.economics_price_items_table.to_dict("records")
    economics_cost_rows[0] = {**economics_cost_rows[0], "amount_COP": 456_000.0}
    economics_price_rows[0] = {**economics_price_rows[0], "value": 14}

    next_payload, status = _apply_admin_edits_call(
        1,
        payload,
        "Proyecto Economics Preview",
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        economics_cost_rows,
        economics_price_rows,
        "es",
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    assert updated_active.scan_result is not None
    assert updated_active.scan_fingerprint == active.scan_fingerprint
    assert updated_active.selected_candidate_key == active.selected_candidate_key
    assert updated_active.dirty is False
    assert "pendientes hasta volver a ejecutar" not in status

    preview_children = _render_preview_call(next_payload, lang="es")
    preview_status = _find_component(preview_children, "economics-preview-status")
    preview_summary = _find_component(preview_children, "economics-summary-cards")

    assert preview_status is not None
    assert "diseño determinístico vigente" in str(preview_status.children)
    assert preview_summary is not None


def test_render_economics_preview_shows_localized_placeholders_from_ui_not_engine(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)

    def _fake_preview(_scenario, *, economics_cost_items, economics_price_items, **_kwargs):
        _ = economics_cost_items, economics_price_items
        return EconomicsPreviewResult(
            state="ready",
            candidate_key="12.000::None",
            candidate_source="best_fallback",
            message_key="workspace.admin.economics.preview.state.ready",
            result=EconomicsResult(
                quantities=EconomicsQuantities(
                    candidate_key="12.000::None",
                    kWp=12.0,
                    panel_count=24,
                    inverter_count=1,
                    battery_kwh=0.0,
                    battery_name="",
                    inverter_name="",
                    panel_name="",
                ),
                cost_rows=(),
                price_rows=(),
                technical_subtotal_COP=0.0,
                installed_subtotal_COP=0.0,
                cost_total_COP=0.0,
                taxable_base_COP=0.0,
                tax_total_COP=0.0,
                subtotal_with_tax_COP=0.0,
                commercial_adjustment_COP=0.0,
                post_tax_adjustments_total_COP=0.0,
                commercial_offer_COP=0.0,
                sale_adjustment_COP=0.0,
                final_price_COP=0.0,
                final_price_per_kwp_COP=0.0,
            ),
        )

    monkeypatch.setattr(admin_callbacks, "resolve_economics_preview", _fake_preview)

    children = _render_preview_call(payload, lang="es")

    candidate_source = _find_component(children, "economics-preview-quantity-candidate-source")
    panel_name = _find_component(children, "economics-preview-quantity-panel-name")
    inverter_name = _find_component(children, "economics-preview-quantity-inverter-name")
    battery_name = _find_component(children, "economics-preview-quantity-battery-name")

    assert candidate_source is not None
    assert "Mejor diseño disponible" in str(candidate_source.children)
    assert panel_name is not None
    assert "Sin panel de catálogo" in str(panel_name.children)
    assert inverter_name is not None
    assert "Sin inversor asignado" in str(inverter_name.children)
    assert battery_name is not None
    assert "Sin batería asignada" in str(battery_name.children)


def test_economics_cost_editor_round_trips_source_mode_and_hardware_binding(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    editor_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    editor_rows[0] = {
        **editor_rows[0],
        "source_mode": "Manual",
        "hardware_binding": "Panel",
        "amount_COP": 321_000.0,
    }

    raw_rows = economics_cost_items_rows_from_editor(editor_rows)

    assert raw_rows[0]["source_mode"] == "manual"
    assert raw_rows[0]["hardware_binding"] == "panel"
    assert float(raw_rows[0]["amount_COP"]) == pytest.approx(321_000.0)

    round_trip_editor = economics_cost_items_rows_to_editor(pd.DataFrame(raw_rows, columns=COST_COLUMNS), lang="es")
    assert round_trip_editor[0]["source_mode"] == "Manual"
    assert round_trip_editor[0]["hardware_binding"] == "Panel"


def test_selected_hardware_none_keeps_line_unavailable_without_fallback(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    cost_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    cost_rows[0] = {
        **cost_rows[0],
        "source_mode": "Hardware seleccionado",
        "hardware_binding": "Sin vínculo",
        "amount_COP": 999_999.0,
    }

    children = _render_preview_call(
        payload,
        economics_cost_rows=cost_rows,
        economics_price_rows=price_rows,
        economics_price_rows_are_editor=True,
        lang="es",
    )

    warnings_shell = _find_component(children, "economics-preview-warnings-shell")
    technical_table = _find_component(children, "economics-breakdown-technical-table")

    assert warnings_shell is not None
    assert "requiere un vínculo hardware" in str(warnings_shell.children)
    assert technical_table is not None
    assert technical_table.data[0]["value_source"] == "No disponible"
    assert technical_table.data[0]["hardware_binding"] == "Sin vínculo"
    assert float(technical_table.data[0]["unit_rate_COP"]) == pytest.approx(0.0)
    assert float(technical_table.data[0]["line_amount_COP"]) == pytest.approx(0.0)


def test_preview_selected_battery_hardware_uses_one_battery_not_energy_kwh(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state, active = _replace_selected_battery_detail(
        state,
        active,
        {
            "name": "BAT-ENERGY",
            "nom_kWh": 10.0,
            "max_kW": 80.0,
            "max_ch_kW": 80.0,
            "max_dis_kW": 80.0,
            "price_COP": 12_500_000.0,
        },
    )
    payload = commit_client_session(client_state, state).to_payload()

    children = _render_preview_call(payload, lang="es")
    technical_table = _find_component(children, "economics-breakdown-technical-table")

    assert technical_table is not None
    battery_row = next(row for row in technical_table.data if row["name"] == "Battery hardware")
    assert float(battery_row["multiplier"]) == pytest.approx(1.0)
    assert "1 batería" in str(battery_row["calculation"])
    assert "80" not in str(battery_row["calculation"])


def test_preview_live_hardware_warnings_do_not_persist_before_apply(monkeypatch, tmp_path) -> None:
    client_state, state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    cost_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    cost_rows[0] = {**cost_rows[0], "source_mode": "Hardware seleccionado", "hardware_binding": "Sin vínculo"}

    children = _render_preview_call(
        payload,
        economics_cost_rows=cost_rows,
        economics_price_rows=price_rows,
        economics_price_rows_are_editor=True,
        lang="es",
    )
    warnings_shell = _find_component(children, "economics-preview-warnings-shell")

    assert warnings_shell is not None
    assert "requiere un vínculo hardware" in str(warnings_shell.children)

    _, current_state = resolve_client_session(payload, language="es")
    current_active = current_state.get_scenario()
    assert current_active is not None
    persisted_messages = [issue.message for issue in current_active.config_bundle.issues if issue.field == "economics_cost_items"]
    assert "Economics_Cost_Items fila 1: 'selected_hardware' requiere un 'hardware_binding' distinto de 'none'." not in persisted_messages


def test_preview_live_battery_energy_warning_does_not_persist_before_apply(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state, active = _replace_selected_battery_detail(
        state,
        active,
        {
            "name": "BAT-POWER-ONLY",
            "price_COP": 12_500_000.0,
            "max_kW": 80.0,
            "max_ch_kW": 80.0,
            "max_dis_kW": 80.0,
        },
    )
    payload = commit_client_session(client_state, state).to_payload()

    children = _render_preview_call(payload, lang="es")
    warnings_shell = _find_component(children, "economics-preview-warnings-shell")

    assert warnings_shell is not None
    assert "no una energía válida" in str(warnings_shell.children)

    _, current_state = resolve_client_session(payload, language="es")
    current_active = current_state.get_scenario()
    assert current_active is not None
    persisted_messages = [issue.message for issue in current_active.config_bundle.issues if issue.field == "economics_cost_items"]
    assert (
        "Economics_Cost_Items fila 3: la batería seleccionada tiene campos de potencia pero no una energía válida ('nom_kWh' o alias soportado); la cantidad energética quedará en 0 kWh."
        not in persisted_messages
    )


def test_apply_persists_hardware_resolution_warning_when_scan_is_preserved(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Economics Hardware Warning", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None and active.scan_result is not None

    economics_cost_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    economics_price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    economics_cost_rows[0] = {
        **economics_cost_rows[0],
        "source_mode": "Hardware seleccionado",
        "hardware_binding": "Sin vínculo",
        "amount_COP": 456_000.0,
    }

    next_payload, status = _apply_admin_edits_call(
        1,
        payload,
        "Proyecto Economics Hardware Warning",
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        economics_cost_rows,
        economics_price_rows,
        "es",
        economics_price_rows_are_editor=True,
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    assert updated_active.scan_result is not None
    assert updated_active.dirty is False
    assert "pendientes hasta volver a ejecutar" not in status
    persisted_messages = [issue.message for issue in updated_active.config_bundle.issues if issue.field == "economics_cost_items"]
    assert "Economics_Cost_Items fila 1: 'selected_hardware' requiere un 'hardware_binding' distinto de 'none'." in persisted_messages

    preview_children = _render_preview_call(next_payload, lang="es")
    warnings_shell = _find_component(preview_children, "economics-preview-warnings-shell")
    assert warnings_shell is not None
    assert "requiere un vínculo hardware" in str(warnings_shell.children)


def test_apply_persists_battery_energy_warning_when_scan_is_preserved(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Economics Battery Energy Warning", language="es")
    active = state.get_scenario()
    assert active is not None
    state, active = _replace_selected_battery_detail(
        state,
        active,
        {
            "name": "BAT-POWER-ONLY",
            "price_COP": 12_500_000.0,
            "max_kW": 80.0,
            "max_ch_kW": 80.0,
            "max_dis_kW": 80.0,
        },
    )
    payload = commit_client_session(client_state, state).to_payload()

    economics_cost_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    economics_price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    economics_cost_rows[0] = {**economics_cost_rows[0], "notes": "refresh warning persistence"}

    next_payload, status = _apply_admin_edits_call(
        1,
        payload,
        "Proyecto Economics Battery Energy Warning",
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        economics_cost_rows,
        economics_price_rows,
        "es",
        economics_price_rows_are_editor=True,
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert updated_active is not None
    assert updated_active.scan_result is not None
    assert updated_active.dirty is False
    assert "pendientes hasta volver a ejecutar" not in status
    persisted_messages = [issue.message for issue in updated_active.config_bundle.issues if issue.field == "economics_cost_items"]
    assert (
        "Economics_Cost_Items fila 3: la batería seleccionada tiene campos de potencia pero no una energía válida ('nom_kWh' o alias soportado); la cantidad energética quedará en 0 kWh."
        in persisted_messages
    )

    preview_children = _render_preview_call(next_payload, lang="es")
    warnings_shell = _find_component(preview_children, "economics-preview-warnings-shell")
    assert warnings_shell is not None
    assert "no una energía válida" in str(warnings_shell.children)


def test_run_scan_persists_hardware_resolution_warning_when_selected_hardware_is_unavailable(monkeypatch, tmp_path) -> None:
    _client_state, state, active, _payload = _admin_payload(monkeypatch, tmp_path)
    assert active is not None
    changed_costs = active.config_bundle.economics_cost_items_table.copy()
    changed_costs.at[0, "source_mode"] = "selected_hardware"
    changed_costs.at[0, "hardware_binding"] = "none"
    changed_bundle = replace(active.config_bundle, economics_cost_items_table=changed_costs)
    state = update_scenario_bundle(state, active.scenario_id, changed_bundle)
    state = run_scenario_scan(state, active.scenario_id)
    scanned = state.get_scenario()

    assert scanned is not None
    messages = [issue.message for issue in scanned.config_bundle.issues if issue.field == "economics_cost_items"]
    assert "Economics_Cost_Items fila 1: 'selected_hardware' requiere un 'hardware_binding' distinto de 'none'." in messages


def test_amount_cop_manual_value_survives_mode_toggles() -> None:
    rows = economics_cost_items_rows_to_editor(load_example_config().economics_cost_items_table, lang="es")
    rows[0] = {**rows[0], "amount_COP": 654_321.0, "source_mode": "Manual", "hardware_binding": "Panel"}
    manual_rows = economics_cost_items_rows_from_editor(rows)

    rows[0] = {**rows[0], "source_mode": "Hardware seleccionado", "hardware_binding": "Panel"}
    selected_rows = economics_cost_items_rows_from_editor(rows)

    rows[0] = {**rows[0], "source_mode": "Manual", "hardware_binding": "Panel"}
    manual_again_rows = economics_cost_items_rows_from_editor(rows)

    assert float(manual_rows[0]["amount_COP"]) == pytest.approx(654_321.0)
    assert float(selected_rows[0]["amount_COP"]) == pytest.approx(654_321.0)
    assert float(manual_again_rows[0]["amount_COP"]) == pytest.approx(654_321.0)


def test_bridge_cta_is_disabled_until_preview_is_ready(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _admin_payload(monkeypatch, tmp_path)

    disabled, note = sync_economics_bridge_cta(payload, *_bridge_args(active))

    assert disabled is True
    assert "escaneo determinístico" in note.lower()


def test_bridge_cta_blocks_live_hardware_warnings(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    economics_cost_rows = economics_cost_items_rows_to_editor(active.config_bundle.economics_cost_items_table, lang="es")
    economics_cost_rows[0] = {
        **economics_cost_rows[0],
        "source_mode": "Hardware seleccionado",
        "hardware_binding": "Sin vínculo",
    }

    disabled, note = sync_economics_bridge_cta(
        payload,
        *_bridge_args(active, economics_cost_rows=economics_cost_rows),
    )

    assert disabled is True
    assert "warnings live" in note.lower()


def test_bridge_cta_blocks_when_non_economics_admin_drafts_exist(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)

    disabled, note = sync_economics_bridge_cta(
        payload,
        *_bridge_args(
            active,
            assumption_input_ids=[{"field": "buy_tariff_COP_kWh"}],
            assumption_values=[float(active.config_bundle.config["buy_tariff_COP_kWh"]) + 10.0],
        ),
    )

    assert disabled is True
    assert "fuera de economics" in note.lower()


def test_bridge_callback_reresolves_preview_and_writes_runtime_total(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    assert active.scan_result is not None
    selected_candidate = next(
        candidate_key for candidate_key in active.scan_result.candidate_details if candidate_key != active.selected_candidate_key
    )
    selected_payload = admin_callbacks.update_admin_preview_candidate_state(selected_candidate, payload)
    preview_state = admin_callbacks.sync_admin_preview_candidate_state(selected_payload, {})
    _, selected_state = resolve_client_session(selected_payload, language="es")
    selected_active = selected_state.get_scenario()
    assert selected_active is not None
    captured: dict[str, object] = {}
    real_apply = admin_callbacks.apply_prepared_economics_runtime_price_bridge

    def _fake_prepare(scenario, *, economics_cost_items, economics_price_items, candidate_key=None, applied_at=None):
        captured["scenario_id"] = scenario.scenario_id
        captured["cost_items"] = economics_cost_items
        captured["price_items"] = economics_price_items
        captured["applied_at"] = applied_at
        captured["candidate_key"] = candidate_key
        return _prepared_bridge_result(
            selected_active,
            candidate_key=str(candidate_key),
            final_price_COP=38_750_000.0,
            normalized_cost_rows=economics_cost_items,
            normalized_price_rows=economics_price_items,
            applied_at=str(applied_at),
        )

    def _wrapped_apply(state, scenario_id, prepared, *, mark_project_dirty):
        captured["applied_scenario_id"] = scenario_id
        captured["applied_mark_project_dirty"] = mark_project_dirty
        return real_apply(state, scenario_id, prepared, mark_project_dirty=mark_project_dirty)

    monkeypatch.setattr(admin_callbacks, "prepare_economics_runtime_price_bridge", _fake_prepare)
    monkeypatch.setattr(admin_callbacks, "apply_prepared_economics_runtime_price_bridge", _wrapped_apply)

    next_payload, status = apply_economics_runtime_price_bridge(
        1,
        selected_payload,
        "",
        *_bridge_args(selected_active),
        preview_state,
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()

    assert captured["scenario_id"] == active.scenario_id
    assert isinstance(captured["cost_items"], list)
    assert isinstance(captured["price_items"], list)
    assert captured["candidate_key"] == selected_candidate
    assert captured["applied_scenario_id"] == active.scenario_id
    assert captured["applied_mark_project_dirty"] is True
    assert updated_active is not None
    assert updated_active.config_bundle.config["pricing_mode"] == "total"
    assert float(updated_active.config_bundle.config["price_total_COP"]) == pytest.approx(38_750_000.0)
    assert updated_active.config_bundle.config["include_hw_in_price"] is False
    assert float(updated_active.config_bundle.config["price_others_total"]) == pytest.approx(0.0)
    assert updated_active.config_bundle.config["include_var_others"] == active.config_bundle.config["include_var_others"]
    assert updated_active.runtime_price_bridge is not None
    assert updated_active.runtime_price_bridge.candidate_key == selected_candidate
    assert updated_active.runtime_price_bridge.final_price_COP == pytest.approx(38_750_000.0)
    assert updated_active.runtime_price_bridge.resolved_preview_state == "ready"
    assert updated_active.runtime_price_bridge.applied_price_total_COP == pytest.approx(38_750_000.0)
    assert "38" in status


def test_candidate_change_keeps_preview_live_and_marks_bridge_historical(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    assert active.scan_result is not None

    bridged_payload, _status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "",
        *_bridge_args(active),
    )
    _, bridged_state = resolve_client_session(bridged_payload, language="es")
    bridged_active = bridged_state.get_scenario()
    assert bridged_active is not None
    assert bridged_active.runtime_price_bridge is not None

    previous_candidate = bridged_active.selected_candidate_key
    next_candidate = next(
        candidate_key
        for candidate_key in bridged_active.scan_result.candidate_details
        if candidate_key != previous_candidate
    )
    selected_payload = admin_callbacks.update_admin_preview_candidate_state(next_candidate, bridged_payload)
    synced_state = admin_callbacks.sync_admin_preview_candidate_state(selected_payload, {})
    _, updated_state = resolve_client_session(selected_payload, language="es")
    updated_active = updated_state.get_scenario()
    preview_children = _render_preview_call(selected_payload, lang="es", admin_preview_candidate_state=synced_state)
    preview_status = _find_component(preview_children, "economics-preview-status")
    preview_candidate = _find_component(preview_children, "economics-preview-quantity-candidate")
    bridge_status = render_runtime_price_bridge_ui(selected_payload, "es")

    assert updated_active is not None
    assert updated_active.selected_candidate_key == next_candidate
    assert updated_active.dirty is False
    assert updated_active.runtime_price_bridge is not None
    assert updated_active.runtime_price_bridge.stale is True
    assert resolve_runtime_price_bridge_state(updated_active) == "stale"
    assert updated_active.config_bundle.config["pricing_mode"] == bridged_active.config_bundle.config["pricing_mode"]
    assert float(updated_active.config_bundle.config["price_total_COP"]) == pytest.approx(
        float(bridged_active.config_bundle.config["price_total_COP"])
    )
    assert preview_status is not None
    assert "diseño determinístico vigente" in str(preview_status.children)
    assert preview_candidate is not None
    assert next_candidate in str(preview_candidate.children)
    assert previous_candidate in str(bridge_status)
    assert next_candidate in str(bridge_status)
    assert "histórico" in str(bridge_status).lower()


def test_bridge_callback_aborts_cleanly_if_preview_becomes_ineligible(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)

    def _blocked_prepare(_scenario, *, economics_cost_items, economics_price_items, candidate_key=None, applied_at=None):
        _ = economics_cost_items, economics_price_items, candidate_key, applied_at
        return PreparedEconomicsRuntimePriceBridge(
            applied=False,
            candidate_key=active.runtime_price_bridge.candidate_key if active.runtime_price_bridge is not None else None,
            preview_state="no_scan",
            blocker_key="preview_state:no_scan",
        )

    monkeypatch.setattr(admin_callbacks, "prepare_economics_runtime_price_bridge", _blocked_prepare)

    next_payload, status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "",
        *_bridge_args(active),
    )

    _, unchanged_state = resolve_client_session(next_payload, language="es")
    unchanged_active = unchanged_state.get_scenario()

    assert unchanged_active is not None
    assert unchanged_active.runtime_price_bridge == active.runtime_price_bridge
    assert unchanged_active.config_bundle.config["pricing_mode"] == active.config_bundle.config["pricing_mode"]
    assert float(unchanged_active.config_bundle.config["price_total_COP"]) == pytest.approx(
        float(active.config_bundle.config["price_total_COP"])
    )
    assert "escaneo determinístico" in status.lower()


def test_bridge_is_idempotent_for_repeated_clicks_on_same_ready_state(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)

    first_payload, _first_status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "",
        *_bridge_args(active),
    )
    second_payload, _second_status = apply_economics_runtime_price_bridge(
        2,
        payload,
        "",
        *_bridge_args(active),
    )

    _, first_state = resolve_client_session(first_payload, language="es")
    _, second_state = resolve_client_session(second_payload, language="es")
    first_active = first_state.get_scenario()
    second_active = second_state.get_scenario()

    assert first_active is not None
    assert second_active is not None
    assert first_active.config_bundle.config["pricing_mode"] == "total"
    assert second_active.config_bundle.config["pricing_mode"] == "total"
    assert float(first_active.config_bundle.config["price_total_COP"]) == pytest.approx(
        float(second_active.config_bundle.config["price_total_COP"])
    )
    assert first_active.runtime_price_bridge is not None
    assert second_active.runtime_price_bridge is not None
    assert first_active.runtime_price_bridge.candidate_key == second_active.runtime_price_bridge.candidate_key
    assert first_active.runtime_price_bridge.final_price_COP == pytest.approx(second_active.runtime_price_bridge.final_price_COP)
    assert first_active.runtime_price_bridge.stale is False
    assert second_active.runtime_price_bridge.stale is False


def test_bridge_persists_active_provenance_and_updates_runtime_note(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Bridge Runtime", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    next_payload, _status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "Proyecto Bridge Runtime",
        *_bridge_args(active),
    )

    _, updated_state = resolve_client_session(next_payload, language="es")
    updated_active = updated_state.get_scenario()
    assert updated_active is not None
    assert updated_active.runtime_price_bridge is not None
    assert resolve_runtime_price_bridge_state(updated_active) == "active"
    assert updated_active.runtime_price_bridge.applied_economics_signature == compute_economics_runtime_signature(
        updated_active.config_bundle.economics_cost_items_table,
        updated_active.config_bundle.economics_price_items_table,
    )

    manifest = read_project_manifest(updated_state.project_slug)
    manifest_scenario = next(item for item in manifest.scenarios if item.scenario_id == updated_active.scenario_id)
    assert manifest_scenario.runtime_price_bridge is not None
    assert manifest_scenario.runtime_price_bridge.final_price_COP == pytest.approx(
        updated_active.runtime_price_bridge.final_price_COP
    )
    assert manifest_scenario.runtime_price_bridge.applied_economics_signature == updated_active.runtime_price_bridge.applied_economics_signature

    reopened = open_project(updated_state.project_slug)
    reopened_active = reopened.get_scenario(updated_active.scenario_id)
    assert reopened_active is not None
    assert reopened_active.runtime_price_bridge is not None
    assert resolve_runtime_price_bridge_state(reopened_active) == "active"

    bridge_status = render_runtime_price_bridge_ui(next_payload, "es")

    assert bridge_status is not None
    assert "total vigente del runtime proviene de economics".lower() in str(bridge_status).lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pricing_mode", "variable"),
        ("price_total_COP", 12_345_678.0),
        ("include_hw_in_price", True),
        ("price_others_total", 999_000.0),
    ],
)
def test_bridge_goes_stale_when_legacy_runtime_fields_diverge(field, value, monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Bridge Stale", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    bridged_payload, _status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "Proyecto Bridge Stale",
        *_bridge_args(active),
    )
    bridged_client, bridged_state = resolve_client_session(bridged_payload, language="es")
    bridged_active = bridged_state.get_scenario()
    assert bridged_active is not None
    assert bridged_active.runtime_price_bridge is not None

    changed_bundle = replace(
        bridged_active.config_bundle,
        config={**bridged_active.config_bundle.config, field: value},
    )
    stale_state = update_scenario_bundle(bridged_state, bridged_active.scenario_id, changed_bundle)
    stale_payload = commit_client_session(bridged_client, stale_state).to_payload()
    stale_active = stale_state.get_scenario()

    assert stale_active is not None
    assert stale_active.runtime_price_bridge is not None
    assert stale_active.runtime_price_bridge.stale is True
    assert resolve_runtime_price_bridge_state(stale_active) == "stale"

    bridge_status = render_runtime_price_bridge_ui(stale_payload, "es")
    assert "histórico" in str(bridge_status).lower()


def test_bridge_goes_stale_when_economics_signature_changes_for_same_design(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Bridge Economics Signature", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    bridged_payload, _status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "Proyecto Bridge Economics Signature",
        *_bridge_args(active),
    )
    bridged_client, bridged_state = resolve_client_session(bridged_payload, language="es")
    bridged_active = bridged_state.get_scenario()
    assert bridged_active is not None
    assert bridged_active.runtime_price_bridge is not None

    changed_prices = bridged_active.config_bundle.economics_price_items_table.copy()
    changed_prices.at[0, "value"] = float(changed_prices.at[0, "value"]) + 0.01
    changed_bundle = replace(
        bridged_active.config_bundle,
        economics_price_items_table=changed_prices,
    )
    stale_state = update_scenario_bundle(bridged_state, bridged_active.scenario_id, changed_bundle)
    stale_active = stale_state.get_scenario()

    assert stale_active is not None
    assert stale_active.runtime_price_bridge is not None
    assert stale_active.runtime_price_bridge.stale is True
    assert resolve_runtime_price_bridge_state(stale_active) == "stale"
    assert stale_active.runtime_price_bridge.candidate_key == bridged_active.runtime_price_bridge.candidate_key
    assert stale_active.runtime_price_bridge.applied_economics_signature != compute_economics_runtime_signature(
        stale_active.config_bundle.economics_cost_items_table,
        stale_active.config_bundle.economics_price_items_table,
    )


def test_new_bridge_replaces_previous_provenance_snapshot(monkeypatch, tmp_path) -> None:
    client_state, state, active, _payload = _scanned_admin_payload(monkeypatch, tmp_path)
    state = save_project(state, project_name="Proyecto Bridge Replace", language="es")
    payload = commit_client_session(client_state, state).to_payload()
    active = state.get_scenario()
    assert active is not None

    first_price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    first_price_rows[1] = {**first_price_rows[1], "value": 5}
    first_payload, _ = apply_economics_runtime_price_bridge(
        1,
        payload,
        "Proyecto Bridge Replace",
        *_bridge_args(active, economics_price_rows=first_price_rows, economics_price_rows_are_editor=True),
    )
    first_client, first_state = resolve_client_session(first_payload, language="es")
    first_active = first_state.get_scenario()
    assert first_active is not None and first_active.runtime_price_bridge is not None
    first_total = float(first_active.runtime_price_bridge.final_price_COP)

    rerun_state = run_scenario_scan(first_state, first_active.scenario_id)
    rerun_payload = commit_client_session(first_client, rerun_state).to_payload()
    rerun_active = rerun_state.get_scenario()
    assert rerun_active is not None and rerun_active.scan_result is not None

    second_price_rows = economics_price_items_rows_to_editor(rerun_active.config_bundle.economics_price_items_table, lang="es")
    second_price_rows[1] = {**second_price_rows[1], "value": 25}
    second_payload, _ = apply_economics_runtime_price_bridge(
        2,
        rerun_payload,
        "Proyecto Bridge Replace",
        *_bridge_args(rerun_active, economics_price_rows=second_price_rows, economics_price_rows_are_editor=True),
    )
    _, second_state = resolve_client_session(second_payload, language="es")
    second_active = second_state.get_scenario()

    assert second_active is not None
    assert second_active.runtime_price_bridge is not None
    assert float(second_active.runtime_price_bridge.final_price_COP) != pytest.approx(first_total)
    assert second_active.runtime_price_bridge.applied_economics_signature != first_active.runtime_price_bridge.applied_economics_signature


def test_manual_bridge_persists_normalized_economics_tables_and_signature(monkeypatch, tmp_path) -> None:
    _client_state, _state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    economics_price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    economics_price_rows[0] = {**economics_price_rows[0], "value": 17}

    bridged_payload, _status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "",
        *_bridge_args(active, economics_price_rows=economics_price_rows, economics_price_rows_are_editor=True),
    )
    _, bridged_state = resolve_client_session(bridged_payload, language="es")
    bridged_active = bridged_state.get_scenario()

    assert bridged_active is not None
    expected_prices = pd.DataFrame(
        economics_price_items_rows_from_editor(economics_price_rows),
        columns=bridged_active.config_bundle.economics_price_items_table.columns,
    )
    pdt.assert_frame_equal(
        bridged_active.config_bundle.economics_price_items_table.reset_index(drop=True),
        expected_prices.reset_index(drop=True),
    )
    assert bridged_active.runtime_price_bridge is not None
    assert bridged_active.runtime_price_bridge.applied_economics_signature == compute_economics_runtime_signature(
        bridged_active.config_bundle.economics_cost_items_table,
        bridged_active.config_bundle.economics_price_items_table,
    )


def test_editing_economics_without_bridge_does_not_change_legacy_runtime_fields(monkeypatch, tmp_path) -> None:
    client_state, state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    economics_price_rows = economics_price_items_rows_to_editor(active.config_bundle.economics_price_items_table, lang="es")
    economics_price_rows[0] = {**economics_price_rows[0], "value": 22}

    _meta = _sync_admin_draft_call(
        payload,
        [],
        [],
        active.config_bundle.inverter_catalog.to_dict("records"),
        active.config_bundle.battery_catalog.to_dict("records"),
        active.config_bundle.panel_catalog.to_dict("records"),
        active.config_bundle.month_profile_table.to_dict("records"),
        active.config_bundle.sun_profile_table.to_dict("records"),
        active.config_bundle.economics_cost_items_table.to_dict("records"),
        economics_price_rows,
        economics_price_rows_are_editor=True,
    )

    _, current_state = resolve_client_session(payload, language="es")
    current_active = current_state.get_scenario()

    assert current_active is not None
    assert current_active.runtime_price_bridge == active.runtime_price_bridge
    assert current_active.config_bundle.config["pricing_mode"] == active.config_bundle.config["pricing_mode"]
    assert float(current_active.config_bundle.config["price_total_COP"]) == pytest.approx(
        float(active.config_bundle.config["price_total_COP"])
    )


def test_legacy_runtime_uses_bridged_total_after_rerun(monkeypatch, tmp_path) -> None:
    _client_state, state, active, payload = _scanned_admin_payload(monkeypatch, tmp_path)
    bridged_payload, _status = apply_economics_runtime_price_bridge(
        1,
        payload,
        "",
        *_bridge_args(active),
    )
    _, bridged_state = resolve_client_session(bridged_payload, language="es")
    bridged_active = bridged_state.get_scenario()

    assert bridged_active is not None
    bridged_total = float(bridged_active.config_bundle.config["price_total_COP"])

    rerun_state = run_scenario_scan(bridged_state, bridged_active.scenario_id)
    rerun_active = rerun_state.get_scenario()
    assert rerun_active is not None
    assert rerun_active.scan_result is not None
    assert rerun_active.runtime_price_bridge is not None

    best_key = rerun_active.scan_result.best_candidate_key
    detail = rerun_active.scan_result.candidate_details[best_key]

    assert float(detail["summary"]["capex_client"]) == pytest.approx(bridged_total)
    assert rerun_active.config_bundle.config["pricing_mode"] == "total"
    assert float(rerun_active.config_bundle.config["price_total_COP"]) == pytest.approx(
        float(rerun_active.runtime_price_bridge.final_price_COP)
    )
    assert prepare_economics_runtime_price_bridge(rerun_active).final_price_COP == pytest.approx(
        float(rerun_active.config_bundle.config["price_total_COP"])
    )
