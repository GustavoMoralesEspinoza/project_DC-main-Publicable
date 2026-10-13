# Monte Carlo HC Framework — PV · BESS · EV/CS · Data Center

Stochastic hosting-capacity assessment for medium-voltage distribution networks using OpenDSS.  
The framework performs Monte Carlo sweeps over penetration levels of distributed energy resources (DERs) and reports voltage, loss, and transformer-loading KPIs per iteration.

## Supported DER modules

| Module | Type | Config flag |
|--------|------|-------------|
| PV | Generation (PVSystem) | `ENABLE_PV` |
| BESS | Storage | `ENABLE_BESS` |
| EV/CS | Load (charging stations) | `ENABLE_EV_CS` |
| Data Center | Load (variable) | `ENABLE_DC` |

## Requirements

- Python 3.9+
- [OpenDSS](https://www.epri.com/pages/sa/opendss) installed (Windows)
- Python packages:

```
pip install -r requirements.txt
```

## Quick start

1. **Configure** — edit `config.py`:
   - Choose a network: `NETWORK_NAME = "18Bus"` or `"CHS031"`
   - Enable modules: `ENABLE_PV = True`, etc.
   - Set penetration levels and iteration count

2. **Run the full Monte Carlo sweep:**
   ```
   python main.py
   ```
   Results are written to `results/resultados_<scenario>.csv`.

3. **Run a single debug iteration** (no CSV output, prints KPIs + plots):
   ```
   python verify.py
   ```

4. **Generate plots** from existing result CSVs:
   ```
   python plot_all.py
   ```

## Project structure

```
project/
├── config.py            ← All user-editable parameters
├── main.py              ← Entry point (Monte Carlo sweep)
├── verify.py            ← Debug tool: 1 iteration + console report
├── plot_all.py          ← Batch plot generation
│
├── core/
│   ├── network.py       ← OpenDSS wrapper (base case + DER simulation)
│   └── monte_carlo.py   ← Main loop
│
├── modules/
│   ├── pv/              ← PV allocation + DSS scenario generation
│   ├── bess/            ← BESS allocation + DSS scenario generation
│   ├── ev_cs/           ← EV/CS allocation + DSS scenario generation
│   └── dc/              ← Data Center allocation + DSS scenario generation
│
├── plots/               ← Visualization scripts (read results/ CSVs)
│
├── results/
│   └── reporter.py      ← CSV writer (called by the Monte Carlo loop)
│
└── data/
    ├── networks/        ← OpenDSS network files (.dss)
    │   ├── 18Bus/       ← IEEE 18-bus feeder
    │   ├── 18Bus_Mod/   ← Modified 18-bus feeder
    │   └── CHS031/      ← Real MV feeder (CHS031)
    ├── irradiance/      ← Solar irradiance + temperature CSVs (hourly, monthly)
    ├── bess_profiles/   ← BESS dispatch curves (24-value CSV, one per file)
    ├── ev_profiles/     ← EV load curves (24-value CSV, one per file)
    └── dc_profiles/     ← Data center workload profiles (24-value CSV)
```

## Adding custom profiles

All profile directories follow the same convention: one CSV file per profile, 24 comma-separated values (normalized, 0–1 range). Drop the file in the appropriate folder and the framework picks it up automatically on the next run.

**BESS profiles** (`data/bess_profiles/`): negative = charging, positive = discharging, range −1 to 1.

**EV profiles** (`data/ev_profiles/`): normalized load curve, 0–1.

**DC profiles** (`data/dc_profiles/`): normalized workload curve, 0–1.

## Generating irradiance data

Two helper scripts are included to build the irradiance CSV from public APIs:

- `generar_perfil_irradiancia_arequipa.py` — NASA POWER API (hourly)
- `generar_perfil_irradiancia_arequipa_nasapower.py` — NASA POWER API (alternative endpoint)

Edit the coordinates and year range, then run the script. The output replaces `data/irradiance/Geracao_Solar.csv`.

## Output columns (results CSV)

| Column | Description |
|--------|-------------|
| `Penetration_Level` | Sweep variable (% of daily network energy) |
| `Pen_PV/BESS/EV/DC` | Actual penetration per module (%) |
| `B_Vmin / B_Vmax` | Buses with under/over-voltage in ≥1 hour |
| `Sev_Vmin_pct / Sev_Vmax_pct` | Severity index: % of (bus × hour) pairs outside limits |
| `Vmin_24h / Vmax_24h` | System-wide min/max voltage over 24 h [pu] |
| `Trafo_Loading_pct` | Peak transformer loading [%] |
| `Energy_Losses` | Daily active energy losses [kWh] |
| `Cost_*_Peru / Cost_*_Intl` | Investment cost estimates (local and international) [USD] |
