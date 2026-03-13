from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PVSystem:
    """Inputs fijos del sistema FV (sin estado mutable)."""

    kwp: float
    pr: float
    hsp_month: np.ndarray
    solar_shape: np.ndarray  # 24 values sum to 1
    inverter_ac_kw: float
    deg_rate: float = 0.0
    name: str = "PV"


@dataclass(frozen=True)
class Battery:
    """Parámetros de batería (no guarda SoC interno)."""

    name: str
    usable_kwh: float
    max_ch_kw: float
    max_dis_kw: float
    eta_ch: float
    eta_dis: float
    coupling: str = "ac"  # ac | dc
    soc_init: float = 0.5
    price_cop: float = 0.0


@dataclass(frozen=True)
class DispatchConfig:
    """Configuración de despacho (grid/zero-export/isla via flags)."""

    inverter_ac_kw: float
    allow_import: bool = True
    allow_export: bool = True
    export_limit_kw: Optional[float] = None  # 0 -> zero-export
    mode: str = "grid"


@dataclass(frozen=True)
class DispatchResult:
    pv_to_load: np.ndarray
    pv_to_batt: np.ndarray
    batt_to_load: np.ndarray
    export_energy: np.ndarray
    import_energy: np.ndarray
    curtail: np.ndarray
    unserved: np.ndarray
    soc_end: float

    def day_totals(self) -> dict:
        return {
            "PV_to_load_day": float(self.pv_to_load.sum()),
            "PV_to_batt_day": float(self.pv_to_batt.sum()),
            "Batt_to_load_day": float(self.batt_to_load.sum()),
            "Export_day": float(self.export_energy.sum()),
            "Import_day": float(self.import_energy.sum()),
            "Curtail_day": float(self.curtail.sum()),
            "Unserved_day": float(self.unserved.sum()),
            "AC_day": float((self.pv_to_load + self.batt_to_load).sum()),
        }


@dataclass(frozen=True)
class SimResult:
    monthly: pd.DataFrame
    summary: dict
