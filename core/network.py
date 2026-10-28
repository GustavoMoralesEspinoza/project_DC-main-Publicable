# project/core/network.py
"""
Carga la red en OpenDSS y corre el caso base (sin DERs).
Retorna todas las métricas de 24 horas que necesita el loop Monte Carlo.
"""

import numpy as np
import py_dss_interface


def run_base_case(dss_file, transformer_mva, only_three_phase=True, excluded_buses=None,
                  control_mode="off", allow_forms=False, only_mt=True, load_mult=1.0):
    """
    Compila la red y corre simulación diaria de 24 horas sin DERs.

    Parámetros
    ----------
    dss_file        : str   — ruta absoluta al master.dss de la red
    transformer_mva : float — potencia nominal del transformador principal en MVA
    only_three_phase: bool  — si True, devuelve solo barras trifásicas como candidatas
    control_mode    : str   — modo del lazo de control OpenDSS ("off"|"static"|"time").
                              "off" congela reguladores/capacitores (sin iteraciones
                              de control extra); "static" los deja actuar normalmente.

    Retorna
    -------
    dict con las siguientes claves:
        energy_kwh       : float — energía activa diaria de la red [kWh]
        p_max_kw         : float — demanda máxima activa [kW]
        mt_buses         : list  — nombres de barras MT candidatas
        mt_kv            : list  — tensión base de cada barra MT [kV fase-neutro]
        mt_phases        : list  — número de fases de cada barra MT
        perfil_vmin      : list  — tensión mínima por hora (24 valores) [pu]
        perfil_vmax      : list  — tensión máxima por hora (24 valores) [pu]
        perfil_pactiva   : list  — potencia activa por hora (24 valores) [kW]
        perfil_preactiva : list  — potencia reactiva por hora (24 valores) [kVar]
        perfil_losses    : list  — pérdidas activas por hora (24 valores) [kW]
        perfil_trafo     : list  — cargamento del transformador por hora (24 valores) [%]
        n_viol_vmin      : list  — barras con Vmin por hora (24 valores)
        n_viol_vmax      : list  — barras con Vmax por hora (24 valores)
        fluxo_min        : float — flujo mínimo en la subestación en 24h [kW]
    """
    dss = py_dss_interface.DSS()
    # Disable modal forms/alert boxes so nothing can block an unattended batch
    dss.dssinterface.allow_forms = 1 if allow_forms else 0
    dss.text(f"compile [{dss_file}]")
    dss.text(f"set controlmode={control_mode}")
    # Escala las cargas de la red (las del DC y EV se escriben con status=exempt)
    dss.text(f"set loadmult={load_mult}")

    # --- Identificar barras MT candidatas ---
    mt_buses, mt_kv, mt_phases = _get_mt_buses(dss, only_three_phase, excluded_buses)
    if len(mt_buses) == 0:
        raise ValueError(
            "No se encontraron barras MT candidatas. "
            "Revise los límites de tensión o el archivo de red."
        )
    all_mt_buses, _, _ = _get_mt_buses(dss, only_three_phase, excluded_buses=None)
    n_mt_total = len(all_mt_buses)

    # --- Correr 24 horas ---
    kva_base = transformer_mva * 1000.0

    perfil_vmin, perfil_vmax = [], []
    perfil_pactiva, perfil_preactiva, perfil_losses = [], [], []
    perfil_trafo = []

    # Sets de barras únicas afectadas en al menos 1 hora de las 24h
    buses_vmin = set()   # barras con subtensión  (<0.95 pu) en al menos 1 hora
    buses_vmax = set()   # barras con sobretensión (>1.05 pu) en al menos 1 hora

    for hour in range(24):
        dss.text("Set mode=daily")
        dss.text(f"Set number={hour + 1}")
        dss.text("Solve")

        # Tensiones — acumula barras afectadas en los sets
        vmin, vmax, buses_bajo, buses_alto, _, _ = _get_voltage_stats(
            dss, only_mt=only_mt, only_three_phase=only_three_phase)
        perfil_vmin.append(vmin)
        perfil_vmax.append(vmax)
        buses_vmin.update(buses_bajo)
        buses_vmax.update(buses_alto)

        # Potencia y pérdidas
        p_act  = -(dss.circuit._total_power()[0])
        p_reac = abs(dss.circuit._total_power()[1])
        losses = abs(dss.circuit._losses()[0]) / 1000.0

        perfil_pactiva.append(p_act)
        perfil_preactiva.append(p_reac)
        perfil_losses.append(losses)

        # Cargamento transformador
        s_kva = (p_act**2 + p_reac**2) ** 0.5
        perfil_trafo.append(100.0 * s_kva / kva_base)

    energy_kwh = float(np.sum(perfil_pactiva))
    p_max_kw   = float(np.max(perfil_pactiva))
    fluxo_min  = float(np.min(perfil_pactiva))  # negativo = flujo reverso

    return {
        "energy_kwh":       energy_kwh,
        "p_max_kw":         p_max_kw,
        "mt_buses":         mt_buses,
        "mt_kv":            mt_kv,
        "mt_phases":        mt_phases,

        # KPIs utilizados en general para evaluar cada iteración del Monte Carlo
        "perfil_vmin":      perfil_vmin,
        "perfil_vmax":      perfil_vmax,
        "perfil_pactiva":   perfil_pactiva,
        "perfil_preactiva": perfil_preactiva,
        "perfil_losses":    perfil_losses,
        "perfil_trafo":     perfil_trafo,
        # Contadores finales de barras únicas afectadas en las 24h
        "buses_vmin":       buses_vmin,   # set de nombres de barra
        "buses_vmax":       buses_vmax,   # set de nombres de barra
        "fluxo_min":        fluxo_min,
        "n_mt_total":       n_mt_total,
    }


