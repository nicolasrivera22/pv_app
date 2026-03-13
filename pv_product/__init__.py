"""
Pequeño paquete con la arquitectura refactorizada para la app FV.

Incluye:
  - Dataclasses livianas para inputs de simulación.
  - Motor de despacho puro (una sola función).
  - Orquestadores livianos (Simulator, Optimizer).
  - Funciones utilitarias para lectura de Excel, generación de plantillas,
    cálculos de hardware, gráficos, etc.

El objetivo es mantener reproducibilidad (sin estado compartido mutable) y
parametrizar grid/zero-export/isla con simples flags.
"""

from .models import Battery, DispatchConfig, DispatchResult, PVSystem, SimResult
from .dispatch import dispatch_day
from .simulator import Simulator
from .optimizer import Optimizer
from .hardware import compute_kwp_seed, generate_kwp_candidates, peak_ratio_ok, select_inverter_and_strings
from .utils import DEFAULT_CONFIG, safe_div, ann_to_month_rate, read_table_from_excel, solar_profile_24, build_7x24_from_excel, ensure_template, load_config_from_excel, _make_battery_obj, _build_profiles, _dispatch_one_day, day_pv_load_flow_export, day_pv_load_flow_zero_export, day_pv_load_flow_island, simulate_monthly_series_dow, optimize_scan, simulate_monte_carlo, plot_npv_scan, plot_autoconsumo_anual, _silverman_bandwidth, _kde_gauss, plot_payback_kde, plot_dia_tipico, plot_cumulated_npv, plot_battery_monthly

__all__ = [
    "Battery",
    "DispatchConfig",
    "DispatchResult",
    "PVSystem",
    "SimResult",
    "dispatch_day",
    "Simulator",
    "Optimizer",
    "compute_kwp_seed",
    "generate_kwp_candidates",
    "peak_ratio_ok",
    "select_inverter_and_strings",
    "DEFAULT_CONFIG",
    "safe_div",
    "ann_to_month_rate",
    "read_table_from_excel",
    "solar_profile_24",
    "build_7x24_from_excel",
    "ensure_template",
    "load_config_from_excel",
    "_make_battery_obj",
    "_build_profiles",
    "_dispatch_one_day",
    "day_pv_load_flow_export",
    "day_pv_load_flow_zero_export",
    "day_pv_load_flow_island",
    "simulate_monthly_series_dow",
    "optimize_scan",
    "simulate_monte_carlo",
    "plot_npv_scan",
    "plot_autoconsumo_anual",
    "_silverman_bandwidth",
    "_kde_gauss",
    "plot_payback_kde",
    "plot_dia_tipico",
    "plot_cumulated_npv",
    "plot_battery_monthly",
]
