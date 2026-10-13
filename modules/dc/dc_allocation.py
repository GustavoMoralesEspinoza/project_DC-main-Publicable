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
        f.write(f"! Penetración DC       : {penetration_pct} %\n")
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
                f"model=1 daily={shape_name}\n"
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
