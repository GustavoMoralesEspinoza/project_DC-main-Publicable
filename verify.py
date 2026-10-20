# verify.py
"""
Single-iteration debug tool.

Runs exactly one simulation with the scenario defined below, prints a full
KPI report to the console, generates the scenario DSS files, and optionally
saves diagnostic plots. Does NOT write to the results CSV.

Usage:
    python verify.py

Configure the scenario in the SCENARIO SETTINGS block at the top of this file:
  - ENABLE_* flags  : choose which DER modules to activate for this test
  - PEN_*           : penetration level for each module [%]
  - SEED            : random seed for reproducibility
  - SAVE_PLOTS      : whether to generate PNG diagnostic figures

DER sizes, probabilities, and network paths are read from config.py.
"""

# =============================================================================
# SCENARIO SETTINGS  â€”  edit this block
# =============================================================================

ENABLE_PV    = True    # Include PV generation in this test
ENABLE_BESS  = False   # Include battery storage in this test
ENABLE_EV_CS = False   # Include EV charging stations in this test
ENABLE_DC    = False   # Include data centers in this test

PEN_PV   = 50    # PV penetration level   [% of daily network energy]
PEN_BESS = 0     # BESS penetration level [% of daily network energy]
PEN_EV   = 0     # EV/CS penetration level [% of daily network energy]
PEN_DC   = 0     # DC penetration level   [% of daily network energy]

SEED = 42        # Random seed (integer for reproducibility, or None)

SAVE_PLOTS = True   # Save voltage and system profile plots to results/figures/

# =============================================================================

import os
import random
import numpy as np

# Seed
if SEED is not None:
    random.seed(SEED)
    np.random.seed(SEED)

import config as cfg

# --- DSS scenario file paths ---
# Disabled modules get a None path: no file is created and run_with_ders
# skips the redirect for that DER. Only enabled modules produce a .dss file.
cenarios_dir = cfg.CENARIOS_DIR
os.makedirs(cenarios_dir, exist_ok=True)


def _scenario_path(der, pen, enabled):
    if not enabled:
        return None
    if cfg.SCENARIO_MODE == "full":
        return os.path.join(cenarios_dir,
            f"cenario_{der}_pen{int(round(pen)):03d}_seed{SEED}.dss")
    return os.path.join(cenarios_dir, f"cenario_{der}.dss")


path_pv   = _scenario_path("PV",   PEN_PV,   ENABLE_PV)
path_bess = _scenario_path("BESS", PEN_BESS, ENABLE_BESS)
path_ev   = _scenario_path("EV",   PEN_EV,   ENABLE_EV_CS)
path_dc   = _scenario_path("DC",   PEN_DC,   ENABLE_DC)

# =============================================================================
# 1. BASE CASE  â€”  load network and compute daily energy reference
# =============================================================================

from core.network import run_base_case, run_with_ders

base = run_base_case(
    cfg.NETWORK_DSS_PATH,
    cfg.TRANSFORMER_MVA,
    cfg.ONLY_THREE_PHASE,
    excluded_buses=cfg.EXCLUDED_BUSES,
    control_mode=getattr(cfg, "CONTROL_MODE", "off"),
)
mt_buses   = base["mt_buses"]
mt_kv      = base["mt_kv"]
mt_phases  = base["mt_phases"]
energy     = base["energy_kwh"]
n_mt_total = base["n_mt_total"]

# =============================================================================
# 2. GENERATE SCENARIO FILES
# =============================================================================

# --- PV ---
pv_units   = []
p_total_pv = 0.0
if ENABLE_PV and PEN_PV > 0:
    from modules.pv.pv_profiles  import load_irradiance_matrices, sample_monthly_profile
    from modules.pv.pv_allocation import allocate_pv, generate_cenario_pv

    irr_matrix, temp_matrix = load_irradiance_matrices(cfg.IRRADIANCE_FILE)
    irrad_pu, temp_c, psh, month = sample_monthly_profile(irr_matrix, temp_matrix)
    pv_units, p_total_pv = allocate_pv(
        energy, PEN_PV, psh,
        mt_buses, mt_kv, mt_phases,
        cfg.PV_SIZES_KW, cfg.PV_PROBS,
        cfg.PV_POWER_FACTOR,
    )
    generate_cenario_pv(pv_units, irrad_pu, temp_c, path_pv, PEN_PV, month)

