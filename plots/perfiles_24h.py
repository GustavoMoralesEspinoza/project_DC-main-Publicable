# plots/perfiles_24h.py
"""
24h daily profiles with penetration-level color gradient (IEEE single-column).
One line per penetration level, colorbar as legend.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from matplotlib.ticker import MultipleLocator, AutoMinorLocator
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plots.style import apply_style, SWEEP_LABELS, detect_sweep_col


class Perfiles24h:
    def __init__(self, hourly_dir: str = "results/hourly",
                 output_dir: str = "figures/perfiles24h"):
        self.hourly_dir = hourly_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self.kpi_config = {
            "Pnet": {
                "file":   "perfil24h_Pnet.csv",
                "ylabel": "Active power — substation (kW)",
                "cmap":   "Blues",
                "hlimit": None,
                "hlabel": None,
            },
            "Plosses": {
                "file":   "perfil24h_Plosses.csv",
                "ylabel": "Active power losses (kW)",
                "cmap":   "Reds",
                "hlimit": None,
                "hlabel": None,
            },
            "Trafo": {
                "file":   "perfil24h_Trafo.csv",
                "ylabel": "Transformer loading (%)",
                "cmap":   "Oranges",
                "hlimit": 100.0,
                "hlabel": "100% limit",
            },
            "Vmin": {
                "file":   "perfil24h_Vmin.csv",
                "ylabel": "Minimum system voltage (pu)",
                "cmap":   "Blues",
                "hlimit": 0.95,
                "hlabel": "0.95 pu",
            },
            "Vmax": {
                "file":   "perfil24h_Vmax.csv",
                "ylabel": "Maximum system voltage (pu)",
                "cmap":   "Reds",
                "hlimit": 1.05,
                "hlabel": "1.05 pu",
            },
        }

    def plot_all(self):
        for kpi_name in self.kpi_config:
            print(f"  Generating 24h profile: {kpi_name}")
            self.plot_kpi(kpi_name)

    def plot_kpi(self, kpi_name: str):
        cfg = self.kpi_config[kpi_name]
        csv_path = os.path.join(self.hourly_dir, cfg["file"])

        if not os.path.isfile(csv_path):
            print(f"  [WARN] Not found: {csv_path}")
            return

        df = pd.read_csv(csv_path)
        hour_cols = [f"H{h}" for h in range(24)]

        sweep_col, secondary_col = detect_sweep_col(df)
        pen_levels = sorted(df[sweep_col].unique())
        n_levels = len(pen_levels)

        mean_profiles = np.zeros((n_levels, 24))
        for i, pen in enumerate(pen_levels):
            subset = df.loc[df[sweep_col] == pen, hour_cols]
            mean_profiles[i, :] = subset.mean(axis=0).values

        apply_style()
        plt.rcParams.update({"lines.linewidth": 1.0})

        fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)

        cmap = plt.get_cmap(cfg["cmap"])
        color_values = np.linspace(0.25, 0.95, n_levels)
        colors = [cmap(v) for v in color_values]

        hours = np.arange(24)

        for i, (pen, profile) in enumerate(zip(pen_levels, mean_profiles)):
            lw = 1.2 if pen == 0 else 1.0
            ls = "--" if pen == 0 else "-"
            ax.plot(hours, profile,
                    color=colors[i], linewidth=lw, linestyle=ls,
                    label=f"{int(pen)}%", zorder=3 + i * 0.1)

        if cfg["hlimit"] is not None:
            ax.axhline(cfg["hlimit"], color="black", linestyle=":",
                       linewidth=0.8, label=cfg["hlabel"], zorder=10)

        ax.set_xticks(np.arange(0, 24, 2))
        ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)],
                           fontsize=5.5)
        ax.set_xlim(-0.5, 23.5)
        ax.set_xlabel("Hour of day", labelpad=4)
        ax.set_ylabel(cfg["ylabel"], labelpad=4)

        ax.xaxis.set_minor_locator(MultipleLocator(1))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        ax.tick_params(axis="x", which="minor", width=0.4, length=1.5)
        ax.tick_params(axis="y", which="minor", width=0.4, length=1.5)

        sm = cm.ScalarMappable(
            cmap=cmap,
            norm=mcolors.Normalize(vmin=pen_levels[0], vmax=pen_levels[-1]),
        )
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, shrink=0.85, pad=0.02, aspect=20)
        cbar_label = SWEEP_LABELS.get(sweep_col, sweep_col)
        cbar.set_label(cbar_label, fontsize=5.5)
        cbar.set_ticks(pen_levels)
        cbar.set_ticklabels([str(int(p)) for p in pen_levels])
        cbar.ax.tick_params(labelsize=5)

        if cfg["hlimit"] is not None:
            limit_handle = Line2D([0], [0], color="black", linestyle=":",
                                  linewidth=0.8, label=cfg["hlabel"])
            ax.legend(handles=[limit_handle], loc="best",
                      borderpad=0.4, handlelength=1.5, fontsize=5.5)

        fig.tight_layout(pad=0.5)

        for fmt in ["png", "pdf"]:
            path = os.path.join(self.output_dir, f"perfil24h_{kpi_name}.{fmt}")
            fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"    Saved: perfil24h_{kpi_name}.png / .pdf")


def _make_synthetic_hourly(hourly_dir: str):
    """Create synthetic test CSVs if real data doesn't exist."""
    os.makedirs(hourly_dir, exist_ok=True)
    t = np.arange(24)
    base_load = np.clip(
        35000 + 10000 * np.sin((t - 6) * np.pi / 12)
        + 5000 * np.sin((t - 19) * np.pi / 5),
        20000, 55000,
    )
    solar = np.clip(30000 * np.exp(-((t - 12) ** 2) / 8), 0, None)

    configs = {
        "Pnet":    lambda pen, s: base_load - solar * pen / 100
                   + np.random.default_rng(s).normal(0, 500, 24),
        "Plosses": lambda pen, s: 1200 - 400 * (pen / 100)
                   + solar * 0.005 * (pen / 100)
                   + np.random.default_rng(s).normal(0, 50, 24),
        "Trafo":   lambda pen, s: (base_load - solar * (pen / 100)) / 600
                   + np.random.default_rng(s).normal(0, 0.5, 24),
        "Vmin":    lambda pen, s: 0.97 - 0.02 * (pen / 100)
                   * (1 - solar / solar.max())
                   + np.random.default_rng(s).normal(0, 0.002, 24),
        "Vmax":    lambda pen, s: 1.01 + 0.04 * (pen / 100)
                   * solar / solar.max()
                   + np.random.default_rng(s).normal(0, 0.002, 24),
    }

    for name, fn in configs.items():
        rows = []
        for pen in range(0, 110, 10):
            for it in range(10):
                seed = int(pen * 100 + it)
                vals = fn(pen, seed)
                row = {"Pen_PV": pen, "Pen_BESS": 0, "Pen_EV": 0,
                       "Pen_DC": pen * 0.5, "Seed": seed}
                for h, v in enumerate(vals):
                    row[f"H{h}"] = round(float(v), 4)
                rows.append(row)
        path = os.path.join(hourly_dir, f"perfil24h_{name}.csv")
        pd.DataFrame(rows).to_csv(path, index=False)
        print(f"  Synthetic data created: {path}")


if __name__ == "__main__":
    hourly_dir = (sys.argv[1] if len(sys.argv) > 1
                  else "results/hourly")

    if not os.path.isfile(os.path.join(hourly_dir, "perfil24h_Pnet.csv")):
        print("  [INFO] Creating synthetic hourly data for testing...")
        _make_synthetic_hourly(hourly_dir)

    plotter = Perfiles24h(hourly_dir=hourly_dir)
    plotter.plot_all()
