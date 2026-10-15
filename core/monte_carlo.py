# project/core/monte_carlo.py
"""
Main Monte Carlo loop.
Supports two execution modes controlled by cfg.SCENARIO_MODE:

  "replace"  (default) — classic sequential mode. Four shared scenario DSS
             files are overwritten each iteration. Simple and robust.

  "full"     — one unique DSS file per iteration per DER, stored in cenarios/.
             Required for parallel execution. Hourly profiles are also written
             per-iteration and merged at the end into the same consolidated
             format as "replace" mode.

Parallel execution (cfg.ENABLE_PARALLEL = True) requires SCENARIO_MODE = "full".
Uses multiprocessing.Pool with a shared initializer to avoid re-loading heavy
data (irradiance matrices, profiles) on every task.
"""

import os
import glob
import random
import types
import numpy as np

from core.network import run_base_case, run_with_ders
from results.reporter import init_csv, append_row


# =============================================================================
# Internal helpers
# =============================================================================

def _merge_hourly_files(iter_dir, hourly_dir):
    """
    Reads all per-iteration hourly CSVs from iter_dir and writes the standard
    5 consolidated perfil24h_*.csv files in hourly_dir.
    Output format is identical to "replace" mode output.
    """
    import csv as _csv

    PROFILES = ["Pnet", "Plosses", "Trafo", "Vmin", "Vmax"]
    header   = (["Penetration_Level", "Pen_PV", "Pen_BESS", "Pen_EV", "Pen_DC", "Seed"]
                + [f"H{h}" for h in range(24)])

    rows_by_profile = {p: [] for p in PROFILES}
    all_files = sorted(glob.glob(os.path.join(iter_dir, "hourly_*.csv")))

    for fpath in all_files:
        with open(fpath, "r", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                profile = row.pop("Profile")
                if profile in rows_by_profile:
                    rows_by_profile[profile].append(row)

    for profile in PROFILES:
        out_path = os.path.join(hourly_dir, f"perfil24h_{profile}.csv")
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows_by_profile[profile])

    print(f"  Hourly merge: {len(all_files)} iteration files -> 5 consolidated CSVs")


def _build_cenario_paths(cenarios_dir, pen_pv, pen_bess, pen_ev, pen_dc, seed_it, mode):
    """Returns (path_pv, path_bess, path_ev, path_dc) for the given mode."""
    if mode == "full":
        return (
            os.path.join(cenarios_dir,
                f"cenario_PV_pen{int(round(pen_pv)):03d}_seed{seed_it}.dss"),
            os.path.join(cenarios_dir,
                f"cenario_BESS_pen{int(round(pen_bess)):03d}_seed{seed_it}.dss"),
            os.path.join(cenarios_dir,
                f"cenario_EV_pen{int(round(pen_ev)):03d}_seed{seed_it}.dss"),
            os.path.join(cenarios_dir,
                f"cenario_DC_pen{int(round(pen_dc)):03d}_seed{seed_it}.dss"),
        )
    else:  # replace
        return (
            os.path.join(cenarios_dir, "cenario_PV.dss"),
            os.path.join(cenarios_dir, "cenario_BESS.dss"),
            os.path.join(cenarios_dir, "cenario_EV.dss"),
            os.path.join(cenarios_dir, "cenario_DC.dss"),
        )


def _cfg_to_namespace(cfg):
    """
    Converts the config module to a picklable SimpleNamespace containing only
    primitive values (str, int, float, bool, list, tuple, None).
    Required for passing cfg to multiprocessing workers.
    """
    ns = {}
    for k in dir(cfg):
        if k.startswith("_"):
            continue
        v = getattr(cfg, k)
        if isinstance(v, (str, int, float, bool, list, tuple, type(None))):
            ns[k] = v
    return types.SimpleNamespace(**ns)


# =============================================================================
# Parallel worker
# =============================================================================

_worker_data = {}


