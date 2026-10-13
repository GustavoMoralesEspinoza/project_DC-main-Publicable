# project/modules/bess/bess_allocation.py
"""
Lógica de inserción estocástica de BESS.
Sigue la misma metodología que PV: sortear tamaños hasta alcanzar
el objetivo de energía, luego sortear barras.

BESS_PLACEMENT (config.py):
  "colocated" — misma barra que una unidad PV ya asignada en esta iteración
  "free"      — cualquier barra MT, igual que PV
"""

import random
import numpy as np
from modules.bess.bess_profiles import sample_dispatch_profile  # noqa — llamada con profiles,names


def allocate_bess(energy_kwh, penetration_pct,
                  mt_buses, mt_kv, mt_phases,
                  bess_sizes_kwh, bess_probs,
                  charge_hours, placement,
                  profiles, profile_names,
                  pv_units=None,
                  power_factor=1.0):
    """
    Sortea unidades BESS hasta alcanzar el objetivo de energía instalada.

    Parámetros
    ----------
    energy_kwh      : float — energía diaria de la red [kWh]
    penetration_pct : float — penetración BESS como % de energy_kwh
    mt_buses        : list  — barras MT candidatas
    mt_kv           : list  — kV base (fase-neutro) de cada barra
    mt_phases       : list  — fases de cada barra
    bess_sizes_kwh  : list  — tamaños discretos [kWh]
    bess_probs      : list  — probabilidades de cada tamaño
    charge_hours    : float — horas de carga (para calcular kW rated)
    placement       : str   — "colocated" o "free"
    pv_units        : list  — resultado de allocate_pv (solo necesario para "colocated")
    power_factor    : float — factor de potencia

    Retorna
    -------
    units       : list de dicts — una entrada por unidad sorteada
    e_total_kwh : float — energía BESS total instalada [kWh]
    """
    e_objetivo = energy_kwh * (penetration_pct / 100.0)

    if e_objetivo <= 0:
        return [], 0.0

    probs = _normalizar(bess_probs)
    sizes = []
    suma  = 0.0
    guard = 0

    while suma < e_objetivo:
        guard += 1
        if guard > 10000:
            break
        size = int(np.random.choice(bess_sizes_kwh, p=probs))
        if suma + size <= e_objetivo:
            sizes.append(size)
            suma += size
        else:
            if not sizes:
                sizes.append(min(bess_sizes_kwh))
            break

    units = []
    for i, kwh in enumerate(sizes):
        bus, phases, kv = _pick_bus(placement, mt_buses, mt_kv, mt_phases, pv_units)
        kv_ll    = kv * np.sqrt(3)
        kw_rated = kwh / charge_hours
        profile, profile_name = sample_dispatch_profile(profiles, profile_names)

        units.append({
            "name":         f"Bat_{i}",
            "bus":          bus,
            "phases":       phases,
            "kv_ll":        round(kv_ll, 3),
            "kwh_rated":    kwh,
            "kw_rated":     round(kw_rated, 2),
            "power_factor": power_factor,
            "profile":      profile,
            "profile_name": profile_name,
        })

    return units, float(suma)


def generate_cenario_bess(units, output_path, penetration_pct,
                          vminpu=0.75, vmaxpu=1.25,
                          eff_charge=100, eff_discharge=100):
    """
    Escribe el archivo cenario_BESS.dss con todos los Storage sorteados.
    Cada unidad puede tener su propia curva de despacho.

    Parámetros
    ----------
    units           : list  — resultado de allocate_bess
    output_path     : str   — ruta completa del archivo a escribir
    penetration_pct : float — para comentario de cabecera
    vminpu          : float — Vminpu del Storage (ver config.BESS_VMINPU)
    vmaxpu          : float — Vmaxpu del Storage (ver config.BESS_VMAXPU)
    eff_charge      : float — %EffCharge del Storage (ver config.BESS_EFF_CHARGE)
    eff_discharge   : float — %EffDischarge del Storage (ver config.BESS_EFF_DISCHARGE)
    """
    def fmt(lst):
        return " ".join(f"{v:.5f}" for v in lst)

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        _tot_kw_bess   = sum(u["kw_rated"]  for u in units)
        _tot_kwh_bess  = sum(u["kwh_rated"] for u in units)
        _perfiles_bess = sorted(set(u["profile_name"] for u in units))
        f.write("! ──────────────────────────────────────\n")
        f.write("! CENARIO BESS — Generado automáticamente\n")
        f.write(f"! Penetración BESS     : {penetration_pct} %\n")
        f.write(f"! Unidades BESS         : {len(units)}\n")
        f.write(f"! Potencia total        : {_tot_kw_bess:.1f} kW\n")
        f.write(f"! Capacidad total       : {_tot_kwh_bess:.1f} kWh\n")
        f.write(f"! Perfiles usados       : {_perfiles_bess}\n")
        f.write("! ──────────────────────────────────────\n\n")

        if not units:
            f.write("! Sin unidades asignadas\n")
            return

        # Una loadshape por unidad (pueden ser distintas entre sí)
        for u in units:
            shape_name = f"CurvaBat_{u['name']}"
            f.write(
                f"New Loadshape.{shape_name} npts=24 interval=1 "
                f"mult=[{fmt(u['profile'])}]\n"
            )

        f.write("\n")

        for u in units:
            shape_name = f"CurvaBat_{u['name']}"
            f.write(
                f"New Storage.{u['name']} "
                f"bus1={u['bus']} "
                f"phases={u['phases']} "
                f"kv={u['kv_ll']:.3f} "
                f"kWrated={u['kw_rated']:.2f} "
                f"kWhRated={u['kwh_rated']:.2f} "
                f"%stored=20 state=idling "
                f"daily={shape_name} dispmode=follow "
                f"Vminpu={vminpu:.2f} Vmaxpu={vmaxpu:.2f} "
                f"%EffCharge={eff_charge:.2f} %EffDischarge={eff_discharge:.2f}\n"
            )


# ---------------------------------------------------------------------------
def _pick_bus(placement, mt_buses, mt_kv, mt_phases, pv_units):
    """Selecciona una barra según la estrategia de placement."""
    if placement == "colocated" and pv_units:
        pu  = random.choice(pv_units)
        bus = pu["bus"]
        if bus in mt_buses:
            bi = mt_buses.index(bus)
            return bus, mt_phases[bi], mt_kv[bi]
        # fallback a free si el bus PV no está en la lista MT
    idx = random.randint(0, len(mt_buses) - 1)
    return mt_buses[idx], mt_phases[idx], mt_kv[idx]


def _normalizar(probs):
    arr = np.array(probs, dtype=float)
    s   = arr.sum()
    if s <= 0:
        raise ValueError("La suma de probabilidades debe ser mayor que cero.")
    return list(arr / s)
