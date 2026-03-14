from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from pv_product.utils import (
    plot_autoconsumo_anual,
    plot_battery_monthly,
    plot_cumulated_npv,
    plot_dia_tipico,
    plot_npv_scan,
)

from .types import MonteCarloRunResult, ScenarioRecord

LEGACY_DETERMINISTIC_TOP_LEVEL = (
    "resumen_valor_presente_neto.csv",
    "resumen_optimizacion.txt",
    "chart_npv_vs_kWp.png",
    "autoconsumo_anual",
    "dia_tipico",
    "valor_presente_neto_proyeccion",
    "battery_monthly",
)

LEGACY_RISK_FILES = (
    "chart_payback_kde.png",
    "histograma_vpn.png",
    "histograma_payback.png",
    "riesgo_percentiles.csv",
    "riesgo_resumen.txt",
)


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip())
    return cleaned.strip("_") or "escenario"


def _resolve_output_root(output_root: Path) -> Path:
    root = Path(output_root).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _scenario_root(output_root: Path, scenario: ScenarioRecord) -> Path:
    return output_root / _safe_name(scenario.name)


def legacy_deterministic_export_manifest() -> tuple[str, ...]:
    return LEGACY_DETERMINISTIC_TOP_LEVEL


def legacy_risk_export_manifest() -> tuple[str, ...]:
    return LEGACY_RISK_FILES


def _selected_detail(scenario: ScenarioRecord) -> tuple[str, dict]:
    if scenario.scan_result is None:
        raise ValueError(f"El escenario '{scenario.name}' no tiene resultados para exportar.")
    candidate_key = scenario.selected_candidate_key or scenario.scan_result.best_candidate_key
    return candidate_key, scenario.scan_result.candidate_details[candidate_key]


def _ordered_details(scenario: ScenarioRecord) -> list[dict]:
    if scenario.scan_result is None:
        return []
    return sorted(scenario.scan_result.candidate_details.values(), key=lambda detail: int(detail["scan_order"]))


def _ensure_legacy_directories(output_dir: Path) -> dict[str, Path]:
    directories = {
        "root": output_dir,
        "autoconsumo_anual": output_dir / "autoconsumo_anual",
        "dia_tipico": output_dir / "dia_tipico",
        "valor_presente_neto_proyeccion": output_dir / "valor_presente_neto_proyeccion",
        "battery_monthly": output_dir / "battery_monthly",
    }
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=True)
    for key in ("autoconsumo_anual", "dia_tipico", "valor_presente_neto_proyeccion", "battery_monthly"):
        (directories[key] / "detalle_bateria").mkdir(parents=True, exist_ok=True)
    return directories


def _legacy_scan_frame(scenario: ScenarioRecord) -> pd.DataFrame:
    assert scenario.scan_result is not None
    frame = scenario.scan_result.candidates.copy()
    frame["filtered"] = "ok"
    frame["best_battery"] = frame["best_battery_for_kwp"].astype(bool)
    frame = frame.rename(columns={"NPV_COP": "NPV"})
    return frame[["kWp", "battery", "NPV", "peak_ratio", "filtered", "best_battery"]].copy()