def _worker_init(shared):
    """Called once per worker process to load shared read-only data."""
    global _worker_data
    _worker_data = shared


def _run_single_iteration(task):
    """
    Executes one Monte Carlo iteration in a worker process.

    Receives a lightweight task dict with iteration-specific scalars.
    Heavy data (base_result, irradiance matrices, profiles) is read from
    _worker_data, which is initialized once per process by _worker_init.

    Returns (kpi_row_dict, hourly_row_dict or None) — no shared file I/O.
    """
    import random as _random
    import numpy as _np

    cfg_ns         = _worker_data["cfg_ns"]
    base           = _worker_data["base"]
    cenarios_dir   = _worker_data["cenarios_dir"]
    hourly_enabled = _worker_data["hourly_enabled"]
    hourly_iter_dir = _worker_data.get("hourly_iter_dir")

    level    = task["level"]
    pen_pv   = task["pen_pv"]
    pen_bess = task["pen_bess"]
    pen_ev   = task["pen_ev"]
    pen_dc   = task["pen_dc"]
    seed_it  = task["seed_it"]
    count    = task["count"]

    if seed_it != 0:
        _random.seed(seed_it)
        _np.random.seed(seed_it)

    mt_buses   = base["mt_buses"]
    mt_kv      = base["mt_kv"]
    mt_phases  = base["mt_phases"]
    energy     = base["energy_kwh"]
    n_mt_total = base["n_mt_total"]

    path_pv, path_bess, path_ev, path_dc = _build_cenario_paths(
        cenarios_dir, pen_pv, pen_bess, pen_ev, pen_dc, seed_it, "full"
    )

    # --- PV ---
    pv_units = []
    if cfg_ns.ENABLE_PV:
        from modules.pv.pv_profiles  import sample_monthly_profile
        from modules.pv.pv_allocation import allocate_pv, generate_cenario_pv
        irr_matrix  = _worker_data["irr_matrix"]
        temp_matrix = _worker_data["temp_matrix"]
        irrad_pu, temp_c, psh, mes = sample_monthly_profile(irr_matrix, temp_matrix)
        pv_units, _ = allocate_pv(
            energy, pen_pv, psh,
            mt_buses, mt_kv, mt_phases,
            cfg_ns.PV_SIZES_KW, cfg_ns.PV_PROBS, cfg_ns.PV_POWER_FACTOR,
        )
        generate_cenario_pv(pv_units, irrad_pu, temp_c, path_pv, pen_pv, mes)
    else:
        open(path_pv, "w").close()

    # --- BESS ---
    bess_units = []
    if cfg_ns.ENABLE_BESS:
        from modules.bess.bess_allocation import allocate_bess, generate_cenario_bess
        from modules.bess.bess_profiles   import sample_dispatch_profile
        bess_profiles      = _worker_data["bess_profiles"]
        bess_profile_names = _worker_data["bess_profile_names"]
        bess_units, _ = allocate_bess(
            energy, pen_bess,
            mt_buses, mt_kv, mt_phases,
            cfg_ns.BESS_SIZES_KWH, cfg_ns.BESS_PROBS,
            cfg_ns.BESS_CHARGE_HOURS, cfg_ns.BESS_PLACEMENT,
            bess_profiles, bess_profile_names,
            pv_units=pv_units, power_factor=cfg_ns.BESS_POWER_FACTOR,
        )
        generate_cenario_bess(
            bess_units, path_bess, pen_bess,
            vminpu=cfg_ns.BESS_VMINPU, vmaxpu=cfg_ns.BESS_VMAXPU,
            eff_charge=cfg_ns.BESS_EFF_CHARGE, eff_discharge=cfg_ns.BESS_EFF_DISCHARGE,
        )
    else:
        open(path_bess, "w").close()

    # --- EV/CS ---
    ev_units = []
    if cfg_ns.ENABLE_EV_CS:
        from modules.ev_cs.ev_allocation import allocate_ev, generate_cenario_ev
        ev_profiles      = _worker_data["ev_profiles"]
        ev_profile_names = _worker_data["ev_profile_names"]
        ev_units, _ = allocate_ev(
            energy, pen_ev,
            mt_buses, mt_kv, mt_phases,
            cfg_ns.EV_SIZES_KW, cfg_ns.EV_PROBS,
            cfg_ns.EV_ELIGIBLE_BUSES,
            ev_profiles, ev_profile_names, cfg_ns.EV_POWER_FACTOR,
        )
        generate_cenario_ev(ev_units, path_ev, pen_ev)
    else:
        open(path_ev, "w").close()

    # --- DC ---
    dc_units = []
    if cfg_ns.ENABLE_DC:
        from modules.dc.dc_allocation import allocate_dc, generate_cenario_dc
        dc_profiles      = _worker_data["dc_profiles"]
        dc_profile_names = _worker_data["dc_profile_names"]
        dc_gen_profile   = _worker_data.get("dc_gen_profile")
        dc_units, _ = allocate_dc(
            energy, pen_dc,
            mt_buses, mt_kv, mt_phases,
            cfg_ns.NUM_DC, dc_profiles, dc_profile_names,
            cfg_ns.DC_PUE_RANGE, cfg_ns.DC_NOISE_BAND,
            excluded_buses=cfg_ns.EXCLUDED_BUSES,
        )
        generate_cenario_dc(
            dc_units, path_dc, pen_dc,
            enable_dc_gen=cfg_ns.ENABLE_DC_GEN,
            dc_self_supply_frac=cfg_ns.DC_SELF_SUPPLY_FRAC,
            dc_gen_profile=dc_gen_profile,
        )
    else:
        open(path_dc, "w").close()

    # --- Simulate ---
    sim = run_with_ders(
        cfg_ns.NETWORK_DSS_PATH, cfg_ns.TRANSFORMER_MVA,
        enable_pv=cfg_ns.ENABLE_PV,    path_pv=path_pv,
        enable_bess=cfg_ns.ENABLE_BESS, path_bess=path_bess,
        enable_ev=cfg_ns.ENABLE_EV_CS,  path_ev=path_ev,
        enable_dc=cfg_ns.ENABLE_DC,     path_dc=path_dc,
        n_mt_total=n_mt_total,
    )

    # --- Costs ---
    pv_kw_inst    = sum(u["pmpp_kw"]   for u in pv_units)
    bess_kwh_inst = sum(u["kwh_rated"] for u in bess_units)
    ev_kw_inst    = sum(u["kw"]        for u in ev_units)
    dc_kw_inst    = sum(u["peak_kw"]   for u in dc_units)
    energy_losses_kwh = float(_np.sum(sim["perfil_losses"]))

    costs = {
        "PV_kW_inst":     pv_kw_inst,
        "BESS_kWh_inst":  bess_kwh_inst,
        "EV_kW_inst":     ev_kw_inst,
        "DC_kW_inst":     dc_kw_inst,
        "Cost_PV_Local":  pv_kw_inst    * cfg_ns.PV_USD_PER_KW_LOCAL,
        "Cost_PV_Intl":   pv_kw_inst    * cfg_ns.PV_USD_PER_KW_INTL,
        "Cost_BESS_Local":bess_kwh_inst * cfg_ns.BESS_USD_PER_KWH_LOCAL,
        "Cost_BESS_Intl": bess_kwh_inst * cfg_ns.BESS_USD_PER_KWH_INTL,
        "Cost_EVCS_Local":ev_kw_inst    * cfg_ns.EVCS_USD_PER_KW_LOCAL,
        "Cost_EVCS_Intl": ev_kw_inst    * cfg_ns.EVCS_USD_PER_KW_INTL,
        "Cost_DC":        dc_kw_inst    * cfg_ns.DC_USD_PER_KW,
        "Energy_Losses_USD": energy_losses_kwh * cfg_ns.ENERGY_LOSS_TARIFF_USD_PER_KWH,
    }
    costs["Cost_Total_Local"] = costs["Cost_PV_Local"] + costs["Cost_BESS_Local"] + costs["Cost_EVCS_Local"]
    costs["Cost_Total_Intl"]  = costs["Cost_PV_Intl"]  + costs["Cost_BESS_Intl"]  + costs["Cost_EVCS_Intl"]

    # --- Build KPI row dict (same structure as append_row expects) ---
    buses_vmin = sim["buses_vmin"]
    buses_vmax = sim["buses_vmax"]
    kpi_row = dict(
        level=level, pen_pv=pen_pv, pen_bess=pen_bess,
        pen_ev=pen_ev, pen_dc=pen_dc,
        sim=sim, seed_it=seed_it, costs=costs,
    )

    # --- Build hourly row dict (if enabled) ---
    hourly_row = None
    if hourly_enabled and hourly_iter_dir:
        import csv as _csv
        idx_vals = [str(level), str(pen_pv), str(pen_bess), str(pen_ev), str(pen_dc), str(seed_it)]
        profiles_map = {
            "Pnet":    sim["perfil_pactiva"],
            "Plosses": sim["perfil_losses"],
            "Trafo":   sim["perfil_trafo"],
            "Vmin":    sim["perfil_vmin"],
            "Vmax":    sim["perfil_vmax"],
        }
        iter_file = os.path.join(
            hourly_iter_dir, f"hourly_pen{int(level):03d}_seed{seed_it}.csv"
        )
        hdr = (["Profile", "Penetration_Level", "Pen_PV", "Pen_BESS",
                "Pen_EV", "Pen_DC", "Seed"] + [f"H{h}" for h in range(24)])
        with open(iter_file, "w", encoding="utf-8", newline="") as f:
            f.write(",".join(hdr) + "\n")
            for key, profile in profiles_map.items():
                row = [key] + idx_vals + [f"{v:.4f}" for v in profile]
                f.write(",".join(row) + "\n")

    return kpi_row


