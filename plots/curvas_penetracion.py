# plots/curvas_penetracion.py
"""
Penetration curves with median + IQR + P5-P95 bands (IEEE single-column).
Dual X-axis: PV penetration (bottom) and DC penetration (top).
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plots.style import apply_style, SWEEP_LABELS, detect_sweep_col


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

_KPI_COLOR = {
    "B_Vmin":        "#2166AC",
    "B_Vmax":        "#B2182B",
    "B_VminVmax":    "#B2182B",
    "Energy_Losses": "#1B7837",
    "Max_PLosses":       "#2166AC",
    "Min_PLosses":       "#B2182B",
    "Min_Fluxo_Subestacao": "#4393C3",
    "Trafo_Loading_pct": "#4393C3",
    "Vmin_24h":          "#4393C3",
    "Vmax_24h":          "#4393C3",
    "Sev_Vmin_pct":      "#4393C3",
    "Sev_Vmax_pct":      "#4393C3",
    "Sev_VminVmax_pct":  "#4393C3",
    
}

_KPIS = list(_KPI_YLABEL.keys())


class CurvasPenetracion:
    def __init__(self, csv_path: str, output_dir: str = "figures/curvas"):
        self.csv_path = csv_path
        self.output_dir = output_dir
        self.df = pd.read_csv(csv_path)
        os.makedirs(output_dir, exist_ok=True)

    def plot_all(self):
        for kpi in _KPIS:
            print(f"  Generating curve: {kpi}")
            self.plot_kpi(kpi)

    def plot_kpi(self, kpi: str):
        apply_style()
        plt.rcParams.update({"lines.linewidth": 1.2})

        df = self.df
        sweep_col, secondary_col = detect_sweep_col(df)
        pen_levels = sorted(df[sweep_col].unique())

        stats = {k: [] for k in ("p5", "q1", "median", "mean", "q3", "p95")}

        for pen in pen_levels:
            sub = df.loc[df[sweep_col] == pen, kpi].dropna()
            stats["p5"].append(np.percentile(sub, 5))
            stats["q1"].append(np.percentile(sub, 25))
            stats["median"].append(np.percentile(sub, 50))
            stats["mean"].append(sub.mean())
            stats["q3"].append(np.percentile(sub, 75))
            stats["p95"].append(np.percentile(sub, 95))

        x = np.array(pen_levels, dtype=float)
        for k in stats:
            stats[k] = np.array(stats[k])

        color = _KPI_COLOR.get(kpi, "#444444")

        fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)

        ax.fill_between(x, stats["p5"], stats["p95"],
                        color=color, alpha=0.15, linewidth=0,
                        label="P5–P95")

        ax.fill_between(x, stats["q1"], stats["q3"],
                        color=color, alpha=0.35, linewidth=0,
                        label="IQR [Q1–Q3]")

        ax.plot(x, stats["median"],
                color=color, linewidth=1.4,
                marker="o", markersize=3.5, markeredgewidth=0,
                label="Median", zorder=5)

        ax.plot(x, stats["mean"],
                color=color, linewidth=0.9, linestyle="--",
                alpha=0.75, label="Mean", zorder=4)

        secondary_vals = []
        for pen in pen_levels:
            subset = df.loc[df[sweep_col] == pen, secondary_col]
            secondary_vals.append(subset.iloc[0] if len(subset) > 0 else 0.0)

        xlabel_bottom = SWEEP_LABELS.get(sweep_col, sweep_col)
        xlabel_top = SWEEP_LABELS.get(secondary_col, secondary_col)

        ax.set_xticks(x)
        ax.set_xticklabels([str(int(v)) for v in x], fontsize=6)
        ax.set_xlabel(xlabel_bottom, labelpad=4)
        ax.set_xlim(x[0] - 3, x[-1] + 3)

        secondary_has_variation = len(set(secondary_vals)) > 1 or any(v != 0 for v in secondary_vals)
        if secondary_has_variation:
            ax2 = ax.twiny()
            ax2.set_xlim(ax.get_xlim())
            ax2.set_xticks(x)
            ax2.set_xticklabels([str(int(v)) for v in secondary_vals], fontsize=6)
            ax2.set_xlabel(xlabel_top, labelpad=4)
            ax2.tick_params(axis="x", width=0.5, length=3)

        ax.set_ylabel(_KPI_YLABEL.get(kpi, kpi), labelpad=4)

        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles, labels, loc="upper left",
                  borderpad=0.5, labelspacing=0.25,
                  handletextpad=0.4, handlelength=1.8)

        fig.tight_layout(pad=0.5)

        for fmt in ["png", "pdf"]:
            path = os.path.join(self.output_dir, f"curva_{kpi}.{fmt}")
            fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"    Saved: curva_{kpi}.png / .pdf")


if __name__ == "__main__":
    csv_path = (sys.argv[1] if len(sys.argv) > 1
                else "results/resultados_18Bus_PV100_BESS0_EV0_DC25.csv")

    plotter = CurvasPenetracion(csv_path=csv_path)
    plotter.plot_all()
