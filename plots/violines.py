# plots/violines.py
"""
Violin plots comparing scenario distributions at a fixed penetration level.
Each violin = one scenario, with strip plot (jitter) overlay.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plots.style import apply_style, SCENARIO_META

KPI_META = {
    "B_Vmin":               {"ylabel": "Buses with undervoltage",      "unit": "count"},
    "B_Vmax":               {"ylabel": "Buses with overvoltage",       "unit": "count"},
    "B_VminVmax":           {"ylabel": "Buses with voltage violation", "unit": "count"},
    "Energy_Losses":        {"ylabel": "Daily energy losses",          "unit": "kWh"},
    "Max_PLosses":          {"ylabel": "Peak active power losses",     "unit": "kW"},
    "Min_PLosses":          {"ylabel": "Min. active power losses",     "unit": "kW"},
    "Trafo_Loading_pct":    {"ylabel": "Transformer loading",          "unit": "%",  "hlimit": 100.0},
    "Vmin_24h":             {"ylabel": "Minimum system voltage",       "unit": "pu", "hlimit": 0.95},
    "Vmax_24h":             {"ylabel": "Maximum system voltage",       "unit": "pu", "hlimit": 1.05},
    "Sev_Vmin_pct":         {"ylabel": "Undervoltage severity",        "unit": "%"},
    "Sev_Vmax_pct":         {"ylabel": "Overvoltage severity",         "unit": "%"},
    "Sev_VminVmax_pct":     {"ylabel": "Voltage severity (combined)",  "unit": "%"},
    "Min_Fluxo_Subestacao": {"ylabel": "Min. substation flow",         "unit": "kW", "hlimit": 0.0},
}

_ALL_KPIS = [
    "B_Vmin", "B_Vmax", "B_VminVmax",
    "Energy_Losses", "Max_PLosses",
    "Trafo_Loading_pct",
    "Vmin_24h", "Vmax_24h",
    "Sev_Vmin_pct", "Sev_Vmax_pct", "Sev_VminVmax_pct",
    "Min_Fluxo_Subestacao",
]


class ViolinPlotter:
    def __init__(self, csv_map: dict, output_dir: str = "figures/violines"):
        self.csv_map = csv_map
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self.data = {}
        for sname, path in csv_map.items():
            if os.path.isfile(path):
                self.data[sname] = pd.read_csv(path)
                print(f"  Loaded: {sname} ({len(self.data[sname])} rows)")
            else:
                print(f"  [WARN] Not found: {path}")

    def plot_all(self, pen_fixed: float = 100.0):
        for kpi in _ALL_KPIS:
            print(f"  Violin — {kpi} at pen={pen_fixed}%")
            self.plot_kpi(kpi=kpi, pen_fixed=pen_fixed)

    def plot_kpi(self, kpi: str, pen_fixed: float = 100.0,
                 scenarios: list = None, filename: str = None):
        if scenarios is None:
            scenarios = list(self.data.keys())

        violin_data = []
        colors_list = []
        labels_list = []

        for sname in scenarios:
            if sname not in self.data:
                continue
            meta = SCENARIO_META[sname]
            df = self.data[sname]
            pen_col = meta["pen_col"]

            if kpi not in df.columns:
                print(f"  [WARN] {sname}: column '{kpi}' missing — skipped.")
                continue
            if pen_fixed not in df[pen_col].values:
                available = sorted(df[pen_col].unique())
                closest = min(available, key=lambda v: abs(v - pen_fixed))
                print(f"  [INFO] {sname}: pen={pen_fixed} not in {pen_col}, using {closest}")
                pen_use = closest
            else:
                pen_use = pen_fixed

            sub = df.loc[df[pen_col] == pen_use, kpi].dropna()
            if len(sub) < 2:
                print(f"  [WARN] {sname}: only {len(sub)} values — skipped.")
                continue

            violin_data.append(sub.values)
            colors_list.append(meta["color"])
            labels_list.append(meta["label"])

        if not violin_data:
            print(f"  [WARN] No data for '{kpi}' at pen={pen_fixed} — skipped.")
            return

        apply_style()
        plt.rcParams.update({"axes.grid.axis": "y"})   # violin: grid horizontal solamente

        positions = np.arange(len(violin_data))
        fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)

        vp = ax.violinplot(violin_data, positions=positions, widths=0.65,
                           showmeans=True, showmedians=True, showextrema=False)

        for i, body in enumerate(vp["bodies"]):
            body.set_facecolor(colors_list[i])
            body.set_alpha(0.35)
            body.set_edgecolor(colors_list[i])
            body.set_linewidth(0.7)

        vp["cmedians"].set_color("black")
        vp["cmedians"].set_linewidth(0.9)
        vp["cmeans"].set_color("black")
        vp["cmeans"].set_linewidth(0.7)
        vp["cmeans"].set_linestyle("--")

        for i, vals in enumerate(violin_data):
            rng = np.random.default_rng(i)
            jitter = rng.uniform(-0.12, 0.12, len(vals))
            ax.scatter(positions[i] + jitter, vals,
                       color=colors_list[i], s=5, alpha=0.5,
                       zorder=3, linewidths=0)

        kpi_info = KPI_META.get(kpi, {"ylabel": kpi, "unit": ""})

        if "hlimit" in kpi_info:
            ax.axhline(kpi_info["hlimit"], color="black", linestyle=":",
                       linewidth=0.8)

        ax.set_xticks(positions)
        ax.set_xticklabels(
            [lbl.replace(" ", "\n") for lbl in labels_list],
            fontsize=4.5, ha="center",
        )

        unit_str = f" ({kpi_info['unit']})" if kpi_info.get("unit") else ""
        ax.set_ylabel(f"{kpi_info['ylabel']}{unit_str}", labelpad=4)

        leg_handles = [
            Line2D([0], [0], color="black", linewidth=0.9, label="Median"),
            Line2D([0], [0], color="black", linewidth=0.7,
                   linestyle="--", label="Mean"),
        ]
        if "hlimit" in kpi_info:
            leg_handles.append(
                Line2D([0], [0], color="black", linewidth=0.8,
                       linestyle=":", label=f"{kpi_info['hlimit']} {kpi_info['unit']}")
            )
        ax.legend(handles=leg_handles, loc="best", fontsize=5)

        fig.tight_layout(pad=0.5)

        if filename is None:
            filename = f"violin_{kpi}_pen{int(pen_fixed)}"
        for fmt in ["png", "pdf"]:
            path = os.path.join(self.output_dir, f"{filename}.{fmt}")
            fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"    Saved: {filename}.png / .pdf")


if __name__ == "__main__":
    csv_map = {
        "S_PV":    "results/resultados_18Bus_PV100_BESS0_EV0_DC0.csv",
        "S_DC":    "results/resultados_18Bus_PV0_BESS0_EV0_DC100.csv",
        "S_DC25":  "results/resultados_18Bus_PV100_BESS0_EV0_DC25.csv",
        "S_DC50":  "results/resultados_18Bus_PV100_BESS0_EV0_DC50.csv",
        "S_DC100": "results/resultados_18Bus_PV100_BESS0_EV0_DC100.csv",
    }

    plotter = ViolinPlotter(csv_map=csv_map)
    plotter.plot_all(pen_fixed=50.0)
