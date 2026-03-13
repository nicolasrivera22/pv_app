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


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip())
    return cleaned.strip("_") or "escenario"


def _scenario_root(output_root: Path, scenario: ScenarioRecord) -> Path:
    return output_root / _safe_name(scenario.name)


def _selected_detail(scenario: ScenarioRecord) -> tuple[str, dict]:
    if scenario.scan_result is None:
        raise ValueError(f"El escenario '{scenario.name}' no tiene resultados para exportar.")
    candidate_key = scenario.selected_candidate_key or scenario.scan_result.best_candidate_key
    return candidate_key, scenario.scan_result.candidate_details[candidate_key]


def _write_summary_text(path: Path, scenario: ScenarioRecord, candidate_key: str, detail: dict) -> None:
    summary = detail["summary"]
    lines = [
        f"Escenario: {scenario.name}",
        f"Fuente: {scenario.source_name}",
        f"Candidato: {candidate_key}",
        f"kWp: {float(detail['kWp']):.3f}",
        f"Batería: {detail['battery_name']}",
        f"VPN [COP]: {float(summary['cum_disc_final']):,.0f}",
        f"Payback [años]: {summary['payback_years'] if summary['payback_years'] is not None else 'NaN'}",
        f"Relación pico: {float(detail['peak_ratio']):.3f}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def export_deterministic_artifacts(
    scenario_record: ScenarioRecord,
    output_root: Path = Path("Resultados"),
) -> list[Path]:
    if scenario_record.scan_result is None or scenario_record.dirty:
        raise ValueError(f"El escenario '{scenario_record.name}' necesita una corrida determinística válida antes de exportar.")

    output_dir = _scenario_root(output_root, scenario_record)
    detail_dir = output_dir / "detalle_bateria"
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_dir.mkdir(parents=True, exist_ok=True)

    candidate_key, detail = _selected_detail(scenario_record)
    cfg = scenario_record.config_bundle.config
    monthly = detail["monthly"]
    best_kwp = float(detail["kWp"])
    n_mods = max(1, int(round(1000.0 * best_kwp / float(cfg["P_mod_W"]))))

    scan_df = scenario_record.scan_result.candidates.rename(columns={"NPV_COP": "NPV"})
    npv_png = output_dir / "grafica_vpn_vs_kwp.png"
    plot_npv_scan(
        scan_df=scan_df,
        seed_kwp=float(scenario_record.scan_result.seed_kwp),
        best_kwp=best_kwp,
        out_png=str(npv_png),
        wp_panel=float(cfg["P_mod_W"]),
    )

    autoconsumo_png = output_dir / f"autoconsumo_{best_kwp:.3f}kWp.png"
    plot_autoconsumo_anual(
        monthly,
        str(output_dir),
        autoconsumo_png.name,
        n_mods=n_mods,
        export_allowed=bool(cfg.get("export_allowed", True)),
        best=True,
    )

    dia_tipico_png = output_dir / f"dia_tipico_{best_kwp:.3f}kWp.png"
    plot_dia_tipico(
        kWp=best_kwp,
        inv_sel=detail["inv_sel"],
        cfg=cfg,
        w24=scenario_record.config_bundle.demand_profile_7x24[0],
        s24=scenario_record.config_bundle.solar_profile,
        export_allowed=bool(cfg.get("export_allowed", True)),
        out_path=str(dia_tipico_png),
        out_dir=str(output_dir),
        hsp_month=scenario_record.config_bundle.hsp_month,
        demand_month_factor=scenario_record.config_bundle.demand_month_factor,
        best=True,
        battery=detail["battery"],
        name_png=dia_tipico_png.name,
    )

    plot_cumulated_npv(monthly, best_kwp, str(output_dir), cfg)

    exported_paths = [
        npv_png,
        autoconsumo_png,
        dia_tipico_png,
        output_dir / f"grafica_flujo_acumulado_{best_kwp}kWp.png",
    ]

    battery = detail.get("battery") or {}
    if float(battery.get("nom_kWh", 0) or 0) > 0:
        battery_month = monthly.iloc[:12].copy()
        fig_demand, fig_dest = plot_battery_monthly(battery_month, best_kwp, cfg)
        battery_cover_png = detail_dir / f"bateria_cobertura_{best_kwp:.3f}kWp.png"
        battery_dest_png = detail_dir / f"bateria_destino_{best_kwp:.3f}kWp.png"
        fig_demand.savefig(battery_cover_png, dpi=160)
        fig_dest.savefig(battery_dest_png, dpi=160)
        plt.close(fig_demand)
        plt.close(fig_dest)
        exported_paths.extend([battery_cover_png, battery_dest_png])

    candidates_csv = output_dir / "candidatos_factibles.csv"
    monthly_csv = output_dir / "mensual_candidato_seleccionado.csv"
    summary_txt = output_dir / "resumen_escenario.txt"
    scenario_record.scan_result.candidates.to_csv(candidates_csv, index=False)
    monthly.to_csv(monthly_csv, index=False)
    _write_summary_text(summary_txt, scenario_record, candidate_key, detail)
    exported_paths.extend([candidates_csv, monthly_csv, summary_txt])
    return exported_paths


def _plot_probability_histogram(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    title: str,
    x_label: str,
    highlight_range: tuple[float, float] | None = None,
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


def export_risk_artifacts(
    scenario_record: ScenarioRecord,
    monte_carlo_result: MonteCarloRunResult,
    output_root: Path = Path("Resultados"),
) -> list[Path]:
    output_dir = _scenario_root(output_root, scenario_record) / "riesgo"
    output_dir.mkdir(parents=True, exist_ok=True)

    npv_png = output_dir / "histograma_vpn.png"
    payback_png = output_dir / "histograma_payback.png"
    summary_csv = output_dir / "riesgo_percentiles.csv"
    metadata_txt = output_dir / "riesgo_resumen.txt"

    _plot_probability_histogram(
        monte_carlo_result.views.histograms["NPV_COP"],
        npv_png,
        title="Distribución de VPN",
        x_label="VPN [COP]",
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
                "Banda central del histograma de payback: P10-P90 sobre paybacks finitos.",
            ]
        ),
        encoding="utf-8",
    )

    return [npv_png, payback_png, summary_csv, metadata_txt]
