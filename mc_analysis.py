# mc_analysis.py
"""
Monte Carlo Convergence Analysis Tool.

Answers the key scientific question: how many iterations (N) are needed
for the simulation statistics to be stable and trustworthy?

Two modes:
  "single"  — subsamples one large CSV at increasing N values.
               No new simulations needed — convergence is assessed from
               the data already collected.
  "compare" — loads multiple CSVs of different sizes and compares their
               distributions directly (e.g. N=100 vs N=500 vs N=1000).

Five figures produced (mode "single"):
  Fig 1 — Violin + jitter by N        : distribution shape evolution
  Fig 2 — ECDF comparison by N        : cumulative distribution convergence
  Fig 3 — CV heatmap                  : coefficient of variation across
                                        all penetration levels × all N
  Fig 4 — Convergence curve           : mean + P10/P90 vs N with threshold
  Fig 5 — SE_MC curve                 : standard error vs N with 1/sqrt(N) ref.

Plus a convergence_summary.csv table: minimum N per KPI per penetration level.

Usage:
    Edit the ANALYSIS SETTINGS block below, then run:
        python mc_analysis.py
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plots.style import apply_style, save_figure, STYLE, TECH_COLORS, detect_sweep_col

# =============================================================================
# ANALYSIS SETTINGS  —  edit this block
# =============================================================================

MODE = "single"   # "single" → subsample one large CSV
                  # "compare" → compare multiple CSVs side by side

# Mode "single": path to one large CSV (more iterations = better baseline)
CSV_FILE = "results/results_18Bus_PV100_BESS0_EV0_DC0.csv"

# Mode "compare": {label: csv_path} — labels appear in plot legends and axes
CSV_FILES = {
    "N=100":  "results/results_18Bus_PV100_BESS0_EV0_DC0_N100.csv",
    "N=500":  "results/results_18Bus_PV100_BESS0_EV0_DC0_N500.csv",
    "N=1000": "results/results_18Bus_PV100_BESS0_EV0_DC0_N1000.csv",
}

# KPI used for the deep-dive figures (Figs 1, 2, 4)
KPI_PRIMARY = "Vmax_24h"

# KPIs used in the heatmap (Fig 3), SE_MC (Fig 5), and summary table
KPI_LIST = [
    "B_VminVmax",
    "Sev_VminVmax_pct",
    "Vmax_24h",
    "Trafo_Loading_pct",
    "Energy_Losses",
]

# Penetration level for single-level deep-dive figures (Figs 1, 2, 4)
# If not found in the data, the closest available level is used.
PENETRATION_FOCUS = 50

# N values to evaluate in mode "single" (auto-capped at available rows per level)
SUBSAMPLE_SIZES = [10, 30, 50, 100, 500, 1000]

# Relative change threshold to declare convergence: 0.02 = 2%
CONVERGENCE_THRESHOLD = 0.02

OUTPUT_DIR = os.path.join("results", "mc_analysis")

# =============================================================================

# ── KPI display metadata ──────────────────────────────────────────────────────
_KPI_META = {
    "B_Vmin":            {"label": "Undervoltage buses",    "ylabel": "Buses (count)"},
    "B_Vmax":            {"label": "Overvoltage buses",     "ylabel": "Buses (count)"},
    "B_VminVmax":        {"label": "Affected buses",        "ylabel": "Buses with violation (count)"},
    "Sev_Vmin_pct":      {"label": "Undervoltage severity", "ylabel": "Severity (%)"},
    "Sev_Vmax_pct":      {"label": "Overvoltage severity",  "ylabel": "Severity (%)"},
    "Sev_VminVmax_pct":  {"label": "Combined severity",     "ylabel": "Severity (% bus x hour)"},
    "Vmin_24h":          {"label": "Min voltage 24h",       "ylabel": "Voltage (pu)"},
    "Vmax_24h":          {"label": "Max voltage 24h",       "ylabel": "Voltage (pu)"},
    "Trafo_Loading_pct": {"label": "Transformer loading",   "ylabel": "Peak loading (%)"},
    "Energy_Losses":     {"label": "Energy losses",         "ylabel": "Daily losses (kWh)"},
    "Max_PLosses":       {"label": "Peak active losses",    "ylabel": "Peak losses (kW)"},
}

_FALLBACK_META = {"label": "KPI", "ylabel": "Value"}


def _meta(kpi):
    return _KPI_META.get(kpi, _FALLBACK_META)


# =============================================================================
# 1. DATA LOADING
# =============================================================================

def _load_data():
    """
    Returns (df_single, df_compare_dict) depending on MODE.
    df_single     : full DataFrame for mode "single" (None in compare mode)
    df_compare_dict: {label: DataFrame} for mode "compare" (None in single mode)
    """
    if MODE == "single":
        path = CSV_FILE if os.path.isabs(CSV_FILE) else os.path.join(
            os.path.dirname(os.path.abspath(__file__)), CSV_FILE)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"CSV not found: {path}\n"
                "Update CSV_FILE in the ANALYSIS SETTINGS block."
            )
        df = pd.read_csv(path)
        if "Penetration_Level" not in df.columns:
            sweep_col, _ = detect_sweep_col(df)
            df["Penetration_Level"] = df[sweep_col]
        print(f"  Loaded: {path}  ({len(df):,} rows)")
        return df, None

    elif MODE == "compare":
        dfs = {}
        base = os.path.dirname(os.path.abspath(__file__))
        for label, path in CSV_FILES.items():
            full = path if os.path.isabs(path) else os.path.join(base, path)
            if not os.path.isfile(full):
                print(f"  [WARN] CSV not found for '{label}': {full}. Skipped.")
                continue
            df = pd.read_csv(full)
            if "Penetration_Level" not in df.columns:
                sweep_col, _ = detect_sweep_col(df)
                df["Penetration_Level"] = df[sweep_col]
            dfs[label] = df
            print(f"  Loaded [{label}]: {full}  ({len(df):,} rows)")
        if not dfs:
            raise ValueError("No valid CSV files found in CSV_FILES. Check paths.")
        return None, dfs

    else:
        raise ValueError(f"Unknown MODE '{MODE}'. Use 'single' or 'compare'.")


# =============================================================================
# 2. CORE ENGINE: SUBSAMPLE STATISTICS
# =============================================================================

def _subsample_stats(df, sizes, kpis):
    """
    For each (penetration_level, n) combination, computes statistics on the
    first n rows of that penetration level's group.

    Returns: {kpi: DataFrame} where each DataFrame has columns:
        penetration_level, n, mean, std, p10, p50, p90, se_mc, cv, rel_err
    """
    all_rows = {kpi: [] for kpi in kpis}

    for pen_level, group in df.groupby("Penetration_Level"):
        group = group.reset_index(drop=True)
        n_max = len(group)

        # Compute full-N baselines for relative error
        baselines = {}
        for kpi in kpis:
            if kpi not in group.columns:
                continue
            baselines[kpi] = float(group[kpi].mean())

        # Deduplicate sizes capped at n_max
        effective_sizes = sorted(set(min(n, n_max) for n in sizes))
        # Always include n_max as the final reference point
        if n_max not in effective_sizes:
            effective_sizes.append(n_max)

        for n_actual in effective_sizes:
            subset = group.iloc[:n_actual]
            for kpi in kpis:
                if kpi not in subset.columns:
                    continue
                vals = subset[kpi].dropna().values
                if len(vals) == 0:
                    continue

                mean_v = float(np.mean(vals))
                std_v  = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
                se_mc  = std_v / np.sqrt(n_actual)
                cv     = std_v / abs(mean_v) if abs(mean_v) > 1e-10 else 0.0

                baseline = baselines.get(kpi, mean_v)
                rel_err  = (abs(mean_v - baseline) / abs(baseline)
                            if abs(baseline) > 1e-10 else 0.0)

                all_rows[kpi].append({
                    "penetration_level": pen_level,
                    "n":                 n_actual,
                    "mean":              mean_v,
                    "std":               std_v,
                    "p10":               float(np.percentile(vals, 10)),
                    "p50":               float(np.percentile(vals, 50)),
                    "p90":               float(np.percentile(vals, 90)),
                    "se_mc":             se_mc,
                    "cv":                cv,
                    "rel_err":           rel_err,
                })

    return {kpi: pd.DataFrame(rows) for kpi, rows in all_rows.items() if rows}


def _closest_pen(df, target):
    """Returns the penetration level in the data closest to target."""
    levels = sorted(df["Penetration_Level"].unique())
    return min(levels, key=lambda x: abs(x - target))


# =============================================================================
# 3. FIGURE 1 — VIOLIN + JITTER BY N
# =============================================================================

def _fig1_violin_jitter(df_full, kpi, pen, sizes, out_dir):
    """
    One violin per subsample size at the target penetration level.
    Shows how the distribution shape stabilizes as N grows.
    """
    group = df_full[df_full["Penetration_Level"] == pen].reset_index(drop=True)
    n_max = len(group)
    valid = sorted(set(min(n, n_max) for n in sizes))

    apply_style()
    fig, ax = plt.subplots(figsize=STYLE["figsize_double"])

    blues   = cm.Blues
    n_cols  = len(valid)
    colors  = [blues(0.30 + 0.55 * i / max(n_cols - 1, 1)) for i in range(n_cols)]
    rng     = np.random.default_rng(42)
    jitter_w = 0.15

    for i, n in enumerate(valid):
        vals = group[kpi].iloc[:n].dropna().values
        if len(vals) == 0:
            continue

        parts = ax.violinplot(vals, positions=[i], widths=0.65,
                              showmedians=False, showmeans=False,
                              showextrema=True)
        for pc in parts["bodies"]:
            pc.set_facecolor(colors[i])
            pc.set_edgecolor(colors[i])
            pc.set_alpha(0.55)
        for key in ("cbars", "cmins", "cmaxes"):
            if key in parts:
                parts[key].set_color(colors[i])
                parts[key].set_linewidth(0.7)

        # Jitter scatter
        jitter = rng.uniform(-jitter_w, jitter_w, size=len(vals))
        ax.scatter(i + jitter, vals, s=5, color=colors[i], alpha=0.45,
                   linewidths=0, zorder=3)

        # Median (solid) and mean (dashed)
        ax.hlines(np.median(vals), i - 0.25, i + 0.25,
                  colors="black", linewidth=1.0, zorder=5)
        ax.hlines(np.mean(vals),   i - 0.20, i + 0.20,
                  colors="black", linestyles="--", linewidth=0.7, zorder=5)

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels([f"N={n}" for n in valid])
    ax.set_xlabel("Sample size (N)")
    ax.set_ylabel(_meta(kpi)["ylabel"])
    ax.set_title(
        f"Distribution evolution — {_meta(kpi)['label']}  |  "
        f"Penetration = {pen}%",
        pad=4,
    )

    legend_handles = [
        Line2D([0], [0], color="black", linewidth=1.0, label="Median"),
        Line2D([0], [0], color="black", linewidth=0.7, linestyle="--", label="Mean"),
    ]
    ax.legend(handles=legend_handles, loc="upper right")
    fig.tight_layout(pad=0.5)
    save_figure(fig, os.path.join(out_dir, f"fig1_violin_{kpi}_pen{int(pen)}"))
    print(f"    Fig 1 saved: fig1_violin_{kpi}_pen{int(pen)}")


# =============================================================================
# 4. FIGURE 2 — ECDF COMPARISON BY N
# =============================================================================

def _fig2_ecdf(df_full, kpi, pen, sizes, out_dir):
    """
    Empirical CDF for each subsample size at the target penetration level.
    Lines converge as N grows — divergence reveals instability.
    """
    group = df_full[df_full["Penetration_Level"] == pen].reset_index(drop=True)
    n_max = len(group)
    valid = sorted(set(min(n, n_max) for n in sizes))

    apply_style()
    fig, ax = plt.subplots(figsize=STYLE["figsize_double"])

    norm  = plt.Normalize(vmin=valid[0], vmax=valid[-1])
    cmap  = cm.viridis

    for n in valid:
        vals = np.sort(group[kpi].iloc[:n].dropna().values)
        if len(vals) == 0:
            continue
        y = np.arange(1, len(vals) + 1) / len(vals)
        ax.step(vals, y, where="post", color=cmap(norm(n)), linewidth=0.9, alpha=0.85)

    # Reference percentiles from the full dataset
    full_vals = group[kpi].dropna().values
    for pct, ls, label, va in [(10, ":", "P10", "bottom"),
                                (50, "--", "P50", "bottom"),
                                (90, ":",  "P90", "top")]:
        val = float(np.percentile(full_vals, pct))
        ax.axvline(val, color="#555555", linestyle=ls, linewidth=0.6, alpha=0.6)
        y_pos = 0.05 if va == "bottom" else 0.93
        ax.text(val, y_pos, f" {label}", fontsize=6, va=va, ha="left",
                color="#555555", transform=ax.get_xaxis_transform())

    # Colorbar for N scale
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, pad=0.02, aspect=25)
    cb.set_label("Sample size (N)", fontsize=STYLE["font_size_legend"])

    ax.set_xlabel(_meta(kpi)["ylabel"])
    ax.set_ylabel("Cumulative probability F(x)")
    ax.set_ylim(0, 1)
    ax.set_title(
        f"ECDF convergence — {_meta(kpi)['label']}  |  "
        f"Penetration = {pen}%",
        pad=4,
    )
    fig.tight_layout(pad=0.5)
    save_figure(fig, os.path.join(out_dir, f"fig2_ecdf_{kpi}_pen{int(pen)}"))
    print(f"    Fig 2 saved: fig2_ecdf_{kpi}_pen{int(pen)}")


# =============================================================================
# 5. FIGURE 3 — CV HEATMAP
# =============================================================================

def _fig3_cv_heatmap(stats_df, kpi, out_dir):
    """
    Coefficient of variation (std/mean) for every (penetration_level, N) cell.
    Red = high CV = unstable; green = low CV = stable.
    """
    if stats_df.empty:
        return

    pivot = stats_df.pivot_table(
        index="n", columns="penetration_level", values="cv", aggfunc="mean"
    ).sort_index(ascending=False)

    pen_levels = list(pivot.columns)
    n_values   = list(pivot.index)
    Z          = pivot.values
    Z_plot     = np.where(np.isnan(Z), 0.0, Z)

    apply_style()
    fig, ax = plt.subplots(figsize=STYLE["figsize_double"])

    vmax = max(0.5, float(np.nanpercentile(Z_plot[Z_plot > 0], 95))) if Z_plot.any() else 0.5
    im = ax.pcolormesh(
        np.arange(len(pen_levels) + 1),
        np.arange(len(n_values) + 1),
        Z_plot,
        cmap="RdYlGn_r", vmin=0, vmax=vmax,
    )

    # Cell annotations
    for i, _ in enumerate(n_values):
        for j, _ in enumerate(pen_levels):
            val = Z[i, j]
            if np.isnan(val):
                continue
            text_color = "white" if val > vmax * 0.65 else "black"
            ax.text(j + 0.5, i + 0.5, f"{val:.2f}",
                    ha="center", va="center", fontsize=5.5, color=text_color)

    cb = fig.colorbar(im, ax=ax, pad=0.02, aspect=25)
    cb.set_label("CV = std / mean", fontsize=STYLE["font_size_legend"])

    ax.set_xticks(np.arange(len(pen_levels)) + 0.5)
    ax.set_xticklabels(
        [f"{int(p)}%" for p in pen_levels],
        rotation=45 if len(pen_levels) > 7 else 0,
    )
    ax.set_yticks(np.arange(len(n_values)) + 0.5)
    ax.set_yticklabels([f"N={n}" for n in n_values])
    ax.set_xlabel("Penetration level (%)")
    ax.set_ylabel("Sample size (N)")
    ax.set_title(
        f"Coefficient of variation — {_meta(kpi)['label']}",
        pad=4,
    )
    fig.tight_layout(pad=0.5)
    save_figure(fig, os.path.join(out_dir, f"fig3_cv_heatmap_{kpi}"))
    print(f"    Fig 3 saved: fig3_cv_heatmap_{kpi}")


# =============================================================================
# 6. FIGURE 4 — CONVERGENCE CURVE
# =============================================================================

def _fig4_convergence_curve(stats_df, kpi, pen, threshold, out_dir):
    """
    Mean + P10/P90 band vs N at the target penetration level.
    A vertical dashed line marks where convergence is first reached.
    """
    sub = stats_df[stats_df["penetration_level"] == pen].sort_values("n")
    if sub.empty:
        return

    # Exclude the last point (n_max) from convergence detection since rel_err = 0 by construction
    ns     = sub["n"].values
    colors = {
        "mean": TECH_COLORS["PV"],
        "p50":  TECH_COLORS["BESS"],
        "band": TECH_COLORS["PV"],
    }

    apply_style()
    fig, ax = plt.subplots(figsize=STYLE["figsize_double"])

    ax.fill_between(ns, sub["p10"], sub["p90"],
                    alpha=STYLE["band_alpha"], color=colors["band"], label="P10–P90")
    ax.plot(ns, sub["mean"], color=colors["mean"], linewidth=1.4,
            marker="o", markersize=3, markeredgewidth=0, label="Mean", zorder=4)
    ax.plot(ns, sub["p50"], color=colors["p50"], linewidth=0.9,
            linestyle=":", marker="s", markersize=2, markeredgewidth=0,
            label="Median (P50)", zorder=3)
    ax.plot(ns, sub["p10"], color=colors["band"], linewidth=0.7,
            linestyle="--", alpha=0.6, label="P10 / P90")
    ax.plot(ns, sub["p90"], color=colors["band"], linewidth=0.7,
            linestyle="--", alpha=0.6)

    # Convergence marker — exclude n_max (rel_err = 0 by definition)
    sub_inner = sub.iloc[:-1]  # exclude last row (full N)
    converged = sub_inner[sub_inner["rel_err"] <= threshold]
    if not converged.empty:
        n_conv = int(converged.iloc[0]["n"])
        ax.axvline(n_conv, color="black", linestyle="--", linewidth=0.8, alpha=0.75,
                   label=f"Converged (N={n_conv})")
        ylim = ax.get_ylim()
        ax.text(n_conv * 1.02, ylim[0] + 0.92 * (ylim[1] - ylim[0]),
                f"N={n_conv}", fontsize=6, va="top", ha="left", color="black")

    ax.set_xlabel("Sample size (N)")
    ax.set_ylabel(_meta(kpi)["ylabel"])
    ax.set_title(
        f"Convergence — {_meta(kpi)['label']}  |  "
        f"Penetration = {pen}%  (threshold {threshold*100:.0f}%)",
        pad=4,
    )
    ax.legend(loc="best", fontsize=STYLE["font_size_legend"])
    fig.tight_layout(pad=0.5)
    save_figure(fig, os.path.join(out_dir, f"fig4_convergence_{kpi}_pen{int(pen)}"))
    print(f"    Fig 4 saved: fig4_convergence_{kpi}_pen{int(pen)}")


# =============================================================================
# 7. FIGURE 5 — SE_MC CURVE
# =============================================================================

def _fig5_se_mc(stats_dict, kpi_list, out_dir):
    """
    SE_MC = std/sqrt(N) per penetration level vs N.
    Overlay theoretical 1/sqrt(N) reference to confirm expected convergence rate.
    """
    for kpi in kpi_list:
        if kpi not in stats_dict:
            continue
        stats_df = stats_dict[kpi]
        pen_levels = sorted(stats_df["penetration_level"].unique())
        if not pen_levels:
            continue

        apply_style()
        fig, ax = plt.subplots(figsize=STYLE["figsize_double"])

        blues  = cm.Blues
        n_pens = len(pen_levels)
        colors = [blues(0.30 + 0.60 * i / max(n_pens - 1, 1)) for i in range(n_pens)]

        ref_pen  = pen_levels[-1]
        ref_data = stats_df[stats_df["penetration_level"] == ref_pen].sort_values("n")

        for i, pen in enumerate(pen_levels):
            sub = stats_df[stats_df["penetration_level"] == pen].sort_values("n")
            if sub.empty:
                continue
            ax.plot(sub["n"], sub["se_mc"],
                    color=colors[i], linewidth=1.0,
                    marker="o", markersize=2.5, markeredgewidth=0,
                    label=f"{int(pen)}%")

        # Theoretical 1/sqrt(N) fitted to the reference penetration's first point
        if len(ref_data) >= 2:
            n0   = float(ref_data["n"].iloc[0])
            se0  = float(ref_data["se_mc"].iloc[0])
            k    = se0 * np.sqrt(n0)
            ns_t = np.linspace(n0, float(ref_data["n"].iloc[-1]), 120)
            ax.plot(ns_t, k / np.sqrt(ns_t),
                    color="black", linewidth=0.8, linestyle="--", alpha=0.55,
                    label="1/√N  (ref.)")

        ax.set_xlabel("Sample size (N)")
        ax.set_ylabel("SE_MC = std / √N")
        ax.set_title(
            f"Standard error of the mean — {_meta(kpi)['label']}",
            pad=4,
        )
        ax.legend(title="Penetration", fontsize=STYLE["font_size_legend"],
                  title_fontsize=STYLE["font_size_legend"])
        fig.tight_layout(pad=0.5)
        save_figure(fig, os.path.join(out_dir, f"fig5_se_mc_{kpi}"))
        print(f"    Fig 5 saved: fig5_se_mc_{kpi}")


# =============================================================================
# 8. MODE "COMPARE" — BOXPLOT COMPARISON ACROSS CSVs
# =============================================================================

def _fig_compare_boxplots(dfs_dict, kpi, pen, out_dir):
    """
    One boxplot per CSV label at the target penetration level.
    Directly shows whether distributions agree across different N runs.
    """
    labels = list(dfs_dict.keys())
    data_per_label = []

    for label, df in dfs_dict.items():
        sub = df[df["Penetration_Level"] == pen][kpi].dropna().values
        data_per_label.append(sub)

    if all(len(d) == 0 for d in data_per_label):
        return

    apply_style()
    fig, ax = plt.subplots(figsize=STYLE["figsize_double"])

    bp = ax.boxplot(
        data_per_label,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 1.0},
        whiskerprops={"color": "#555555", "linewidth": 0.7},
        capprops={"color": "#555555", "linewidth": 0.7},
    )
    blues = cm.Blues
    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(blues(0.30 + 0.55 * i / max(len(labels) - 1, 1)))
        patch.set_alpha(0.7)
        patch.set_linewidth(0.6)

        # Mean dot overlay
        vals = data_per_label[i]
        if len(vals) > 0:
            ax.plot(i + 1, np.mean(vals), marker="D", markersize=4,
                    color="black", markeredgewidth=0, zorder=5)

    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels)
    ax.set_xlabel("Simulation set")
    ax.set_ylabel(_meta(kpi)["ylabel"])
    ax.set_title(
        f"Distribution comparison — {_meta(kpi)['label']}  |  "
        f"Penetration = {pen}%",
        pad=4,
    )
    ax.legend(
        [Line2D([0], [0], marker="D", color="black", markersize=4,
                linewidth=0, label="Mean")],
        ["Mean"], loc="upper right",
    )
    fig.tight_layout(pad=0.5)
    save_figure(fig, os.path.join(out_dir, f"compare_boxplot_{kpi}_pen{int(pen)}"))
    print(f"    Compare boxplot saved: compare_boxplot_{kpi}_pen{int(pen)}")


# =============================================================================
# 9. CONVERGENCE SUMMARY TABLE
# =============================================================================

def _summary_table(stats_dict, kpi_list, threshold, out_dir):
    """
    For each (KPI, penetration_level), reports:
      N_min       — smallest N where relative change to N_max < threshold
      SE_at_Nmax  — standard error at full N
      CV_at_Nmax  — coefficient of variation at full N
    """
    rows = []

    for kpi in kpi_list:
        if kpi not in stats_dict:
            continue
        stats_df = stats_dict[kpi]

        for pen in sorted(stats_df["penetration_level"].unique()):
            sub = stats_df[stats_df["penetration_level"] == pen].sort_values("n")
            if sub.empty:
                continue

            n_max_row = sub.iloc[-1]

            # Exclude n_max row (rel_err = 0 by definition) before checking convergence
            sub_inner = sub.iloc[:-1]
            converged = sub_inner[sub_inner["rel_err"] <= threshold]

            n_min       = int(converged.iloc[0]["n"]) if not converged.empty else None
            se_at_nmax  = round(float(n_max_row["se_mc"]), 5)
            cv_at_nmax  = round(float(n_max_row["cv"]),    5)

            rows.append({
                "KPI":        kpi,
                "Pen_Level":  int(pen),
                "N_max":      int(n_max_row["n"]),
                "N_min":      n_min if n_min is not None else ">N_max",
                "SE_at_Nmax": se_at_nmax,
                "CV_at_Nmax": cv_at_nmax,
                "Converged":  "Yes" if n_min is not None else "No",
            })

    if not rows:
        print("  [WARN] No convergence data to summarize.")
        return

    df_summary = pd.DataFrame(rows)
    csv_path = os.path.join(out_dir, "convergence_summary.csv")
    df_summary.to_csv(csv_path, index=False, encoding="utf-8")

    # Console table
    W = 70
    print("\n" + "=" * W)
    print(f"  CONVERGENCE SUMMARY  (threshold: {threshold * 100:.0f}% relative change)")
    print("=" * W)
    print(f"  {'KPI':<22} {'Pen%':>5} {'N_max':>7} {'N_min':>8} "
          f"{'SE@Nmax':>9} {'CV@Nmax':>9} {'OK':>4}")
    print("-" * W)
    for _, r in df_summary.iterrows():
        print(f"  {r['KPI']:<22} {r['Pen_Level']:>5} {r['N_max']:>7} "
              f"{str(r['N_min']):>8} {r['SE_at_Nmax']:>9.5f} "
              f"{r['CV_at_Nmax']:>9.5f} {r['Converged']:>4}")
    print("=" * W)
    print(f"  Table saved: {csv_path}")


# =============================================================================
# 10. MAIN ORCHESTRATION
# =============================================================================

def main():
    import time
    t0 = time.time()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 55)
    print(f"  MC Convergence Analysis")
    print(f"  Mode        : {MODE}")
    print(f"  Output dir  : {OUTPUT_DIR}")
    print("=" * 55)

    # ── Load data ──────────────────────────────────────────────
    df_single, df_compare = _load_data()

    # ── Validate KPI list ──────────────────────────────────────
    ref_df = df_single if df_single is not None else list(df_compare.values())[0]
    kpi_available = [k for k in KPI_LIST if k in ref_df.columns]
    kpi_missing   = [k for k in KPI_LIST if k not in ref_df.columns]
    if kpi_missing:
        print(f"  [WARN] KPIs not found in CSV, skipped: {kpi_missing}")
    if KPI_PRIMARY not in ref_df.columns:
        raise KeyError(
            f"KPI_PRIMARY '{KPI_PRIMARY}' not found in CSV. "
            f"Available: {list(ref_df.columns)}"
        )

    # ── Resolve PENETRATION_FOCUS ──────────────────────────────
    pen = _closest_pen(ref_df, PENETRATION_FOCUS)
    if pen != PENETRATION_FOCUS:
        print(f"  [INFO] PENETRATION_FOCUS={PENETRATION_FOCUS}% not found. "
              f"Using closest: {pen}%")

    # ===========================================================
    # MODE "single"
    # ===========================================================
    if MODE == "single":

        print(f"\n  Building subsample statistics...")
        all_kpis    = list(set([KPI_PRIMARY] + kpi_available))
        stats_dict  = _subsample_stats(df_single, SUBSAMPLE_SIZES, all_kpis)

        stats_primary = stats_dict.get(KPI_PRIMARY)
        if stats_primary is None or stats_primary.empty:
            raise ValueError(f"No statistics computed for KPI_PRIMARY '{KPI_PRIMARY}'.")

        print(f"\n  Generating figures for penetration = {pen}%...")

        print("\n  [Fig 1] Violin + jitter by N")
        _fig1_violin_jitter(df_single, KPI_PRIMARY, pen, SUBSAMPLE_SIZES, OUTPUT_DIR)

        print("\n  [Fig 2] ECDF comparison by N")
        _fig2_ecdf(df_single, KPI_PRIMARY, pen, SUBSAMPLE_SIZES, OUTPUT_DIR)

        print("\n  [Fig 3] CV heatmap (all penetration levels x all N)")
        for kpi in kpi_available:
            if kpi in stats_dict:
                _fig3_cv_heatmap(stats_dict[kpi], kpi, OUTPUT_DIR)

        print("\n  [Fig 4] Convergence curve")
        _fig4_convergence_curve(
            stats_primary, KPI_PRIMARY, pen, CONVERGENCE_THRESHOLD, OUTPUT_DIR
        )

        print("\n  [Fig 5] SE_MC curve (all penetration levels)")
        _fig5_se_mc(stats_dict, kpi_available, OUTPUT_DIR)

        print("\n  [Table] Convergence summary")
        _summary_table(stats_dict, kpi_available, CONVERGENCE_THRESHOLD, OUTPUT_DIR)

    # ===========================================================
    # MODE "compare"
    # ===========================================================
    elif MODE == "compare":

        print(f"\n  Generating comparison figures for penetration = {pen}%...")

        for kpi in [KPI_PRIMARY] + [k for k in kpi_available if k != KPI_PRIMARY]:
            print(f"\n  [Compare boxplot] {kpi}")
            _fig_compare_boxplots(df_compare, kpi, pen, OUTPUT_DIR)

        # Violin + jitter using CSV sizes as the x-axis positions
        print("\n  [Fig 1] Violin + jitter across CSV sets")
        apply_style()
        for kpi in [KPI_PRIMARY] + [k for k in kpi_available if k != KPI_PRIMARY]:
            labels = list(df_compare.keys())
            apply_style()
            fig, ax = plt.subplots(figsize=STYLE["figsize_double"])

            blues   = cm.Blues
            n_cols  = len(labels)
            colors  = [blues(0.30 + 0.55 * i / max(n_cols - 1, 1)) for i in range(n_cols)]
            rng     = np.random.default_rng(42)

            for i, (label, df) in enumerate(df_compare.items()):
                vals = df[df["Penetration_Level"] == pen][kpi].dropna().values
                if len(vals) == 0:
                    continue
                parts = ax.violinplot(vals, positions=[i], widths=0.65,
                                      showmedians=False, showmeans=False, showextrema=True)
                for pc in parts["bodies"]:
                    pc.set_facecolor(colors[i]); pc.set_alpha(0.55)
                for key in ("cbars", "cmins", "cmaxes"):
                    if key in parts:
                        parts[key].set_color(colors[i]); parts[key].set_linewidth(0.7)
                jitter = rng.uniform(-0.15, 0.15, size=len(vals))
                ax.scatter(i + jitter, vals, s=5, color=colors[i], alpha=0.45,
                           linewidths=0, zorder=3)
                ax.hlines(np.median(vals), i - 0.25, i + 0.25,
                          colors="black", linewidth=1.0, zorder=5)
                ax.hlines(np.mean(vals),   i - 0.20, i + 0.20,
                          colors="black", linestyles="--", linewidth=0.7, zorder=5)

            ax.set_xticks(range(n_cols))
            ax.set_xticklabels(labels)
            ax.set_xlabel("Simulation set")
            ax.set_ylabel(_meta(kpi)["ylabel"])
            ax.set_title(
                f"Distribution comparison — {_meta(kpi)['label']}  |  Pen. = {pen}%",
                pad=4,
            )
            fig.tight_layout(pad=0.5)
            save_figure(fig, os.path.join(OUTPUT_DIR, f"fig1_violin_compare_{kpi}_pen{int(pen)}"))
            print(f"    Saved: fig1_violin_compare_{kpi}_pen{int(pen)}")

    elapsed = time.time() - t0
    print(f"\n  Done. Elapsed: {elapsed:.1f} s")
    print(f"  Output: {os.path.abspath(OUTPUT_DIR)}/")
    print("=" * 55)


if __name__ == "__main__":
    main()
