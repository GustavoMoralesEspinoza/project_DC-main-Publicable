# project/modules/ev_cs/ev_allocation.py
"""
Lógica de inserción estocástica de estaciones EV/CS.
Sigue la misma metodología que PV y BESS.

Las barras candidatas son solo las indicadas en EV_ELIGIBLE_BUSES (config.py).
Si la lista está vacía, se usan todas las barras MT como fallback.

Cada estación sortea su curva de carga independientemente
desde los perfiles cargados de data/ev_profiles/.
"""

import random
import numpy as np
from modules.ev_cs.ev_profiles import sample_ev_profile


def allocate_ev(energy_kwh, penetration_pct,
                mt_buses, mt_kv, mt_phases,
                ev_sizes_kw, ev_probs,
                ev_eligible_buses,
                profiles, profile_names,
                power_factor=0.98):
    """
    Sortea estaciones EV/CS hasta alcanzar el objetivo de energía.

    Parámetros
    ----------
    energy_kwh        : float — energía diaria de la red [kWh]
    penetration_pct   : float — penetración EV como % de energy_kwh
    mt_buses          : list  — todas las barras MT
    mt_kv             : list  — kV base de cada barra MT
    mt_phases         : list  — fases de cada barra MT
    ev_sizes_kw       : list  — tamaños discretos de estación [kW]
    ev_probs          : list  — probabilidades de cada tamaño
    ev_eligible_buses : list  — barras candidatas (vacío = todas las MT)
    profiles          : list  — curvas cargadas por load_ev_profiles()
    profile_names     : list  — nombres de las curvas
    power_factor      : float — factor de potencia de la carga EV

    Retorna
    -------
    units       : list de dicts — una entrada por estación sorteada
    e_total_kwh : float — energía EV estimada total [kWh/día]
    """
    # Factor de energía basado en la curva promedio de todos los perfiles
    # (área bajo la curva promedio = kWh/día por cada kW instalado)
    avg_curve   = [sum(p[h] for p in profiles) / len(profiles) for h in range(24)]
    factor_energia = sum(avg_curve)   # kWh/día por kW instalado

    e_objetivo = energy_kwh * (penetration_pct / 100.0)
    if e_objetivo <= 0:
        return [], 0.0

    # Barras elegibles
    if ev_eligible_buses:
        cand_idx = [i for i, b in enumerate(mt_buses) if b in ev_eligible_buses]
        if not cand_idx:
            cand_idx = list(range(len(mt_buses)))
    else:
        cand_idx = list(range(len(mt_buses)))

    probs  = _normalizar(ev_probs)
    sizes  = []
    e_acum = 0.0
    guard  = 0

    while True:
        guard += 1
        if guard > 10000:
            break
        size       = int(np.random.choice(ev_sizes_kw, p=probs))
        e_estacion = size * factor_energia

        dif_actual = abs(e_objetivo - e_acum)
        dif_nueva  = abs(e_objetivo - (e_acum + e_estacion))

        if dif_nueva <= dif_actual:
            sizes.append(size)
            e_acum += e_estacion
        else:
            if not sizes:
                size_min = min(ev_sizes_kw)
                sizes.append(size_min)
                e_acum += size_min * factor_energia
            break

        if e_acum >= e_objetivo:
            break

    units = []
    for i, kw in enumerate(sizes):
        ci    = random.choice(cand_idx)
        kv_ll = mt_kv[ci] * np.sqrt(3)
        # Cada estación sortea su propia curva
        profile, profile_name = sample_ev_profile(profiles, profile_names)
        units.append({
            "name":         f"EV_{i}",
            "bus":          mt_buses[ci],
            "phases":       mt_phases[ci],
            "kv_ll":        round(kv_ll, 3),
            "kw":           kw,
            "power_factor": power_factor,
            "profile":      profile,
            "profile_name": profile_name,
        })

    return units, float(e_acum)


def generate_cenario_ev(units, output_path, penetration_pct):
    """
    Escribe cenario_EV.dss con todas las estaciones de carga sorteadas.
    Cada estación puede tener su propia curva de carga.

    Parámetros
    ----------
    units           : list  — resultado de allocate_ev
    output_path     : str   — ruta completa del archivo a escribir
    penetration_pct : float — para comentario de cabecera
    """
    def fmt(lst):
        return " ".join(f"{v:.5f}" for v in lst)

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        _tot_kw_ev   = sum(u["kw"] for u in units)
        _perfiles_ev = sorted(set(u["profile_name"] for u in units))
        f.write("! ──────────────────────────────────────\n")
        f.write("! CENARIO EV/CS — Generado automáticamente\n")
        f.write(f"! Penetración EV       : {penetration_pct} %\n")
        f.write(f"! Estaciones EV         : {len(units)}\n")
        f.write(f"! Potencia total inst.  : {_tot_kw_ev:.1f} kW\n")
        f.write(f"! Perfiles usados       : {_perfiles_ev}\n")
        f.write("! ──────────────────────────────────────\n\n")

        if not units:
            f.write("! Sin unidades asignadas\n")
            return

        # Una loadshape por estación (pueden ser distintas entre sí)
        for u in units:
            shape_name = f"CurvaEV_{u['name']}"
            f.write(
                f"New Loadshape.{shape_name} npts=24 interval=1 "
                f"mult=[{fmt(u['profile'])}]\n"
            )

        f.write("\n")

        for u in units:
            shape_name = f"CurvaEV_{u['name']}"
            f.write(
                f"New Load.{u['name']} "
                f"bus1={u['bus']} "
                f"phases={u['phases']} "
                f"conn=wye "
                f"kv={u['kv_ll']:.3f} "
                f"kw={u['kw']:.2f} "
                f"pf={u['power_factor']:.3f} "
                f"model=1 status=exempt daily={shape_name}\n"
            )


# ---------------------------------------------------------------------------
def _normalizar(probs):
    arr = np.array(probs, dtype=float)
    s   = arr.sum()
    if s <= 0:
        raise ValueError("La suma de probabilidades debe ser mayor que cero.")
    return list(arr / s)