# --- BESS ---
bess_units   = []
e_total_bess = 0.0
if ENABLE_BESS and PEN_BESS > 0:
    from modules.bess.bess_profiles   import load_bess_profiles
    from modules.bess.bess_allocation import allocate_bess, generate_cenario_bess

    bess_profiles, bess_profile_names = load_bess_profiles(cfg.BESS_PROFILES_DIR)
    bess_units, e_total_bess = allocate_bess(
        energy, PEN_BESS,
        mt_buses, mt_kv, mt_phases,
        cfg.BESS_SIZES_KWH, cfg.BESS_PROBS,
        cfg.BESS_CHARGE_HOURS, cfg.BESS_PLACEMENT,
        bess_profiles, bess_profile_names,
        pv_units=pv_units,
        power_factor=cfg.BESS_POWER_FACTOR,
    )
    generate_cenario_bess(
        bess_units, path_bess, PEN_BESS,
        vminpu=cfg.BESS_VMINPU, vmaxpu=cfg.BESS_VMAXPU,
        eff_charge=cfg.BESS_EFF_CHARGE, eff_discharge=cfg.BESS_EFF_DISCHARGE,
    )

# --- EV/CS ---
ev_units   = []
e_total_ev = 0.0
if ENABLE_EV_CS and PEN_EV > 0:
    from modules.ev_cs.ev_profiles   import load_ev_profiles
    from modules.ev_cs.ev_allocation import allocate_ev, generate_cenario_ev

    ev_profiles, ev_profile_names = load_ev_profiles(cfg.EV_PROFILES_DIR)
    ev_units, e_total_ev = allocate_ev(
        energy, PEN_EV,
        mt_buses, mt_kv, mt_phases,
        cfg.EV_SIZES_KW, cfg.EV_PROBS,
        cfg.EV_ELIGIBLE_BUSES,
        ev_profiles, ev_profile_names,
        cfg.EV_POWER_FACTOR,
    )
    generate_cenario_ev(ev_units, path_ev, PEN_EV)

# --- DC ---
dc_units   = []
e_total_dc = 0.0
if ENABLE_DC and PEN_DC > 0:
    from modules.dc.dc_profiles   import load_dc_profiles, load_dc_gen_profile
    from modules.dc.dc_allocation import allocate_dc, generate_cenario_dc

    dc_profiles, dc_profile_names = load_dc_profiles(cfg.DC_PROFILES_DIR)
    dc_gen_profile = None
    if cfg.ENABLE_DC_GEN:
        dc_gen_profile, _ = load_dc_gen_profile(cfg.DC_PROFILES_DIR)
    dc_units, e_total_dc = allocate_dc(
        energy, PEN_DC,
        mt_buses, mt_kv, mt_phases,
        cfg.NUM_DC,
        dc_profiles, dc_profile_names,
        cfg.DC_PUE_RANGE, cfg.DC_NOISE_BAND,
        excluded_buses=cfg.EXCLUDED_BUSES,
    )
    generate_cenario_dc(
        dc_units, path_dc, PEN_DC,
        enable_dc_gen=cfg.ENABLE_DC_GEN,
        dc_self_supply_frac=cfg.DC_SELF_SUPPLY_FRAC,
        dc_gen_profile=dc_gen_profile,
    )

# =============================================================================
# 3. SIMULATION WITH DERs
# =============================================================================

sim = run_with_ders(
    cfg.NETWORK_DSS_PATH,
    cfg.TRANSFORMER_MVA,
    enable_pv=ENABLE_PV,    path_pv=path_pv,
    enable_bess=ENABLE_BESS, path_bess=path_bess,
    enable_ev=ENABLE_EV_CS,  path_ev=path_ev,
    enable_dc=ENABLE_DC,     path_dc=path_dc,
    n_mt_total=n_mt_total,
    control_mode=getattr(cfg, "CONTROL_MODE", "off"),
)

# =============================================================================
# 4. CONSOLE REPORT
# =============================================================================

SEP = "=" * 52

b_vmin     = len(sim["buses_vmin"])
b_vmax     = len(sim["buses_vmax"])
b_vminvmax = len(sim["buses_vmin"] | sim["buses_vmax"])

print(SEP)
print(f"  VERIFY â€” {cfg.NETWORK_NAME} | seed={SEED}")
print(f"  PV={PEN_PV}%  BESS={PEN_BESS}%  EV={PEN_EV}%  DC={PEN_DC}%")
print(SEP)

