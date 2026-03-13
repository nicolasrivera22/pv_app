"""Service layer for deterministic PV scenario execution and Dash integration."""

from .io_excel import ensure_template, load_config_from_excel, load_example_config
from .scenario_runner import run_scan, run_scenario
from .types import LoadedConfigBundle, ScanRunResult, ScenarioRunResult, ValidationIssue
from .validation import validate_config

__all__ = [
    "LoadedConfigBundle",
    "ScanRunResult",
    "ScenarioRunResult",
    "ValidationIssue",
    "ensure_template",
    "load_config_from_excel",
    "load_example_config",
    "run_scan",
    "run_scenario",
    "validate_config",
]
