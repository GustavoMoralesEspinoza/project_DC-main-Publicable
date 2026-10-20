# config.py — Main configuration file
# =============================================================================
# This is the ONLY file you need to edit to run the framework.
#
# Quick start:
#   1. Set NETWORK_NAME to the network you want to simulate.
#   2. Enable the DER modules you want (ENABLE_PV, ENABLE_BESS, etc.).
#   3. Adjust NUM_ITERATIONS and PENETRATION_LEVELS_PV for your study.
#   4. Run:  python main.py
#
# Available networks (data/networks/):
#   "18Bus"      — IEEE 18-bus test feeder        (set TRANSFORMER_MVA = 7.2)
#   "18Bus_Mod"  — Modified 18-bus test feeder    (set TRANSFORMER_MVA = 7.2)
#   "CHS031"     — Real MV distribution feeder    (set TRANSFORMER_MVA = 60.0)
# =============================================================================

import os

# =============================================================================
# 1. ACTIVE MODULES
#    Set each flag to True to include that DER type in the simulation.
#    Modules set to False are completely skipped — no elements are added
#    to the network and their penetration is fixed at 0%.
# =============================================================================

ENABLE_PV    = True    # Photovoltaic generation (PVSystem elements in OpenDSS)
ENABLE_BESS  = False   # Battery energy storage  (Storage elements in OpenDSS)
ENABLE_EV_CS = False   # EV charging stations    (Load elements in OpenDSS)
ENABLE_DC    = False   # Data centers            (Load elements in OpenDSS)

# =============================================================================
# 2. NETWORK SELECTION
#    NETWORK_NAME must match a subfolder name inside data/networks/.
#    NETWORK_FILE is the OpenDSS master file inside that subfolder.
#    TRANSFORMER_MVA is the rated power of the main substation transformer;
#    it is used to compute per-unit transformer loading in results.
# =============================================================================

NETWORK_NAME    = "RBRR1303"                              # Options: "18Bus" | "18Bus_Mod" | "CHS031" | "RCSO1307" | "RBRR1303"
NETWORK_FILE    = "DU_1_Master_391_BRR_RBRR1303.dss"      # Options: "master.dss" | "CHS031_Master.dss" | "DU_1_Master_391_CSO_RCSO1307.dss" | "DU_1_Master_391_BRR_RBRR1303.dss"
TRANSFORMER_MVA = 5.25                                    # Options:  7.2 (18Bus/18Bus_Mod)  |  60.0 (CHS031)  |  15.0 (RCSO1307)  |  5.25 (RBRR1303 — 3×1750 kVA regulators)

# Scenario file naming mode:
#   "replace" — single shared files (cenario_PV.dss, cenario_BESS.dss, ...)
#               overwritten each iteration. Default, compatible with all tools.
#   "full"    — one file per iteration (cenario_PV_pen050_seed1001.dss, ...)
#               stored in data/networks/<network>/cenarios/ subfolder.
#               Required for parallel execution (eliminates file write conflicts).
SCENARIO_MODE = "full"   # Options: "replace" | "full"

# Only relevant in SCENARIO_MODE = "full":
#   True  → delete all files in cenarios/ at the start of each run (clean slate)
#   False → keep files from previous runs (useful for debugging/auditing)
KEEP_SCENARIO_FILES = False

# Parallel execution — requires SCENARIO_MODE = "full"
#   ENABLE_PARALLEL: set True to distribute iterations across CPU cores.
#   NUM_WORKERS: number of parallel worker processes.
#     None  → uses os.cpu_count() (all available cores)
#     N     → use N cores. Recommended: os.cpu_count() - 1 to keep one core free.
ENABLE_PARALLEL = True
NUM_WORKERS     = None

# =============================================================================
# 3. PATHS  —  do not edit
#    All paths are derived automatically from the settings above.
# =============================================================================

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
NETWORK_DIR       = os.path.join(BASE_DIR, "data", "networks", NETWORK_NAME)
NETWORK_DSS_PATH  = os.path.join(NETWORK_DIR, NETWORK_FILE)
CENARIOS_DIR      = os.path.join(NETWORK_DIR, "cenarios")
IRRADIANCE_FILE   = os.path.join(BASE_DIR, "data", "irradiance", "Geracao_Solar.csv")
BESS_PROFILES_DIR = os.path.join(BASE_DIR, "data", "bess_profiles")
EV_PROFILES_DIR   = os.path.join(BASE_DIR, "data", "ev_profiles")
DC_PROFILES_DIR   = os.path.join(BASE_DIR, "data", "dc_profiles")
RESULTS_DIR       = os.path.join(BASE_DIR, "results")