def run_with_ders(dss_file, transformer_mva,
                  enable_pv=False, path_pv=None,
                  enable_bess=False, path_bess=None,
                  enable_ev=False, path_ev=None,
                  enable_dc=False, path_dc=None,
                  n_mt_total=1, control_mode="off", allow_forms=False,
                  only_mt=True, only_three_phase=True, load_mult=1.0):
    """
    Compila la red y carga los DERs activos con redirect explícito.
    Solo hace redirect a los archivos de los módulos habilitados.

    Parámetros
    ----------
    dss_file        : str  — ruta al master.dss
    transformer_mva : float
    enable_pv       : bool — si True, carga cenario_PV.dss
    path_pv         : str  — ruta completa de cenario_PV.dss
    enable_bess     : bool — si True, carga cenario_BESS.dss
    path_bess       : str  — ruta completa de cenario_BESS.dss
    enable_ev       : bool — si True, carga cenario_EV.dss
    path_ev         : str  — ruta completa de cenario_EV.dss
    enable_dc       : bool — si True, carga cenario_DC.dss
    path_dc         : str  — ruta completa de cenario_DC.dss
    """
    dss = py_dss_interface.DSS()
    # Disable modal forms/alert boxes so nothing can block an unattended batch
    dss.dssinterface.allow_forms = 1 if allow_forms else 0
    dss.text(f"compile [{dss_file}]")
    dss.text(f"set controlmode={control_mode}")

    # Cargar solo los DERs activos en esta simulación
    if enable_pv and path_pv:
        dss.text(f"redirect [{path_pv}]")
    if enable_bess and path_bess:
        dss.text(f"redirect [{path_bess}]")
    if enable_ev and path_ev:
        dss.text(f"redirect [{path_ev}]")
    if enable_dc and path_dc:
        dss.text(f"redirect [{path_dc}]")
    # Escala las cargas de la red (las del DC y EV se escriben con status=exempt)
    dss.text(f"set loadmult={load_mult}")

    kva_base = transformer_mva * 1000.0

    perfil_vmin, perfil_vmax = [], []
    perfil_pactiva, perfil_preactiva, perfil_losses = [], [], []
    perfil_trafo = []

    buses_vmin = set()
    buses_vmax = set()
    tension_barras = {}   # {bus_name: {hour: avg_v_pu}}
    acum_bajo  = 0
    acum_alto  = 0
    acum_union = 0

    for hour in range(24):
        dss.text("Set mode=daily")
        dss.text(f"Set number={hour + 1}")
        dss.text("Solve")

        vmin, vmax, buses_bajo, buses_alto, n_bajo_hora, n_alto_hora = _get_voltage_stats(
            dss, only_mt=only_mt, only_three_phase=only_three_phase)
        perfil_vmin.append(vmin)
        perfil_vmax.append(vmax)
        buses_vmin.update(buses_bajo)
        buses_vmax.update(buses_alto)
        acum_bajo  += n_bajo_hora
        acum_alto  += n_alto_hora
        acum_union += len(buses_bajo | buses_alto)

        p_act  = -(dss.circuit._total_power()[0])
        p_reac = abs(dss.circuit._total_power()[1])
        losses = abs(dss.circuit._losses()[0]) / 1000.0

        perfil_pactiva.append(p_act)
        perfil_preactiva.append(p_reac)
        perfil_losses.append(losses)

        s_kva = (p_act**2 + p_reac**2) ** 0.5
        perfil_trafo.append(100.0 * s_kva / kva_base)

        # Tensión promedio por barra en esta hora (mismo filtro MT que los KPIs)
        for bus in dss.circuit.buses_names:
            bus_clean = _clean_bus_name(bus)
            if not bus_clean:
                continue
            dss.circuit.set_active_bus(bus_clean)
            base_v = dss.bus.kv_base * 1000.0
            if base_v <= 0:
                continue
            if only_mt and not _is_mt_bus(dss, only_three_phase):
                continue
            voltages_v = dss.bus.vmag_angle[::2]
            v_pu = [v / base_v for v in voltages_v if v / base_v > 0.05]
            if v_pu:
                if bus_clean not in tension_barras:
                    tension_barras[bus_clean] = {}
                tension_barras[bus_clean][hour] = float(np.mean(v_pu))

    perfil_tension_barras = {
        bus: [tension_barras[bus].get(h, None) for h in range(24)]
        for bus in tension_barras
        if sum(1 for v in tension_barras[bus].values() if v is not None) == 24
    }

    denom = n_mt_total * 24
    sev_vmin_pct  = round(100.0 * acum_bajo  / denom, 4) if denom > 0 else 0.0
    sev_vmax_pct  = round(100.0 * acum_alto  / denom, 4) if denom > 0 else 0.0
    sev_union_pct = round(100.0 * acum_union / denom, 4) if denom > 0 else 0.0

    return {
        "perfil_vmin":           perfil_vmin,
        "perfil_vmax":           perfil_vmax,
        "perfil_pactiva":        perfil_pactiva,
        "perfil_preactiva":      perfil_preactiva,
        "perfil_losses":         perfil_losses,
        "perfil_trafo":          perfil_trafo,
        "buses_vmin":            buses_vmin,
        "buses_vmax":            buses_vmax,
        "fluxo_min":             float(np.min(perfil_pactiva)),
        "perfil_tension_barras": perfil_tension_barras,
        "sev_vmin_pct":          sev_vmin_pct,
        "sev_vmax_pct":          sev_vmax_pct,
        "sev_union_pct":         sev_union_pct,
        "vmin_24h":              float(np.min(perfil_vmin)),
        "vmax_24h":              float(np.max(perfil_vmax)),
    }

