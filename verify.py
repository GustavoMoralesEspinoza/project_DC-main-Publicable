# verify.py
"""
Debug tool — runs exactly one Monte Carlo iteration and prints a full
KPI report to the console. Also generates voltage and system profile plots.
Does NOT write to the results CSV.

Usage:
    python verify.py

To test a specific scenario, edit the parameters at the top of this file:
    PEN_PV   — PV penetration level [%]
    PEN_BESS — BESS penetration level [%]
    PEN_EV   — EV/CS penetration level [%]
    PEN_DC   — Data Center penetration level [%]
    SEED     — random seed for reproducibility

Output (written to results/figures/):
    voltage_profile_<scenario>.png
    system_profile_<scenario>.png
"""

# ============================================================
# PARÁMETROS EDITABLES
# ============================================================
PEN_PV   = 0    # penetración PV   [%]
PEN_BESS = 0    # penetración BESS [%]
PEN_EV   = 0     # penetración EV   [%]
PEN_DC   = 0     # penetración DC   [%]
SEED     = 2077    # semilla
# ============================================================

import os
import random
import numpy as np

# 1. Semilla
random.seed(SEED)
np.random.seed(SEED)

# 2. Configuración
import config as cfg

# Rutas .dss generados
path_pv   = os.path.join(cfg.NETWORK_DIR, "cenario_PV.dss")
path_bess = os.path.join(cfg.NETWORK_DIR, "cenario_BESS.dss")
path_ev   = os.path.join(cfg.NETWORK_DIR, "cenario_EV.dss")
path_dc   = os.path.join(cfg.NETWORK_DIR, "cenario_DC.dss")

for path in [path_pv, path_bess, path_ev, path_dc]:
    if not os.path.exists(path):
        open(path, "w").close()

# 3. Caso base
from core.network import run_base_case, run_with_ders

base = run_base_case(
    cfg.NETWORK_DSS_PATH,
    cfg.TRANSFORMER_MVA,
    cfg.ONLY_THREE_PHASE,
    excluded_buses=cfg.EXCLUDED_BUSES,
)
mt_buses   = base["mt_buses"]
mt_kv      = base["mt_kv"]
mt_phases  = base["mt_phases"]
energy     = base["energy_kwh"]
n_mt_total = base["n_mt_total"]

# 4. PV
pv_units   = []
p_total_pv = 0.0
#if cfg.ENABLE_PV and PEN_PV > 0:
if PEN_PV > 0:
    from modules.pv.pv_profiles  import load_irradiance_matrices, sample_monthly_profile
    from modules.pv.pv_allocation import allocate_pv, generate_cenario_pv

    irr_matrix, temp_matrix = load_irradiance_matrices(cfg.IRRADIANCE_FILE)
    irrad_pu, temp_c, psh, mes = sample_monthly_profile(irr_matrix, temp_matrix)
    pv_units, p_total_pv = allocate_pv(
        energy, PEN_PV, psh,
        mt_buses, mt_kv, mt_phases,
        cfg.PV_SIZES_KW, cfg.PV_PROBS,
        cfg.PV_POWER_FACTOR,
    )
    generate_cenario_pv(pv_units, irrad_pu, temp_c, path_pv, PEN_PV, mes)
else:
    open(path_pv, "w").close()

# 5. BESS
bess_units   = []
e_total_bess = 0.0
#if cfg.ENABLE_BESS and PEN_BESS > 0:
if PEN_BESS > 0:
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
else:
    open(path_bess, "w").close()

# 6. EV/CS
ev_units = []
#if cfg.ENABLE_EV_CS and PEN_EV > 0:
if PEN_EV > 0:
    from modules.ev_cs.ev_profiles   import load_ev_profiles
    from modules.ev_cs.ev_allocation import allocate_ev, generate_cenario_ev

    ev_profiles, ev_profile_names = load_ev_profiles(cfg.EV_PROFILES_DIR)
    ev_units, _ = allocate_ev(
        energy, PEN_EV,
        mt_buses, mt_kv, mt_phases,
        cfg.EV_SIZES_KW, cfg.EV_PROBS,
        cfg.EV_ELIGIBLE_BUSES,
        ev_profiles, ev_profile_names,
        cfg.EV_POWER_FACTOR,
    )
    generate_cenario_ev(ev_units, path_ev, PEN_EV)
else:
    open(path_ev, "w").close()

# 7. DC
dc_units   = []
e_total_dc = 0.0
if PEN_DC > 0:
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
else:
    open(path_dc, "w").close()

# 8. Simulación con DERs
sim = run_with_ders(
    cfg.NETWORK_DSS_PATH,
    cfg.TRANSFORMER_MVA,
    enable_pv=cfg.ENABLE_PV,    path_pv=path_pv,
    enable_bess=cfg.ENABLE_BESS, path_bess=path_bess,
    enable_ev=cfg.ENABLE_EV_CS,  path_ev=path_ev,
    enable_dc=(PEN_DC > 0),      path_dc=path_dc,
    n_mt_total=n_mt_total,
)

