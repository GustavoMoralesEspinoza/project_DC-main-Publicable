# project/modules/dc/dc_allocation.py
"""
Lógica de inserción estocástica de Data Centers (DC).
El DC es una carga variable de alta potencia, no un DER.

Metodología (espejo de PV):
  - La penetración fija la energía total: E_objetivo = pen_DC% × E_red_diaria
  - El workload sorteado fija la forma normalizada del perfil
  - El escalado energético convierte forma → kW reales hora a hora

Separación forma/magnitud garantiza que dos DCs con distinto arquetipo
pero la misma penetración consuman exactamente la misma energía diaria.
"""

import random
import numpy as np
from modules.dc.dc_profiles import sample_dc_workload

# Potencia pico por servidor [kW] — Zhang et al. (IET GTD 2024)
_P_SERVER_PEAK_KW = 0.6


def allocate_dc(energy_kwh, penetration_pct,
                mt_buses, mt_kv, mt_phases,
                num_dc,
                profiles, profile_names,
                pue_range=(1.2, 1.8),
                noise_band=0.05,
                excluded_buses=None):
    """
    Genera num_dc Data Centers cuya energía conjunta equivale a
    energy_kwh * penetration_pct / 100.

    Parámetros
    ----------
    energy_kwh      : float      — energía diaria de la red [kWh]
    penetration_pct : float      — penetración DC como % de energy_kwh
    mt_buses        : list[str]  — nombres de barras MT candidatas
    mt_kv           : list[float]— kV base (fase-neutro) de cada barra
    mt_phases       : list[int]  — número de fases de cada barra
    num_dc          : int        — número de DCs a instalar
    profiles        : list       — curvas de workload cargadas por load_dc_profiles()
    profile_names   : list[str]  — nombres de las curvas
    pue_range       : tuple      — (pue_min, pue_max) para sorteo uniforme
    noise_band      : float      — amplitud del ruido horario (±noise_band)
    excluded_buses  : list[str]  — barras a excluir del sorteo (None = sin exclusión)

    Retorna
    -------
    units      : list[dict] — una entrada por DC
    total_energy: float    — energía DC total asignada [kWh]

    Cada dict contiene:
        name            str   — identificador del DC
        bus             str   — barra MT asignada
        phases          int   — número de fases
        kv_ll           float — tensión línea-línea [kV]
        profile_kw      list  — perfil horario en kW (24 valores, ya escalado)
        profile_name    str   — nombre del arquetipo sorteado
        pue             float — PUE sorteado para este DC
        n_servers_equiv int   — servidores implícitos (retro-cálculo)
        energy_kwh      float — energía asignada a este DC [kWh]
        peak_kw         float — potencia pico del DC [kW]
    """
    e_objetivo = energy_kwh * (penetration_pct / 100.0)

    if e_objetivo <= 0 or num_dc <= 0:
        return [], 0.0

    # Barras candidatas (respeta excluded_buses)
    excl = set(excluded_buses) if excluded_buses else set()
    cand_idx = [i for i, b in enumerate(mt_buses) if b not in excl]
    if not cand_idx:
        cand_idx = list(range(len(mt_buses)))

    # Fracciones de energía por DC
    fracciones = _sortear_fracciones(num_dc)

    units = []
    total_asignado = 0.0

    for i, frac in enumerate(fracciones):
        e_dc = e_objetivo * frac

        # Barra aleatoria
        ci = random.choice(cand_idx)
        bus    = mt_buses[ci]
        phases = mt_phases[ci]
        kv_ll  = round(mt_kv[ci] * np.sqrt(3), 3)

        # Arquetipo y PUE
        raw_profile, p_name = sample_dc_workload(profiles, profile_names)
        pue = round(random.uniform(pue_range[0], pue_range[1]), 4)

        # Ruido horario independiente por DC
        noisy = [
            v * (1.0 + random.uniform(-noise_band, noise_band))
            for v in raw_profile
        ]

        # Escalar forma a energía asignada: P[h] = E_dc × noisy[h] / Σnoisy
        suma_noisy = sum(noisy)
        profile_kw = [e_dc * v / suma_noisy for v in noisy]

        peak_kw = max(profile_kw)

        # Retro-cálculo de servidores: pico IT = pico_total / PUE
        p_it_peak_kw = peak_kw / pue
        n_servers = max(1, int(round(p_it_peak_kw / _P_SERVER_PEAK_KW)))

        total_asignado += e_dc

        units.append({
            "name":           f"DC_{i}",
            "bus":            bus,
            "phases":         phases,
            "kv_ll":          kv_ll,
            "profile_kw":     profile_kw,
            "profile_name":   p_name,
            "pue":            pue,
            "n_servers_equiv": n_servers,
            "energy_kwh":     round(e_dc, 4),
            "peak_kw":        round(peak_kw, 4),
        })

    return units, round(total_asignado, 4)


