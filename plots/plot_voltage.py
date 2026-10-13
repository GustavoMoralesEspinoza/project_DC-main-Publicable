# project/plot_voltage.py

import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

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


def plot_voltage_heatmap(perfil_tension_barras, pen_pv, pen_bess, pen_ev,
                         seed, output_dir, network_name, pen_dc=0):
    buses = list(perfil_tension_barras.keys())
    matrix = np.array([perfil_tension_barras[b] for b in buses], dtype=float)

    order = np.argsort(matrix.mean(axis=1))
    matrix = matrix[order]
    buses_sorted = [buses[i] for i in order]

    fig, ax = plt.subplots(figsize=(12, 7))
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn",
                   vmin=0.90, vmax=1.10,
                   extent=[-0.5, 23.5, -0.5, len(buses_sorted) - 0.5])

    for h in (6, 12, 18):
        ax.axvline(h, color="white", linestyle="--", linewidth=0.8, alpha=0.5)

    cb = fig.colorbar(im, ax=ax)
    cb.set_label("Voltage (pu)")

    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24))
    ax.set_yticks(range(len(buses_sorted)))
    ax.set_yticklabels(buses_sorted, fontsize=7)
    ax.set_xlabel("Hour of day")
    ax.set_title(
        f"Voltage by bus 24h - {network_name}  "
        f"[PV={pen_pv}%  DC={pen_dc}%  BESS={pen_bess}%  EV={pen_ev}%  seed={seed}]",
        fontsize=9, pad=4,
    )

    filename = f"heatmap_PV{pen_pv}_DC{pen_dc}_BESS{pen_bess}_EV{pen_ev}_seed{seed}.png"
    filepath = os.path.join(output_dir, filename)
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {filepath}")


def plot_voltage_lines(perfil_tension_barras, pen_pv, pen_bess, pen_ev,
                       seed, output_dir, network_name, pen_dc=0):
    horas = list(range(24))
    fig, ax = plt.subplots(figsize=FIG_SIZE, dpi=FIG_DPI)

    for bus, perfil in perfil_tension_barras.items():
        if any(v < 0.95 for v in perfil):
            color, alpha, lw = "#B2182B", 0.90, 1.4
        elif any(v > 1.05 for v in perfil):
            color, alpha, lw = "#E08214", 0.90, 1.4
        else:
            color, alpha, lw = "#2166AC", 0.30, 1.0
        ax.plot(horas, perfil, color=color, alpha=alpha, linewidth=lw,
                marker="o", markersize=1.5, markeredgewidth=0)

    ax.axhline(0.95, color=C_LIMIT, linestyle="--", linewidth=0.8,
               label="Lower limit 0.95 pu")
    ax.axhline(1.05, color=C_LIMIT, linestyle=":",  linewidth=0.8,
               label="Upper limit 1.05 pu")

    legend_handles = [
        Line2D([0], [0], color="#B2182B", linewidth=1.4,
               marker="o", markersize=3, markeredgewidth=0,
               label="Undervoltage (<0.95 pu)"),
        Line2D([0], [0], color="#E08214", linewidth=1.4,
               marker="o", markersize=3, markeredgewidth=0,
               label="Overvoltage (>1.05 pu)"),
        Line2D([0], [0], color="#2166AC", linewidth=1.0, alpha=0.5,
               marker="o", markersize=2, markeredgewidth=0,
               label="Normal"),
        Line2D([0], [0], color="black", linewidth=0.8, linestyle="--",
               label="0.95 pu"),
        Line2D([0], [0], color="black", linewidth=0.8, linestyle=":",
               label="1.05 pu"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", borderpad=0.4)

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax.set_ylim(0.88, 1.12)
    ax.set_xlabel("Hour of day", labelpad=3)
    ax.set_ylabel("Voltage (pu)", labelpad=3)
    ax.set_title(
        f"Voltage profile by bus 24h - {network_name}  "
        f"[PV={pen_pv}%  DC={pen_dc}%  BESS={pen_bess}%  EV={pen_ev}%  seed={seed}]",
        fontsize=9, pad=4,
    )
    fig.tight_layout(pad=0.5)

    filename = f"lines_PV{pen_pv}_DC{pen_dc}_BESS{pen_bess}_EV{pen_ev}_seed{seed}.png"
    filepath = os.path.join(output_dir, filename)
    fig.savefig(filepath, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {filepath}")


def plot_voltage_profile(perfil_tension_barras, pen_pv, pen_bess, pen_ev,
                         seed, output_dir, network_name, pen_dc=0):
    os.makedirs(output_dir, exist_ok=True)
    plot_voltage_lines(perfil_tension_barras, pen_pv, pen_bess, pen_ev,
                       seed, output_dir, network_name, pen_dc)