# 9. Reporte en consola
SEP = "═" * 48

b_vmin     = len(sim["buses_vmin"])
b_vmax     = len(sim["buses_vmax"])
b_vminvmax = len(sim["buses_vmin"] | sim["buses_vmax"])

max_losses    = float(np.max(sim["perfil_losses"]))
energy_losses = float(np.sum(sim["perfil_losses"]))
trafo_max     = float(np.max(sim["perfil_trafo"]))

rel_pv   = os.path.relpath(path_pv,   cfg.BASE_DIR).replace("\\", "/")
rel_bess = os.path.relpath(path_bess, cfg.BASE_DIR).replace("\\", "/")
rel_ev   = os.path.relpath(path_ev,   cfg.BASE_DIR).replace("\\", "/")
rel_dc   = os.path.relpath(path_dc,   cfg.BASE_DIR).replace("\\", "/")

print(SEP)
print(f" VERIFY — {cfg.NETWORK_NAME} | PV={PEN_PV}%  BESS={PEN_BESS}%  EV={PEN_EV}%  DC={PEN_DC}%  seed={SEED}")
print(SEP)

print(" Red")
print(f"   Energía diaria        : {energy:,.1f} kWh")
print(f"   Demanda máxima        : {base['p_max_kw']:,.1f} kW")
print(f"   Barras MT candidatas  : {len(mt_buses)}")
print()

if cfg.ENABLE_PV:
    print(" PV instalado")
    print(f"   Unidades              : {len(pv_units)}")
    print(f"   Potencia total        : {p_total_pv:,.1f} kW")
    print()

if cfg.ENABLE_BESS:
    print(" BESS instalado")
    print(f"   Unidades              : {len(bess_units)}")
    print(f"   Energía total         : {e_total_bess:,.1f} kWh")
    print()

print(" EV/CS instalado")
print(f"   Estaciones            : {len(ev_units)}")
print()

if dc_units:
    avg_pue     = sum(u["pue"] for u in dc_units) / len(dc_units)
    tot_servers = sum(u["n_servers_equiv"] for u in dc_units)
    tot_peak    = sum(u["peak_kw"] for u in dc_units)
    arquetipos  = ", ".join(dict.fromkeys(u["profile_name"] for u in dc_units))
    print(" Data Center")
    print(f"   DCs instalados        : {len(dc_units)}")
    print(f"   Energía total DC      : {e_total_dc:,.1f} kWh")
    print(f"   Pico máximo           : {tot_peak:,.1f} kW")
    print(f"   PUE promedio          : {avg_pue:.2f}")
    print(f"   Servidores equiv.     : {tot_servers:,}")
    print(f"   Arquetipo(s)          : {arquetipos}")
    print()

print(" KPIs simulación")
print(f"   B_Vmin                : {b_vmin}  barras con subtensión")
print(f"   B_Vmax                : {b_vmax}  barras con sobretensión")
print(f"   B_VminVmax            : {b_vminvmax}  barras afectadas (unión)")
print(f"   Max pérdidas activas  : {max_losses:,.1f} kW")
print(f"   Energía pérdidas      : {energy_losses:,.1f} kWh")
print(f"   Cargamento trafo máx  : {trafo_max:.1f} %")
print(f"   Vmin 24h              : {sim['vmin_24h']:.3f} pu")
print(f"   Vmax 24h              : {sim['vmax_24h']:.3f} pu")
print(f"   Sev. subtensión       : {sim['sev_vmin_pct']:.2f} %")
print(f"   Sev. sobretensión     : {sim['sev_vmax_pct']:.2f} %")
print(f"   Sev. combinada        : {sim['sev_union_pct']:.2f} %")
print()

print(" Archivos DSS generados en:")
print(f"   {rel_pv}")
print(f"   {rel_bess}")
print(f"   {rel_ev}")
print(f"   {rel_dc}")
print(SEP)

# 10. Gráfico de tensión
from plots.plot_voltage import plot_voltage_profile

plot_voltage_profile(
    sim["perfil_tension_barras"],
    PEN_PV, PEN_BESS, PEN_EV, SEED,
    os.path.join(cfg.RESULTS_DIR, "figures"),
    cfg.NETWORK_NAME,
    pen_dc=PEN_DC,
)

# 11. Gráficos de sistema (flujo, transformador, pérdidas)
from plots.plot_system import plot_system_profile

plot_system_profile(
    sim,
    cfg.TRANSFORMER_MVA,
    PEN_PV, PEN_BESS, PEN_EV, SEED,
    os.path.join(cfg.RESULTS_DIR, "figures"),
    cfg.NETWORK_NAME,
    pen_dc=PEN_DC,
)
