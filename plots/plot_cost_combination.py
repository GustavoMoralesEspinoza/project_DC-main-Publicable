"""
plot_cost_combination.py

Generates two figures that combine BESS installation cost with the
economic cost of energy losses, as a function of PV penetration
level (Pen_PV) — the driver variable of the Monte Carlo sweep (see
config.py PENETRATION_LEVELS_PV). Pen_BESS is derived from Pen_PV via
a fixed ratio (BESS_PV_RATIO) and is not used as the x-axis here.

  Option D - Total system cost: stacked bars (BESS + Losses) per
             Pen_PV level, showing whether a total cost minimum
             exists (optimal PV/BESS sizing point).

  Option E - Break-even point: two lines (increasing BESS cost,
             energy losses cost) with a marker at the crossover,
             if one exists within the data range.

Follows the same pattern as the other scripts in plots/ (matplotlib
Agg, IEEE single-column style, dpi=300, png+pdf export). If
plots/style.py already exists (Task 2 completed), its TECH_COLORS
and apply_style()/save_figure() are reused; otherwise it falls back
to equivalent local values so it doesn't depend on that task being
finished.

USAGE:
    Edit CSV_NAME (and optionally COSTO) below and run:
        python plots/plot_cost_combination.py
    (same pattern as CSV_NAME in plot_curves.py — the CSV itself is not a
    CLI argument). Optional CLI overrides for the two assumptions that are
    worth varying without editing the file (cost band, BESS lifetime):
        python plots/plot_cost_combination.py --costo Intl --lifetime 15

The CSV must live at results/<CSV_NAME>.csv and contain, at minimum,
the columns generated in TASK 1:
    Pen_PV, Cost_BESS_Peru, Cost_BESS_Intl, Energy_Losses_USD

Data is grouped by Pen_PV and the MEDIAN of each metric is taken
across the Monte Carlo iterations of that level (same criterion used
by curvas_penetracion.py elsewhere in the project).

NOTE: both Cost_BESS and Energy_Losses are annualized (USD/year) so they
are directly comparable: Cost_BESS is amortized linearly over
BESS_LIFETIME_YEARS_DEFAULT (default 10 years, override with --lifetime);
Energy_Losses is annualized by x365 (see DIAS_POR_ANIO below).
"""

import os
import sys
import argparse
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Bootstrap: if the script is run as `python plots/plot_cost_combination.py`,
# sys.path[0] ends up pointing at plots/ (not the project root), so
# `from plots.style import ...` can't resolve the "plots" package. The
# project root is added to sys.path so the import works regardless of
# where the script is invoked from (same pattern as the other files in
# plots/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# 1) STYLE - reuses plots/style.py if it exists, otherwise falls
#    back to equivalent local defaults
# ============================================================

try:
    from plots.style import TECH_COLORS, apply_style, save_figure
    _HAS_PROJECT_STYLE = True
except ImportError:
    _HAS_PROJECT_STYLE = False

    TECH_COLORS = {
        "PV": "#2166AC",
        "DC": "#B2182B",
        "Load": "#555555",
        "Trafo": "#E08214",
        "Reverse": "#762A83",
        "Limit": "black",
        "BESS": "#35978F",
        "EVCS": "#BF812D",
    }

    def apply_style():
        plt.rcParams.update({
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": 8,
            "axes.titlesize": 9,
            "legend.fontsize": 7,
            "grid.color": "#E0E0E0",
            "grid.alpha": 0.5,
            "grid.linestyle": "--",
        })

    def save_figure(fig, filepath_no_ext):
        filepath_no_ext = Path(filepath_no_ext)
        filepath_no_ext.parent.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(f"{filepath_no_ext}.{ext}", dpi=300, bbox_inches="tight")

# Color for the losses cost: does NOT reuse any hex already assigned to
# a technology (PV/DC/BESS/EVCS/Trafo/Reverse) to avoid the same
# ambiguity that was detected and fixed in TASK 2 (style diagnostic,
# Sec. 3). Chosen from the ColorBrewer RdBu palette; does not collide
# with C_DC (#B2182B) or any other color.
LOSSES_COLOR = "#D6604D"

FIGSIZE_SINGLE = (3.5, 2.8)
DPI = 300

# ============================================================
# EDITABLE CONFIGURATION (same pattern as CSV_NAME in plot_curves.py)
# ============================================================
CSV_NAME = "resultados_18Bus_Mod_PV100_BESS25_EV50_DC0"   # CSV name in results/, no extension
COSTO    = "Peru"                                        # "Peru" or "Intl" - BESS cost band
DIAS_POR_ANIO = 365
BESS_LIFETIME_YEARS_DEFAULT = 10


