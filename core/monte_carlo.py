# project/core/monte_carlo.py
"""
Loop principal Monte Carlo.
Itera sobre los niveles de penetración PV definidos en config.
BESS y EV/CS se calculan automáticamente con los ratios BESS_PV_RATIO y EV_PV_RATIO.
"""

import os
import random
import numpy as np

from core.network import run_base_case, run_with_ders
from results.reporter import init_csv, append_row


def run_monte_carlo(cfg):
    """
    Ejecuta el loop Monte Carlo completo.

    Parámetro
    ---------
    cfg : module o SimpleNamespace — configuración (import config as cfg)
    """
    # --- Importar módulos activos y pre-cargar datos ---
    if cfg.ENABLE_PV:
        from modules.pv.pv_profiles   import load_irradiance_matrices, sample_monthly_profile
        from modules.pv.pv_allocation  import allocate_pv, generate_cenario_pv
        irr_matrix, temp_matrix = load_irradiance_matrices(cfg.IRRADIANCE_FILE)

    if cfg.ENABLE_BESS:
        from modules.bess.bess_profiles   import load_bess_profiles
        from modules.bess.bess_allocation import allocate_bess, generate_cenario_bess
        bess_profiles, bess_profile_names = load_bess_profiles(cfg.BESS_PROFILES_DIR)
        print(f"  Curvas BESS cargadas: {bess_profile_names}")

    if cfg.ENABLE_EV_CS:
        from modules.ev_cs.ev_profiles    import load_ev_profiles
        from modules.ev_cs.ev_allocation  import allocate_ev, generate_cenario_ev
        # Cargar todas las curvas EV una sola vez al inicio
        ev_profiles, ev_profile_names = load_ev_profiles(cfg.EV_PROFILES_DIR)
        print(f"  Curvas EV cargadas: {ev_profile_names}")

    if cfg.ENABLE_DC:
        from modules.dc.dc_profiles   import load_dc_profiles, load_dc_gen_profile
        from modules.dc.dc_allocation import allocate_dc, generate_cenario_dc
        dc_profiles, dc_profile_names = load_dc_profiles(cfg.DC_PROFILES_DIR)
        print(f"  Curvas DC cargadas: {dc_profile_names}")
        dc_gen_profile = None
        if cfg.ENABLE_DC_GEN:
            dc_gen_profile, dc_gen_name = load_dc_gen_profile(cfg.DC_PROFILES_DIR)
            print(f"  Perfil generador DC: {dc_gen_name}")

    # --- Rutas de los archivos .dss generados ---
    path_pv   = os.path.join(cfg.NETWORK_DIR, "cenario_PV.dss")
    path_bess = os.path.join(cfg.NETWORK_DIR, "cenario_BESS.dss")
    path_ev   = os.path.join(cfg.NETWORK_DIR, "cenario_EV.dss")
    path_dc   = os.path.join(cfg.NETWORK_DIR, "cenario_DC.dss")

    for path in [path_pv, path_bess, path_ev, path_dc]:
        if not os.path.exists(path):
            open(path, "w").close()

    # --- Inicializar CSV ---
    init_csv(cfg.RESULTS_FILE)

    if cfg.ENABLE_HOURLY_EXPORT:
        os.makedirs(cfg.HOURLY_DIR, exist_ok=True)
        hourly_header = ["Penetration_Level","Pen_PV","Pen_BESS","Pen_EV","Pen_DC","Seed"] + [f"H{h}" for h in range(24)]
        hourly_files = {
            "Pnet":    os.path.join(cfg.HOURLY_DIR, "perfil24h_Pnet.csv"),
            "Plosses": os.path.join(cfg.HOURLY_DIR, "perfil24h_Plosses.csv"),
            "Trafo":   os.path.join(cfg.HOURLY_DIR, "perfil24h_Trafo.csv"),
            "Vmin":    os.path.join(cfg.HOURLY_DIR, "perfil24h_Vmin.csv"),
            "Vmax":    os.path.join(cfg.HOURLY_DIR, "perfil24h_Vmax.csv"),
        }
        # Inicializar (sobrescribir) cada archivo con la cabecera
        for key, fpath in hourly_files.items():
            with open(fpath, "w", encoding="utf-8", newline="") as f:
                f.write(",".join(hourly_header) + "\n")

    # --- Loop principal ---
    # El barrido SIEMPRE recorre la lista de niveles (es el driver del experimento,
    # independiente de qué módulo esté activo). Cada módulo deriva su penetración
    # desde 'level' solo si está habilitado. Esto permite escenarios "Solo DC",
    # "Solo BESS", etc., sin que apagar PV colapse el barrido.
    sweep_levels = cfg.PENETRATION_LEVELS_PV
    total        = len(sweep_levels) * cfg.NUM_ITERATIONS
    count        = 0

    for level in sweep_levels:
        # Cada penetración se calcula desde 'level' SOLO si su módulo está activo.
        # Si el módulo está apagado, su penetración es 0 (no se instala nada).
        pen_pv   = level                                      if cfg.ENABLE_PV    else 0
        pen_bess = round(level * cfg.BESS_PV_RATIO, 4)        if cfg.ENABLE_BESS  else 0
        pen_ev   = round(level * cfg.EV_PV_RATIO,   4)        if cfg.ENABLE_EV_CS else 0
        pen_dc   = round(level * cfg.DC_PV_RATIO,   4)        if cfg.ENABLE_DC    else 0

        for it in range(cfg.NUM_ITERATIONS):
            count += 1
            print(
                f"[{count}/{total}] "
                f"PV={pen_pv}%  BESS={pen_bess}%  EV={pen_ev}%  DC={pen_dc}%  "
                f"iter={it + 1}/{cfg.NUM_ITERATIONS}"
            )

            # Semilla por iteración para reproducibilidad
            if cfg.RANDOM_SEED is not None:
                seed_it = cfg.RANDOM_SEED + count
                random.seed(seed_it)
                np.random.seed(seed_it)
            else:
                seed_it = 0

            # --- Caso base (sin DERs) ---
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

            # --- PV ---
            pv_units = []
            if cfg.ENABLE_PV:
                irrad_pu, temp_c, psh, mes = sample_monthly_profile(irr_matrix, temp_matrix)
                pv_units, _ = allocate_pv(
                    energy, pen_pv, psh,
                    mt_buses, mt_kv, mt_phases,
                    cfg.PV_SIZES_KW, cfg.PV_PROBS,
                    cfg.PV_POWER_FACTOR,
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
                    pv_units=pv_units,
                    power_factor=cfg.BESS_POWER_FACTOR,
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
                    cfg.EV_SIZES_KW, cfg.EV_PROBS,
                    cfg.EV_ELIGIBLE_BUSES,
                    ev_profiles, ev_profile_names,
                    cfg.EV_POWER_FACTOR,
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
                    cfg.NUM_DC,
                    dc_profiles, dc_profile_names,
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

            # --- Simulación con DERs ---
            # Solo carga los módulos activos — el master.dss queda limpio
            sim = run_with_ders(
                cfg.NETWORK_DSS_PATH,
                cfg.TRANSFORMER_MVA,
                enable_pv=cfg.ENABLE_PV,    path_pv=path_pv,
                enable_bess=cfg.ENABLE_BESS, path_bess=path_bess,
                enable_ev=cfg.ENABLE_EV_CS,  path_ev=path_ev,
                enable_dc=cfg.ENABLE_DC,     path_dc=path_dc,
                n_mt_total=n_mt_total,
            )

            # --- Capacidades instaladas y costos económicos ---
            pv_kw_inst    = sum(u["pmpp_kw"]   for u in pv_units)
            bess_kwh_inst = sum(u["kwh_rated"] for u in bess_units)
            ev_kw_inst    = sum(u["kw"]        for u in ev_units)
            dc_kw_inst    = sum(u["peak_kw"]   for u in dc_units)

            energy_losses_kwh = float(np.sum(sim["perfil_losses"]))

            costs = {
                "PV_kW_inst":    pv_kw_inst,
                "BESS_kWh_inst": bess_kwh_inst,
                "EV_kW_inst":    ev_kw_inst,
                "DC_kW_inst":    dc_kw_inst,
                "Cost_PV_Peru":   pv_kw_inst    * cfg.PV_USD_PER_KW_PERU,
                "Cost_PV_Intl":   pv_kw_inst    * cfg.PV_USD_PER_KW_INTL,
                "Cost_BESS_Peru": bess_kwh_inst * cfg.BESS_USD_PER_KWH_BASE,
                "Cost_BESS_Intl": bess_kwh_inst * cfg.BESS_USD_PER_KWH_INTL,
                "Cost_EVCS_Peru": ev_kw_inst    * cfg.EVCS_USD_PER_KW_PERU,
                "Cost_EVCS_Intl": ev_kw_inst    * cfg.EVCS_USD_PER_KW_INTL,
                "Cost_DC":        dc_kw_inst    * cfg.DC_USD_PER_KW,
                "Energy_Losses_USD": energy_losses_kwh * cfg.ENERGY_LOSS_TARIFF_USD_PER_KWH,
            }
            costs["Cost_Total_Peru"] = (
                costs["Cost_PV_Peru"] + costs["Cost_BESS_Peru"] + costs["Cost_EVCS_Peru"]
            )
            costs["Cost_Total_Intl"] = (
                costs["Cost_PV_Intl"] + costs["Cost_BESS_Intl"] + costs["Cost_EVCS_Intl"]
            )

            # --- Guardar fila en CSV ---
            append_row(cfg.RESULTS_FILE, level, pen_pv, pen_bess, pen_ev, pen_dc, sim, seed_it, costs)

            if cfg.ENABLE_HOURLY_EXPORT:
                idx_vals = [str(level), str(pen_pv), str(pen_bess), str(pen_ev), str(pen_dc), str(seed_it)]
                profiles_map = {
                    "Pnet":    sim["perfil_pactiva"],
                    "Plosses": sim["perfil_losses"],
                    "Trafo":   sim["perfil_trafo"],
                    "Vmin":    sim["perfil_vmin"],
                    "Vmax":    sim["perfil_vmax"],
                }
                for key, profile in profiles_map.items():
                    row = idx_vals + [f"{v:.4f}" for v in profile]
                    with open(hourly_files[key], "a", encoding="utf-8", newline="") as f:
                        f.write(",".join(row) + "\n")

    print(f"\nSimulacion completa. Resultados en: {cfg.RESULTS_FILE}")