# ---------------------------------------------------------------------------
# Funciones internas (no llamar desde otros módulos)
# ---------------------------------------------------------------------------

def _clean_bus_name(bus):
    """
    Limpia el nombre de barra antes de pasarlo a set_active_bus.
    - Filtra None (py_dss_interface a veces incluye None en la lista)
    - Toma solo la parte antes del punto: 'busname.1.2.3' -> 'busname'
    - Elimina caracteres no-ASCII que rompen el encode('ascii') interno
    Retorna string limpio, o cadena vacia si el nombre no es valido.
    """
    if bus is None:
        return ""
    name = str(bus).split(".")[0].strip()
    return name.encode("ascii", errors="ignore").decode("ascii")


def _get_mt_buses(dss, only_three_phase, excluded_buses=None):
    """Retorna listas paralelas: nombres, kV base y número de fases de barras MT."""
    buses, kvs, phases = [], [], []
    for bus in dss.circuit.buses_names:
        bus_clean = _clean_bus_name(bus)
        if not bus_clean:
            continue
        if excluded_buses and bus_clean in excluded_buses:
            continue
        dss.circuit.set_active_bus(bus_clean)
        kv_base   = dss.bus.kv_base
        num_nodes = dss.bus.num_nodes
        v_pu      = dss.bus.vmag_angle_pu[::2]

        es_mt        = 2.3 <= kv_base <= 25
        tiene_v      = any(v > 0.05 for v in v_pu)
        es_trifasica = num_nodes == 3

        if es_mt and tiene_v:
            if only_three_phase and not es_trifasica:
                continue
            buses.append(bus_clean)
            kvs.append(kv_base)
            phases.append(num_nodes)
    return buses, kvs, phases