# ============================================================
# 2) DATA LOADING AND AGGREGATION
# ============================================================

REQUIRED_COLUMNS = ["Pen_PV", "Cost_BESS_Peru", "Cost_BESS_Intl", "Energy_Losses_USD"]


def cargar_y_agregar(csv_path, usar_costo="Peru", lifetime_years=BESS_LIFETIME_YEARS_DEFAULT):
    """
    Loads the results CSV and aggregates by Pen_PV, taking the
    median of each metric across the Monte Carlo iterations of that
    level.

    usar_costo: "Peru" or "Intl" - which BESS cost column to use
                (Cost_BESS_Peru or Cost_BESS_Intl).
    lifetime_years: BESS lifetime in years, used to linearly amortize
                     the CAPEX into an annualized cost.
    """
    df = pd.read_csv(csv_path)

    faltantes = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"CSV is missing required columns: {faltantes}. "
            f"Verify this is a CSV generated after TASK 1 (costs)."
        )

    col_bess = f"Cost_BESS_{usar_costo}"

    # Grouped by Pen_PV (the independent/driver variable of the Monte Carlo
    # sweep, see config.py PENETRATION_LEVELS_PV) instead of Pen_BESS (a
    # value derived from Pen_PV via a fixed ratio, BESS_PV_RATIO). Plotting
    # against Pen_PV matches the x-axis used by the rest of the project's
    # penetration-curve figures (e.g. curvas_penetracion.py).
    agregado = df.groupby("Pen_PV").agg(
        Cost_BESS=(col_bess, "median"),
        Energy_Losses_USD=("Energy_Losses_USD", "median"),
    ).reset_index().sort_values("Pen_PV")

    # Convert to thousand USD for more legible axes.
    # BESS CAPEX amortized linearly over its lifetime (BESS_LIFETIME_YEARS,
    # default 10 years - a conservative value for LFP at distribution
    # scale; see NREL ATB Utility-Scale/Commercial Battery Storage, which
    # reports ~15 years technical life with cell replacement included in
    # O&M). Linear amortization WITHOUT a discount rate, consistent with
    # the simplified economic scope of this paper (simple cost-
    # effectiveness, not NPV/cash flow). Cost_BESS_k and Energy_Losses_k
    # are now on the SAME time basis (USD/year), enabling direct comparison.
    agregado["Cost_BESS_k"] = (agregado["Cost_BESS"] / lifetime_years) / 1000.0

    # Energy_Losses_USD is a daily value (comes from a 24h power flow
    # simulation). It is annualized by multiplying by 365 so it can be
    # compared against the (now also annualized) Cost_BESS.
    agregado["Energy_Losses_k"] = (agregado["Energy_Losses_USD"] * DIAS_POR_ANIO) / 1000.0

    agregado["Total_k"] = agregado["Cost_BESS_k"] + agregado["Energy_Losses_k"]

    return agregado


# ============================================================
# 3) OPTION D - Stacked bars of total system cost
# ============================================================

def graficar_opcion_D(agregado, outdir):
    apply_style()

    fig, ax = plt.subplots(figsize=FIGSIZE_SINGLE, dpi=DPI)

    # Format as e.g. "5%" for whole numbers or "12.5%" if Pen_PV has a
    # fractional value in a given CSV.
    x = agregado["Pen_PV"].map(lambda v: f"{v:g}%")
    bess = agregado["Cost_BESS_k"].values
    losses = agregado["Energy_Losses_k"].values

    ax.bar(x, bess, label="BESS (annualized CAPEX)", color=TECH_COLORS["BESS"],
           edgecolor="none", width=0.6)
    ax.bar(x, losses, bottom=bess, label="Energy losses (annualized)", color=LOSSES_COLOR,
           edgecolor="none", width=0.6)

    total = bess + losses
    idx_min = int(np.argmin(total))
    ax.annotate(
        "minimum",
        xy=(idx_min, total[idx_min]),
        xytext=(idx_min, total[idx_min] * 1.08),
        ha="center", fontsize=7,
        arrowprops=dict(arrowstyle="-", lw=0.6, color="black"),
    )

    ax.set_xlabel("PV penetration (%)")
    ax.set_ylabel("Total annualized cost (thousand USD/year)")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y")
    fig.tight_layout()

    save_figure(fig, str(Path(outdir) / "cost_combination_opcionD_stacked"))
    plt.close(fig)

    print(f"Pen_PV level with minimum total annualized cost: {agregado['Pen_PV'].iloc[idx_min]}% "
          f"(total annualized cost = {total[idx_min]:.1f}k USD)")


