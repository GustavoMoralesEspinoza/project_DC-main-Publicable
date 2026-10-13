# config.py — Main configuration file
# ============================================================
# This is the ONLY file you need to edit to run the framework.
#
# Quick start:
#   1. Set NETWORK_NAME to the network you want to simulate.
#   2. Enable the DER modules you want (ENABLE_PV, ENABLE_BESS, etc.).
#   3. Adjust NUM_ITERATIONS and PENETRATION_LEVELS_PV for your study.
#   4. Run:  python main.py
#
# Available networks (data/networks/):
#   "18Bus"      — IEEE 18-bus test feeder   (TRANSFORMER_MVA = 7.2)
#   "18Bus_Mod"  — Modified 18-bus feeder    (TRANSFORMER_MVA = 7.2)
#   "CHS031"     — Real MV feeder CHS031     (TRANSFORMER_MVA = 60.0)
# ============================================================

import os

# --- Módulos activos ---
ENABLE_PV    = True
ENABLE_BESS  = False
ENABLE_EV_CS = False
ENABLE_DC    = False                    # Activar módulo Data Center

# --- Red a usar ---
NETWORK_NAME    = "18Bus"       # nombre de subcarpeta en data/networks/   CHS031 o 18Bus
NETWORK_FILE    = "master.dss"  # archivo principal de la red    CHS031_Master o master
# TRANSFORMER_MVA = 60.0          # MVA del transformador principal
TRANSFORMER_MVA = 7.2          # MVA del transformador principal

# --- Rutas (no editar) ---
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
NETWORK_DIR      = os.path.join(BASE_DIR, "data", "networks", NETWORK_NAME)
NETWORK_DSS_PATH = os.path.join(NETWORK_DIR, NETWORK_FILE)
IRRADIANCE_FILE  = os.path.join(BASE_DIR, "data", "irradiance", "Geracao_Solar.csv")
BESS_PROFILES_DIR = os.path.join(BASE_DIR, "data", "bess_profiles")
EV_PROFILES_DIR   = os.path.join(BASE_DIR, "data", "ev_profiles")
RESULTS_DIR      = os.path.join(BASE_DIR, "results")

# --- Monte Carlo ---
NUM_ITERATIONS   = 10          # iteraciones por nivel de penetración
RANDOM_SEED      = 1000           # semilla (None = aleatorio)
ONLY_THREE_PHASE = True         # True = solo barras trifásicas para DERs

# --- Buses excluidos del sorteo de DERs ---
# Buses que NO serán candidatos para instalar PV, BESS ni EV/CS
# Ejemplo: el sourcebus no tiene sentido como punto de conexión
EXCLUDED_BUSES = ["sourcebus"]

# --- Niveles de penetración PV (% de energía diaria de la red) ---
# BESS y EV/CS se calculan automáticamente con los ratios de abajo.
PENETRATION_LEVELS_PV = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]    

# --- Relación BESS y EV/CS respecto a PV ---
# Ejemplos:
#   BESS_PV_RATIO = 1.0  →  ratio 1:1  (BESS = 100% de la penetración PV)
#   BESS_PV_RATIO = 0.5  →  ratio 1:2  (BESS =  50% de la penetración PV)
#   BESS_PV_RATIO = 0.25 →  ratio 1:4  (BESS =  25% de la penetración PV)
BESS_PV_RATIO = 0.25     # penetración BESS = pen_pv * BESS_PV_RATIO
EV_PV_RATIO   = 0.25    # penetración EV   = pen_pv * EV_PV_RATIO

# --- PV ---
#PV_SIZES_KW    = [30, 60, 120, 180, 240]   # tamaños discretos [kW]
#PV_PROBS       = [0.25, 0.30, 0.25, 0.15, 0.05] # probabilidades (deben sumar 1)
PV_SIZES_KW     = [1200, 1600, 2200, 2400, 3200]   # tamaños discretos [kW]
PV_PROBS        = [0.25, 0.30, 0.25, 0.15, 0.05] # probabilidades (deben sumar 1)
PV_POWER_FACTOR = 1.0

# --- BESS ---
BESS_SIZES_KWH = [120, 240, 480, 720, 960]  # tamaños discretos [kWh]
BESS_PROBS     = [0.25, 0.30, 0.25, 0.15, 0.05]  # probabilidades (deben sumar 1)
BESS_CHARGE_HOURS = 4            # horas de carga del BESS
BESS_POWER_FACTOR = 1.0
BESS_PLACEMENT    = "colocated"  # "colocated" = misma barra que PV / "free" = cualquier barra MT