# =============================================================================
# Main entry point
# =============================================================================

def run_monte_carlo(cfg):
    """
    Executes the full Monte Carlo sweep.

    Parameters
    ----------
    cfg : module or SimpleNamespace — configuration (import config as cfg)
    """
    # Guard: parallel requires full mode
    if getattr(cfg, "ENABLE_PARALLEL", False) and cfg.SCENARIO_MODE != "full":
        raise ValueError(
            "ENABLE_PARALLEL = True requires SCENARIO_MODE = 'full'. "
            "Update config.py."
        )

    # --- Load profiles once ---
    irr_matrix = temp_matrix = None
    if cfg.ENABLE_PV:
        from modules.pv.pv_profiles  import load_irradiance_matrices, sample_monthly_profile
        from modules.pv.pv_allocation import allocate_pv, generate_cenario_pv
        irr_matrix, temp_matrix = load_irradiance_matrices(cfg.IRRADIANCE_FILE)

    bess_profiles = bess_profile_names = None
    if cfg.ENABLE_BESS:
        from modules.bess.bess_profiles   import load_bess_profiles
        from modules.bess.bess_allocation import allocate_bess, generate_cenario_bess
        bess_profiles, bess_profile_names = load_bess_profiles(cfg.BESS_PROFILES_DIR)
        print(f"  BESS profiles loaded: {bess_profile_names}")

    ev_profiles = ev_profile_names = None
    if cfg.ENABLE_EV_CS:
        from modules.ev_cs.ev_profiles   import load_ev_profiles
        from modules.ev_cs.ev_allocation import allocate_ev, generate_cenario_ev
        ev_profiles, ev_profile_names = load_ev_profiles(cfg.EV_PROFILES_DIR)
        print(f"  EV profiles loaded: {ev_profile_names}")

    dc_profiles = dc_profile_names = dc_gen_profile = None
    if cfg.ENABLE_DC:
        from modules.dc.dc_profiles   import load_dc_profiles, load_dc_gen_profile
        from modules.dc.dc_allocation import allocate_dc, generate_cenario_dc
        dc_profiles, dc_profile_names = load_dc_profiles(cfg.DC_PROFILES_DIR)
        print(f"  DC profiles loaded: {dc_profile_names}")
        if cfg.ENABLE_DC_GEN:
            dc_gen_profile, dc_gen_name = load_dc_gen_profile(cfg.DC_PROFILES_DIR)
            print(f"  DC generator profile: {dc_gen_name}")

    # --- Cenarios directory setup ---
    cenarios_dir = cfg.CENARIOS_DIR
    os.makedirs(cenarios_dir, exist_ok=True)

    if cfg.SCENARIO_MODE == "full" and not cfg.KEEP_SCENARIO_FILES:
        removed = 0
        for f in glob.glob(os.path.join(cenarios_dir, "cenario_*.dss")):
            os.remove(f)
            removed += 1
        if removed:
            print(f"  Cleaned {removed} previous scenario files from cenarios/")

    # replace mode: create fixed-path placeholders once
    if cfg.SCENARIO_MODE == "replace":
        path_pv, path_bess, path_ev, path_dc = _build_cenario_paths(
            cenarios_dir, 0, 0, 0, 0, 0, "replace"
        )
        for path in [path_pv, path_bess, path_ev, path_dc]:
            if not os.path.exists(path):
                open(path, "w").close()

    # --- Hourly export setup ---
    hourly_files    = None
    hourly_iter_dir = None
    if cfg.ENABLE_HOURLY_EXPORT:
        os.makedirs(cfg.HOURLY_DIR, exist_ok=True)
        if cfg.SCENARIO_MODE == "replace":
            hourly_header = (["Penetration_Level", "Pen_PV", "Pen_BESS", "Pen_EV", "Pen_DC", "Seed"]
                             + [f"H{h}" for h in range(24)])
            hourly_files = {
                "Pnet":    os.path.join(cfg.HOURLY_DIR, "perfil24h_Pnet.csv"),
                "Plosses": os.path.join(cfg.HOURLY_DIR, "perfil24h_Plosses.csv"),
                "Trafo":   os.path.join(cfg.HOURLY_DIR, "perfil24h_Trafo.csv"),
                "Vmin":    os.path.join(cfg.HOURLY_DIR, "perfil24h_Vmin.csv"),
                "Vmax":    os.path.join(cfg.HOURLY_DIR, "perfil24h_Vmax.csv"),
            }
            for fpath in hourly_files.values():
                with open(fpath, "w", encoding="utf-8", newline="") as f:
                    f.write(",".join(hourly_header) + "\n")
        else:  # full mode
            hourly_iter_dir = os.path.join(cfg.HOURLY_DIR, "iter")
            os.makedirs(hourly_iter_dir, exist_ok=True)

    # --- Initialize results CSV ---
    init_csv(cfg.RESULTS_FILE)

    # --- Build sweep ---
    sweep_levels = cfg.PENETRATION_LEVELS_PV
    total        = len(sweep_levels) * cfg.NUM_ITERATIONS

    # =========================================================================
    # PARALLEL PATH
    # =========================================================================
    if getattr(cfg, "ENABLE_PARALLEL", False):
        import multiprocessing as _mp

        # Run base case once (result is identical for all iterations)
        base = run_base_case(
            cfg.NETWORK_DSS_PATH, cfg.TRANSFORMER_MVA,
            cfg.ONLY_THREE_PHASE, excluded_buses=cfg.EXCLUDED_BUSES,
        )

        # Build all task dicts
        tasks = []
        count = 0
        for level in sweep_levels:
            pen_pv   = level                               if cfg.ENABLE_PV    else 0
            pen_bess = round(level * cfg.BESS_PV_RATIO, 4) if cfg.ENABLE_BESS  else 0
            pen_ev   = round(level * cfg.EV_PV_RATIO,   4) if cfg.ENABLE_EV_CS else 0
            pen_dc   = round(level * cfg.DC_PV_RATIO,   4) if cfg.ENABLE_DC    else 0
            for _ in range(cfg.NUM_ITERATIONS):
                count += 1
                seed_it = (cfg.RANDOM_SEED + count) if cfg.RANDOM_SEED is not None else 0
                tasks.append(dict(
                    level=level, pen_pv=pen_pv, pen_bess=pen_bess,
                    pen_ev=pen_ev, pen_dc=pen_dc, seed_it=seed_it, count=count,
                ))

        cfg_ns = _cfg_to_namespace(cfg)
        shared = dict(
            cfg_ns=cfg_ns, base=base,
            cenarios_dir=cenarios_dir,
            hourly_enabled=cfg.ENABLE_HOURLY_EXPORT,
            hourly_iter_dir=hourly_iter_dir,
            irr_matrix=irr_matrix,
            temp_matrix=temp_matrix,
            bess_profiles=bess_profiles,
            bess_profile_names=bess_profile_names,
            ev_profiles=ev_profiles,
            ev_profile_names=ev_profile_names,
            dc_profiles=dc_profiles,
            dc_profile_names=dc_profile_names,
            dc_gen_profile=dc_gen_profile,
        )

        n_workers = getattr(cfg, "NUM_WORKERS", None) or _mp.cpu_count()
        print(f"  Parallel execution: {n_workers} workers, {total} tasks")

        # Windows requires spawn context; use it explicitly for portability
        ctx = _mp.get_context("spawn")
        with ctx.Pool(processes=n_workers,
                      initializer=_worker_init,
                      initargs=(shared,)) as pool:
            kpi_rows = pool.map(_run_single_iteration, tasks)

        # Coordinator: write results in order
        for kpi_row in kpi_rows:
            append_row(
                cfg.RESULTS_FILE,
                kpi_row["level"], kpi_row["pen_pv"], kpi_row["pen_bess"],
                kpi_row["pen_ev"], kpi_row["pen_dc"],
                kpi_row["sim"], kpi_row["seed_it"], kpi_row["costs"],
            )

        if cfg.ENABLE_HOURLY_EXPORT:
            _merge_hourly_files(hourly_iter_dir, cfg.HOURLY_DIR)

        print(f"\nSimulation complete. Results: {cfg.RESULTS_FILE}")
        return

    # =========================================================================
    # SEQUENTIAL PATH
    # =========================================================================
    count = 0

    for level in sweep_levels:
        pen_pv   = level                               if cfg.ENABLE_PV    else 0
        pen_bess = round(level * cfg.BESS_PV_RATIO, 4) if cfg.ENABLE_BESS  else 0
        pen_ev   = round(level * cfg.EV_PV_RATIO,   4) if cfg.ENABLE_EV_CS else 0
        pen_dc   = round(level * cfg.DC_PV_RATIO,   4) if cfg.ENABLE_DC    else 0

        for it in range(cfg.NUM_ITERATIONS):
            count += 1
            print(
                f"[{count}/{total}] "
                f"PV={pen_pv}%  BESS={pen_bess}%  EV={pen_ev}%  DC={pen_dc}%  "
                f"iter={it + 1}/{cfg.NUM_ITERATIONS}"
            )

            # Seed
            if cfg.RANDOM_SEED is not None:
                seed_it = cfg.RANDOM_SEED + count
                random.seed(seed_it)
                np.random.seed(seed_it)
            else:
                seed_it = 0

            # Paths (replace: already set; full: compute per iteration)
            if cfg.SCENARIO_MODE == "full":
                path_pv, path_bess, path_ev, path_dc = _build_cenario_paths(
                    cenarios_dir, pen_pv, pen_bess, pen_ev, pen_dc, seed_it, "full"
                )

            # --- Base case ---
            base = run_base_case(
                cfg.NETWORK_DSS_PATH, cfg.TRANSFORMER_MVA,
                cfg.ONLY_THREE_PHASE, excluded_buses=cfg.EXCLUDED_BUSES,
            )
            mt_buses   = base["mt_buses"]
            mt_kv      = base["mt_kv"]
            mt_phases  = base["mt_phases"]
            energy     = base["energy_kwh"]
            n_mt_total = base["n_mt_total"]

            # --- PV ---
            pv_units = []
            if cfg.ENABLE_PV:
                irrad_pu, temp_c, psh, mes = sample_monthly_profile(irr_matrix, temp_matrix)
                pv_units, _ = allocate_pv(
                    energy, pen_pv, psh,
                    mt_buses, mt_kv, mt_phases,
                    cfg.PV_SIZES_KW, cfg.PV_PROBS, cfg.PV_POWER_FACTOR,
                )
                generate_cenario_pv(pv_units, irrad_pu, temp_c, path_pv, pen_pv, mes)
            else:
                open(path_pv, "w").close()

            # --- BESS ---
            bess_units = []
            if cfg.ENABLE_BESS:
                bess_units, _ = allocate_bess(
                    energy, pen_bess,
                    mt_buses, mt_kv, mt_phases,
                    cfg.BESS_SIZES_KWH, cfg.BESS_PROBS,
                    cfg.BESS_CHARGE_HOURS, cfg.BESS_PLACEMENT,
                    bess_profiles, bess_profile_names,
                    pv_units=pv_units, power_factor=cfg.BESS_POWER_FACTOR,
                )
                generate_cenario_bess(
                    bess_units, path_bess, pen_bess,
                    vminpu=cfg.BESS_VMINPU, vmaxpu=cfg.BESS_VMAXPU,
                    eff_charge=cfg.BESS_EFF_CHARGE, eff_discharge=cfg.BESS_EFF_DISCHARGE,
                )
            else:
                open(path_bess, "w").close()

            # --- EV/CS ---
            ev_units = []
            if cfg.ENABLE_EV_CS:
                ev_units, _ = allocate_ev(
                    energy, pen_ev,
                    mt_buses, mt_kv, mt_phases,
                    cfg.EV_SIZES_KW, cfg.EV_PROBS, cfg.EV_ELIGIBLE_BUSES,
                    ev_profiles, ev_profile_names, cfg.EV_POWER_FACTOR,
                )
                generate_cenario_ev(ev_units, path_ev, pen_ev)
            else:
                open(path_ev, "w").close()

            # --- DC ---
            dc_units = []
            if cfg.ENABLE_DC:
                dc_units, _ = allocate_dc(
                    energy, pen_dc,
                    mt_buses, mt_kv, mt_phases,
                    cfg.NUM_DC, dc_profiles, dc_profile_names,
                    cfg.DC_PUE_RANGE, cfg.DC_NOISE_BAND,
                    excluded_buses=cfg.EXCLUDED_BUSES,
                )
                generate_cenario_dc(
                    dc_units, path_dc, pen_dc,
                    enable_dc_gen=cfg.ENABLE_DC_GEN,
                    dc_self_supply_frac=cfg.DC_SELF_SUPPLY_FRAC,
                    dc_gen_profile=dc_gen_profile,
                )
            else:
                open(path_dc, "w").close()

            # --- Simulate ---
            sim = run_with_ders(
                cfg.NETWORK_DSS_PATH, cfg.TRANSFORMER_MVA,
                enable_pv=cfg.ENABLE_PV,    path_pv=path_pv,
                enable_bess=cfg.ENABLE_BESS, path_bess=path_bess,
                enable_ev=cfg.ENABLE_EV_CS,  path_ev=path_ev,
                enable_dc=cfg.ENABLE_DC,     path_dc=path_dc,
                n_mt_total=n_mt_total,
            )

            # --- Costs ---
            pv_kw_inst    = sum(u["pmpp_kw"]   for u in pv_units)
            bess_kwh_inst = sum(u["kwh_rated"] for u in bess_units)
            ev_kw_inst    = sum(u["kw"]        for u in ev_units)
            dc_kw_inst    = sum(u["peak_kw"]   for u in dc_units)
            energy_losses_kwh = float(np.sum(sim["perfil_losses"]))

            costs = {
                "PV_kW_inst":     pv_kw_inst,
                "BESS_kWh_inst":  bess_kwh_inst,
                "EV_kW_inst":     ev_kw_inst,
                "DC_kW_inst":     dc_kw_inst,
                "Cost_PV_Local":  pv_kw_inst    * cfg.PV_USD_PER_KW_LOCAL,
                "Cost_PV_Intl":   pv_kw_inst    * cfg.PV_USD_PER_KW_INTL,
                "Cost_BESS_Local":bess_kwh_inst * cfg.BESS_USD_PER_KWH_LOCAL,
                "Cost_BESS_Intl": bess_kwh_inst * cfg.BESS_USD_PER_KWH_INTL,
                "Cost_EVCS_Local":ev_kw_inst    * cfg.EVCS_USD_PER_KW_LOCAL,
                "Cost_EVCS_Intl": ev_kw_inst    * cfg.EVCS_USD_PER_KW_INTL,
                "Cost_DC":        dc_kw_inst    * cfg.DC_USD_PER_KW,
                "Energy_Losses_USD": energy_losses_kwh * cfg.ENERGY_LOSS_TARIFF_USD_PER_KWH,
            }
            costs["Cost_Total_Local"] = (
                costs["Cost_PV_Local"] + costs["Cost_BESS_Local"] + costs["Cost_EVCS_Local"]
            )
            costs["Cost_Total_Intl"] = (
                costs["Cost_PV_Intl"] + costs["Cost_BESS_Intl"] + costs["Cost_EVCS_Intl"]
            )

            # --- Save KPI row ---
            append_row(
                cfg.RESULTS_FILE, level, pen_pv, pen_bess, pen_ev, pen_dc,
                sim, seed_it, costs,
            )

            # --- Hourly export ---
            if cfg.ENABLE_HOURLY_EXPORT:
                idx_vals = [str(level), str(pen_pv), str(pen_bess),
                            str(pen_ev), str(pen_dc), str(seed_it)]
                profiles_map = {
                    "Pnet":    sim["perfil_pactiva"],
                    "Plosses": sim["perfil_losses"],
                    "Trafo":   sim["perfil_trafo"],
                    "Vmin":    sim["perfil_vmin"],
                    "Vmax":    sim["perfil_vmax"],
                }
                if cfg.SCENARIO_MODE == "replace":
                    for key, profile in profiles_map.items():
                        row = idx_vals + [f"{v:.4f}" for v in profile]
                        with open(hourly_files[key], "a", encoding="utf-8", newline="") as f:
                            f.write(",".join(row) + "\n")
                else:  # full mode
                    iter_file = os.path.join(
                        hourly_iter_dir,
                        f"hourly_pen{int(level):03d}_seed{seed_it}.csv"
                    )
                    hdr = (["Profile", "Penetration_Level", "Pen_PV", "Pen_BESS",
                            "Pen_EV", "Pen_DC", "Seed"] + [f"H{h}" for h in range(24)])
                    with open(iter_file, "w", encoding="utf-8", newline="") as f:
                        f.write(",".join(hdr) + "\n")
                        for key, profile in profiles_map.items():
                            row = [key] + idx_vals + [f"{v:.4f}" for v in profile]
                            f.write(",".join(row) + "\n")

    if cfg.ENABLE_HOURLY_EXPORT and cfg.SCENARIO_MODE == "full":
        _merge_hourly_files(hourly_iter_dir, cfg.HOURLY_DIR)

    print(f"\nSimulation complete. Results: {cfg.RESULTS_FILE}")
