# project/modules/pv/pv_allocation.py
"""
Lógica de inserción estocástica de sistemas PV.
Metodología común: sortear tamaños hasta alcanzar el objetivo
de energía, luego sortear barras.
"""

import random
import numpy as np


def allocate_pv(energy_kwh, penetration_pct, psh,
                mt_buses, mt_kv, mt_phases,
                pv_sizes_kw, pv_probs,
                power_factor=1.0):
    """
    Sortea unidades PV hasta alcanzar el objetivo de potencia instalada.

    Parámetros
    ----------
    energy_kwh      : float — energía diaria de la red [kWh]
    penetration_pct : float — penetración PV como % de energy_kwh
    psh             : float — peak sun hours del mes sorteado
    mt_buses        : list  — barras MT candidatas
    mt_kv           : list  — kV base (fase-neutro) de cada barra
    mt_phases       : list  — fases de cada barra
    pv_sizes_kw     : list  — tamaños discretos disponibles [kW]
    pv_probs        : list  — probabilidades de cada tamaño (deben sumar 1)
    power_factor    : float — factor de potencia del PVSystem

    Retorna
    -------
    units      : list de dicts — una entrada por unidad sorteada
    p_total_kw : float — potencia PV total instalada [kW]
    """
    e_objetivo = energy_kwh * (penetration_pct / 100.0)
    p_objetivo = e_objetivo / psh

    if p_objetivo <= 0:
        return [], 0.0

    probs = _normalizar(pv_probs)
    sizes = []
    suma  = 0.0
    guard = 0

    while suma < p_objetivo:
        guard += 1
        if guard > 10000:
            break
        size = int(np.random.choice(pv_sizes_kw, p=probs))
        if suma + size <= p_objetivo:
            sizes.append(size)
            suma += size
        else:
            if not sizes:
                sizes.append(min(pv_sizes_kw))
            break

    units = []
    for i, pmpp in enumerate(sizes):
        idx   = random.randint(0, len(mt_buses) - 1)
        kv_ll = mt_kv[idx] * np.sqrt(3)
        units.append({
            "name":         f"PV_{i}",
            "bus":          mt_buses[idx],
            "phases":       mt_phases[idx],
            "kv_ll":        round(kv_ll, 3),
            "pmpp_kw":      pmpp,
            "kva":          round(1.2 * pmpp, 2),
            "power_factor": power_factor,
        })

    return units, float(suma)


def generate_cenario_pv(units, irrad_pu, temp_c, output_path, penetration_pct, mes):
    """
    Escribe el archivo cenario_PV.dss con todos los PVSystems sorteados.

    Parámetros
    ----------
    units           : list  — resultado de allocate_pv
    irrad_pu        : list  — perfil de irradiancia normalizado (24 valores)
    temp_c          : list  — perfil de temperatura en °C (24 valores)
    output_path     : str   — ruta completa del archivo a escribir
    penetration_pct : float — para comentario de cabecera
    mes             : int   — mes sorteado, para comentario de cabecera
    """
    def fmt(lst):
        return " ".join(f"{v:.5f}" for v in lst)

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        _tot_kw_pv = sum(u["pmpp_kw"] for u in units)
        f.write("! ──────────────────────────────────────\n")
        f.write("! CENARIO PV — Generado automáticamente\n")
        f.write(f"! Penetración PV       : {penetration_pct} %\n")
        f.write(f"! Unidades PV           : {len(units)}\n")
        f.write(f"! Potencia pico total   : {_tot_kw_pv:.1f} kW\n")
        f.write(f"! Mes sorteado          : {mes}\n")
        f.write("! ──────────────────────────────────────\n\n")

        if not units:
            f.write("! Sin unidades asignadas\n")
            return

        f.write(f"New Loadshape.Irrad npts=24 interval=1 mult=[{fmt(irrad_pu)}]\n")
        f.write(f"New Tshape.Temp npts=24 interval=1 temp=[{fmt(temp_c)}]\n\n")
        f.write("New XYCurve.Eff npts=4 xarray=[0.1 0.2 0.4 1.0] yarray=[0.86 0.90 0.93 0.97]\n")
        f.write("New XYCurve.FatorPvsT npts=4 xarray=[0 25 75 100] yarray=[1.2 1.0 0.8 0.6]\n\n")

        for u in units:
            f.write(
                f"New PVSystem.{u['name']} "
                f"Phases={u['phases']} "
                f"Bus1={u['bus']} "
                f"Pmpp={u['pmpp_kw']:.2f} "
                f"kV={u['kv_ll']:.3f} "
                #f"kV={13.8/(3**(1/2))} "
                f"kVA={u['kva']:.2f} "
                f"effcurve=Eff P-TCurve=FatorPvsT "
                f"daily=Irrad Tdaily=Temp "
                f"pf={u['power_factor']:.3f}\n"
            )


# ---------------------------------------------------------------------------
def _normalizar(probs):
    arr = np.array(probs, dtype=float)
    s   = arr.sum()
    if s <= 0:
        raise ValueError("La suma de probabilidades debe ser mayor que cero.")
    return list(arr / s)