# =============================================================================
# 4. MONTE CARLO SETTINGS
# =============================================================================

# Number of random iterations per penetration level.
# Higher values give smoother statistical distributions but longer runtimes.
# Recommended: 10 (quick test) | 30 (standard) | 100+ (publication quality)
NUM_ITERATIONS = 5000

# Global random seed for full reproducibility across runs.
# Set to None to use a different random draw every time.
# Each iteration uses seed = RANDOM_SEED + iteration_counter internally.
RANDOM_SEED = 1   # Options: any integer | None (fully random)

# If True, only three-phase buses are candidates for DER placement.
# Recommended True for medium-voltage studies; set False to include
# single- and two-phase buses as well.
ONLY_THREE_PHASE = True

# OpenDSS control-loop mode. Governs whether in-network controls
# (voltage regulators / SVR, switched capacitors) act during each solve.
#   "off"    — controls frozen at their initial state; no extra control
#              iterations. DEFAULT and fastest. Use this when you want the
#              hosting-capacity sweep to be independent of tap/cap action.
#   "static" — controls act normally each solve (physically faithful). A few
#              networks with very tight regulator bands (e.g. RBRR1303, whose
#              regulator band is ~5x smaller than one tap step) can enter
#              control "hunting" and fail to converge on some random draws.
#   "time"   — time-based control actions (pre-set tap/cap schedules).
# An invalid value is passed through to OpenDSS as-is (no local validation).
CONTROL_MODE = "off"

# OpenDSS "AllowForms" switch. When forms are allowed, OpenDSS can pop up modal
# dialog / alert boxes (e.g. on solver warnings) that BLOCK execution until a
# human clicks them — fatal for unattended batch runs of 10,000+ iterations.
#   False — forms disabled (AllowForms=0). Nothing can halt the run. DEFAULT.
#   True  — forms allowed (interactive debugging only).
# Note: OpenDSS only lets you turn this OFF within a session; leave False for
# production sweeps.
ALLOW_FORMS = False

# =============================================================================
# 5. EXCLUDED BUSES
#    List of bus names that will never receive any DER (PV, BESS, EV, DC).
#    Always exclude the source/slack bus — it has no physical meaning
#    as a DER connection point.
#    Example with multiple exclusions: ["sourcebus", "bus1", "bus18"]
# =============================================================================

EXCLUDED_BUSES = ["MT8563317ID"]   # RBRR1303 source bus. Use ["busA"] for RCSO1307 | ["sourcebus"] for 18Bus/CHS031.

# =============================================================================
# 6. PENETRATION SWEEP  —  PV levels [% of daily network energy]
#    This list drives the entire Monte Carlo sweep.
#    BESS, EV/CS, and DC penetrations are derived automatically from
#    these values using the ratios defined in Section 7.
#
#    Examples:
#      Coarse sweep  : [0, 25, 50, 75, 100]
#      Standard sweep: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
#      Fine sweep    : [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50,
#                       55, 60, 65, 70, 75, 80, 85, 90, 95, 100]
# =============================================================================

PENETRATION_LEVELS_PV = [20, 50, 70, 100]
# PENETRATION_LEVELS_PV = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# =============================================================================
# 7. DER PENETRATION RATIOS  —  relative to PV level
#    pen_BESS = pen_PV * BESS_PV_RATIO
#    pen_EV   = pen_PV * EV_PV_RATIO
#    pen_DC   = pen_PV * DC_PV_RATIO
#
#    Examples:
#      1.0  → 1:1 ratio  (BESS capacity equals 100% of PV penetration)
#      0.5  → 1:2 ratio  (BESS capacity equals  50% of PV penetration)
#      0.25 → 1:4 ratio  (BESS capacity equals  25% of PV penetration)
# =============================================================================

BESS_PV_RATIO = 0.25   # BESS penetration = PV level × 0.25
EV_PV_RATIO   = 0.25   # EV/CS penetration = PV level × 0.25
DC_PV_RATIO   = 1.0    # DC penetration = PV level × 1.0

