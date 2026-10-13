# plot_curves.py
"""
Visualization entry point — generates all standard figures for one scenario.

Reads the output CSV produced by main.py and generates four figure families:
    1. Boxplots        — KPI distribution per penetration level
    2. Penetration curves — median + confidence band across the sweep
    3. 3D histograms   — joint distribution of penetration vs KPI
    4. 24h profiles    — hourly power, voltage and loss curves
                         (requires ENABLE_HOURLY_EXPORT = True in config.py)

Usage:
    Edit CSV_NAME below to match the scenario you want to plot, then run:
        python plot_curves.py

Output:
    figures/<CSV_NAME>/boxplots/
    figures/<CSV_NAME>/curvas/
    figures/<CSV_NAME>/histogramas3d/
    figures/<CSV_NAME>/perfiles24h/
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


CSV_NAME = "resultados_18Bus_PV100_BESS0_EV0_DC0"


def main():
    csv_path = os.path.join("results", f"{CSV_NAME}.csv")
    name = CSV_NAME
    if not os.path.isfile(csv_path):
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)

    hourly_dir = os.path.join(os.path.dirname(csv_path), "hourly")
    out_base = os.path.join("figures", name)

    print("=" * 60)
    print(f"  PLOT CURVES — {name}")
    print(f"  CSV:     {csv_path}")
    print(f"  Hourly:  {hourly_dir}")
    print(f"  Output:  {out_base}/")
    print("=" * 60)

    # --1. Boxplots -----------------------------------------──
    print("\n--Boxplots --")
    from plots.boxplots import BoxplotPlotter
    BoxplotPlotter(
        csv_path=csv_path,
        output_dir=os.path.join(out_base, "boxplots"),
    ).plot_all()

    # --2. Curvas de penetracion -----------------------------─
    print("\n--Curvas de penetracion --")
    from plots.curvas_penetracion import CurvasPenetracion
    CurvasPenetracion(
        csv_path=csv_path,
        output_dir=os.path.join(out_base, "curvas"),
    ).plot_all()
    
    # --3. Histogramas 3D -----------------------------------──
    print("\n--Histogramas 3D --")
    from plots.histogramas3d import Histogram3DPlotter
    h3d = Histogram3DPlotter(
        csv_path=csv_path,
        output_dir=os.path.join(out_base, "histogramas3d"),
    )
    h3d.plot_all(smooth=True)
    for kpi in ["B_Vmin", "B_Vmax", "B_VminVmax", "Energy_Losses"]:
        h3d.plot_2d_slice(kpi=kpi, pen_pv_fixed=50.0)

    # --4. Perfiles 24h --------------------------------------
    print("\n--Perfiles 24h --")
    if os.path.isdir(hourly_dir):
        from plots.perfiles_24h import Perfiles24h
        Perfiles24h(
            hourly_dir=hourly_dir,
            output_dir=os.path.join(out_base, "perfiles24h"),
        ).plot_all()
    else:
        print(f"  [WARN] Hourly directory not found: {hourly_dir}")
        print("  Skipping perfiles_24h. Run simulation with ENABLE_HOURLY_EXPORT=True first.")

    # --Summary --------------------------------------------──
    print("\n" + "=" * 60)
    total = sum(
        len([f for f in os.listdir(os.path.join(out_base, d)) if f.endswith(".png")])
        for d in os.listdir(out_base)
        if os.path.isdir(os.path.join(out_base, d))
    )
    print(f"  Done. {total} PNGs generated in {out_base}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