# ============================================================
# 4) OPTION E - Lines with break-even point
# ============================================================

def _encontrar_cruce(x, y1, y2):
    """
    Finds the first sign change of (y1 - y2) and linearly interpolates
    the crossover point. Returns (x_cross, y_cross) or None if there is
    no crossover within the data range.
    """
    diff = y1 - y2
    signos = np.sign(diff)
    cambios = np.where(np.diff(signos) != 0)[0]
    if len(cambios) == 0:
        return None

    i = cambios[0]
    x0, x1 = x[i], x[i + 1]
    d0, d1 = diff[i], diff[i + 1]
    # linear interpolation of the point where diff crosses zero
    t = -d0 / (d1 - d0)
    x_cruce = x0 + t * (x1 - x0)
    y_cruce = y1[i] + t * (y1[i + 1] - y1[i])
    return x_cruce, y_cruce


def graficar_opcion_E(agregado, outdir):
    apply_style()

    fig, ax = plt.subplots(figsize=FIGSIZE_SINGLE, dpi=DPI)

    # Numeric x, used for both plotting and _encontrar_cruce() (crossover
    # interpolation needs the real values, not a formatted string).
    x = agregado["Pen_PV"].values.astype(float)
    bess = agregado["Cost_BESS_k"].values
    losses = agregado["Energy_Losses_k"].values

    ax.plot(x, bess, marker="o", ms=3, lw=1.3, color=TECH_COLORS["BESS"],
            label="BESS (annualized CAPEX)")
    ax.plot(x, losses, marker="o", ms=3, lw=1.3, color=LOSSES_COLOR,
            label="Energy losses (annualized)")

    # Separate tick labels only, formatted like Option D ("5%"/"12.5%"),
    # without touching the numeric x array used above.
    ax.set_xticks(x)
    ax.set_xticklabels([f"{v:g}%" for v in x])

    cruce = _encontrar_cruce(x, bess, losses)
    if cruce is not None:
        x_c, y_c = cruce
        ax.plot(x_c, y_c, marker="x", ms=6, color="black", mew=1.2)
        ax.annotate(
            f"break-even\n{x_c:.1f}% PV",
            xy=(x_c, y_c), xytext=(x_c, y_c * 1.15),
            ha="center", fontsize=7,
            arrowprops=dict(arrowstyle="-", lw=0.6, color="black"),
        )
        print(f"Break-even point found at Pen_PV = {x_c:.2f}% "
              f"(annualized cost = {y_c:.1f}k USD)")
    else:
        print("No break-even point found within the data range "
              "(one curve dominates the other across the whole range).")

    ax.set_xlabel("PV penetration (%)")
    ax.set_ylabel("Annualized cost (thousand USD/year)")
    ax.legend(frameon=False, loc="best")
    ax.grid(axis="y")
    fig.tight_layout()

    save_figure(fig, str(Path(outdir) / "cost_combination_opcionE_crossover"))
    plt.close(fig)


# ============================================================
# 5) MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Plot BESS annualized CAPEX + annualized energy losses cost (Options D and E)."
    )
    parser.add_argument("--costo", type=str, default=COSTO, choices=["Peru", "Intl"],
                         help=f"Which BESS cost band to use: Peru or Intl (default: {COSTO}).")
    parser.add_argument("--lifetime", type=float, default=BESS_LIFETIME_YEARS_DEFAULT,
                         help="BESS lifetime in years, used to amortize the CAPEX "
                              "(default: 10 years, a conservative value typical for LFP "
                              "at distribution scale).")
    args = parser.parse_args()

    csv_path = Path("results") / f"{CSV_NAME}.csv"
    if not csv_path.exists():
        print(f"ERROR: file not found: {csv_path}")
        sys.exit(1)

    outdir = Path("figures") / CSV_NAME / "cost_combination"

    print(f"Project style (plots/style.py) {'FOUND' if _HAS_PROJECT_STYLE else 'NOT found, using local defaults'}.")
    print(f"Loading {csv_path} ...")
    print(f"BESS lifetime used for amortization: {args.lifetime} years")
    agregado = cargar_y_agregar(csv_path, usar_costo=args.costo, lifetime_years=args.lifetime)
    print(f"Pen_PV levels found: {list(agregado['Pen_PV'])}")

    graficar_opcion_D(agregado, outdir)
    graficar_opcion_E(agregado, outdir)

    print(f"Figures saved to: {outdir}/")


if __name__ == "__main__":
    main()