def generate_cenario_dc(units, output_path, penetration_pct,
                        enable_dc_gen=False,
                        dc_self_supply_frac=0.0,
                        dc_gen_profile=None):
    """
    Escribe cenario_DC.dss con elementos Load que representan cada DC.

    El loadshape se normaliza al pico (max=1.0) y kw del Load es el pico.
    OpenDSS escala internamente: P(t) = kw × loadshape_mult(t).

    Si enable_dc_gen=True, agrega por cada DC un Generator co-ubicado
    que representa generación BTM (behind-the-meter) primaria.

    Parámetros
    ----------
    units              : list   — resultado de allocate_dc()
    output_path        : str    — ruta completa del archivo a escribir
    penetration_pct    : float  — para comentario de cabecera
    enable_dc_gen      : bool   — agrega generador BTM por DC
    dc_self_supply_frac: float  — fracción de energía del DC autogenerada
    dc_gen_profile     : list   — perfil normalizado del generador (24 floats); None si no aplica
    """
    def fmt(lst):
        return " ".join(f"{v:.5f}" for v in lst)

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        _tot_e_dc    = sum(u["energy_kwh"]      for u in units)
        _tot_kw_dc   = sum(u["peak_kw"]         for u in units)
        _avg_pue     = (sum(u["pue"] for u in units) / len(units)) if units else 0.0
        _tot_serv    = sum(u["n_servers_equiv"]  for u in units)
        _arqs_dc     = sorted(set(u["profile_name"] for u in units))
        _autogen_str = f"Sí ({dc_self_supply_frac * 100:.0f}%)" if enable_dc_gen else "No"
        f.write("! ──────────────────────────────────────\n")
        f.write("! CENARIO DC — Generado automáticamente\n")
        f.write(f"! Penetración DC        : {penetration_pct} %\n")
        f.write(f"! Data Centers          : {len(units)}\n")
        f.write(f"! Energía total DC      : {_tot_e_dc:.1f} kWh\n")
        f.write(f"! Potencia pico total   : {_tot_kw_dc:.1f} kW\n")
        f.write(f"! PUE promedio          : {_avg_pue:.2f}\n")
        f.write(f"! Servidores equiv.     : {_tot_serv}\n")
        f.write(f"! Arquetipos            : {_arqs_dc}\n")
        f.write(f"! Autogeneración        : {_autogen_str}\n")
        f.write("! ──────────────────────────────────────\n\n")

        if not units:
            f.write("! Sin unidades asignadas\n")
            return

        # --- Loadshapes de carga DC ---
        for u in units:
            peak = u["peak_kw"]
            if peak <= 0:
                peak = 1.0
            # Normalizar al pico para que OpenDSS escale con kw=peak
            ls_norm = [v / peak for v in u["profile_kw"]]
            shape_name = f"CurvaDC_{u['name']}"
            f.write(
                f"New Loadshape.{shape_name} npts=24 interval=1 "
                f"mult=[{fmt(ls_norm)}]\n"
            )

        # --- Loadshapes del generador BTM (si aplica) ---
        if enable_dc_gen and dc_gen_profile is not None:
            gen_peak_norm = max(dc_gen_profile) if max(dc_gen_profile) > 0 else 1.0
            gen_norm = [v / gen_peak_norm for v in dc_gen_profile]
            for u in units:
                gen_shape_name = f"CurvaGenDC_{u['name']}"
                f.write(
                    f"New Loadshape.{gen_shape_name} npts=24 interval=1 "
                    f"mult=[{fmt(gen_norm)}]\n"
                )

        f.write("\n")

        # --- Elementos Load (DC) ---
        for u in units:
            shape_name = f"CurvaDC_{u['name']}"
            f.write(
                f"New Load.{u['name']} "
                f"bus1={u['bus']} "
                f"phases={u['phases']} "
                f"conn=wye "
                f"kv={u['kv_ll']:.3f} "
                f"kw={u['peak_kw']:.2f} "
                f"pf=1.0 "
                f"model=1 status=exempt daily={shape_name}\n"
            )

        # --- Generadores BTM (si aplica) ---
        if enable_dc_gen and dc_gen_profile is not None:
            f.write("\n")
            gen_sum = sum(dc_gen_profile) if sum(dc_gen_profile) > 0 else 1.0
            for u in units:
                gen_shape_name = f"CurvaGenDC_{u['name']}"
                # Potencia del generador escalada a la fracción de autogeneración
                gen_energy = dc_self_supply_frac * u["energy_kwh"]
                gen_peak   = gen_energy / gen_sum * max(dc_gen_profile if dc_gen_profile else [1.0])
                f.write(
                    f"New Generator.GenDC_{u['name']} "
                    f"bus1={u['bus']} "
                    f"phases={u['phases']} "
                    f"kv={u['kv_ll']:.3f} "
                    f"kw={gen_peak:.2f} "
                    f"pf=1.0 "
                    f"model=1 daily={gen_shape_name}\n"
                )


