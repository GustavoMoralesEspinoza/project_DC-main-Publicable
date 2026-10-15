# Monte Carlo Hosting Capacity Framework
### PV · BESS · EV/CS · Data Centers

A stochastic framework for assessing the **hosting capacity** of medium-voltage
distribution networks under the integration of distributed energy resources (DERs).
Built on [OpenDSS](https://www.epri.com/pages/sa/opendss) via `py_dss_interface`.

---

## What it does

The framework answers a core planning question:

> *How much distributed generation or load can a distribution network absorb
> before voltage limits or transformer capacity are violated?*

Rather than simulating a single fixed scenario, it runs a **Monte Carlo sweep**:
for each penetration level it draws hundreds of random combinations of DER sizes
and locations, simulates each one in OpenDSS across a full 24-hour daily cycle,
and records the resulting KPIs. The output is a statistical distribution of
hosting capacity indicators — not a single number.

---

## Requirements

- **Python** 3.9 or later
- **OpenDSS** installed on Windows (`py_dss_interface` wraps the OpenDSS COM engine)

## Installation

Create and activate the virtual environment, then install dependencies:

```bash
# Create the virtual environment (only once)
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

All subsequent commands (`python main.py`, `python verify.py`, etc.) should be
run with the virtual environment active.

`requirements.txt` contains: `numpy`, `pandas`, `matplotlib`, `py-dss-interface`

---

## Quick start

```
1. Edit config.py       → choose network, enable DER modules, set parameters
2. python main.py       → run the full Monte Carlo sweep
3. python plot_curves.py → generate figures from the results CSV
```

To test a single scenario before running the full sweep:
```
python verify.py        → single iteration, full KPI report + diagnostic plots
```

---

## Using any network

The framework is network-agnostic. Three networks are included in `data/networks/`:

| Folder | Description | Transformer MVA |
|--------|-------------|-----------------|
| `18Bus` | IEEE 18-bus test feeder | 7.2 MVA |
| `18Bus_Mod` | Modified 18-bus feeder | 7.2 MVA |
| `CHS031` | Real MV distribution feeder | 60.0 MVA |

To switch networks, edit two lines in `config.py`:

```python
NETWORK_NAME    = "CHS031"           # must match subfolder name in data/networks/
NETWORK_FILE    = "CHS031_Master.dss" # master DSS file inside that folder
TRANSFORMER_MVA = 60.0               # rated power of the main substation transformer
```

**To add your own network:**
1. Create a subfolder inside `data/networks/` with your network name.
2. Place your OpenDSS files there. The main file must compile the entire network
   (`compile [master.dss]` should load all lines, loads, transformers, etc.).
3. Set `NETWORK_NAME`, `NETWORK_FILE`, and `TRANSFORMER_MVA` in `config.py`.

The framework automatically identifies all medium-voltage buses (2.3–25 kV) as
DER candidates. The source/slack bus is excluded by default (`EXCLUDED_BUSES`).

---

## How penetration levels work

Penetration is defined as a **percentage of the network's daily active energy demand**.
This makes the metric network-independent: 50% penetration means the same thing
on a 7.2 MVA feeder and a 60 MVA feeder.

### PV penetration

```
E_target [kWh] = Daily_Network_Energy [kWh] × (PEN_PV / 100)
P_target [kW]  = E_target / PSH
```

where **PSH** (Peak Sun Hours) is drawn from the irradiance data file for a
randomly selected month. The framework then draws PV unit sizes from `PV_SIZES_KW`
until the installed capacity reaches `P_target`.

### BESS penetration

```
E_target [kWh] = Daily_Network_Energy [kWh] × (PEN_BESS / 100)
```

BESS sizes are drawn from `BESS_SIZES_KWH` until the total installed energy
capacity reaches `E_target`. Rated power is derived as `kWh / BESS_CHARGE_HOURS`.

### EV/CS penetration

```
E_target [kWh] = Daily_Network_Energy [kWh] × (PEN_EV / 100)
```

The number of stations is determined by how much energy each station contributes
per day, estimated from the average area under the available load curves.

### DC penetration

```
E_target [kWh] = Daily_Network_Energy [kWh] × (PEN_DC / 100)
```

The data center load is scaled so that its total daily energy consumption equals
`E_target`. A random workload archetype from `data/dc_profiles/` defines the
shape; the PUE is drawn uniformly from `DC_PUE_RANGE`.

### Linking DER penetrations

BESS, EV/CS, and DC penetrations are coupled to the PV sweep via fixed ratios:

```python
PEN_BESS = PEN_PV × BESS_PV_RATIO   # e.g. 0.25 → BESS is 25% of PV level
PEN_EV   = PEN_PV × EV_PV_RATIO
PEN_DC   = PEN_PV × DC_PV_RATIO
```

Setting a ratio to `0` effectively disables that DER even if its module is
enabled. Setting it to `1.0` means it scales 1:1 with the PV sweep.

---

## Adding custom DER load curves

All profile directories use the same convention: **one CSV file per profile,
24 comma-separated values, one value per hour (hours 0–23).**

The framework scans the folder at startup and automatically includes every
valid CSV it finds.

### BESS dispatch profiles — `data/bess_profiles/`

Values represent normalized dispatch: **negative = charging, positive = discharging**.
Range: −1.0 to +1.0. The framework scales to rated power automatically.

Example — charge at midday, discharge in the evening:
```
0,0,0,0,0,0,0,0,0,-0.5,-1,-1,-0.5,0,0,0,0,0.5,1,1,0.5,0,0,0
```

### EV/CS load profiles — `data/ev_profiles/`

Values represent normalized load: **0.0 to 1.0** (1.0 = peak load).
The framework normalizes each curve to its own maximum on load.

Example — residential overnight charging pattern:
```
0.1,0.1,0.1,0.1,0.1,0.1,0.1,0.2,0.4,0.3,0.2,0.1,0.1,0.1,0.1,0.2,0.5,0.8,1.0,0.9,0.7,0.5,0.3,0.2
```

### Data center workload profiles — `data/dc_profiles/`

Values represent normalized IT workload: **0.0 to 1.0**.
The framework scales the shape to match the energy target for each iteration.

Example — daytime-heavy compute workload:
```
0.4,0.4,0.4,0.4,0.4,0.5,0.7,0.9,1.0,1.0,1.0,1.0,0.9,0.9,0.8,0.8,0.7,0.6,0.5,0.5,0.4,0.4,0.4,0.4
```

> If a profile folder is empty, the framework falls back to a built-in generic
> curve and prints an `[INFO]` message. Simulations will still run.

---

## Configuration reference (`config.py`)

`config.py` is the **only file you need to edit**. It is organized in 13 numbered
sections — below is a summary of the most important parameters.

| Section | Key parameters | Description |
|---------|---------------|-------------|
| 1 | `ENABLE_PV/BESS/EV_CS/DC` | Toggle each DER module on/off |
| 2 | `NETWORK_NAME`, `TRANSFORMER_MVA` | Select the network to simulate |
| 4 | `NUM_ITERATIONS`, `RANDOM_SEED` | Monte Carlo sample size and reproducibility |
| 6 | `PENETRATION_LEVELS_PV` | The sweep vector (% of daily energy) |
| 7 | `BESS_PV_RATIO`, `EV_PV_RATIO`, `DC_PV_RATIO` | How other DERs scale with PV |
| 8–11 | `*_SIZES_*`, `*_PROBS` | Discrete size distributions for each DER |
| 12 | `*_USD_PER_KW*` | Unit costs for investment estimates |
| 13 | `ENABLE_HOURLY_EXPORT` | Write per-hour profiles to CSV |

---

## Output files

### Main results CSV — `results/results_<scenario>.csv`

One row per Monte Carlo iteration. Key columns:

| Column | Units | Description |
|--------|-------|-------------|
| `Penetration_Level` | % | Sweep variable (same for all active DERs) |
| `Pen_PV / Pen_BESS / Pen_EV / Pen_DC` | % | Actual penetration per module |
| `B_Vmin` | buses | Buses with undervoltage (< 0.95 pu) in at least one hour |
| `B_Vmax` | buses | Buses with overvoltage (> 1.05 pu) in at least one hour |
| `B_VminVmax` | buses | Union of the two above (total affected buses) |
| `Sev_Vmin_pct` | % | Severity: % of (bus × hour) pairs below 0.95 pu |
| `Sev_Vmax_pct` | % | Severity: % of (bus × hour) pairs above 1.05 pu |
| `Vmin_24h / Vmax_24h` | pu | System-wide min/max voltage over the full 24 h |
| `Trafo_Loading_pct` | % | Peak transformer loading |
| `Energy_Losses` | kWh | Daily active energy losses |
| `Cost_PV_Local / Cost_PV_Intl` | USD | PV investment cost (local vs international price) |
| `Cost_Total_Local / Cost_Total_Intl` | USD | Total DER investment (PV + BESS + EV/CS) |
| `Energy_Losses_USD` | USD | Monetary value of daily energy losses |

### Hourly profiles — `results/hourly/` *(if `ENABLE_HOURLY_EXPORT = True`)*

Five CSV files, one row per iteration, 24 columns (H0–H23):

| File | Variable |
|------|----------|
| `perfil24h_Pnet.csv` | Net active power at substation [kW] |
| `perfil24h_Plosses.csv` | Active power losses [kW] |
| `perfil24h_Trafo.csv` | Transformer loading [%] |
| `perfil24h_Vmin.csv` | System minimum voltage [pu] |
| `perfil24h_Vmax.csv` | System maximum voltage [pu] |

### Diagnostic plots — `results/figures/` *(generated by `verify.py`)*

Five PNG figures per run:
- `lines_*` — voltage profile per bus over 24 h (color-coded by violation)
- `flow_*` — substation active power flow (highlights reverse flow)
- `trafo_*` — transformer loading curve with 80% and 100% thresholds
- `losses_*` — active power losses curve
- `decomp_*` — power decomposition (net flow, PV generation, DC load)

---

## Reproducing results

Set `RANDOM_SEED` to any integer. The framework derives each iteration's seed
as `RANDOM_SEED + iteration_counter`, so the same seed always produces the
exact same sequence of DER placements across runs.

Set `RANDOM_SEED = None` to draw a fresh random sequence every run.

---

## Project structure

```
project/
├── config.py            ← Only file you need to edit
├── main.py              ← Entry point: runs the full Monte Carlo sweep
├── verify.py            ← Debug tool: one iteration + console report + plots
├── plot_curves.py       ← Generates all figures for one results CSV
│
├── core/
│   ├── network.py       ← OpenDSS interface: base case + DER simulation
│   └── monte_carlo.py   ← Main loop over penetration levels and iterations
│
├── modules/
│   ├── pv/              ← PV allocation and DSS scenario file generation
│   ├── bess/            ← BESS allocation and DSS scenario file generation
│   ├── ev_cs/           ← EV/CS allocation and DSS scenario file generation
│   └── dc/              ← Data center allocation and DSS scenario file generation
│
├── plots/               ← Visualization scripts (read results/ CSVs)
│   ├── style.py         ← Shared plot style
│   ├── plot_voltage.py  ← Voltage profile figures (used by verify.py)
│   ├── plot_system.py   ← System KPI figures (used by verify.py)
│   ├── boxplots.py      ← KPI distribution per penetration level
│   ├── curvas_penetracion.py ← Median + band penetration curves
│   ├── histogramas3d.py ← 3D distribution histograms
│   └── perfiles_24h.py  ← 24-hour profile plots from hourly CSVs
│
├── results/
│   └── reporter.py      ← CSV writer called by the Monte Carlo loop
│
└── data/
    ├── networks/        ← OpenDSS network files (.dss)
    ├── irradiance/      ← Solar irradiance + temperature CSVs (hourly × monthly)
    ├── bess_profiles/   ← BESS dispatch curves (24-value CSV per archetype)
    ├── ev_profiles/     ← EV load curves (24-value CSV per archetype)
    └── dc_profiles/     ← Data center workload profiles (24-value CSV per archetype)
```