def _is_mt_bus(dss, only_three_phase):
    """
    True si la barra ACTIVA cumple el criterio de media tensión (2.3-25 kV).
    Mismo criterio que _get_mt_buses para que el conteo de violaciones y el
    denominador de severidad (n_mt_total) usen el mismo universo de barras.
    Asume que la barra ya fue activada con set_active_bus.
    """
    kv_base = dss.bus.kv_base
    if not (2.3 <= kv_base <= 25):
        return False
    if only_three_phase and dss.bus.num_nodes != 3:
        return False
    return True


def _get_voltage_stats(dss, only_mt=True, only_three_phase=True):
    """
    Recorre las barras en un instante horario y devuelve:
        vmin        : tensión mínima del sistema en pu
        vmax        : tensión máxima del sistema en pu
        buses_bajo  : set de nombres de barras con al menos una fase < 0.95 pu
        buses_alto  : set de nombres de barras con al menos una fase > 1.05 pu

    Si only_mt=True, solo se consideran barras de media tensión (2.3-25 kV),
    evitando que barras BT con base de tensión inconsistente contaminen los KPIs.

    El loop de 24h acumula estos sets con .update() para obtener
    el total de barras únicas afectadas en toda la simulación.
    """
    all_v = []
    buses_bajo = set()
    buses_alto = set()

    for bus in dss.circuit.buses_names:
        bus_clean = _clean_bus_name(bus)
        if not bus_clean:
            continue
        dss.circuit.set_active_bus(bus_clean)
        base_v = dss.bus.kv_base * 1000.0
        if base_v <= 0:
            continue
        if only_mt and not _is_mt_bus(dss, only_three_phase):
            continue
        voltages_v = dss.bus.vmag_angle[::2]
        v_pu = [v / base_v for v in voltages_v if v / base_v > 0.05]
        if not v_pu:
            continue
        all_v.extend(v_pu)
        if any(v < 0.95 for v in v_pu):
            buses_bajo.add(bus_clean)
        if any(v > 1.05 for v in v_pu):
            buses_alto.add(bus_clean)

    vmin = float(np.min(all_v)) if all_v else 1.0
    vmax = float(np.max(all_v)) if all_v else 1.0

    return vmin, vmax, buses_bajo, buses_alto, len(buses_bajo), len(buses_alto)
