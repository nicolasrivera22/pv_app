from __future__ import annotations

import math
import random
from typing import Optional

import numpy as np
import pandas as pd

from .dispatch import dispatch_day
from .models import Battery, DispatchConfig, DispatchResult, PVSystem, SimResult


def _draw_normal(rng, std: float) -> float:
    """Draw a zero-mean normal deviate from either a Python Random or NumPy Generator."""
    if std <= 0:
        return 0.0
    if hasattr(rng, "normal"):
        return float(rng.normal(0.0, std))
    return float(rng.normalvariate(0.0, std))


def _ann_to_month_rate(r_annual: float) -> float:
    """Convierte tasa anual efectiva a mensual equivalente."""
    return (1.0 + r_annual) ** (1.0 / 12.0) - 1.0


def calculate_capex_client(
    cfg: dict,
    kwp: float,
    inv_sel: dict,
    battery_sel: Optional[dict],
    price_per_kwp_cop: Optional[float],
) -> float:
    """
    Calcula el CapEx del cliente.

    Semántica actual:
      - `pricing_mode="variable"` usa el precio por kWp de las tablas.
      - `pricing_mode="total"` usa `price_total_COP`.
      - `include_var_others=True` debe venir reflejado en `price_per_kwp_cop`.
      - `price_others_total` siempre se suma.
      - `include_hw_in_price=True` agrega inversor y batería encima del precio base.
      - `include_hw_in_price=False` asume que el precio base ya incluye esos HW.
    """
    if (str(cfg["pricing_mode"]).lower() == "variable") and (price_per_kwp_cop is not None):
        capex_client = float(price_per_kwp_cop) * float(kwp)
    else:
        capex_client = float(cfg["price_total_COP"])

    if cfg["include_hw_in_price"]:
        capex_client += float(inv_sel["inverter"].get("price_COP", 0.0))
        if (battery_sel is not None) and (float(battery_sel.get("nom_kWh", 0) or 0) > 0):
            capex_client += float(battery_sel.get("price_COP", 0.0))

    capex_client += float(cfg["price_others_total"])
    return capex_client


