# plots/curvas_multiescenario.py
"""
Multi-scenario penetration curves with P10-P90 bands (IEEE format).
A1: all scenarios on one KPI.  A2: subset.  A3: dual-panel stacked.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, AutoMinorLocator

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

def _calc_stats(df, pen_col, kpi):
    pen_levels = sorted(df[pen_col].unique())
    p50, p10, p90 = [], [], []
    for lv in pen_levels:
        sub = df.loc[df[pen_col] == lv, kpi].dropna()
        if len(sub) == 0:
            p50.append(np.nan)
            p10.append(np.nan)
            p90.append(np.nan)
        else:
            p50.append(np.median(sub))
            p10.append(np.percentile(sub, 10))
            p90.append(np.percentile(sub, 90))
    return {
        "levels": np.array(pen_levels, dtype=float),
        "p50": np.array(p50),
        "p10": np.array(p10),
        "p90": np.array(p90),
    }


def _plot_scenario_on_ax(ax, sname, stats):
    meta = SCENARIO_META[sname]
    x = stats["levels"]
    ax.fill_between(x, stats["p10"], stats["p90"],
                    color=meta["color"], alpha=0.13, linewidth=0)
    ax.plot(x, stats["p50"],
            color=meta["color"], linestyle=meta["ls"],
            linewidth=1.2, marker="o", markersize=2.5, markeredgewidth=0)


def _make_handle(sname):
    meta = SCENARIO_META[sname]
    return Line2D([0], [0], color=meta["color"], linestyle=meta["ls"],
                  linewidth=1.2, marker="o", markersize=2.5,
                  markeredgewidth=0, label=meta["label"])


def _add_hlimit(ax, kpi):
    info = KPI_META.get(kpi, {})
    if "hlimit" not in info:
        return None
    ax.axhline(info["hlimit"], color="0.3", linestyle=":", linewidth=0.8)
    return Line2D([0], [0], color="0.3", linestyle=":",
                  linewidth=0.8, label=f"{info['hlimit']} {info.get('unit','')}")


def _ylabel(kpi):
    info = KPI_META.get(kpi, {"ylabel": kpi, "unit": ""})
    unit = f" ({info['unit']})" if info.get("unit") else ""
    return f"{info['ylabel']}{unit}"


class CurvasMultiescenario:
    def __init__(self, csv_map: dict, output_dir: str = "figures/curvas_multi"):
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

    # ------------------------------------------------------------------
    # A1 / A2 — single panel
    # ------------------------------------------------------------------

    def plot_single(self, kpi: str, scenarios: list = None,
                    filename: str = None):
        apply_style()
        plt.rcParams.update({"lines.linewidth": 1.2})

        if scenarios is None:
            scenarios = list(self.data.keys())

        fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)
        handles = []

        for sname in scenarios:
            if sname not in self.data:
                continue
            df = self.data[sname]
            meta = SCENARIO_META[sname]
            if kpi not in df.columns:
                print(f"  [WARN] {sname}: column '{kpi}' missing — skipped.")
                continue
            stats = _calc_stats(df, meta["pen_col"], kpi)
            _plot_scenario_on_ax(ax, sname, stats)
            handles.append(_make_handle(sname))

        if not handles:
            print(f"  [WARN] No data for '{kpi}' — figure not generated.")
            plt.close(fig)
            return

        h = _add_hlimit(ax, kpi)
        if h:
            handles.append(h)

        ax.set_xlabel("Penetration level (%)", labelpad=4)
        ax.set_ylabel(_ylabel(kpi), labelpad=4)
        ax.set_xlim(left=0)
        ax.xaxis.set_minor_locator(MultipleLocator(5))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))

        ax.annotate("Shaded: P10–P90", xy=(0.98, 0.03),
                    xycoords="axes fraction", ha="right",
                    fontsize=4.5, color="0.45", style="italic")

        ax.legend(handles=handles, loc="best",
                  borderpad=0.5, labelspacing=0.25,
                  handletextpad=0.4, handlelength=2.0)

        fig.tight_layout(pad=0.5)

        if filename is None:
            filename = f"multi_{kpi}"
        for fmt in ["png", "pdf"]:
            path = os.path.join(self.output_dir, f"{filename}.{fmt}")
            fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"    Saved: {filename}.png / .pdf")

    # ------------------------------------------------------------------
    # A3 — dual panel stacked
    # ------------------------------------------------------------------

    def plot_dual(self, kpi_top: str, kpi_bottom: str,
                  scenarios: list = None, filename: str = None):
        apply_style()
        plt.rcParams.update({"lines.linewidth": 1.2})

        if scenarios is None:
            scenarios = list(self.data.keys())

        fig, (ax_top, ax_bot) = plt.subplots(
            2, 1, figsize=(3.5, 4.2), dpi=300, sharex=True)

        handles = []

        for sname in scenarios:
            if sname not in self.data:
                continue
            df = self.data[sname]
            meta = SCENARIO_META[sname]
            plotted = False

            for ax_cur, kpi_cur in [(ax_top, kpi_top), (ax_bot, kpi_bottom)]:
                if kpi_cur not in df.columns:
                    continue
                stats = _calc_stats(df, meta["pen_col"], kpi_cur)
                _plot_scenario_on_ax(ax_cur, sname, stats)
                plotted = True

            if plotted:
                handles.append(_make_handle(sname))

        if not handles:
            print(f"  [WARN] No data for dual plot — figure not generated.")
            plt.close(fig)
            return

        ax_top.set_ylabel(_ylabel(kpi_top), labelpad=4)
        ax_bot.set_ylabel(_ylabel(kpi_bottom), labelpad=4)
        ax_bot.set_xlabel("Penetration level (%)", labelpad=4)
        ax_top.set_xlim(left=0)

        ax_top.set_title("(a)", fontsize=6, loc="left", pad=3)
        ax_bot.set_title("(b)", fontsize=6, loc="left", pad=3)

        _add_hlimit(ax_top, kpi_top)
        _add_hlimit(ax_bot, kpi_bottom)

        ax_top.legend(handles=handles, loc="best", fontsize=4.5, ncol=2,
                      borderpad=0.3, labelspacing=0.15, handletextpad=0.3)

        fig.tight_layout(pad=0.5, h_pad=0.8)

        if filename is None:
            filename = f"dual_{kpi_top}_{kpi_bottom}"
        for fmt in ["png", "pdf"]:
            path = os.path.join(self.output_dir, f"{filename}.{fmt}")
            fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"    Saved: {filename}.png / .pdf")

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def plot_all_kpis(self, scenarios: list = None):
        all_kpis = [
            "B_Vmin", "B_Vmax", "B_VminVmax",
            "Energy_Losses", "Max_PLosses",
            "Trafo_Loading_pct",
            "Vmin_24h", "Vmax_24h",
            "Sev_Vmin_pct", "Sev_Vmax_pct", "Sev_VminVmax_pct",
            "Min_Fluxo_Subestacao",
        ]

        for kpi in all_kpis:
            print(f"  A1 — {kpi}")
            self.plot_single(kpi=kpi, scenarios=scenarios)

        print("  A3 — Sev_Vmin vs Sev_Vmax")
        self.plot_dual("Sev_Vmin_pct", "Sev_Vmax_pct",
                       scenarios=scenarios, filename="dual_SevVmin_SevVmax")

        print("  A3 — B_Vmin vs B_Vmax")
        self.plot_dual("B_Vmin", "B_Vmax",
                       scenarios=scenarios, filename="dual_BVmin_BVmax")

        print("  A3 — Vmin_24h vs Vmax_24h")
        self.plot_dual("Vmin_24h", "Vmax_24h",
                       scenarios=scenarios, filename="dual_Vmin24h_Vmax24h")


if __name__ == "__main__":
    csv_map = {
        "S_PV":    "results/resultados_18Bus_PV100_BESS0_EV0_DC0.csv",
        "S_DC":    "results/resultados_18Bus_PV0_BESS0_EV0_DC100.csv",
        "S_DC25":  "results/resultados_18Bus_PV100_BESS0_EV0_DC25.csv",
        "S_DC50":  "results/resultados_18Bus_PV100_BESS0_EV0_DC50.csv",
        "S_DC100": "results/resultados_18Bus_PV100_BESS0_EV0_DC100.csv",
    }

    plotter = CurvasMultiescenario(csv_map=csv_map)

    plotter.plot_all_kpis()

    plotter.plot_single(
        kpi="Energy_Losses",
        scenarios=["S_PV", "S_DC25", "S_DC50", "S_DC100"],
        filename="A2_EnergyLosses_PVvsCombined",
    )
