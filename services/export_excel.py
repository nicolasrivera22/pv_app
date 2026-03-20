from __future__ import annotations

from io import BytesIO

import pandas as pd

from .design_compare import build_design_comparison_export_frames
from .result_views import build_comparison_table, build_kpis
from .types import ScenarioRecord, ScenarioSessionState


def _config_frame(config: dict) -> pd.DataFrame:
    return pd.DataFrame([{"field": key, "value": value} for key, value in config.items()])


def _summary_frame(scenario: ScenarioRecord) -> pd.DataFrame:
    if scenario.scan_result is None:
        raise ValueError(f"El escenario '{scenario.name}' no tiene resultados para exportar.")
    candidate_key = scenario.selected_candidate_key or scenario.scan_result.best_candidate_key
    if not candidate_key:
        raise ValueError(f"El escenario '{scenario.name}' no tiene diseños viables para exportar.")
    detail = scenario.scan_result.candidate_details[candidate_key]
    kpis = build_kpis(detail)
    return pd.DataFrame(
        [
            {"metric": "scenario", "value": scenario.name},
            {"metric": "source_name", "value": scenario.source_name},
            {"metric": "candidate_key", "value": candidate_key},
            {"metric": "best_kWp", "value": kpis["best_kWp"]},
            {"metric": "battery", "value": kpis["selected_battery"]},
            {"metric": "NPV_COP", "value": kpis["NPV"]},
            {"metric": "payback_years", "value": kpis["payback_years"]},
            {"metric": "self_consumption_ratio", "value": kpis["self_consumption_ratio"]},
            {"metric": "self_sufficiency_ratio", "value": kpis["self_sufficiency_ratio"]},
            {"metric": "annual_import_kwh", "value": kpis["annual_import_kwh"]},
            {"metric": "annual_export_kwh", "value": kpis["annual_export_kwh"]},
        ]
    )


def _sheet_name(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)
    return clean[:31]


def export_scenario_workbook(scenario_record: ScenarioRecord) -> bytes:
    if scenario_record.scan_result is None:
        raise ValueError(f"El escenario '{scenario_record.name}' no tiene resultados para exportar.")
    candidate_key = scenario_record.selected_candidate_key or scenario_record.scan_result.best_candidate_key
    if not candidate_key:
        raise ValueError(f"El escenario '{scenario_record.name}' no tiene diseños viables para exportar.")
    detail = scenario_record.scan_result.candidate_details[candidate_key]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _summary_frame(scenario_record).to_excel(writer, sheet_name="Summary", index=False)
        _config_frame(scenario_record.config_bundle.config).to_excel(writer, sheet_name="Config", index=False)
        scenario_record.config_bundle.inverter_catalog.to_excel(writer, sheet_name="Inverters", index=False)
        scenario_record.config_bundle.battery_catalog.to_excel(writer, sheet_name="Batteries", index=False)
        scenario_record.scan_result.candidates.to_excel(writer, sheet_name="Candidates", index=False)
        detail["monthly"].to_excel(writer, sheet_name="Monthly_Selected", index=False)
    return output.getvalue()


def export_comparison_workbook(session_state: ScenarioSessionState, scenario_records: list[ScenarioRecord]) -> bytes:
    clean_records = [
        scenario
        for scenario in scenario_records
        if scenario.scan_result is not None and not scenario.dirty and scenario.scan_result.best_candidate_key
    ]
    if not clean_records:
        raise ValueError("No hay escenarios ejecutados para exportar la comparación.")

    summary = build_comparison_table(clean_records)
    metrics = summary[
        [
            "scenario",
            "best_kWp",
            "battery",
            "NPV_COP",
            "payback_years",
            "self_consumption_ratio",
            "self_sufficiency_ratio",
            "annual_import_kwh",
            "annual_export_kwh",
        ]
    ].copy()

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Comparison_Summary", index=False)
        metrics.to_excel(writer, sheet_name="Comparison_KPIs", index=False)
        for scenario in clean_records:
            assert scenario.scan_result is not None
            sheet_name = _sheet_name(f"Candidates_{scenario.scenario_id}")
            scenario.scan_result.candidates.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def export_design_comparison_workbook(
    scenario_record: ScenarioRecord,
    selected_candidate_keys: list[str] | tuple[str, ...],
    *,
    lang: str = "es",
) -> bytes:
    if scenario_record.scan_result is None or scenario_record.dirty:
        raise ValueError(f"El escenario '{scenario_record.name}' necesita un escaneo determinístico válido para exportar la comparación.")

    frames = build_design_comparison_export_frames(scenario_record, selected_candidate_keys, lang=lang)
    if frames["Design_Comparison_Summary"].empty:
        raise ValueError("No hay diseños seleccionados para exportar.")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in frames.items():
            frame.to_excel(writer, sheet_name=_sheet_name(sheet_name), index=False)
    return output.getvalue()