print("\n  Network")
print(f"    Daily energy demand   : {energy:>10,.1f} kWh")
print(f"    Peak demand           : {base['p_max_kw']:>10,.1f} kW")
print(f"    MV candidate buses    : {len(mt_buses):>10}")

if ENABLE_PV and pv_units:
    print(f"\n  PV  ({PEN_PV}%)")
    print(f"    Units installed       : {len(pv_units):>10}")
    print(f"    Total power           : {p_total_pv:>10,.1f} kWp")

if ENABLE_BESS and bess_units:
    print(f"\n  BESS  ({PEN_BESS}%)")
    print(f"    Units installed       : {len(bess_units):>10}")
    print(f"    Total capacity        : {e_total_bess:>10,.1f} kWh")

if ENABLE_EV_CS and ev_units:
    print(f"\n  EV/CS  ({PEN_EV}%)")
    print(f"    Stations installed    : {len(ev_units):>10}")
    print(f"    Total power           : {sum(u['kw'] for u in ev_units):>10,.1f} kW")

if ENABLE_DC and dc_units:
    avg_pue  = sum(u["pue"] for u in dc_units) / len(dc_units)
    tot_peak = sum(u["peak_kw"] for u in dc_units)
    archetypes = ", ".join(dict.fromkeys(u["profile_name"] for u in dc_units))
    print(f"\n  Data Centers  ({PEN_DC}%)")
    print(f"    DCs installed         : {len(dc_units):>10}")
    print(f"    Total energy          : {e_total_dc:>10,.1f} kWh")
    print(f"    Peak power            : {tot_peak:>10,.1f} kW")
    print(f"    Avg PUE               : {avg_pue:>10.2f}")
    print(f"    Archetype(s)          : {archetypes}")

print(f"\n  Simulation KPIs")
print(f"    Undervoltage buses    : {b_vmin:>10}   (< 0.95 pu in â‰¥1 hour)")
print(f"    Overvoltage buses     : {b_vmax:>10}   (> 1.05 pu in â‰¥1 hour)")
print(f"    Affected buses (union): {b_vminvmax:>10}")
print(f"    Vmin over 24h         : {sim['vmin_24h']:>10.4f} pu")
print(f"    Vmax over 24h         : {sim['vmax_24h']:>10.4f} pu")
print(f"    Undervoltage severity : {sim['sev_vmin_pct']:>10.2f} %  (busÃ—hour pairs)")
print(f"    Overvoltage severity  : {sim['sev_vmax_pct']:>10.2f} %  (busÃ—hour pairs)")
print(f"    Combined severity     : {sim['sev_union_pct']:>10.2f} %")
print(f"    Peak active losses    : {float(np.max(sim['perfil_losses'])):>10,.1f} kW")
print(f"    Daily energy losses   : {float(np.sum(sim['perfil_losses'])):>10,.1f} kWh")
print(f"    Peak transformer load : {float(np.max(sim['perfil_trafo'])):>10.1f} %")

print(f"\n  Generated DSS files")
for label, path in [("PV", path_pv), ("BESS", path_bess),
                    ("EV/CS", path_ev), ("DC", path_dc)]:
    if path is None:
        print(f"    {label:<6}: (module disabled, no file)")
        continue
    rel = os.path.relpath(path, cfg.BASE_DIR).replace("\\", "/")
    size = os.path.getsize(path)
    print(f"    {label:<6}: {rel}  [{size:,} B]")

print(SEP)

# =============================================================================
# 5. DIAGNOSTIC PLOTS
# =============================================================================

if SAVE_PLOTS:
    out_dir = os.path.join(cfg.RESULTS_DIR, "figures")

    from plots.plot_voltage import plot_voltage_profile
    plot_voltage_profile(
        sim["perfil_tension_barras"],
        PEN_PV, PEN_BESS, PEN_EV, SEED,
        out_dir, cfg.NETWORK_NAME,
        pen_dc=PEN_DC,
    )

    from plots.plot_system import plot_system_profile
    plot_system_profile(
        sim, cfg.TRANSFORMER_MVA,
        PEN_PV, PEN_BESS, PEN_EV, SEED,
        out_dir, cfg.NETWORK_NAME,
        pen_dc=PEN_DC,
    )

    print(f"\n  Plots saved to: {out_dir}/")
    print(SEP)

