# project/results/reporter.py
"""
Inicializa el archivo CSV de resultados y agrega filas por iteración.
Una fila = una iteración Monte Carlo completa.
"""

import os
import csv
import numpy as np

COLUMNS = [
    "Penetration_Level",
    "Pen_PV", "Pen_BESS", "Pen_EV", "Pen_DC",
    "B_Vmin", "B_Vmax", "B_VminVmax",
    "Max_PLosses", "Min_PLosses", "Energy_Losses",
    "Min_Fluxo_Subestacao",
    "Trafo_Loading_pct",
    "Vmin_24h", "Vmax_24h",
    "Sev_Vmin_pct", "Sev_Vmax_pct", "Sev_VminVmax_pct",
    "Seed",
    "PV_kW_inst", "BESS_kWh_inst", "EV_kW_inst", "DC_kW_inst",
    "Cost_PV_Peru", "Cost_PV_Intl",
    "Cost_BESS_Peru", "Cost_BESS_Intl",
    "Cost_EVCS_Peru", "Cost_EVCS_Intl",
    "Cost_DC",
    "Cost_Total_Peru", "Cost_Total_Intl",
    "Energy_Losses_USD",
]


def init_csv(filepath):
    """
    Crea el archivo CSV con la cabecera.
    Si ya existe, lo sobreescribe.
    Crea la carpeta results/ si no existe.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()


def append_row(filepath, level, pen_pv, pen_bess, pen_ev, pen_dc, sim_results, seed_it, costs):
    """
    Agrega una fila al CSV de resultados.

    Parámetros
    ----------
    filepath     : str   — ruta del CSV
    level        : float — nivel de barrido crudo (elemento de cfg.PENETRATION_LEVELS_PV
                            para esta iteración), guardado tal cual en "Penetration_Level".
                            Es la variable de barrido inequívoca: a diferencia de Pen_PV,
                            no se apaga a 0 cuando ENABLE_PV=False, así que los scripts de
                            plots/ pueden usarla directamente sin adivinar cuál Pen_* varía
                            (antes fallaba en escenarios "solo EV" o "solo BESS", que
                            colapsaban a un único punto porque la detección solo miraba
                            Pen_PV/Pen_DC — ver STYLE_DIAGNOSTIC / fix de sweep detection).
    pen_pv       : float — penetración PV usada en esta iteración
    pen_bess     : float — penetración BESS usada en esta iteración
    pen_ev       : float — penetración EV usada en esta iteración
    pen_dc       : float — penetración DC usada en esta iteración
    sim_results  : dict  — resultado de core.network.run_with_ders()
    seed_it      : int   — semilla usada en esta iteración
    costs        : dict  — capacidades instaladas y costos económicos de la iteración
                            (ver claves calculadas en core.monte_carlo.run_monte_carlo)

    Contadores de tensión (barras únicas afectadas en al menos 1h de las 24h):
        B_Vmin    : barras con subtensión  (<0.95 pu) en al menos 1 hora
        B_Vmax    : barras con sobretensión (>1.05 pu) en al menos 1 hora
        B_VminVmax: barras con sub O sobretensión en al menos 1 hora (unión de los dos sets)
    """
    buses_vmin = sim_results["buses_vmin"]   # set de nombres de barra
    buses_vmax = sim_results["buses_vmax"]   # set de nombres de barra

    b_vmin     = len(buses_vmin)
    b_vmax     = len(buses_vmax)
    b_vminvmax = len(buses_vmin | buses_vmax)   # unión — evita doble conteo

    row = {
        "Penetration_Level":    level,
        "Pen_PV":               pen_pv,
        "Pen_DC":               pen_dc,
        "Pen_BESS":             pen_bess,
        "Pen_EV":               pen_ev,
        "B_Vmin":               b_vmin,
        "B_Vmax":               b_vmax,
        "B_VminVmax":           b_vminvmax,
        "Max_PLosses":          round(float(np.max(sim_results["perfil_losses"])), 4),
        "Min_PLosses":          round(float(np.min(sim_results["perfil_losses"])), 4),
        "Energy_Losses":        round(float(np.sum(sim_results["perfil_losses"])), 4),
        "Min_Fluxo_Subestacao": round(float(sim_results["fluxo_min"]),             4),
        "Trafo_Loading_pct":    round(float(np.max(sim_results["perfil_trafo"])),   4),
        "Vmin_24h":             round(float(sim_results["vmin_24h"]),              4),
        "Vmax_24h":             round(float(sim_results["vmax_24h"]),              4),
        "Sev_Vmin_pct":         round(float(sim_results["sev_vmin_pct"]),          4),
        "Sev_Vmax_pct":         round(float(sim_results["sev_vmax_pct"]),          4),
        "Sev_VminVmax_pct":     round(float(sim_results["sev_union_pct"]),         4),
        "Seed":                 seed_it,
        "PV_kW_inst":           round(float(costs["PV_kW_inst"]),    4),
        "BESS_kWh_inst":        round(float(costs["BESS_kWh_inst"]), 4),
        "EV_kW_inst":           round(float(costs["EV_kW_inst"]),    4),
        "DC_kW_inst":           round(float(costs["DC_kW_inst"]),    4),
        "Cost_PV_Peru":         round(float(costs["Cost_PV_Peru"]),   2),
        "Cost_PV_Intl":         round(float(costs["Cost_PV_Intl"]),   2),
        "Cost_BESS_Peru":       round(float(costs["Cost_BESS_Peru"]), 2),
        "Cost_BESS_Intl":       round(float(costs["Cost_BESS_Intl"]), 2),
        "Cost_EVCS_Peru":       round(float(costs["Cost_EVCS_Peru"]), 2),
        "Cost_EVCS_Intl":       round(float(costs["Cost_EVCS_Intl"]), 2),
        "Cost_DC":              round(float(costs["Cost_DC"]),        2),
        "Cost_Total_Peru":      round(float(costs["Cost_Total_Peru"]), 2),
        "Cost_Total_Intl":      round(float(costs["Cost_Total_Intl"]), 2),
        "Energy_Losses_USD":    round(float(costs["Energy_Losses_USD"]), 4),
    }

    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)
