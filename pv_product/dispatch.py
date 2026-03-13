from __future__ import annotations

from typing import Optional

import numpy as np

from .models import Battery, DispatchConfig, DispatchResult


def _apply_export_policy(
    export_candidate: float, curtail: float, cfg: DispatchConfig
) -> tuple[float, float]:
    """Aplica flags de export y límite, devolviendo (export, curtail_extra)."""
    if not cfg.allow_export:
        return 0.0, curtail + export_candidate

    export_val = export_candidate
    if cfg.export_limit_kw is not None:
        export_val = min(export_val, max(cfg.export_limit_kw, 0.0))
        curtail += max(export_candidate - export_val, 0.0)
    return export_val, curtail


def dispatch_day(
    pv_kw: np.ndarray,
    load_kw: np.ndarray,
    battery: Optional[Battery],
    config: DispatchConfig,
    soc0: float,
) -> DispatchResult:
    """
    Motor de despacho puro (24h) parametrizable:
      - grid: allow_import=True, allow_export=True
      - zero-export: allow_import=True, allow_export=True, export_limit_kw=0
      - isla: allow_import=False, allow_export=False

    No guarda estado interno; SoC inicial se pasa explícitamente y se devuelve
    SoC final.
    """
    pv_kw = np.asarray(pv_kw, dtype=float)
    load_kw = np.asarray(load_kw, dtype=float)

    pv_to_load = np.zeros(24)
    pv_to_batt = np.zeros(24)
    batt_to_load = np.zeros(24)
    export_energy = np.zeros(24)
    import_energy = np.zeros(24)
    curtail = np.zeros(24)
    unserved = np.zeros(24)

    soc = float(soc0)
    usable = battery.usable_kwh if battery else 0.0

    for h in range(24):
        load = load_kw[h]
        pv_dc = pv_kw[h]
        pv_ac_cap = config.inverter_ac_kw
        pv_ac_nominal = min(pv_dc, pv_ac_cap)

        # 1) PV -> Load
        pv2load = min(pv_ac_nominal, load)
        pv_to_load[h] = pv2load

        # Battery charge
        charge = 0.0
        if battery and usable > 0:
            room = max(0.0, usable - soc)
            coupling = battery.coupling.lower()
            eta_ch = battery.eta_ch
            # Excedentes según acople
            if coupling == "ac":
                ac_excess = max(pv_ac_nominal - pv2load, 0.0)
                charge = min(ac_excess, battery.max_ch_kw, room / max(eta_ch, 1e-9))
                pv_to_batt[h] = charge
                soc += eta_ch * charge
                export_candidate = max(ac_excess - charge, 0.0)
                curtail_candidate = 0.0
            else:  # dc
                dc_excess_after_load = max(pv_dc - pv2load, 0.0)
                charge = min(
                    dc_excess_after_load, battery.max_ch_kw, room / max(eta_ch, 1e-9)
                )
                pv_to_batt[h] = charge
                soc += eta_ch * charge
                inv_headroom = max(pv_ac_cap - pv2load, 0.0)
                export_candidate = min(
                    inv_headroom, max(dc_excess_after_load - charge, 0.0)
                )
                curtail_candidate = max(
                    pv_dc - (pv2load + charge + export_candidate), 0.0
                )
            export_energy[h], curtail_extra = _apply_export_policy(
                export_candidate, curtail_candidate, config
            )
            curtail[h] = curtail_extra
        else:
            export_candidate = max(pv_ac_nominal - pv2load, 0.0)
            export_energy[h], curtail[h] = _apply_export_policy(
                export_candidate, 0.0, config
            )

        # 3) Déficit y descarga
        deficit = max(load - pv2load, 0.0)
        if battery and usable > 0 and deficit > 0:
            pdis_possible = min(battery.max_dis_kw, soc * battery.eta_dis)
            pdis = min(deficit, pdis_possible)
            batt_to_load[h] = pdis
            soc -= pdis / max(battery.eta_dis, 1e-9)
            deficit = max(deficit - pdis, 0.0)

        if deficit > 0:
            if config.allow_import:
                import_energy[h] = deficit
            else:
                unserved[h] = deficit

        # Clamp SoC y chequeo rápido
        soc = max(0.0, min(soc, usable))

    return DispatchResult(
        pv_to_load=pv_to_load,
        pv_to_batt=pv_to_batt,
        batt_to_load=batt_to_load,
        export_energy=export_energy,
        import_energy=import_energy,
        curtail=curtail,
        unserved=unserved,
        soc_end=float(soc),
    )