# =============================================================================
# 8. PV — Photovoltaic Systems
#    PV_SIZES_KW : discrete unit sizes drawn randomly each iteration [kWp]
#    PV_PROBS    : probability of each size being selected (must sum to 1.0)
#    PV_POWER_FACTOR: operating power factor of the PVSystem element
#
#    Residential / small commercial scale:
#      PV_SIZES_KW = [30, 60, 120, 180, 240]
#      PV_PROBS    = [0.25, 0.30, 0.25, 0.15, 0.05]
#
#    Utility / large commercial scale (current setting):
#      PV_SIZES_KW = [1200, 1600, 2200, 2400, 3200]
#      PV_PROBS    = [0.25, 0.30, 0.25, 0.15, 0.05]
# =============================================================================

PV_SIZES_KW     = [1200, 1600, 2200, 2400, 3200]
PV_PROBS        = [0.25, 0.30, 0.25, 0.15, 0.05]
PV_POWER_FACTOR = 1.0

# =============================================================================
# 9. BESS — Battery Energy Storage Systems
#    BESS_SIZES_KWH  : discrete unit capacities drawn randomly [kWh]
#    BESS_PROBS      : probability of each size (must sum to 1.0)
#    BESS_CHARGE_HOURS: assumed charge/discharge duration [h];
#                       rated power = kWh_rated / BESS_CHARGE_HOURS
#    BESS_PLACEMENT  : where batteries are installed relative to PV units
#      "colocated"   → each BESS shares the same bus as an existing PV unit
#      "free"        → each BESS is placed on any random MV bus
# =============================================================================

BESS_SIZES_KWH    = [120, 240, 480, 720, 960]
BESS_PROBS        = [0.25, 0.30, 0.25, 0.15, 0.05]
BESS_CHARGE_HOURS = 4
BESS_POWER_FACTOR = 1.0
BESS_PLACEMENT    = "colocated"   # Options: "colocated" | "free"

# --- BESS OpenDSS Storage model parameters ---
# Vminpu / Vmaxpu define the voltage band within which the Storage element
# operates at constant power. This range is intentionally wide (0.75–1.25 pu)
# so the storage dispatch profile is not altered by voltage-dependent mode
# switching inside OpenDSS. This is a model parameter only — it does NOT
# change the voltage violation thresholds used in the KPI calculations
# (those remain 0.95 / 1.05 pu as evaluated in network.py).
BESS_VMINPU = 0.75
BESS_VMAXPU = 1.25

# Round-trip efficiency set to 100% to isolate the network-level hosting
# capacity effect from battery internal losses. Declare this explicitly
# as a simplifying assumption in the methodology section of any paper.
# To model real losses, set both values to e.g. 95.
BESS_EFF_CHARGE    = 100   # % charge efficiency    (100 = lossless)
BESS_EFF_DISCHARGE = 100   # % discharge efficiency (100 = lossless)

# =============================================================================
# 10. EV / CHARGING STATIONS
#     Load curves come from CSV files in data/ev_profiles/ (one file per
#     archetype, 24 comma-separated normalized values, max = 1.0).
#     Each station draws a random curve independently every iteration.
#
#     EV_SIZES_KW      : discrete station power ratings [kW]
#     EV_PROBS         : probability of each rating (must sum to 1.0)
#     EV_POWER_FACTOR  : operating power factor of the charging load
#     EV_ELIGIBLE_BUSES: restrict EV placement to specific buses.
#       []             → all MV buses are candidates (default)
#       ["bus5","bus9"] → only those buses receive charging stations
# =============================================================================

EV_SIZES_KW       = [60, 120, 240]
EV_PROBS          = [0.35, 0.45, 0.20]
EV_POWER_FACTOR   = 0.98
EV_ELIGIBLE_BUSES = []   # Example: ["bus5", "bus9", "bus14"] or [] for all MV buses

