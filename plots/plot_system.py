# project/plot_system.py

import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plots.style import apply_style_diagnostic, TECH_COLORS

# Figura de diagnóstico (usada por verify.py) — tamaño 12pt deliberadamente
# mayor que las figuras finales del paper, ver plots/style.py:DIAG_STYLE.
apply_style_diagnostic()

FIG_SIZE  = (7.0, 3.5)
FIG_DPI   = 200

C_PV      = TECH_COLORS["PV"]
C_DC      = TECH_COLORS["DC"]
C_LOAD    = TECH_COLORS["Load"]
C_TRAFO   = TECH_COLORS["Trafo"]
C_REVERSE = TECH_COLORS["Reverse"]
C_LIMIT   = TECH_COLORS["Limit"]


def plot_substation_flow(perfil_pactiva, pen_pv, pen_bess, pen_ev,
                         seed, output_dir, network_name, pen_dc=0):
    horas = list(range(24))
    fig, ax = plt.subplots(figsize=FIG_SIZE, dpi=FIG_DPI)

    ax.plot(horas, perfil_pactiva,
            color=C_LOAD, linewidth=1.4,
            marker="o", markersize=3, markeredgewidth=0,
            label="Substation flow")
    ax.axhline(0, color=C_REVERSE, linestyle="--", linewidth=0.8,
               label="Reverse flow threshold")

    if any(v < 0 for v in perfil_pactiva):
        ax.fill_between(horas, perfil_pactiva, 0,
                        where=[v < 0 for v in perfil_pactiva],
                        color=C_REVERSE, alpha=0.12)
        idx = next(i for i, v in enumerate(perfil_pactiva) if v < 0)
        ax.text(idx + 0.3, min(perfil_pactiva) * 0.6,
                "Reverse flow", color=C_REVERSE, fontsize=6, style="italic")

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour of day", labelpad=3)
    ax.set_ylabel("Active power (kW)", labelpad=3)
    ax.set_title(
        f"Substation power flow 24h - {network_name}  "
        f"[PV={pen_pv}%  DC={pen_dc}%  BESS={pen_bess}%  EV={pen_ev}%  seed={seed}]",
        fontsize=9, pad=4,
    )
    ax.legend(loc="upper right", borderpad=0.4)
    fig.tight_layout(pad=0.5)

    filename = f"flow_PV{pen_pv}_DC{pen_dc}_BESS{pen_bess}_EV{pen_ev}_seed{seed}.png"
    filepath = os.path.join(output_dir, filename)
    fig.savefig(filepath, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {filepath}")


def plot_transformer_loading(perfil_trafo, transformer_mva, pen_pv, pen_bess,
                             pen_ev, seed, output_dir, network_name, pen_dc=0):
    horas = list(range(24))
    fig, ax = plt.subplots(figsize=FIG_SIZE, dpi=FIG_DPI)

    ax.plot(horas, perfil_trafo,
            color=C_TRAFO, linewidth=1.4, marker="o", markersize=3,
            markeredgewidth=0, label="Transformer loading")
    ax.axhline(100, color=C_LIMIT, linestyle=":",  linewidth=0.8, label="100% limit")
    ax.axhline(80,  color=C_LIMIT, linestyle="--", linewidth=0.6,
               alpha=0.5, label="80% threshold")

    if any(v > 100 for v in perfil_trafo):
        ax.fill_between(horas, perfil_trafo, 100,
                        where=[v > 100 for v in perfil_trafo],
                        color=C_TRAFO, alpha=0.15)

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour of day", labelpad=3)
    ax.set_ylabel("Loading (%)", labelpad=3)
    ax.set_title(
        f"Transformer loading 24h - {network_name}  ({transformer_mva} MVA)  "
        f"[PV={pen_pv}%  DC={pen_dc}%  BESS={pen_bess}%  EV={pen_ev}%  seed={seed}]",
        fontsize=9, pad=4,
    )
    ax.legend(loc="upper right", borderpad=0.4)
    fig.tight_layout(pad=0.5)

    filename = f"trafo_PV{pen_pv}_DC{pen_dc}_BESS{pen_bess}_EV{pen_ev}_seed{seed}.png"
    filepath = os.path.join(output_dir, filename)
    fig.savefig(filepath, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {filepath}")


def plot_losses(perfil_losses, pen_pv, pen_bess, pen_ev,
                seed, output_dir, network_name, pen_dc=0):
    horas      = list(range(24))
    max_loss   = max(perfil_losses)
    total_loss = sum(perfil_losses)

    fig, ax = plt.subplots(figsize=FIG_SIZE, dpi=FIG_DPI)

    ax.plot(horas, perfil_losses,
            color=C_LOAD, linewidth=1.4,
            marker="o", markersize=3, markeredgewidth=0,
            label="Active power losses")
    ax.axhline(max_loss, color=C_LIMIT, linestyle=":", linewidth=0.8,
               label=f"Peak: {max_loss:,.0f} kW")
    ax.annotate(
        f"Daily energy losses: {total_loss:,.0f} kWh",
        xy=(0.02, 0.96), xycoords="axes fraction",
        ha="left", va="top", fontsize=6, color=C_LOAD,
    )

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour of day", labelpad=3)
    ax.set_ylabel("Active power losses (kW)", labelpad=3)
    ax.set_title(
        f"Active power losses 24h - {network_name}  "
        f"[PV={pen_pv}%  DC={pen_dc}%  BESS={pen_bess}%  EV={pen_ev}%  seed={seed}]",
        fontsize=9, pad=4,
    )
    ax.legend(loc="upper right", borderpad=0.4)
    fig.tight_layout(pad=0.5)

    filename = f"losses_PV{pen_pv}_DC{pen_dc}_BESS{pen_bess}_EV{pen_ev}_seed{seed}.png"
    filepath = os.path.join(output_dir, filename)
    fig.savefig(filepath, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {filepath}")


def plot_power_decomposition(sim_results, pen_pv, pen_bess, pen_ev,
                              seed, output_dir, network_name, pen_dc=0):
    horas = list(range(24))

    perfil_neto = sim_results.get("perfil_pactiva", [0.0] * 24)
    perfil_pv   = sim_results.get("perfil_pv_gen",  None)
    perfil_dc   = sim_results.get("perfil_dc_load", None)

    fig, ax = plt.subplots(figsize=FIG_SIZE, dpi=FIG_DPI)

    ax.plot(horas, perfil_neto,
            color=C_LOAD, linewidth=1.4,
            marker="o", markersize=3, markeredgewidth=0,
            label="Net substation flow", zorder=4)

    if perfil_pv is not None and any(v > 0 for v in perfil_pv):
        ax.plot(horas, perfil_pv,
                color=C_PV, linewidth=1.1, linestyle="--",
                marker="o", markersize=3, markeredgewidth=0,
                label=f"PV generation  (PV={pen_pv}%)", zorder=3)

    if perfil_dc is not None and any(v > 0 for v in perfil_dc):
        ax.plot(horas, perfil_dc,
                color=C_DC, linewidth=1.1, linestyle="-.",
                marker="o", markersize=3, markeredgewidth=0,
                label=f"DC load  (DC={pen_dc}%)", zorder=3)

    ax.axhline(0, color=C_REVERSE, linestyle=":", linewidth=0.7, alpha=0.7)

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour of day", labelpad=3)
    ax.set_ylabel("Active power (kW)", labelpad=3)
    ax.set_title(
        f"Power decomposition 24h - {network_name}  "
        f"[PV={pen_pv}%  DC={pen_dc}%  BESS={pen_bess}%  EV={pen_ev}%  seed={seed}]",
        fontsize=9, pad=4,
    )
    ax.legend(loc="best", borderpad=0.4)
    fig.tight_layout(pad=0.5)

    filename = f"decomp_PV{pen_pv}_DC{pen_dc}_BESS{pen_bess}_EV{pen_ev}_seed{seed}.png"
    filepath = os.path.join(output_dir, filename)
    fig.savefig(filepath, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {filepath}")


def plot_system_profile(sim_results, transformer_mva, pen_pv, pen_bess,
                        pen_ev, seed, output_dir, network_name, pen_dc=0):
    os.makedirs(output_dir, exist_ok=True)

    plot_substation_flow(
        sim_results["perfil_pactiva"],
        pen_pv, pen_bess, pen_ev, seed, output_dir, network_name, pen_dc=pen_dc,
    )
    plot_transformer_loading(
        sim_results["perfil_trafo"], transformer_mva,
        pen_pv, pen_bess, pen_ev, seed, output_dir, network_name, pen_dc=pen_dc,
    )
    plot_losses(
        sim_results["perfil_losses"],
        pen_pv, pen_bess, pen_ev, seed, output_dir, network_name, pen_dc=pen_dc,
    )
    plot_power_decomposition(
        sim_results,
        pen_pv, pen_bess, pen_ev, seed, output_dir, network_name, pen_dc=pen_dc,
    )