# ---------------------------------------------------------------------------
# Funciones internas
# ---------------------------------------------------------------------------

def _sortear_fracciones(num_dc):
    """
    Genera num_dc fracciones aleatorias que suman 1.0.

    num_dc == 1 → [1.0]
    num_dc == 2 → sortear f ∈ [0.3, 0.7]; fracciones = [f, 1-f]
    num_dc >  2 → sortear N valores U(0,1) y normalizar
    """
    if num_dc == 1:
        return [1.0]
    if num_dc == 2:
        f = random.uniform(0.3, 0.7)
        return [f, 1.0 - f]
    # Caso general: normalización de N uniformes (equivalente a Dirichlet α=1)
    vals = [random.random() for _ in range(num_dc)]
    total = sum(vals)
    return [v / total for v in vals]


# =============================================================================
# Modelo GT&D 2027 (DC_03 seccion 4): potencia maxima de diseno fija,
# energia diaria variable segun mes y temperatura ambiente.
# =============================================================================

def temperature_factor(temp_c, temp_threshold_c, temp_max_c, temp_sensitivity):
    """
    Factor de temperatura (tau_m(h) en el paper), entre 0 y 1.

    temp_c           : array de 24 temperaturas del mes [grados Celsius]
    temp_threshold_c : umbral de refrigeracion (T0) [grados Celsius]
    temp_max_c       : maxima temperatura de las 12x24 [grados Celsius]
    temp_sensitivity : aumento relativo por grado sobre el umbral (beta)
    """
    temp_c = np.asarray(temp_c, dtype=float)
    return ((1.0 + temp_sensitivity * np.maximum(0.0, temp_c - temp_threshold_c))
            / (1.0 + temp_sensitivity * (temp_max_c - temp_threshold_c)))


