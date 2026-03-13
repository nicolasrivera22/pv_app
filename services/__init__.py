"""Service layer for deterministic PV scenario execution and Dash integration."""

from .export_excel import export_comparison_workbook, export_scenario_workbook
from .io_excel import ensure_template, load_config_from_excel, load_example_config
from .result_views import (
    build_comparison_figures,
    build_comparison_table,
    build_session_comparison_rows,
    resolve_selected_candidate_key_for_scenario,
)
from .scenario_runner import run_scan, run_scenario
from .scenario_session import (
    add_scenario,
    create_scenario_record,
    default_scenario_name,
    delete_scenario,
    duplicate_scenario,
    rename_scenario,
    run_scenario_scan,
    set_active_scenario,
    set_comparison_scenarios,
    update_scenario_bundle,
    update_selected_candidate,
)
from .types import (
    LoadedConfigBundle,
    ScanRunResult,
    ScenarioRecord,
    ScenarioRunResult,
    ScenarioSessionState,
    ValidationIssue,
)
from .validation import (
    normalize_battery_catalog_rows,
    normalize_inverter_catalog_rows,
    refresh_bundle_issues,
    validate_config,
)

__all__ = [
    "LoadedConfigBundle",
    "ScanRunResult",
    "ScenarioRecord",
    "ScenarioRunResult",
    "ScenarioSessionState",
    "ValidationIssue",
    "add_scenario",
    "build_comparison_figures",
    "build_comparison_table",
    "build_session_comparison_rows",
    "create_scenario_record",
    "default_scenario_name",
    "delete_scenario",
    "duplicate_scenario",
    "ensure_template",
    "export_comparison_workbook",
    "export_scenario_workbook",
    "load_config_from_excel",
    "load_example_config",
    "normalize_battery_catalog_rows",
    "normalize_inverter_catalog_rows",
    "refresh_bundle_issues",
    "rename_scenario",
    "resolve_selected_candidate_key_for_scenario",
    "run_scan",
    "run_scenario",
    "run_scenario_scan",
    "set_active_scenario",
    "set_comparison_scenarios",
    "update_scenario_bundle",
    "update_selected_candidate",
    "validate_config",
]
