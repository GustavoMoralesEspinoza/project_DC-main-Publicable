# plots/histogramas3d.py
"""
3D probability surfaces + scatter, and 2D histogram slices.
X = penetration level, Y = KPI value, Z = probability (%).
Surface is smoothed via scipy interpolation over the discrete probability grid.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from mpl_toolkits.mplot3d import Axes3D  # noqa — registers 3D projection
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plots.style import apply_style, SWEEP_LABELS, SWEEP_SHORT_LABELS, detect_sweep_col


_KPI_YLABEL_3D = {
    "B_Vmin":        "Buses (undervolt.)",
    "B_Vmax":        "Buses (overvolt.)",
    "B_VminVmax":    "Buses (violation)",
    "Energy_Losses": "Energy losses (kWh)",
}

_KPI_YLABEL_2D = {
    "B_Vmin":        "Buses with undervoltage",
    "B_Vmax":        "Buses with overvoltage",
    "B_VminVmax":    "Buses with voltage violation",
    "Energy_Losses": "Energy losses (kWh)",
}

_KPIS = list(_KPI_YLABEL_3D.keys())

_BIN_WIDTH_ENERGY = 5000


def _interpolate_surface(points, values, grid_x, grid_y, smooth=True):
    Z = None

    if smooth and len(points) >= 4:
        try:
            Z = griddata(points, values, (grid_x, grid_y),
                         method="cubic", fill_value=0.0)
            if np.all(np.isnan(Z)) or np.nanmax(Z) < 1e-9:
                Z = None
        except Exception:
            Z = None

    if Z is None and len(points) >= 3:
        try:
            Z = griddata(points, values, (grid_x, grid_y),
                         method="linear", fill_value=0.0)
            if np.all(np.isnan(Z)):
                Z = None
        except Exception:
            Z = None

    if Z is None:
        try:
            Z = griddata(points, values, (grid_x, grid_y),
                         method="nearest", fill_value=0.0)
        except Exception:
            Z = np.zeros_like(grid_x)

    Z = np.nan_to_num(Z, nan=0.0)
    Z = np.clip(Z, 0, None)

    if smooth and Z.max() > 0:
        Z = gaussian_filter(Z, sigma=0.8)
        Z = np.clip(Z, 0, None)

    return Z


class Histogram3DPlotter:
    def __init__(self, csv_path: str, output_dir: str = "figures/histogramas3d"):
        self.csv_path = csv_path
        self.output_dir = output_dir
        self.df = pd.read_csv(csv_path)
        os.makedirs(output_dir, exist_ok=True)

    def plot_all(self, smooth: bool = True):
        for kpi in _KPIS:
            print(f"  Generating 3D: {kpi}  (smooth={smooth})")
            self.plot_3d(kpi, smooth=smooth)

    # ------------------------------------------------------------------
    # 3D surface
    # ------------------------------------------------------------------

    def plot_3d(self, kpi: str, smooth: bool = True):
        apply_style()
        # 3D: ticks mas pequenos que el default por espacio limitado en los ejes
        plt.rcParams.update({"xtick.labelsize": 5, "ytick.labelsize": 5})

        df = self.df
        sweep_col, secondary_col = detect_sweep_col(df)
        pen_levels = np.array(sorted(df[sweep_col].unique()))

        if df[kpi].nunique() <= 1:
            print(f"  [SKIP] {kpi}: all values are identical ({df[kpi].iloc[0]}), skipping 3D plot.")
            return

        if kpi == "Energy_Losses":
            kpi_vals, prob = self._calc_continuous(df, pen_levels, kpi, sweep_col)
        else:
            kpi_vals, prob = self._calc_integer(df, pen_levels, kpi, sweep_col)

        if prob.max() < 1e-9:
            print(f"  [SKIP] {kpi}: probability matrix is all zeros, skipping 3D plot.")
            return

        # --- Meshgrid of real points ---
        PEN, KPI = np.meshgrid(pen_levels, kpi_vals, indexing="ij")

        mask = (prob > 0) | (PEN == pen_levels[0])
        xp = PEN[mask]
        yp = KPI[mask]
        zp = prob[mask]

        if len(zp) == 0:
            print(f"  [WARN] hist3d: no data for '{kpi}' — skipped.")
            return

        # --- Interpolated surface ---
        pen_fine = np.linspace(pen_levels[0], pen_levels[-1], 60)
        pen_fine[0] = pen_levels[0]
        kpi_fine = np.linspace(kpi_vals[0], kpi_vals[-1], 60)
        PEN_f, KPI_f = np.meshgrid(pen_fine, kpi_fine, indexing="ij")

        points = np.column_stack([xp, yp])

        if len(points) < 3:
            Z_fine = np.zeros_like(PEN_f)
        else:
            Z_fine = _interpolate_surface(points, zp, PEN_f, KPI_f, smooth=smooth)

        # --- Figure ---
        fig = plt.figure(figsize=(3.5, 2.8), dpi=300)
        ax = fig.add_subplot(111, projection="3d")

        ax.plot_surface(
            PEN_f, KPI_f, Z_fine,
            cmap="plasma", alpha=0.75,
            linewidth=0.2, antialiased=True,
            rstride=1, cstride=1,
        )

        # --- Axes ---
        ax.set_xlabel(SWEEP_LABELS.get(sweep_col, sweep_col), fontsize=6, labelpad=6)
        ax.set_ylabel(_KPI_YLABEL_3D.get(kpi, kpi), fontsize=6, labelpad=6)

        if kpi in ("B_Vmin", "B_Vmax", "B_VminVmax"):
            ax.set_zlabel("N° Buses", fontsize=6, labelpad=4)
        else:
            ax.set_zlabel("Probability (%)", fontsize=6, labelpad=4)

        ax.set_xticks(pen_levels)
        ax.set_xticklabels([str(int(p)) for p in pen_levels], fontsize=4.5)

        if kpi == "Energy_Losses":
            idx = np.linspace(0, len(kpi_vals) - 1, 6, dtype=int)
            ax.set_yticks(kpi_vals[idx])
            ax.set_yticklabels([f"{int(kpi_vals[k]/1000)}k" for k in idx],
                               fontsize=4.5)
        else:
            max_val = int(df[kpi].max())
            step = 2 if max_val > 8 else 1
            shown_ticks = np.arange(0, max_val + 1, step)
            ax.set_yticks(shown_ticks)
            ax.set_yticklabels([str(int(v)) for v in shown_ticks], fontsize=5)

        ax.tick_params(axis="z", labelsize=4.5)
        ax.view_init(elev=28, azim=-50)
        ax.set_zlim(bottom=0)

        fig.subplots_adjust(left=0.05, right=0.95, bottom=0.08, top=0.95)

        for fmt in ["png", "pdf"]:
            path = os.path.join(self.output_dir, f"hist3d_{kpi}.{fmt}")
            fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"    Saved: hist3d_{kpi}.png / .pdf")

    # ------------------------------------------------------------------
    # 2D slice at fixed penetration
    # ------------------------------------------------------------------

    def plot_2d_slice(self, kpi: str, pen_pv_fixed: float = 50.0):
        sweep_col, secondary_col = detect_sweep_col(self.df)
        available = sorted(self.df[sweep_col].unique())
        if pen_pv_fixed not in available:
            print(f"  [WARN] {sweep_col}={pen_pv_fixed} not available. "
                  f"Levels: {available}")
            return

        apply_style()
        plt.rcParams.update({"axes.grid.axis": "y"})   # histograma 2D: grid horizontal solamente

        sub = self.df.loc[self.df[sweep_col] == pen_pv_fixed, kpi]
        secondary_val = self.df.loc[
            self.df[sweep_col] == pen_pv_fixed, secondary_col
        ].iloc[0]

        if len(sub) == 0:
            print(f"  [SKIP] No data for {kpi} at {sweep_col}={pen_pv_fixed}")
            return

        if sub.nunique() <= 1 and sub.iloc[0] == 0:
            print(f"  [SKIP] {kpi} is all zeros at {sweep_col}={pen_pv_fixed}, skipping 2D slice.")
            return

        fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)

        if kpi == "Energy_Losses":
            edges = np.arange(
                self.df[kpi].min() // _BIN_WIDTH_ENERGY * _BIN_WIDTH_ENERGY,
                self.df[kpi].max() + _BIN_WIDTH_ENERGY,
                _BIN_WIDTH_ENERGY,
            )
            counts, _ = np.histogram(sub, bins=edges)
            centers = (edges[:-1] + edges[1:]) / 2
            total = counts.sum()
            probs = counts / total * 100.0 if total > 0 else counts * 0.0

            bars = ax.bar(centers, probs, width=_BIN_WIDTH_ENERGY * 0.8,
                          color="#4393C3", edgecolor="black", linewidth=0.5)
            ax.set_xticks(centers)
            ax.set_xticklabels([f"{int(c/1000)}k" for c in centers],
                               fontsize=5, rotation=45)
            x_vals = centers
        else:
            max_val = int(sub.max()) if len(sub) > 0 else 0
            kpi_vals = np.arange(0, max_val + 1)
            n = len(sub)
            probs = np.array([(sub == v).sum() / n * 100.0
                              for v in kpi_vals]) if n > 0 else kpi_vals * 0.0

            bars = ax.bar(kpi_vals, probs, width=0.7,
                          color="#4393C3", edgecolor="black", linewidth=0.5)
            ax.set_xticks(kpi_vals)
            x_vals = kpi_vals

        for bar, p in zip(bars, probs):
            if p > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.5,
                        f"{p:.1f}%", ha="center", va="bottom", fontsize=4.5)

        ax.set_xlabel(_KPI_YLABEL_2D.get(kpi, kpi), labelpad=4)
        ax.set_ylabel("Probability (%)", labelpad=4)
        sweep_short = SWEEP_SHORT_LABELS.get(sweep_col, sweep_col)
        secondary_short = SWEEP_SHORT_LABELS.get(secondary_col, secondary_col)
        title_str = f"{sweep_short} = {int(pen_pv_fixed)}%  |  {secondary_short} = {int(secondary_val)}%"
        ax.set_title(title_str,
                     fontsize=6, pad=4)
        ax.set_ylim(0, max(probs) * 1.25 if max(probs) > 0 else 1)

        fig.tight_layout(pad=0.5)

        for fmt in ["png", "pdf"]:
            path = os.path.join(
                self.output_dir,
                f"hist2d_{kpi}_PV{int(pen_pv_fixed)}.{fmt}",
            )
            fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"    Saved: hist2d_{kpi}_PV{int(pen_pv_fixed)}.png / .pdf")

    # ------------------------------------------------------------------
    # Internal probability calculators
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_integer(df, pen_levels, kpi, sweep_col="Pen_PV"):
        max_val = int(df[kpi].max())
        kpi_vals = np.arange(0, max_val + 1)
        prob = np.zeros((len(pen_levels), len(kpi_vals)))
        for i, pen in enumerate(pen_levels):
            sub = df.loc[df[sweep_col] == pen, kpi]
            n = len(sub)
            if n == 0:
                continue
            for j, v in enumerate(kpi_vals):
                prob[i, j] = (sub == v).sum() / n * 100.0
        return kpi_vals, prob

    @staticmethod
    def _calc_continuous(df, pen_levels, kpi, sweep_col="Pen_PV"):
        lo = df[kpi].min()
        hi = df[kpi].max()
        edges = np.arange(
            lo // _BIN_WIDTH_ENERGY * _BIN_WIDTH_ENERGY,
            hi + _BIN_WIDTH_ENERGY,
            _BIN_WIDTH_ENERGY,
        )
        centers = (edges[:-1] + edges[1:]) / 2
        prob = np.zeros((len(pen_levels), len(centers)))
        for i, pen in enumerate(pen_levels):
            sub = df.loc[df[sweep_col] == pen, kpi]
            counts, _ = np.histogram(sub, bins=edges)
            total = counts.sum()
            if total > 0:
                prob[i, :] = counts / total * 100.0
        return centers, prob


if __name__ == "__main__":
    csv_path = (sys.argv[1] if len(sys.argv) > 1
                else "results/resultados_18Bus_PV100_BESS0_EV0_DC25.csv")

    PEN_FIXED = 50.0

    plotter = Histogram3DPlotter(csv_path=csv_path)

    plotter.plot_all(smooth=True)

    for kpi in _KPIS:
        print(f"  Generating 2D slice at PV={PEN_FIXED}%: {kpi}")
        plotter.plot_2d_slice(kpi=kpi, pen_pv_fixed=PEN_FIXED)
