import math
from math import ceil, floor
from typing import Dict, List, Tuple

import numpy as np

from .panel_technology import resolve_generation_pr


def safe_div(a, b, default=0.0):
    """Divide con protección contra cero/nulos."""
    return a / b if (b is not None and abs(b) > 1e-12) else default


def string_checks(module, inverter, Tmin_C, a_Voc_pct, Ns, Np):
    """Valida Voc/Vmp/Is de strings vs inversor para un número dado de Ns/Np."""
    Voc25 = module["Voc25"]
    Vmp25 = module["Vmp25"]
    Isc = module["Isc"]
    Voc_Tmin = Voc25 * (1 - (a_Voc_pct / 100.0) * (25 - Tmin_C))
    Voc_string = Voc_Tmin * Ns
    ok_voc = Voc_string < inverter["Vdc_max"]
    Vmp_string = Vmp25 * Ns
    ok_mppt = (Vmp_string >= inverter["Vmppt_min"]) and (
        Vmp_string <= inverter["Vmppt_max"]
    )
    strings_total = Np
    strings_per_mppt = ceil(strings_total / inverter["n_mppt"])
    I_mppt = Isc * strings_per_mppt
    ok_current = I_mppt <= inverter["Imax_mppt"]
    details = dict(
        Voc_string=Voc_string,
        Vmp_string=Vmp_string,
        I_mppt=I_mppt,
        strings_per_mppt=strings_per_mppt,
    )
    return ok_voc, ok_mppt, ok_current, details


def select_inverter_and_strings(
    kWp, module, Tmin_C, a_Voc_pct, inv_catalog, ILR_target=(1.1, 1.4)
):
    """Selecciona inversor y strings viables priorizando ILR cercano al target."""
    N_mod = max(1, ceil(kWp * 1000.0 / module["P_mod_W"]))
    cand = []
    mid = 0.5 * (ILR_target[0] + ILR_target[1])
    for _, inv in inv_catalog.iterrows():
        invd = inv.to_dict()
        ILR = safe_div(kWp, invd["AC_kW"], 0.0)
        cand.append((abs(mid - ILR), invd, ILR))
    cand.sort(key=lambda x: x[0])
    for _, inv, ILR in cand[:6]:
        Ns_min = max(1, ceil(inv["Vmppt_min"] / module["Vmp25"]))
        Ns_max_mppt = floor(inv["Vmppt_max"] / module["Vmp25"])
        Voc_Tmin = module["Voc25"] * (1 - (a_Voc_pct / 100.0) * (25 - Tmin_C))
        Ns_max_voc = floor(inv["Vdc_max"] / Voc_Tmin)
        Ns_max = min(Ns_max_mppt, Ns_max_voc, 30)
        for Ns in range(Ns_min, max(Ns_min, Ns_max) + 1):
            Np = ceil(N_mod / Ns) if Ns > 0 else 0
            ok_voc, ok_mppt, ok_curr, details = string_checks(
                module, inv, Tmin_C, a_Voc_pct, Ns, Np
            )
            if ok_voc and ok_mppt and ok_curr and Ns > 0 and Np > 0:
                return dict(
                    inverter=inv,
                    Ns=Ns,
                    Np=Np,
                    N_mod=N_mod,
                    ILR=ILR,
                    checks=details,
                )
    return None


def compute_kwp_seed(cfg) -> float:
    """Calcula semilla de kWp a partir de energía mensual o valor manual."""
    if str(cfg.get("kWp_seed_mode", "auto")).lower() == "manual":
        seed = float(cfg.get("kWp_seed_manual_kWp", 10.0))
    else:
        Dm = 30.0
        pr_eff = resolve_generation_pr(cfg["PR"], cfg.get("panel_technology_mode"))
        seed = cfg["E_month_kWh"] / (pr_eff * cfg["HSP"] * Dm)
    seed = math.ceil(1e3 * seed / cfg["P_mod_W"]) * cfg["P_mod_W"] / 1e3
    return max(seed, 0.1)


