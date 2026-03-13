__version__ = "v7.1"
__author__ = "Nicolás Rivera & ChatGPT"
__status__ = "development"

"""
PV App v7 (Excel-driven, 7x24 DOW-aware)
----------------------------------------
Flujo principal:
  1) Leer configuración/perfiles desde Excel (o crear plantilla).
  2) Escanear combinaciones kWp/batería y elegir el candidato óptimo.
  3) Generar archivos y gráficas con los resultados del escaneo.
  4) Correr Monte Carlo sobre el candidato elegido y guardar el resumen.
"""

import os
import shutil
import sys
import matplotlib.pyplot as plt
import numpy as np
from pv_product import *


def main() -> None:
    """
    Orquesta la lectura de inputs, la optimización y la generación de resultados.
    Pensado para alguien familiarizado con energía/PV: cada paso está comentado
    con la lógica del flujo, no con detalles de Python.
    """
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    xlsx_path = os.path.join(exe_dir, "PV_inputs.xlsx")

    if not os.path.exists(xlsx_path):
        print("No se encontró 'PV_inputs.xlsx'. Generando PLANTILLA...")
        ensure_template(xlsx_path)
        print("Plantilla creada. Edita los valores y vuelve a ejecutar.")
        return

    try:
        (
            cfg,
            s24,
            hsp_month,
            inv_df,
            bat_df,
            dow24,
            day_w,
            demand_month_factor,
            cop_kwp_table,
            cop_kwp_table_others,
        ) = load_config_from_excel(xlsx_path)
    except Exception as e:
        print("Error leyendo Excel:", e)
        return

    export_allowed = bool(cfg["export_allowed"])

    # 1) Leer el Excel y lanzar el escaneo:
    #    - Se prueban distintos tamaños de campo FV (kWp) y opciones de batería.
    #    - El motor de despacho calcula energías y NPV para cada combinación.
    best, scan_df, seed_kwp, detail = optimize_scan(
        cfg,
        inv_df,
        bat_df,
        dow24,
        day_w,
        s24,
        hsp_month,
        export_allowed,
        demand_month_factor,
        cop_kwp_table,
        cop_kwp_table_others,
    )
    if best is None:
        print("No se encontró combinación viable. Ajusta límites o catálogos.")
        return
    kWp_opt = best["kWp"]
    inv_sel = best["inv_sel"]
    batt = best["battery"]
    summ = best["summary"]

    # 2) Preparar carpetas de salida limpias:
    #    - Se borran resultados anteriores para evitar mezclas.
    #    - Se crean subcarpetas para cada tipo de gráfico/tabla.
    out_dir = os.path.join(exe_dir, "Resultados")
    out_dir_i = os.path.join(out_dir, "autoconsumo_anual")
    out_dir_ii = os.path.join(out_dir, "dia_tipico")
    out_dir_iii = os.path.join(out_dir, "valor_presente_neto_proyeccion")
    out_dir_iv = os.path.join(out_dir, "battery_monthly")
    for dir_path in [out_dir, out_dir_i, out_dir_ii, out_dir_iii, out_dir_iv]:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        os.makedirs(dir_path)
        os.makedirs(os.path.join(dir_path, "detalle_bateria"))

    # 3) Guardar escaneo y gráficos base:
    #    - CSV con NPV por candidato.
    #    - Gráficas de autoconsumo, día típico y flujo NPV acumulado por opción.
    scan_df.to_csv(os.path.join(out_dir, "resumen_valor_presente_neto.csv"), index=False)
    plot_npv_scan(scan_df, seed_kwp, best["kWp"], os.path.join(out_dir, "chart_npv_vs_kWp.png"), cfg["P_mod_W"])

    for candidate in detail:
        plot_autoconsumo_anual(
            df=candidate["df"],
            out_dir=out_dir_i,
            name_png=f"autoconsumo_{candidate['kWp']}kWp_batt_{candidate['battery']['name']}.png",
            export_allowed=export_allowed,
            n_mods=int(1e3 * candidate["kWp"] / cfg["P_mod_W"]),
            best=candidate["best_battery"],
        )
        plot_dia_tipico(
            kWp=candidate["kWp"],
            inv_sel=candidate["inv_sel"],
            cfg=cfg,
            w24=dow24[0],
            s24=s24,
            export_allowed=cfg["export_allowed"],
            out_path=os.path.join(out_dir_ii, f"dia_tipico_{candidate['kWp']}kWp.png"),
            hsp_month=hsp_month,
            month_for_plot=None,
            year_for_plot=0,
            out_dir=out_dir_ii,
            demand_month_factor=demand_month_factor,
            best=candidate["best_battery"],
            battery=candidate["battery"],
            name_png=f"dia_tipico_{candidate['kWp']}kWp_batt_{candidate['battery']['name']}.png",
        )
        plot_cumulated_npv(df=candidate["df"], kWp=candidate["kWp"], out_dir=out_dir_iii, cfg=cfg)
        candidate["df"].to_csv(os.path.join(out_dir_iii, f"proyeccion_{candidate['kWp']}kWp.csv"), index=False)

        first_year_df = candidate["df"].iloc[:12].copy()
        if {"PV_a_Carga_kWh", "Bateria_a_Carga_kWh", "Importacion_Red_kWh"}.issubset(first_year_df.columns):
            fig_cov, fig_dest = plot_battery_monthly(first_year_df, kWp=candidate["kWp"], cfg=cfg)
            fig_cov.savefig(os.path.join(out_dir_iv, f"bateria_carga_{candidate['kWp']}kWp.png"), dpi=160)
            fig_dest.savefig(os.path.join(out_dir_iv, f"bateria_destino_pv_{candidate['kWp']}kWp.png"), dpi=160)
            plt.close(fig_cov)
            plt.close(fig_dest)

    # 4) Monte Carlo sobre el óptimo (o kWp manual si está configurado):
    #    - Se perturban PR/tarifas/demanda para ver variabilidad en payback.
    #    - Se genera un KDE con cuantiles P5-P95.
    arr, vals = simulate_monte_carlo(
        cfg=cfg,
        inv_df=inv_df,
        inv_sel=inv_sel,
        kWp_opt=kWp_opt,
        best=best,
        bat_df=bat_df,
        cop_kwp_table=cop_kwp_table,
        cop_kwp_table_others=cop_kwp_table_others,
        export_allowed=export_allowed,
        dow24=dow24,
        s24=s24,
        day_w=day_w,
        hsp_month=hsp_month,
        demand_month_factor=demand_month_factor,
    )
    if np.isfinite(arr).sum() > 0: # Al menos un resultado válido
        plot_payback_kde(
            vals,
            outfile="chart_payback_kde.png",
            out_dir=out_dir,
            title="Distribución de Payback (Monte Carlo) – KDE con cuantiles",
        )

    p5, p10, p50, p90, p95 = np.nanpercentile(arr, [5, 10, 50, 90, 95]).tolist() # Cuantiles clave

    resumen = f"""
    [PV App v7]  export_allowed = {export_allowed}
    kWp semilla (energía o manual): ~{compute_kwp_seed(cfg):.2f} kWp
    kWp óptimo (módulo-step): {kWp_opt:.2f} kWp   |   peak_ratio≈{best.get('peak_ratio', float('nan')):.2f}
    Batería óptima: {('Ninguna' if (batt is None or batt.get('nom_kWh',0)==0) else batt['name'])}
    Inversor: {inv_sel['inverter']['name']} ({inv_sel['inverter']['AC_kW']} kW)  ILR={inv_sel['ILR']:.2f}
    Strings: Ns={inv_sel['Ns']}  Np={inv_sel['Np']}  N_mod={inv_sel['N_mod']}
    Payback (base) ≈ {summ['payback_years']} años
    Monte Carlo (kWp {'manual' if bool(cfg.get('mc_use_manual_kWp', False)) else 'óptimo'}) | P5={p5:.2f}, P50={p50:.2f}, P95={p95:.2f} años
    CapEx cliente (Año 0): {summ['capex_client']:.0f} COP
    """
    with open(os.path.join(out_dir, "resumen_optimizacion.txt"), "w", encoding="utf-8") as f:
        f.write(resumen.strip())
    print(resumen)


if __name__ == "__main__":
    main()