def equivalent_hours(workload_profile, base_load_frac, temp_months,
                     temp_threshold_c, temp_max_c, temp_sensitivity):
    """
    Horas equivalentes a potencia maxima, promedio anual (H_eq,k en el paper):

        (1/12) * sum_m sum_h [base_load_frac + (1 - base_load_frac) * workload(h)] * factor_m(h)

    Sin ruido (determinista). Unidad: horas.
    """
    shape = base_load_frac + (1.0 - base_load_frac) * np.asarray(workload_profile, dtype=float)
    return float(np.mean([
        (shape * temperature_factor(t, temp_threshold_c, temp_max_c, temp_sensitivity)).sum()
        for t in temp_months
    ]))


def allocate_dc_gtd(energy_kwh, energy_share, archetype, workload,
                    mt_buses, mt_kv, mt_phases,
                    temp_months, rng,
                    month_idx=None,
                    base_load_frac_range=(0.20, 0.35),
                    power_factor_range=(0.95, 0.99),
                    temp_sensitivity=0.015,
                    temp_threshold_c=18.0,
                    hourly_noise=0.05,
                    excluded_buses=None):
    """
    Genera UN Data Center con el modelo GT&D 2027.

    Parametros (entre parentesis, el simbolo del paper)
    ----------
    energy_kwh           : float - energia diaria base de la red, E_base [kWh/dia]
    energy_share         : float - (rho_DC) fraccion de E_base; 0.25 = 25 %. NO es porcentaje.
    archetype            : str   - (k) nombre del arquetipo, p.ej. "inference" | "training"
    workload             : list de 24 floats - (u_k) curva de get_workload_profile
    mt_buses, mt_kv, mt_phases : listas del caso base
    temp_months          : np.ndarray (12, 24) - de load_dc_temperature_matrix [grados Celsius]
    rng                  : np.random.Generator - generador propio de la iteracion
    month_idx            : int 0-11 | None - mes sorteado por el PV; None => se sortea con rng
    base_load_frac_range : (min, max) - (phi) fraccion de carga base
    power_factor_range   : (min, max) - (FP) factor de potencia
    temp_sensitivity     : float - (beta) aumento relativo por grado Celsius
    temp_threshold_c     : float - (T0) umbral de temperatura [grados Celsius]
    hourly_noise         : float - (delta) variacion horaria, +/- fraccion
    excluded_buses       : list[str] | None

    Retorna
    -------
    unit : dict | None - None si energy_share <= 0
    """
    if energy_share <= 0:
        return None

    workload = np.asarray(workload, dtype=float)

    # Barras candidatas: MT trifasicas, sin excluidas (independiente de ONLY_THREE_PHASE)
    excl = set(excluded_buses) if excluded_buses else set()
    cand_idx = [i for i, b in enumerate(mt_buses)
                if b not in excl and int(mt_phases[i]) == 3]
    if not cand_idx:
        raise ValueError("DC: no hay barras MT trifasicas candidatas (revise EXCLUDED_BUSES).")

    # Orden fijo de sorteos: carga base -> factor de potencia -> barra -> ruido -> mes
    base_load_frac = float(rng.uniform(*base_load_frac_range))
    power_factor   = float(rng.uniform(*power_factor_range))
    ci             = cand_idx[int(rng.integers(0, len(cand_idx)))]
    noise          = rng.uniform(-hourly_noise, hourly_noise, 24)
    month_from_pv  = month_idx is not None
    if not month_from_pv:
        month_idx = int(rng.integers(0, 12))

    temp_months = np.asarray(temp_months, dtype=float)
    temp_max_c  = float(temp_months.max())

    eq_hours = equivalent_hours(workload, base_load_frac, temp_months,
                                temp_threshold_c, temp_max_c, temp_sensitivity)
    if eq_hours <= 0:
        raise ValueError(f"equivalent_hours={eq_hours:.4f} <= 0 "
                         f"(base_load_frac={base_load_frac:.3f}, archetype={archetype!r})")
    design_max_kw = energy_share * energy_kwh / eq_hours

    workload_noisy = np.clip(workload * (1.0 + noise), 0.0, 1.0)
    factor = temperature_factor(temp_months[month_idx], temp_threshold_c,
                                temp_max_c, temp_sensitivity)
    P = design_max_kw * (base_load_frac + (1.0 - base_load_frac) * workload_noisy) * factor
    Q = P * np.tan(np.arccos(power_factor))

    peak_kw = float(P.max())
    return {
        "name":             "DC_0",
        "bus":              mt_buses[ci],
        "phases":           mt_phases[ci],
        "kv_ll":            round(mt_kv[ci] * np.sqrt(3), 3),
        "profile_kw":       P.tolist(),
        "profile_kvar":     Q.tolist(),
        "archetype":        archetype,
        "energy_share":     energy_share,
        "base_load_frac":   round(base_load_frac, 4),
        "power_factor":     round(power_factor, 4),
        "month":            month_idx + 1,           # 1-12
        "month_from_pv":    month_from_pv,
        "equivalent_hours": round(eq_hours, 4),
        "design_max_kw":    round(design_max_kw, 4), # capacidad instalada (P_DC^max)
        "peak_kw":          round(peak_kw, 4),       # pico del dia simulado (P_DC^peak)
        "peak_ratio":       round(peak_kw / design_max_kw, 4),   # (kappa)
        "day_energy_kwh":   round(float(P.sum()), 4),
    }


