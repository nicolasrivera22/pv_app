from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .hardware import (
    compute_kwp_seed,
    generate_kwp_candidates,
    peak_ratio_ok,
    select_inverter_and_strings,
)
from .models import Battery, DispatchConfig, PVSystem
from .simulator import Simulator


class Optimizer:
    """Escáner liviano que delega en Simulator y el motor de despacho."""

    def __init__(
        self,
        cfg: dict,
        inv_catalog: pd.DataFrame,
        bat_catalog: pd.DataFrame,
        dow24: np.ndarray,
        day_w: np.ndarray,
        s24: np.ndarray,
        hsp_month: np.ndarray,
        demand_month_factor: np.ndarray,
        export_allowed: bool,
        cop_kwp_table: pd.DataFrame,
        cop_kwp_table_others: pd.DataFrame,
    ):
        self.cfg = cfg
        self.inv_catalog = inv_catalog
        self.bat_catalog = bat_catalog
        self.dow24 = dow24
        self.day_w = day_w
        self.s24 = s24
        self.hsp_month = hsp_month
        self.demand_month_factor = demand_month_factor
        self.export_allowed = export_allowed
        self.cop_kwp_table = cop_kwp_table
        self.cop_kwp_table_others = cop_kwp_table_others
        self.simulator = Simulator(
            dow24=dow24,
            day_w=day_w,
            solar_shape=s24,
            hsp_month=hsp_month,
            demand_month_factor=demand_month_factor,
        )

    def _build_battery(self, batt: Optional[dict]) -> Optional[Battery]:
        """Construye Battery desde dict de catálogo (o None si no aplica)."""
        if batt is None or float(batt.get("nom_kWh", 0) or 0) <= 0:
            return None
        usable = float(batt["nom_kWh"]) * float(self.cfg["bat_DoD"])
        coupling = str(self.cfg.get("bat_coupling", "ac")).strip().lower()
        eta_rt = float(self.cfg["bat_eta_rt"])
        eta = np.sqrt(eta_rt)
        return Battery(
            name=str(batt.get("name", "BAT")),
            usable_kwh=usable,
            max_ch_kw=float(batt.get("max_ch_kW", batt.get("max_kW", 0.0))),
            max_dis_kw=float(batt.get("max_dis_kW", batt.get("max_kW", 0.0))),
            eta_ch=eta,
            eta_dis=eta,
            coupling=coupling,
            soc_init=0.5,
            price_cop=float(batt.get("price_COP", 0.0)),
        )

    def run(self) -> Tuple[dict, pd.DataFrame, float, List[dict]]:
        """Ejecuta el barrido de kWp y baterías, devolviendo óptimo y detalle."""
        cfg = self.cfg
        kwp_list, seed = generate_kwp_candidates(cfg)

        bat0 = dict(name="BAT-0", nom_kWh=0.0, max_kW=0.0, max_ch_kW=0.0, max_dis_kW=0.0, price_COP=0.0)
        if cfg["optimize_battery"] and cfg["include_battery"]:
            bat_options = [bat0] + [r.to_dict() for _, r in self.bat_catalog.iterrows()]
        else:
            bat_options = [bat0]
            if cfg["include_battery"] and cfg.get("battery_name"):
                row = self.bat_catalog[
                    self.bat_catalog["name"].astype(str) == str(cfg["battery_name"])
                ]
                if not row.empty:
                    bat_options = [row.iloc[0].to_dict()]

        module = dict(P_mod_W=cfg["P_mod_W"], Voc25=cfg["Voc25"], Vmp25=cfg["Vmp25"], Isc=cfg["Isc"])

        scan_rows = []
        best = None
        detail = []
        island_mode = bool(cfg.get("island_mode", False))
        export_allowed_eff = self.export_allowed and not island_mode

        for kWp in kwp_list:
            best_batt_value = None
            inv_sel = select_inverter_and_strings(
                kWp=kWp,
                module=module,
                Tmin_C=cfg["Tmin_C"],
                a_Voc_pct=cfg["a_Voc_pct"],
                inv_catalog=self.inv_catalog,
                ILR_target=(cfg["ILR_min"], cfg["ILR_max"]),
            )
            if inv_sel is None:
                scan_rows.append(
                    dict(kWp=kWp, battery="N/A", NPV=np.nan, peak_ratio=np.nan, filtered="no_inverter")
                )
                continue

            ok_peak, ratio = peak_ratio_ok(
                cfg, kWp, inv_sel, self.s24, self.hsp_month, self.demand_month_factor, dow24=self.dow24, day_w=self.day_w
            )
            if not ok_peak:
                scan_rows.append(
                    dict(kWp=kWp, battery="N/A", NPV=np.nan, peak_ratio=ratio, filtered="peak_ratio")
                )
                continue

            price_per_kwp_cop = self.cop_kwp_table.loc[
                (self.cop_kwp_table["MIN"] < kWp) & (self.cop_kwp_table["MAX"] >= kWp),
                "PRECIO_POR_KWP",
            ].values[0]
            if cfg["include_var_others"]:
                price_per_kwp_cop_others = self.cop_kwp_table_others.loc[
                    (self.cop_kwp_table_others["MIN"] < kWp)
                    & (self.cop_kwp_table_others["MAX"] >= kWp),
                    "PRECIO_POR_KWP",
                ].values[0]
            else:
                price_per_kwp_cop_others = 0
            price_per_kwp_cop += price_per_kwp_cop_others

            for batt in bat_options:
                battery = self._build_battery(batt)
                system = PVSystem(
                    kwp=kWp,
                    pr=cfg["PR"],
                    hsp_month=self.hsp_month,
                    solar_shape=self.s24,
                    inverter_ac_kw=inv_sel["inverter"]["AC_kW"],
                    deg_rate=cfg.get("deg_rate", 0.0),
                )
                dispatch_cfg = DispatchConfig(
                    inverter_ac_kw=inv_sel["inverter"]["AC_kW"],
                    allow_import=not island_mode,
                    allow_export=export_allowed_eff,
                    export_limit_kw=(0.0 if not self.export_allowed else None),
                    mode=("island" if island_mode else ("zero_export" if not self.export_allowed else "grid")),
                )

                sim_res = self.simulator.run(
                    cfg=cfg,
                    system=system,
                    dispatch_cfg=dispatch_cfg,
                    inv_sel=inv_sel,
                    battery_sel=batt,
                    battery=battery,
                    years=cfg["years"],
                    price_per_kwp_cop=price_per_kwp_cop,
                )

                npv = sim_res.summary["cum_disc_final"]
                scan_rows.append(
                    dict(
                        kWp=kWp,
                        battery=("None" if (batt is None or batt.get("nom_kWh", 0) == 0) else batt["name"]),
                        NPV=npv,
                        peak_ratio=ratio,
                        filtered="ok",
                        best_battery=False,
                    )
                )
                if (best_batt_value is None) or (npv > best_batt_value):
                    best_batt_value = npv
                    # reset previous rows for this kWp
                    for i_r, r in enumerate(scan_rows):
                        if r["kWp"] == kWp:
                            scan_rows[i_r]["best_battery"] = False
                    scan_rows[-1]["best_battery"] = True

                dict_i = dict(
                    kWp=kWp,
                    inv_sel=inv_sel,
                    battery=batt,
                    df=sim_res.monthly,
                    summary=sim_res.summary,
                    value=npv,
                    peak_ratio=ratio,
                    best_battery=scan_rows[-1]["best_battery"],
                )
                detail.append(dict_i)
                if (best is None) or (npv > best["value"]):
                    best = dict_i

        scan_df = pd.DataFrame(scan_rows)
        return best, scan_df, seed, detail
