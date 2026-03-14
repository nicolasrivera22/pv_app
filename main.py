from __future__ import annotations

import multiprocessing
import os

from services.runtime_paths import configure_runtime_environment, user_workbook_path

configure_runtime_environment()

from services import ensure_template, load_config_from_excel, run_scan
from services.result_views import build_kpis

__version__ = "v8.0"
__author__ = "Nicolás Rivera & ChatGPT"
__status__ = "development"


def main() -> None:
    """Legacy CLI entrypoint for the deterministic scan."""
    multiprocessing.freeze_support()
    xlsx_path = os.fspath(user_workbook_path())

    if not os.path.exists(xlsx_path):
        print("No se encontró 'PV_inputs.xlsx'. Generando plantilla compatible...")
        ensure_template(xlsx_path)
        print("Plantilla creada. Edita los valores y vuelve a ejecutar.")
        return

    try:
        bundle = load_config_from_excel(xlsx_path)
    except Exception as exc:
        print(f"Error leyendo Excel: {exc}")
        return

    error_issues = [issue for issue in bundle.issues if issue.level == "error"]
    for issue in bundle.issues:
        print(f"[{issue.level.upper()}] {issue.field}: {issue.message}")
    if error_issues:
        print("Se encontraron errores de validación. Corrige el archivo antes de ejecutar el escaneo.")
        return

    try:
        scan_result = run_scan(bundle)
    except Exception as exc:
        print(f"Error ejecutando el escaneo: {exc}")
        return

    best_detail = scan_result.candidate_details[scan_result.best_candidate_key]
    kpis = build_kpis(best_detail)

    print("[PV App v8] Escaneo determinístico completado")
    print(f"Fuente: {bundle.source_name}")
    print(f"Semilla de kWp: {scan_result.seed_kwp:.2f} kWp")
    print(f"kWp óptimo: {kpis['best_kWp']:.2f} kWp")
    print(f"Batería: {kpis['selected_battery']}")
    print(f"NPV: {kpis['NPV']:.0f} COP")
    print(
        "Payback: "
        + ("n/a" if kpis["payback_years"] is None else f"{float(kpis['payback_years']):.2f} años")
    )
    print(f"Autoconsumo: {100 * float(kpis['self_consumption_ratio']):.2f}%")
    print(f"Candidatos viables: {len(scan_result.candidates)}")


if __name__ == "__main__":
    main()
