# validate_modes.py
"""
Validates that SCENARIO_MODE "replace" and "full" produce identical KPI
results for the same random seed.

Runs N_ITER Monte Carlo iterations over PENETRATION_LEVELS in both modes
sequentially, then compares every KPI column. If both modes are correct,
results must be bit-for-bit identical (same seed → same allocations → same
OpenDSS simulation → same outputs).

Usage:
    python validate_modes.py
"""

import os
import types
import numpy as np
import pandas as pd
import config as cfg
from core.monte_carlo import run_monte_carlo

# =============================================================================
# VALIDATOR SETTINGS
# =============================================================================

N_ITER             = 10
SEED               = 42
PENETRATION_LEVELS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# KPI columns compared between modes (must be numerically identical)
KPI_COLS = [
    "B_Vmin", "B_Vmax", "B_VminVmax",
    "Vmin_24h", "Vmax_24h",
    "Sev_Vmin_pct", "Sev_Vmax_pct", "Sev_VminVmax_pct",
    "Trafo_Loading_pct", "Energy_Losses",
    "Max_PLosses", "Min_Fluxo_Subestacao",
]

# =============================================================================

RESULTS_DIR = os.path.join(cfg.BASE_DIR, "results")


def _make_cfg(mode):
    """
    Returns a SimpleNamespace copy of config with test-specific overrides.
    Writes to separate files so both runs coexist for inspection.
    """
    ns = types.SimpleNamespace(**{
        k: getattr(cfg, k)
        for k in dir(cfg)
        if not k.startswith("_") and isinstance(
            getattr(cfg, k), (str, int, float, bool, list, tuple, type(None))
        )
    })
    ns.SCENARIO_MODE        = mode
    ns.NUM_ITERATIONS       = N_ITER
    ns.RANDOM_SEED          = SEED
    ns.PENETRATION_LEVELS_PV = PENETRATION_LEVELS
    ns.KEEP_SCENARIO_FILES  = True
    ns.ENABLE_PARALLEL      = False

    # Derived paths that depend on SCENARIO_MODE or the output filename
    ns.RESULTS_FILE  = os.path.join(RESULTS_DIR, f"validate_{mode}.csv")
    ns.HOURLY_DIR    = os.path.join(RESULTS_DIR, f"hourly_validate_{mode}")
    ns.CENARIOS_DIR  = os.path.join(
        cfg.BASE_DIR, "data", "networks", cfg.NETWORK_NAME, "cenarios"
    )

    # Auto-compute result filename suffix (used internally by run_monte_carlo)
    _max_pv   = max(PENETRATION_LEVELS) if ns.ENABLE_PV   else 0
    _max_bess = round(_max_pv * ns.BESS_PV_RATIO) if ns.ENABLE_BESS  else 0
    _max_ev   = round(_max_pv * ns.EV_PV_RATIO)   if ns.ENABLE_EV_CS else 0
    _max_dc   = round(_max_pv * ns.DC_PV_RATIO)   if ns.ENABLE_DC    else 0
    ns.RESULTS_FILE = os.path.join(
        RESULTS_DIR,
        f"validate_{mode}_{cfg.NETWORK_NAME}_PV{_max_pv}_BESS{_max_bess}"
        f"_EV{_max_ev}_DC{_max_dc}.csv"
    )

    return ns


def main():
    SEP = "=" * 55

    print(SEP)
    print("  VALIDATOR — replace vs full mode")
    print(f"  N={N_ITER}  seed={SEED}  network={cfg.NETWORK_NAME}")
    print(f"  Penetration levels: {PENETRATION_LEVELS}")
    print(SEP)

    cfg_replace = _make_cfg("replace")
    cfg_full    = _make_cfg("full")

    print(f"\n[1/2] Running REPLACE mode  ({N_ITER * len(PENETRATION_LEVELS)} iterations)...")
    run_monte_carlo(cfg_replace)

    print(f"\n[2/2] Running FULL mode  ({N_ITER * len(PENETRATION_LEVELS)} iterations)...")
    run_monte_carlo(cfg_full)

    print(f"\n  Comparing results...")

    df_r = pd.read_csv(cfg_replace.RESULTS_FILE)
    df_f = pd.read_csv(cfg_full.RESULTS_FILE)

    if len(df_r) != len(df_f):
        print(f"\n  VALIDATION FAILED — row count mismatch: "
              f"replace={len(df_r)}, full={len(df_f)}")
        return

    # Sort by Seed for reliable row-to-row comparison
    df_r = df_r.sort_values("Seed").reset_index(drop=True)
    df_f = df_f.sort_values("Seed").reset_index(drop=True)

    errors   = []
    warnings = []

    for col in KPI_COLS:
        if col not in df_r.columns:
            warnings.append(f"  [WARN] Column not in replace CSV: {col}")
            continue
        if col not in df_f.columns:
            warnings.append(f"  [WARN] Column not in full CSV: {col}")
            continue
        diff = (df_r[col] - df_f[col]).abs()
        if not np.allclose(df_r[col].values, df_f[col].values, rtol=1e-9, atol=1e-9):
            errors.append(
                f"  {col:<28}  max_diff={diff.max():.3e}  "
                f"mean_diff={diff.mean():.3e}  n_nonzero={int((diff > 0).sum())}"
            )

    for w in warnings:
        print(w)

    print()
    if errors:
        print("  VALIDATION FAILED — differences found:")
        for e in errors:
            print(e)
        print(f"\n  replace CSV: {cfg_replace.RESULTS_FILE}")
        print(f"  full CSV:    {cfg_full.RESULTS_FILE}")
    else:
        n_rows = len(df_r)
        print(f"  VALIDATION PASSED")
        print(f"  {n_rows} rows x {len(KPI_COLS)} KPI columns — all identical.")
        print(f"\n  replace CSV: {cfg_replace.RESULTS_FILE}")
        print(f"  full CSV:    {cfg_full.RESULTS_FILE}")

    print(SEP)


if __name__ == "__main__":
    main()