# =============================================================================
# 11. DATA CENTERS
#     Data centers are modeled as variable loads whose daily energy equals
#     pen_DC% of the network daily energy. A random workload archetype is
#     drawn from data/dc_profiles/ each iteration and scaled to match
#     the energy target.
#
#     NUM_DC          : number of data centers installed per iteration
#     DC_PUE_RANGE    : Power Usage Effectiveness drawn uniformly per DC
#                       (1.0 = ideal; typical range 1.2–1.8)
#     DC_NOISE_BAND   : hourly load variability around the archetype [±fraction]
#     DC_POWER_FACTOR : power factor of the data center load
#
#     Behind-the-meter self-generation (optional):
#     ENABLE_DC_GEN      : add an on-site generator element per DC
#     DC_SELF_SUPPLY_FRAC: fraction of DC energy covered by on-site generation
# =============================================================================

NUM_DC              = 1
DC_PUE_RANGE        = (1.2, 1.8)   # Options: (1.2, 1.5) lean DCs | (1.5, 2.0) older DCs
DC_NOISE_BAND       = 0.05         # ±5% hourly variability around the workload profile
DC_POWER_FACTOR     = 0.95

ENABLE_DC_GEN       = False        # Set True to add a BTM generator per DC
DC_SELF_SUPPLY_FRAC = 0.20         # Fraction of DC energy supplied on-site (only if ENABLE_DC_GEN)

# =============================================================================
# 12. ECONOMIC COSTS
#     Used to compute investment cost estimates per iteration.
#     Two price references are provided: local market and international benchmark.
#     Results are written as separate columns in the output CSV so both
#     can be compared without re-running the simulation.
#     Update these values to match your country or study context.
#
#     Reference sources (2026):
#       PV local      : local EPC contracts
#       PV intl       : IRENA Renewable Power Generation Costs 2023
#       BESS          : BloombergNEF Battery Price Survey 2024
#       EV/CS local   : local supply chain estimate
#       EV/CS intl    : IEA Global EV Outlook 2024
#       DC            : Uptime Institute / JLL Data Center Cost Index 2024
#       Energy tariff : local utility rate (used to value network losses)
# =============================================================================

PV_USD_PER_KW_LOCAL            = 1750   # USD/kWp  — local installed cost
PV_USD_PER_KW_INTL             = 691    # USD/kWp  — international benchmark
BESS_USD_PER_KWH_LOCAL         = 200    # USD/kWh  — local / baseline
BESS_USD_PER_KWH_INTL          = 350    # USD/kWh  — international (all-in installed)
EVCS_USD_PER_KW_LOCAL          = 240    # USD/kW   — local installed cost
EVCS_USD_PER_KW_INTL           = 850    # USD/kW   — international benchmark
DC_USD_PER_KW                  = 1200   # USD/kW   — data center installed cost
ENERGY_LOSS_TARIFF_USD_PER_KWH = 0.185  # USD/kWh  — energy tariff for loss valuation

# =============================================================================
# 13. HOURLY EXPORT AND PLOT BANDS
#     ENABLE_HOURLY_EXPORT: write per-hour profiles to results/hourly/.
#       Generates one CSV per variable (Pnet, Plosses, Trafo, Vmin, Vmax),
#       one row per Monte Carlo iteration. Required for 24h profile plots.
#     PLOT_BAND_LOWER / UPPER: percentile band shown in penetration curve plots.
#       Common choices: 10/90 (P10–P90) | 25/75 (IQR) | 5/95 (wider band)
# =============================================================================

ENABLE_HOURLY_EXPORT = True   # Set False to skip hourly CSVs and speed up large runs

PLOT_BAND_LOWER = 10   # Lower percentile for confidence band in plots (e.g. 10 = P10)
PLOT_BAND_UPPER = 90   # Upper percentile for confidence band in plots (e.g. 90 = P90)

# =============================================================================
# AUTO-COMPUTED  —  do not edit below this line
# =============================================================================

HOURLY_DIR = os.path.join(RESULTS_DIR, "hourly")

_max_pv   = max(PENETRATION_LEVELS_PV) if ENABLE_PV   else 0
_max_bess = round(_max_pv * BESS_PV_RATIO) if ENABLE_BESS  else 0
_max_ev   = round(_max_pv * EV_PV_RATIO)   if ENABLE_EV_CS else 0
_max_dc   = round(_max_pv * DC_PV_RATIO)   if ENABLE_DC    else 0
RESULTS_FILE = os.path.join(
    RESULTS_DIR,
    f"results_{NETWORK_NAME}_PV{_max_pv}_BESS{_max_bess}_EV{_max_ev}_DC{_max_dc}.csv"
)