# --- BESS: parámetros del modelo Storage de OpenDSS ---
# Vminpu/Vmaxpu: rango de tensión (pu) dentro del cual el Storage opera a
# potencia constante (fuera de ese rango, OpenDSS pasa a un modelo dependiente
# de tensión). Se fija deliberadamente ancho (0.75-1.25, más ancho que el
# default de OpenDSS 0.90-1.10) para que la FORMA de operación del elemento
# Storage no cambie de régimen por problemas de tensión — es un parámetro del
# MODELO del Storage, NO el límite normativo de violación de tensión del
# estudio (ese sigue siendo 0.95/1.05 pu, usado sin cambios en
# Sev_Vmin_pct/Sev_Vmax_pct y en los gráficos de voltaje).
BESS_VMINPU = 0.75
BESS_VMAXPU = 1.25

# %EffCharge/%EffDischarge = 100 (BESS sin pérdidas internas). Simplificación
# deliberada para aislar el efecto de hosting capacity a nivel de red del
# efecto de las pérdidas propias del BESS — declarar explícitamente como
# supuesto en la sección de metodología del paper.
BESS_EFF_CHARGE    = 100
BESS_EFF_DISCHARGE = 100

# --- EV / Estaciones de carga ---
# Las curvas de carga vienen de archivos CSV en data/ev_profiles/
# Coloca tus curvas ahí (una por archivo, 24 valores, separados por coma).
# En cada iteración cada estación sortea una curva aleatoriamente.
EV_SIZES_KW       = [60, 120, 240]          # potencia máxima de estación [kW]
# EV_SIZES_KW       = [1200, 1200, 1200]          # potencia máxima de estación [kW]
EV_PROBS          = [0.35, 0.45, 0.20]         # probabilidades (deben sumar 1)
# EV_PROBS          = [0.35, 0.45, 0.20]         # probabilidades (deben sumar 1)
EV_POWER_FACTOR   = 0.98
EV_ELIGIBLE_BUSES = []  # barras candidatas para EV/CS, Ejemplo: ["bus5", "bus9", "bus14"]

# ─── Data Center ───────────────────────────────────────────────────────────────

DC_PV_RATIO = 1                # pen_dc = pen_pv × DC_PV_RATIO

NUM_DC = 1                           # Número de DCs por iteración (1, 2, ...)

# Parámetros físicos del DC
DC_PUE_RANGE        = (1.2, 1.8)    # PUE sorteado uniforme por DC
DC_NOISE_BAND       = 0.05          # ±5% ruido horario
DC_POWER_FACTOR     = 0.95          # Factor de potencia del DC

# Autogeneración behind-the-meter (opcional)
ENABLE_DC_GEN       = False         # Activar generación on-site del DC
DC_SELF_SUPPLY_FRAC = 0.20          # Fracción de energía del DC autogenerada

# Directorios
DC_PROFILES_DIR = os.path.join(BASE_DIR, "data", "dc_profiles")

# ─── Costos económicos ─────────────────────────────────────────────────────────
PV_USD_PER_KW_PERU   = 1750
PV_USD_PER_KW_INTL   = 691
BESS_USD_PER_KWH_BASE = 200
BESS_USD_PER_KWH_INTL = 350
EVCS_USD_PER_KW_PERU  = 240
EVCS_USD_PER_KW_INTL  = 850
DC_USD_PER_KW        = 1200
ENERGY_LOSS_TARIFF_USD_PER_KWH = 0.185   # OSINERGMIN, pliego BT5B abril 2026

# ─── Export horario y gráficos ─────────────────────────────────────────────────
ENABLE_HOURLY_EXPORT = True         # Escribir CSVs horarios (Pnet, Plosses, Trafo)
PLOT_BAND_LOWER = 10                # Percentil inferior de banda (ej. 10 = P10)
PLOT_BAND_UPPER = 90                # Percentil superior de banda (ej. 90 = P90)

HOURLY_DIR = os.path.join(RESULTS_DIR, "hourly")

_max_pv   = max(PENETRATION_LEVELS_PV) if ENABLE_PV   else 0
_max_bess = round(_max_pv * BESS_PV_RATIO) if ENABLE_BESS  else 0
_max_ev   = round(_max_pv * EV_PV_RATIO)   if ENABLE_EV_CS else 0
_max_dc   = round(_max_pv * DC_PV_RATIO)   if ENABLE_DC    else 0
RESULTS_FILE = os.path.join(
    RESULTS_DIR,
    f"resultados_{NETWORK_NAME}_PV{_max_pv}_BESS{_max_bess}_EV{_max_ev}_DC{_max_dc}.csv"
)