def generate_cenario_dc_gtd(unit, output_path):
    """
    Escribe cenario_DC.dss para el modelo GT&D 2027.
    Loadshape normalizado al pico del dia; Load con kw=peak_kw y pf=power_factor.
    Si unit es None escribe un archivo sin elementos.
    """
    def fmt(lst):
        return " ".join(f"{v:.5f}" for v in lst)

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("! --------------------------------------\n")
        f.write("! CENARIO DC - Modelo GT&D 2027\n")
        if unit is None:
            f.write("! --------------------------------------\n\n")
            f.write("! Sin unidades asignadas\n")
            return
        src = "PV" if unit["month_from_pv"] else "propio"
        f.write(f"! Fraccion energia base (rho)     : {unit['energy_share'] * 100:.1f} %\n")
        f.write(f"! Arquetipo (k)                   : {unit['archetype']}\n")
        f.write(f"! Fraccion carga base (phi)       : {unit['base_load_frac']:.4f}\n")
        f.write(f"! Factor de potencia (FP)         : {unit['power_factor']:.4f}\n")
        f.write(f"! Mes                             : {unit['month']} ({src})\n")
        f.write(f"! Horas equivalentes (H_eq)       : {unit['equivalent_hours']:.4f} h\n")
        f.write(f"! Potencia maxima diseno (P_max)  : {unit['design_max_kw']:.1f} kW\n")
        f.write(f"! Pico del dia (P_peak)           : {unit['peak_kw']:.1f} kW\n")
        f.write(f"! Pico / maxima (kappa)           : {unit['peak_ratio']:.4f}\n")
        f.write(f"! Energia del dia (E_DC)          : {unit['day_energy_kwh']:.1f} kWh\n")
        f.write(f"! Barra                           : {unit['bus']}\n")
        f.write("! --------------------------------------\n\n")

        peak = unit["peak_kw"] if unit["peak_kw"] > 0 else 1.0
        ls_norm = [v / peak for v in unit["profile_kw"]]
        shape = f"CurvaDC_{unit['name']}"
        f.write(f"New Loadshape.{shape} npts=24 interval=1 mult=[{fmt(ls_norm)}]\n\n")
        f.write(
            f"New Load.{unit['name']} "
            f"bus1={unit['bus']} "
            f"phases={unit['phases']} "
            f"conn=wye "
            f"kv={unit['kv_ll']:.3f} "
            f"kw={unit['peak_kw']:.2f} "
            f"pf={unit['power_factor']:.4f} "
            f"model=1 status=exempt daily={shape}\n"
        )