class Simulator:
    """
    Orquestador liviano: itera días/semanas/meses usando el motor de despacho puro.
    No guarda SoC entre invocaciones (se pasa explícitamente).
    """

    def __init__(
        self,
        dow24: np.ndarray,
        day_w: np.ndarray,
        solar_shape: np.ndarray,
        hsp_month: np.ndarray,
        demand_month_factor: np.ndarray,
        weeks_per_month: float = 4.345,
    ):
        self.dow24 = dow24
        self.day_w = day_w
        self.solar_shape = solar_shape
        self.hsp_month = hsp_month
        self.demand_month_factor = demand_month_factor
        self.weeks_per_month = weeks_per_month

    def _simulate_week(
        self,
        system: PVSystem,
        battery: Optional[Battery],
        dispatch_cfg: DispatchConfig,
        soc0: float,
        pr_month: float,
        month_idx: int,
        E_week: float,
    ) -> tuple[dict, float]:
        """Simula una semana representativa (7 días) devolviendo totales y SoC final."""
        soc = soc0
        totals = dict(
            AC=0.0, EXP=0.0, PV2B=0.0, B2L=0.0, IMP=0.0, CURT=0.0, PVAC=0.0, LOAD=0.0, UNS=0.0
        )

        for d in range(7):
            E_day = E_week * float(self.day_w[d])
            load_profile = np.array(self.dow24[d, :], dtype=float) * E_day
            E_pv_day = system.kwp * pr_month * self.hsp_month[month_idx]
            pv_profile_dc = np.array(self.solar_shape, dtype=float) * E_pv_day

            res: DispatchResult = dispatch_day(
                pv_kw=pv_profile_dc,
                load_kw=load_profile,
                battery=battery,
                config=dispatch_cfg,
                soc0=soc,
            )
            soc = res.soc_end
            totals["AC"] += float((res.pv_to_load + res.batt_to_load).sum())
            totals["EXP"] += float(res.export_energy.sum())
            totals["PV2B"] += float(res.pv_to_batt.sum())
            totals["B2L"] += float(res.batt_to_load.sum())
            totals["IMP"] += float(res.import_energy.sum())
            totals["CURT"] += float(res.curtail.sum())
            totals["PVAC"] += float((res.pv_to_load + res.export_energy).sum())
            totals["LOAD"] += float(load_profile.sum())
            totals["UNS"] += float(res.unserved.sum())
        return totals, soc

    def run(
        self,
        cfg: dict,
        system: PVSystem,
        dispatch_cfg: DispatchConfig,
        inv_sel: dict,
        battery_sel: Optional[dict],
        battery: Optional[Battery],
        years: int,
        price_per_kwp_cop: float,
        rng=None,
        stochastic: bool = False,
    ) -> SimResult:
        """Simula mes a mes durante `years` usando 7x24 + estacionalidad."""
        if rng is None and stochastic:
            rng = random.Random(42)

        island_mode = not dispatch_cfg.allow_import
        export_allowed_eff = dispatch_cfg.allow_export and not island_mode

        g_buy_m = _ann_to_month_rate(cfg["g_tar_buy"])
        g_sell_m = _ann_to_month_rate(cfg["g_tar_sell"])
        r_m = _ann_to_month_rate(cfg["discount_rate"])
        deg_rate = cfg.get("deg_rate", 0.0)

        capex_client = calculate_capex_client(
            cfg=cfg,
            kwp=system.kwp,
            inv_sel=inv_sel,
            battery_sel=battery_sel,
            price_per_kwp_cop=price_per_kwp_cop,
        )

        cum_disc = -capex_client
        payback_month = None

        buy0 = float(cfg["buy_tariff_COP_kWh"])
        sell0 = float(cfg["sell_tariff_COP_kWh"])

        soc_guess = None if battery is None else float(battery.soc_init * battery.usable_kwh)

        rows = []
        for yi in range(int(years)):
            pr_deg_y = (1 - deg_rate) ** yi
            for mi in range(12):
                ym = f"{yi+1:02d}-{mi+1:02d}"

                # Tarifas (crecen mes a mes)
                if yi == 0 and mi == 0:
                    buy_mnth, sell_mnth = buy0, sell0
                else:
                    buy_mnth *= (1 + g_buy_m)
                    sell_mnth *= (1 + g_sell_m)

                if stochastic and cfg.get("mc_buy_std", 0) > 0:
                    buy_mnth *= 1 + _draw_normal(rng, cfg.get("mc_buy_std", 0))
                if stochastic and cfg.get("mc_sell_std", 0) > 0:
                    sell_mnth *= 1 + _draw_normal(rng, cfg.get("mc_sell_std", 0))

                pr_noise = cfg.get("mc_PR_std", 0.0) if stochastic else 0.0
                PR_mon = (
                    system.pr
                    * pr_deg_y
                    * (1 + _draw_normal(rng, pr_noise))
                )
                E_month = float(self.demand_month_factor[mi]) * float(cfg["E_month_kWh"])
                if stochastic and cfg.get("mc_demand_std", 0) > 0:
                    E_month *= 1 + _draw_normal(rng, cfg.get("mc_demand_std", 0))
                E_week = E_month / self.weeks_per_month

                def run_week(soc0: float):
                    return self._simulate_week(
                        system=system,
                        battery=battery,
                        dispatch_cfg=dispatch_cfg,
                        soc0=soc0,
                        pr_month=PR_mon,
                        month_idx=mi,
                        E_week=E_week,
                    )

                # Forzar SoC estacionario semanal (opcional)
                if battery is not None and bool(cfg.get("soc_week_steady", True)):
                    soc0 = float(
                        soc_guess if soc_guess is not None else battery.soc_init * battery.usable_kwh
                    )
                    soc_tol = float(cfg.get("soc_iter_tol_kWh", 1e-3))
                    it_max = int(cfg.get("soc_iter_max", 10))
                    for _ in range(it_max):
                        _, soc_end = run_week(soc0)
                        if abs(soc_end - soc0) <= soc_tol:
                            soc0 = soc_end
                            break
                        soc0 = soc_end
                    soc_guess = soc0
                    week_totals, _ = run_week(soc0)
                else:
                    week_totals, soc_end = run_week(
                        float(
                            soc_guess
                            if soc_guess is not None
                            else (battery.soc_init * battery.usable_kwh if battery else 0.0)
                        )
                    )
                    if battery is not None:
                        soc_guess = soc_end

                # Escalar semana -> mes
                AC_mon = week_totals["AC"] * self.weeks_per_month
                EXP_mon = week_totals["EXP"] * self.weeks_per_month
                PV2B_mon = week_totals["PV2B"] * self.weeks_per_month
                B2L_mon = week_totals["B2L"] * self.weeks_per_month
                IMP_mon = week_totals["IMP"] * self.weeks_per_month
                CURT_mon = week_totals["CURT"] * self.weeks_per_month
                PVAC_mon = week_totals["PVAC"] * self.weeks_per_month
                LOAD_mon = week_totals["LOAD"] * self.weeks_per_month
                UNS_mon = week_totals["UNS"] * self.weeks_per_month

                # Economía
                ahorro_compra = AC_mon * buy_mnth
                util_venta = EXP_mon * (sell_mnth if export_allowed_eff else 0.0)

                neto = ahorro_compra + util_venta
                # descuento mensual
                disc = neto / ((1 + r_m) ** (yi * 12 + mi + 1))
                cum_disc += disc
                if payback_month is None and cum_disc >= 0:
                    payback_month = yi * 12 + mi + 1

                rows.append(
                    dict(
                        Año_mes=ym,
                        Tarifa_Compra_COP_kWh=buy_mnth,
                        Tarifa_Venta_COP_kWh=sell_mnth,
                        Demanda_kWh=LOAD_mon,
                        Generacion_PV_AC_kWh=PVAC_mon,
                        PV_a_Carga_kWh=AC_mon - B2L_mon,
                        Bateria_a_Carga_kWh=B2L_mon,
                        Importacion_Red_kWh=IMP_mon,
                        PV_a_Bateria_kWh=PV2B_mon,
                        Exportacion_kWh=EXP_mon if export_allowed_eff else 0.0,
                        Curtailment_kWh=CURT_mon,
                        Energia_No_Servida_kWh=UNS_mon,
                        Ahorros_Compra_Energia_COP=ahorro_compra,
                        Ingreso_Exportacion_COP=util_venta,
                        Utilidades_en_Venta_COP=util_venta,
                        Ahorro_COP=neto,
                        NPV_COP=cum_disc,
                        Utilidades_Netas_COP=neto,
                    )
                )

        df = pd.DataFrame(rows)
        payback_years = (payback_month / 12.0) if payback_month is not None else None
        summary = dict(
            capex_client=capex_client,
            payback_month=payback_month,
            payback_years=payback_years,
            cum_disc_final=cum_disc,
        )
        return SimResult(monthly=df, summary=summary)