def _write_summary_text(path: Path, scenario: ScenarioRecord, candidate_key: str, detail: dict) -> None:
    summary = detail["summary"]
    lines = [
        f"Escenario: {scenario.name}",
        f"Fuente: {scenario.source_name}",
        f"Candidato seleccionado: {candidate_key}",
        f"kWp seleccionado: {float(detail['kWp']):.3f}",
        f"Batería seleccionada: {detail['battery_name']}",
        f"Inversor: {detail['inv_sel']['inverter']['name']} ({detail['inv_sel']['inverter']['AC_kW']} kW)",
        f"VPN [COP]: {float(summary['cum_disc_final']):,.0f}",
        f"Payback [años]: {summary['payback_years'] if summary['payback_years'] is not None else 'NaN'}",
        f"Relación pico: {float(detail['peak_ratio']):.3f}",
        "Monte Carlo: exporta los artefactos desde la página de Riesgo para incluir la distribución estocástica.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _plot_probability_histogram(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
    x_label: str,
    highlight_range: tuple[float, float] | None = None,
    density_frame: pd.DataFrame | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    if frame.empty:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", transform=ax.transAxes)
    else:
        widths = frame["bin_right"] - frame["bin_left"]
        colors = []
        left, right = highlight_range if highlight_range is not None else (math.inf, -math.inf)
        for _, row in frame.iterrows():
            overlaps = not (row["bin_right"] < left or row["bin_left"] > right)
            colors.append("#0f766e" if overlaps else "#94a3b8")
        ax.bar(frame["bin_left"], frame["probability"], width=widths, align="edge", color=colors, edgecolor="white")
        if density_frame is not None and not density_frame.empty:
            width = float(widths.mean()) if len(widths) else 1.0
            ax.plot(density_frame["value"], density_frame["density"] * width, color="#0f172a", linewidth=2)
        if highlight_range is not None and math.isfinite(left) and math.isfinite(right):
            ax.axvspan(left, right, color="#0f766e", alpha=0.12)
            ax.axvline(left, color="#0f766e", linestyle="--", linewidth=1.0)
            ax.axvline(right, color="#0f766e", linestyle="--", linewidth=1.0)
    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel("Probabilidad")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def _plot_payback_kde(
    density_frame: pd.DataFrame,
    output_path: Path,
    *,
    highlight_range: tuple[float, float] | None = None,
    title: str = "Distribución de Payback (Monte Carlo)",
) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    if density_frame.empty:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", transform=ax.transAxes)
    else:
        ax.plot(density_frame["value"], density_frame["density"] * 100.0, color="#0f172a", linewidth=2.25)
        if highlight_range is not None:
            left, right = highlight_range
            mask = (density_frame["value"] >= left) & (density_frame["value"] <= right)
            ax.fill_between(
                density_frame.loc[mask, "value"],
                0,
                density_frame.loc[mask, "density"] * 100.0,
                color="#0f766e",
                alpha=0.18,
            )
            ax.axvline(left, color="#0f766e", linestyle="--", linewidth=1.0)
            ax.axvline(right, color="#0f766e", linestyle="--", linewidth=1.0)
    ax.set_title(title)
    ax.set_xlabel("Payback (años)")
    ax.set_ylabel("Densidad (%)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def export_deterministic_artifacts(
    scenario_record: ScenarioRecord,
    output_root: Path = Path("Resultados"),
) -> list[Path]:
    if scenario_record.scan_result is None or scenario_record.dirty:
        raise ValueError(f"El escenario '{scenario_record.name}' necesita una corrida determinística válida antes de exportar.")

    output_dir = _scenario_root(_resolve_output_root(output_root), scenario_record)
    directories = _ensure_legacy_directories(output_dir)
    candidate_key, selected_detail = _selected_detail(scenario_record)
    cfg = scenario_record.config_bundle.config
    export_allowed = bool(cfg.get("export_allowed", True))

    scan_df = _legacy_scan_frame(scenario_record)
    summary_csv = output_dir / "resumen_valor_presente_neto.csv"
    summary_txt = output_dir / "resumen_optimizacion.txt"
    chart_png = output_dir / "chart_npv_vs_kWp.png"
    scan_df.to_csv(summary_csv, index=False)
    plot_npv_scan(
        scan_df=scan_df,
        seed_kwp=float(scenario_record.scan_result.seed_kwp),
        best_kwp=float(scenario_record.scan_result.candidates.sort_values(["NPV_COP", "scan_order"], ascending=[False, True], kind="mergesort").iloc[0]["kWp"]),
        out_png=str(chart_png),
        wp_panel=float(cfg["P_mod_W"]),
    )
    _write_summary_text(summary_txt, scenario_record, candidate_key, selected_detail)

    exported_paths: list[Path] = [summary_csv, summary_txt, chart_png]

    for detail in _ordered_details(scenario_record):
        monthly = detail["monthly"]
        k_wp = float(detail["kWp"])
        battery_name = str(detail["battery_name"])
        battery = detail["battery"] or {"name": battery_name}
        n_mods = max(1, int(round(1000.0 * k_wp / float(cfg["P_mod_W"]))))

        autoconsumo_name = f"autoconsumo_{k_wp}kWp_batt_{battery_name}.png"
        plot_autoconsumo_anual(
            df=monthly,
            out_dir=str(directories["autoconsumo_anual"]),
            name_png=autoconsumo_name,
            n_mods=n_mods,
            export_allowed=export_allowed,
            best=bool(detail["best_battery"]),
        )
        exported_paths.append(directories["autoconsumo_anual"] / "detalle_bateria" / autoconsumo_name)
        if bool(detail["best_battery"]):
            exported_paths.append(directories["autoconsumo_anual"] / autoconsumo_name)

        dia_tipico_name = f"dia_tipico_{k_wp}kWp_batt_{battery_name}.png"
        plot_dia_tipico(
            kWp=k_wp,
            inv_sel=detail["inv_sel"],
            cfg=cfg,
            w24=scenario_record.config_bundle.demand_profile_7x24[0],
            s24=scenario_record.config_bundle.solar_profile,
            export_allowed=export_allowed,
            out_path=str(directories["dia_tipico"] / f"dia_tipico_{k_wp}kWp.png"),
            out_dir=str(directories["dia_tipico"]),
            hsp_month=scenario_record.config_bundle.hsp_month,
            demand_month_factor=scenario_record.config_bundle.demand_month_factor,
            best=bool(detail["best_battery"]),
            battery=battery,
            name_png=dia_tipico_name,
        )
        exported_paths.extend(
            [
                directories["dia_tipico"] / f"dia_tipico_{k_wp}kWp.csv",
                directories["dia_tipico"] / "detalle_bateria" / dia_tipico_name,
            ]
        )
        if bool(detail["best_battery"]):
            exported_paths.append(directories["dia_tipico"] / f"dia_tipico_{k_wp}kWp.png")

        plot_cumulated_npv(monthly, k_wp, str(directories["valor_presente_neto_proyeccion"]), cfg)
        projection_csv = directories["valor_presente_neto_proyeccion"] / f"proyeccion_{k_wp}kWp.csv"
        monthly.to_csv(projection_csv, index=False)
        exported_paths.extend(
            [
                directories["valor_presente_neto_proyeccion"] / f"grafica_flujo_acumulado_{k_wp}kWp.png",
                projection_csv,
            ]
        )

        first_year_df = monthly.iloc[:12].copy()
        if {"PV_a_Carga_kWh", "Bateria_a_Carga_kWh", "Importacion_Red_kWh"}.issubset(first_year_df.columns):
            fig_cov, fig_dest = plot_battery_monthly(first_year_df, kWp=k_wp, cfg=cfg)
            battery_cover_png = directories["battery_monthly"] / f"bateria_carga_{k_wp}kWp.png"
            battery_dest_png = directories["battery_monthly"] / f"bateria_destino_pv_{k_wp}kWp.png"
            fig_cov.savefig(battery_cover_png, dpi=160)
            fig_dest.savefig(battery_dest_png, dpi=160)
            plt.close(fig_cov)
            plt.close(fig_dest)
            exported_paths.extend([battery_cover_png, battery_dest_png])

    selected_monthly_csv = output_dir / "mensual_candidato_seleccionado.csv"
    candidates_csv = output_dir / "candidatos_factibles.csv"
    current_summary_txt = output_dir / "resumen_escenario.txt"
    selected_detail["monthly"].to_csv(selected_monthly_csv, index=False)
    scenario_record.scan_result.candidates.to_csv(candidates_csv, index=False)
    _write_summary_text(current_summary_txt, scenario_record, candidate_key, selected_detail)
    exported_paths.extend([selected_monthly_csv, candidates_csv, current_summary_txt])
    return exported_paths


def export_risk_artifacts(
    scenario_record: ScenarioRecord,
    monte_carlo_result: MonteCarloRunResult,
    output_root: Path = Path("Resultados"),
) -> list[Path]:
    output_dir = _scenario_root(_resolve_output_root(output_root), scenario_record) / "riesgo"
    output_dir.mkdir(parents=True, exist_ok=True)

    npv_png = output_dir / "histograma_vpn.png"
    payback_png = output_dir / "histograma_payback.png"
    payback_kde_png = output_dir / "chart_payback_kde.png"
    summary_csv = output_dir / "riesgo_percentiles.csv"
    metadata_txt = output_dir / "riesgo_resumen.txt"

    _plot_probability_histogram(
        monte_carlo_result.views.histograms["NPV_COP"],
        npv_png,
        title="Distribución de VPN",
        x_label="VPN [COP]",
        density_frame=monte_carlo_result.views.densities.get("NPV_COP"),
    )
    payback = monte_carlo_result.summary.payback_years
    highlight = None
    if payback.p10 is not None and payback.p90 is not None:
        highlight = (float(payback.p10), float(payback.p90))
    _plot_probability_histogram(
        monte_carlo_result.views.histograms["payback_years"],
        payback_png,
        title="Distribución de Payback",
        x_label="Payback [años]",
        highlight_range=highlight,
        density_frame=monte_carlo_result.views.densities.get("payback_years"),
    )
    _plot_payback_kde(
        monte_carlo_result.views.densities.get("payback_years", pd.DataFrame()),
        payback_kde_png,
        highlight_range=highlight,
        title="Distribución de Payback (Monte Carlo)",
    )

    monte_carlo_result.views.percentile_table.to_csv(summary_csv, index=False)
    metadata_txt.write_text(
        "\n".join(
            [
                f"Escenario: {scenario_record.name}",
                f"Candidato: {monte_carlo_result.selected_candidate_key}",
                f"kWp: {monte_carlo_result.selected_kWp:.3f}",
                f"Batería: {monte_carlo_result.selected_battery}",
                f"Simulaciones: {monte_carlo_result.n_simulations}",
                f"Semilla: {monte_carlo_result.seed}",
                "Curva suave de payback: KDE gaussiana basada en paybacks finitos.",
                "Banda resaltada: P10-P90 sobre paybacks finitos.",
            ]
        ),
        encoding="utf-8",
    )

    return [npv_png, payback_png, payback_kde_png, summary_csv, metadata_txt]