def generate_kwp_candidates(cfg) -> Tuple[List[float], float]:
    """Genera lista de candidatos kWp en pasos de módulo alrededor de la semilla."""
    P_mod_W = cfg["P_mod_W"]
    seed = compute_kwp_seed(cfg)
    n_seed = max(1, int(round(seed * 1000.0 / P_mod_W)))
    span = int(cfg.get("modules_span_each_side", 40))

    n_min = max(1, n_seed - span)
    n_max = n_seed + span

    if "kWp_min" in cfg and "kWp_max" in cfg:
        n_min = max(n_min, int(math.ceil(cfg["kWp_min"] * 1000.0 / P_mod_W)))
        n_max = min(n_max, int(math.floor(cfg["kWp_max"] * 1000.0 / P_mod_W)))

    candidates = [n * P_mod_W / 1000.0 for n in range(n_min, n_max + 1)]
    return candidates, seed


def peak_ratio_ok(
    cfg,
    kWp,
    inv_sel,
    s24,
    hsp_month,
    demand_month_factor,
    w24=None,
    dow24=None,
    day_w=None,
):
    """
    Compara pico FV vs pico de carga (7x24 si está disponible).
    limit_peak_basis: "weighted_mean" | "max" | "weekday" | "p95"
    """
    mode = str(cfg.get("limit_peak_month_mode", "max")).lower()
    if mode.lower() == "fixed":
        m = int(cfg.get("limit_peak_month_fixed", 1)) - 1
        m = max(0, min(11, m))
    else:
        m = int(np.argmax(demand_month_factor))
    year = int(cfg.get("limit_peak_year", 0))
    # Panel technology is a yield-only assumption in v1. It changes resolved
    # PR, but does not alter module wattage, layout, or hardware constraints.
    generation_pr = resolve_generation_pr(cfg["PR"], cfg.get("panel_technology_mode"))
    PR_eff = generation_pr * ((1 - cfg.get("deg_rate", 0.0)) ** year)

    E_pv_day = kWp * PR_eff * hsp_month[m]
    P_pv_dc = np.array(s24) * E_pv_day * demand_month_factor[m]
    P_AC = float(inv_sel["inverter"]["AC_kW"])
    P_pv_ac = np.minimum(P_pv_dc, P_AC)
    pv_peak = float(np.max(P_pv_ac)) if P_pv_ac.size else 0.0

    basis = str(cfg.get("limit_peak_basis", "weighted_mean")).lower()

    if (dow24 is not None) and (day_w is not None):
        weeks_per_month = 4.345
        E_week = cfg["E_month_kWh"] / weeks_per_month
        peaks = []
        for d in range(7):
            E_day_d = E_week * float(day_w[d])
            P_dem_d = np.array(dow24[d, :]) * E_day_d
            peaks.append(float(np.max(P_dem_d)))
        peaks = np.array(peaks, dtype=float)
        if basis.lower() == "max":
            load_peak = float(np.max(peaks))
        elif basis.lower() == "weekday":
            wk = np.mean(peaks[:5])
            we = np.mean(peaks[5:]) if peaks.size >= 7 else wk
            load_peak = (5 * wk + 2 * we) / 7.0
        elif basis.lower() == "p95":
            load_peak = float(np.percentile(peaks, 95))
        else:
            load_peak = float(np.dot(day_w, peaks))  # weighted_mean
    else:
        E_day = cfg["E_month_kWh"] / 30.0
        P_dem = np.array(w24) * E_day
        load_peak = float(np.max(P_dem))

    ratio = (pv_peak / load_peak) if load_peak > 1e-12 else float("inf")
    if not bool(cfg.get("limit_peak_ratio_enable", False)):
        return True, ratio
    return (ratio <= float(cfg.get("limit_peak_ratio", 0.0)) + 1e-9), ratio
