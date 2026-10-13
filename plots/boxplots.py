# plots/boxplots.py
"""
Boxplot figures for IEEE conference paper (single-column format).
Dual X-axis: PV penetration (top) and DC penetration (bottom).
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plots.style import apply_style, TECH_COLORS, SWEEP_LABELS, detect_sweep_col


_KPI_YLABEL = {
    "B_Vmin":            "Buses with undervoltage (count)",
    "B_Vmax":            "Buses with overvoltage (count)",
    "B_VminVmax":        "Buses with voltage violation (count)",
    "Max_PLosses":       "Maximum power losses (kW)",
    "Min_PLosses":       "Minimum power losses (kW)",
    "Energy_Losses":     "Daily energy losses (kWh)",
    "Min_Fluxo_Subestacao": "Minimum substation power flow (kW)",
    "Trafo_Loading_pct": "Transformer loading (%)",
    "Vmin_24h":          "Minimum system voltage (pu)",
    "Vmax_24h":          "Maximum system voltage (pu)",
    "Sev_Vmin_pct":      "Undervoltage severity (%)",
    "Sev_Vmax_pct":      "Overvoltage severity (%)",
    "Sev_VminVmax_pct":  "Voltage violation severity (%)",
}

_KPIS = list(_KPI_YLABEL.keys())


class BoxplotPlotter:
    def __init__(self, csv_path: str, output_dir: str = "figures/boxplots",
                 color: str = TECH_COLORS["PV"]):
        self.csv_path = csv_path
        self.output_dir = output_dir
        self.color = color
        self.df = pd.read_csv(csv_path)
        os.makedirs(output_dir, exist_ok=True)

    def plot_all(self):
        for kpi in _KPIS:
            self.plot_kpi(kpi)

    def plot_kpi(self, kpi: str):
        apply_style()
        plt.rcParams.update({"axes.grid.axis": "y"})   # boxplot: grid horizontal solamente

        df = self.df
        sweep_col, secondary_col = detect_sweep_col(df)
        pen_levels = sorted(df[sweep_col].unique())

        positions = pen_levels
        data = [df.loc[df[sweep_col] == lv, kpi].values for lv in pen_levels]

        fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)

        bp = ax.boxplot(
            data,
            positions=positions,
            widths=7,
            patch_artist=True,
            showfliers=False,
            medianprops=dict(color="black", linewidth=0.7),
            whiskerprops=dict(color="black", linewidth=0.7),
            capprops=dict(color="black", linewidth=0.7),
            boxprops=dict(facecolor=self.color, edgecolor="black",
                          linewidth=0.7, alpha=0.6),
        )

        means = [float(np.mean(d)) for d in data]
        ax.plot(positions, means, color=self.color, linewidth=1.2,
                marker="o", markersize=3, zorder=5, label="Mean")

        secondary_vals = []
        for pen in pen_levels:
            subset = df.loc[df[sweep_col] == pen, secondary_col]
            secondary_vals.append(subset.iloc[0] if len(subset) > 0 else 0.0)

        xlabel_bottom = SWEEP_LABELS.get(sweep_col, sweep_col)
        xlabel_top = SWEEP_LABELS.get(secondary_col, secondary_col)

        ax.set_xticks(positions)
        ax.set_xticklabels([str(int(v)) for v in pen_levels], fontsize=6)
        ax.set_xlabel(xlabel_bottom, labelpad=4)
        ax.set_ylabel(_KPI_YLABEL.get(kpi, kpi))

        secondary_has_variation = len(set(secondary_vals)) > 1 or any(v != 0 for v in secondary_vals)
        if secondary_has_variation:
            ax2 = ax.twiny()
            ax2.set_xlim(ax.get_xlim())
            ax2.set_xticks(positions)
            ax2.set_xticklabels([str(int(v)) for v in secondary_vals], fontsize=6)
            ax2.set_xlabel(xlabel_top, labelpad=4)
            ax2.tick_params(axis="x", width=0.5, length=3)

        ax.legend(fontsize=6, loc="best")
        fig.tight_layout(pad=0.5)

        stem = os.path.join(self.output_dir, f"boxplot_{kpi}")
        fig.savefig(f"{stem}.png", dpi=300, bbox_inches="tight")
        fig.savefig(f"{stem}.pdf", format="pdf", bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved: {stem}.png / .pdf")


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "results/resultados_18Bus_PV100_BESS0_EV0_DC25.csv"
    plotter = BoxplotPlotter(csv_path=csv_path)
    plotter.plot_all()
