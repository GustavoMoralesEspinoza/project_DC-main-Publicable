# batch_stability.py
"""
Módulo de Análisis de Estabilidad de Monte Carlo por Lotes (Batch Stability).

Evalúa la reproducibilidad y estabilidad estadística de un estudio Monte Carlo
de Hosting Capacity a través del método de medias por lotes independientes (Batch Means).

Determina el tamaño mínimo y óptimo de simulaciones (N_optimo) por nivel de penetración
para que la variación inter-lotes sea menor o igual al umbral X% (por defecto 5%).

KPIs evaluados:
  1. B_VminVmax           — Conteo de barras con violación de tensión (sub o sobretensión)
  2. Sev_VminVmax_pct     — Severidad global de violación de tensión (% barra x hora)
  3. Energy_Losses        — Pérdidas de energía activa diaria (kWh)
  4. Min_Fluxo_Subestacao — Flujo neto mínimo en la subestación (kW, indicador de flujo inverso)
  5. Trafo_Loading_pct    — Cargamento máximo del transformador / subestación (%)

Perspectivas de partición:
  - "exhaustive" : Partición completa de todas las simulaciones disponibles (k = N_total // m).
  - "fixed_k"    : Mantiene k grupos constantes (por defecto k=10) variando el tamaño m.
  - "both"       : Ejecuta y compara ambas perspectivas.

Uso:
    python batch_stability.py
    python batch_stability.py --csv results/results_18Bus_PV100_BESS0_EV0_DC0.csv --pen 50 --threshold 5.0
"""

import os
import sys
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# =============================================================================
# AJUSTES DE ANÁLISIS (Editable directamente para ejecución standalone)
# =============================================================================

# Ruta al archivo CSV con resultados Monte Carlo a analizar
CSV_FILE = "results/results_RBRR1303_PV100_BESS0_EV0_DC0.csv"

# Umbral de tolerancia de estabilidad (X%)
# Un tamaño de lote m se considera ESTABLE si el CV inter-lotes es <= THRESHOLD_X %
THRESHOLD_X = 5.0

# Tamaños de lote (m) a evaluar para hallar la frontera de estabilidad
BATCH_SIZES = [50, 100, 250, 500, 1000, 2500]

# Nivel de penetración a evaluar
# None = auto-detecta la penetración del archivo (si hay un solo nivel)
# o usa el primer nivel disponible. También puede ser un número (ej. 50.0).
PENETRATION_LEVEL = None

# Perspectiva de partición: "exhaustive" | "fixed_k" | "both"
MODE = "both"

# Número de grupos fijos para la perspectiva "fixed_k"
K_FIXED = 10

# KPI para mostrar en la Tabla 1 detallada por lote en consola ("all" o nombre de KPI específico)
DETAILED_KPI = "all"

# Tamaño de lote m para mostrar en la Tabla 1 detallada (None = usa el m mediano disponible)
DETAILED_BATCH_SIZE = 250

# Directorio donde se guardan los reportes generados
OUTPUT_DIR = "results/batch_stability"

# Generar automáticamente las 4 figuras explicativas en PNG (300 dpi) y PDF
SAVE_PLOTS = True

# Lista de KPIs analizados por defecto con sus descripciones
DEFAULT_KPIS = [
    ("B_VminVmax",           "Barras Violadas (conteo)",        "barras"),
    ("Sev_VminVmax_pct",     "Severidad Tension (%)",           "%"),
    ("Energy_Losses",        "Perdidas Energia (kWh)",          "kWh"),
    ("Min_Fluxo_Subestacao", "Flujo Minimo SE (kW)",            "kW"),
    ("Trafo_Loading_pct",    "Cargamento Trafo (%)",            "%"),
]


# =============================================================================
# MOTOR DE ANÁLISIS ESTADÍSTICO
# =============================================================================

class BatchStabilityAnalyzer:
    """
    Analizador de estabilidad estadística por lotes (Batch Means) para estudios Monte Carlo.
    """

    def __init__(self, csv_path: str, penetration_level=None, threshold_pct: float = 5.0,
                 kpis=None, output_dir: str = OUTPUT_DIR):
        self.csv_path = Path(csv_path)
        if not self.csv_path.is_file():
            script_dir = Path(__file__).parent.resolve()
            alt_path = script_dir / csv_path
            if alt_path.is_file():
                self.csv_path = alt_path
            else:
                raise FileNotFoundError(f"Archivo CSV no encontrado: {self.csv_path}")

        self.threshold = float(threshold_pct)
        out_path = Path(output_dir)
        if not out_path.is_absolute():
            script_dir = Path(__file__).parent.resolve()
            out_path = script_dir / output_dir
        self.output_dir = out_path
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.df_raw = pd.read_csv(self.csv_path)
        self.kpis_info = kpis if kpis is not None else DEFAULT_KPIS

        # Resolver nivel de penetración
        self.pen_col = self._detect_penetration_col()
        self.available_pens = sorted(self.df_raw[self.pen_col].unique()) if self.pen_col else []
        
        if penetration_level is not None:
            self.pen_selected = float(penetration_level)
            if self.pen_selected not in self.available_pens:
                closest = min(self.available_pens, key=lambda v: abs(v - self.pen_selected))
                print(f"  [AVISO] Penetracion {self.pen_selected}% no encontrada. Usando la mas cercana: {closest}%")
                self.pen_selected = closest
        else:
            if len(self.available_pens) == 1:
                self.pen_selected = self.available_pens[0]
            elif 50.0 in self.available_pens:
                self.pen_selected = 50.0
            elif len(self.available_pens) > 0:
                self.pen_selected = self.available_pens[0]
            else:
                self.pen_selected = None

        if self.pen_col and self.pen_selected is not None:
            self.df = self.df_raw[self.df_raw[self.pen_col] == self.pen_selected].reset_index(drop=True)
        else:
            self.df = self.df_raw.copy()

        self.n_total = len(self.df)
        if self.n_total == 0:
            raise ValueError("El DataFrame filtrado no contiene filas para analizar.")

    def _detect_penetration_col(self):
        candidates = ["Penetration_Level", "Pen_PV", "pen_pv", "penetration"]
        for c in candidates:
            if c in self.df_raw.columns:
                return c
        return None

    def calculate_single_batch_metrics(self, data_array: np.ndarray) -> dict:
        """
        Calcula el conjunto completo de métricas de tendencia central y dispersión
        para un único lote de simulaciones.
        """
        data = np.asarray(data_array, dtype=float)
        m = len(data)
        if m == 0:
            return {}

        media = float(np.mean(data))
        mediana = float(np.median(data))
        std_trad = float(np.std(data, ddof=1)) if m > 1 else 0.0

        # Dispersión robusta frente a la mediana
        diff_med = np.abs(data - mediana)
        mad = float(np.median(diff_med))
        sigma_mad = float(1.4826 * mad)
        rmsd_mediana = float(np.sqrt(np.mean((data - mediana) ** 2)))

        p25 = float(np.percentile(data, 25))
        p75 = float(np.percentile(data, 75))
        iqr = float(p75 - p25)
        p95 = float(np.percentile(data, 95))

        return {
            "N": m,
            "Media": media,
            "Mediana": mediana,
            "Std_Trad": std_trad,
            "MAD": mad,
            "Sigma_MAD": sigma_mad,
            "RMSD_Mediana": rmsd_mediana,
            "IQR": iqr,
            "P95": p95
        }

    def partition_data(self, data: np.ndarray, batch_size: int, mode: str = "exhaustive", k_fixed: int = 10):
        """
        Divide el vector de datos según el modo especificado.
        Retorna una lista de arrays correspondientes a cada lote.
        """
        n = len(data)
        m = int(batch_size)

        if mode == "fixed_k":
            total_needed = m * k_fixed
            if total_needed > n:
                # No alcanzan los datos para k_fixed grupos de tamano m
                return []
            return [data[i * m : (i + 1) * m] for i in range(k_fixed)]
        elif mode == "exhaustive":
            k = n // m
            if k < 2:
                return []
            return [data[i * m : (i + 1) * m] for i in range(k)]
        else:
            raise ValueError(f"Modo desconocido: {mode}")

    def analyze_batch_distribution(self, kpi: str, batch_size: int, mode: str = "exhaustive", k_fixed: int = 10) -> pd.DataFrame:
        """
        Genera la TABLA 1: Evaluación detallada lote por lote para un KPI y tamaño m dado.
        Incluye fila resumen con el cálculo de CV_inter.
        """
        if kpi not in self.df.columns:
            raise KeyError(f"Columna KPI '{kpi}' no encontrada en el CSV.")

        vals = self.df[kpi].dropna().values
        grupos = self.partition_data(vals, batch_size=batch_size, mode=mode, k_fixed=k_fixed)

        if not grupos:
            return pd.DataFrame()

        rows = []
        for i, g in enumerate(grupos):
            stats = self.calculate_single_batch_metrics(g)
            row = {"Lote": f"Lote_{i+1:02d}"}
            row.update(stats)
            rows.append(row)

        df_table = pd.DataFrame(rows)

        # Fila Resumen: Promedios inter-lotes
        metric_cols = ["Media", "Mediana", "Std_Trad", "MAD", "Sigma_MAD", "RMSD_Mediana", "IQR", "P95"]
        promedios = {"Lote": "PROMEDIO_GLOBAL", "N": batch_size}
        std_inter = {"Lote": "STD_INTER", "N": len(grupos)}
        cv_inter = {"Lote": f"CV_INTER_% (X={self.threshold}%)", "N": len(grupos)}
        status = {"Lote": f"ESTADO (<= {self.threshold}%)", "N": "-"}

        for col in metric_cols:
            col_vals = df_table[col].values
            prom = float(np.mean(col_vals))
            s_inter = float(np.std(col_vals, ddof=1))
            
            # Criterio híbrido para evitar división espuria cuando el promedio es casi nulo (<1.0)
            if abs(prom) >= 1.0:
                cv = (s_inter / abs(prom)) * 100.0
                is_stable = cv <= self.threshold
            else:
                # Tolerancia absoluta proporcional
                abs_tol = (self.threshold / 100.0) * 1.0
                cv = (s_inter / abs(prom)) * 100.0 if abs(prom) > 1e-9 else 0.0
                is_stable = s_inter <= abs_tol

            promedios[col] = prom
            std_inter[col] = s_inter
            cv_inter[col] = cv
            status[col] = "ESTABLE" if is_stable else "INESTABLE"

        df_summary = pd.DataFrame([promedios, std_inter, cv_inter, status])
        df_result = pd.concat([df_table, df_summary], ignore_index=True)
        return df_result

    def analyze_stability_frontier(self, batch_sizes=None, mode: str = "exhaustive", k_fixed: int = 10) -> pd.DataFrame:
        """
        Genera la TABLA 2: Matriz Multi-KPI de CV_inter frente a los tamaños de lote (m).
        Determina N_optimo por KPI y la estabilidad global del sistema.
        """
        if batch_sizes is None:
            batch_sizes = BATCH_SIZES

        active_kpis = [k for k in self.kpis_info if k[0] in self.df.columns]
        rows = []
        n_optimo_dict = {}

        for col, desc, unit in active_kpis:
            vals = self.df[col].dropna().values
            row = {"KPI": col, "Descripcion": desc, "Unidad": unit}
            optimo_encontrado = None

            for m in batch_sizes:
                grupos = self.partition_data(vals, batch_size=m, mode=mode, k_fixed=k_fixed)
                if not grupos:
                    row[f"m={m}"] = np.nan
                    continue

                means = [np.mean(g) for g in grupos]
                meds = [np.median(g) for g in grupos]
                stds = [np.std(g, ddof=1) for g in grupos]

                mean_of_m = float(np.mean(means))
                std_of_m = float(np.std(means, ddof=1))
                mean_of_med = float(np.mean(meds))
                std_of_med = float(np.std(meds, ddof=1))
                mean_of_s = float(np.mean(stds))
                std_of_s = float(np.std(stds, ddof=1))

                # CV de media y mediana (con regla absoluta si el valor medio < 1.0)
                if abs(mean_of_m) >= 1.0:
                    cv_mean = (std_of_m / abs(mean_of_m)) * 100.0
                    ok_mean = cv_mean <= self.threshold
                else:
                    cv_mean = (std_of_m / abs(mean_of_m)) * 100.0 if abs(mean_of_m) > 1e-9 else 0.0
                    ok_mean = std_of_m <= (self.threshold / 100.0)

                if abs(mean_of_med) >= 1.0:
                    cv_med = (std_of_med / abs(mean_of_med)) * 100.0
                    ok_med = cv_med <= self.threshold
                else:
                    cv_med = (std_of_med / abs(mean_of_med)) * 100.0 if abs(mean_of_med) > 1e-9 else 0.0
                    ok_med = std_of_med <= (self.threshold / 100.0)

                # Tomamos la peor dispersión representativa entre Media y Mediana
                cv_max = max(cv_mean, cv_med)
                row[f"m={m}"] = round(cv_max, 2)

                # Si ambas métricas cumplen el umbral <= X%
                if ok_mean and ok_med and optimo_encontrado is None:
                    optimo_encontrado = m

            row[f"N_optimo (X<={self.threshold}%)"] = optimo_encontrado if optimo_encontrado is not None else "> max(m)"
            n_optimo_dict[col] = optimo_encontrado
            rows.append(row)

        df_frontier = pd.DataFrame(rows)

        # Fila de Estabilidad Global del Sistema (el cuello de botella general)
        summary_row = {"KPI": "SISTEMA_GLOBAL", "Descripcion": "Estabilidad simultanea de todos los KPIs", "Unidad": "-"}
        cuello_botella = None
        for m in batch_sizes:
            col_name = f"m={m}"
            if col_name in df_frontier.columns:
                valid_vals = [r[col_name] for _, r in df_frontier.iterrows() if pd.notnull(r[col_name])]
                if valid_vals and len(valid_vals) == len(df_frontier):
                    all_ok = all(v <= self.threshold for v in valid_vals)
                    summary_row[col_name] = "ESTABLE" if all_ok else "INESTABLE"
                    if all_ok and cuello_botella is None:
                        cuello_botella = m
                else:
                    summary_row[col_name] = "N/A"
            else:
                summary_row[col_name] = "-"

        summary_row[f"N_optimo (X<={self.threshold}%)"] = cuello_botella if cuello_botella is not None else "> max(m)"
        df_frontier = pd.concat([df_frontier, pd.DataFrame([summary_row])], ignore_index=True)

        return df_frontier

    def analyze_multi_kpi_breakdown(self, batch_sizes=None, mode: str = "exhaustive", k_fixed: int = 10) -> pd.DataFrame:
        """
        Genera el desglose completo de variabilidad inter-lotes (CV_inter) para cada una de las métricas:
        Media, Mediana, Std_Trad, RMSD_Mediana, MAD, IQR y P95 para todos los KPIs evaluados.
        """
        if batch_sizes is None:
            batch_sizes = BATCH_SIZES

        active_kpis = [k for k in self.kpis_info if k[0] in self.df.columns]
        rows = []

        for col, desc, unit in active_kpis:
            vals = self.df[col].dropna().values

            for m in batch_sizes:
                grupos = self.partition_data(vals, batch_size=m, mode=mode, k_fixed=k_fixed)
                if not grupos:
                    continue

                k_actual = len(grupos)
                means = [float(np.mean(g)) for g in grupos]
                meds  = [float(np.median(g)) for g in grupos]
                stds  = [float(np.std(g, ddof=1)) if len(g) > 1 else 0.0 for g in grupos]
                mads  = [float(np.median(np.abs(g - np.median(g)))) for g in grupos]
                rmsds = [float(np.sqrt(np.mean((g - np.median(g))**2))) for g in grupos]
                iqrs  = [float(np.percentile(g, 75) - np.percentile(g, 25)) for g in grupos]
                p95s  = [float(np.percentile(g, 95)) for g in grupos]

                def calc_cv(arr):
                    m_val = float(np.mean(arr))
                    s_val = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
                    if abs(m_val) >= 1.0:
                        return (s_val / abs(m_val)) * 100.0
                    else:
                        return (s_val / 1.0) * 100.0

                cv_m    = calc_cv(means)
                cv_med  = calc_cv(meds)
                cv_s    = calc_cv(stds)
                cv_rmsd = calc_cv(rmsds)
                cv_mad  = calc_cv(mads)
                cv_iqr  = calc_cv(iqrs)
                cv_p95  = calc_cv(p95s)

                tc_ok   = (cv_m <= self.threshold) and (cv_med <= self.threshold)
                disp_ok = (cv_s <= self.threshold) and (cv_rmsd <= self.threshold) and (cv_mad <= self.threshold)

                rows.append({
                    "KPI": col,
                    "Descripcion": desc,
                    "Unidad": unit,
                    "m": m,
                    "k_lotes": k_actual,
                    "N_sims_eval": m * k_actual,
                    "CV_Media_%": round(cv_m, 2),
                    "CV_Mediana_%": round(cv_med, 2),
                    "CV_StdTrad_%": round(cv_s, 2),
                    "CV_RMSD_Med_%": round(cv_rmsd, 2),
                    "CV_MAD_%": round(cv_mad, 2),
                    "CV_IQR_%": round(cv_iqr, 2),
                    "CV_P95_%": round(cv_p95, 2),
                    "Estado_TendCentral": "ESTABLE" if tc_ok else "INESTABLE",
                    "Estado_Dispersion": "ESTABLE" if disp_ok else "INESTABLE"
                })

        return pd.DataFrame(rows)

    def format_multi_kpi_report(self, df_breakdown: pd.DataFrame, mode_name: str) -> str:
        """
        Formatea el reporte multi-métrica detallado como texto estructurado ("relatorio").
        """
        lines = []
        lines.append("=" * 115)
        lines.append("  RELATORIO DE ESTABILIDAD MULTI-METRICA DE MONTE CARLO POR LOTES (BATCH STABILITY)")
        lines.append("=" * 115)
        lines.append(f"  Archivo Analizado: {self.csv_path.name}")
        lines.append(f"  Simulaciones N:    {self.n_total:,}")
        if self.pen_selected is not None:
            lines.append(f"  Penetracion:       {self.pen_selected}%")
        lines.append(f"  Modo de Particion: {mode_name}")
        lines.append(f"  Criterio de Exito: CV_inter <= {self.threshold}%")
        lines.append("=" * 115 + "\n")

        unique_kpis = df_breakdown["KPI"].unique()

        for kpi in unique_kpis:
            sub = df_breakdown[df_breakdown["KPI"] == kpi].copy()
            kpi_desc = sub["Descripcion"].iloc[0]
            kpi_unit = sub["Unidad"].iloc[0]
            vals = self.df[kpi].dropna().values

            mean_g = float(np.mean(vals))
            med_g  = float(np.median(vals))
            std_g  = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
            mad_g  = float(np.median(np.abs(vals - med_g)))
            rmsd_g = float(np.sqrt(np.mean((vals - med_g)**2)))
            p95_g  = float(np.percentile(vals, 95))

            lines.append("=" * 115)
            lines.append(f"  KPI: {kpi.upper()} [{kpi_desc}] (Unidad: {kpi_unit})")
            lines.append(f"  Poblacion Global N={len(vals):,} | Media: {mean_g:,.2f} | Mediana: {med_g:,.2f} | Std_Trad: {std_g:,.2f} | MAD: {mad_g:,.2f} | RMSD: {rmsd_g:,.2f} | P95: {p95_g:,.2f}")
            lines.append("-" * 115)
            lines.append(f"{'m':<6} | {'k':<5} | {'N_eval':<7} | {'CV_Media':<10} | {'CV_Mediana':<12} | {'CV_StdTrad':<12} | {'CV_RMSD_Med':<12} | {'CV_MAD':<10} | {'Tend.Central':<13} | {'Dispersion'}")
            lines.append("-" * 115)

            opt_tc = None
            opt_disp = None

            for _, r in sub.iterrows():
                m_val = int(r["m"])
                k_val = int(r["k_lotes"])
                n_eval = int(r["N_sims_eval"])
                cv_m = r["CV_Media_%"]
                cv_med = r["CV_Mediana_%"]
                cv_s = r["CV_StdTrad_%"]
                cv_rmsd = r["CV_RMSD_Med_%"]
                cv_mad = r["CV_MAD_%"]
                st_tc = r["Estado_TendCentral"]
                st_disp = r["Estado_Dispersion"]

                if st_tc == "ESTABLE" and opt_tc is None:
                    opt_tc = m_val
                if st_disp == "ESTABLE" and opt_disp is None:
                    opt_disp = m_val

                lines.append(f"{m_val:<6} | {k_val:<5} | {n_eval:<7} | {cv_m:>8.2f}% | {cv_med:>10.2f}% | {cv_s:>10.2f}% | {cv_rmsd:>10.2f}% | {cv_mad:>8.2f}% | {st_tc:<13} | {st_disp}")

            max_m_val = sub["m"].max()
            str_opt_tc = str(opt_tc) if opt_tc is not None else f"> {max_m_val}"
            str_opt_disp = str(opt_disp) if opt_disp is not None else f"> {max_m_val}"

            lines.append("-" * 115)
            lines.append(f"  >>> RESUMEN KPI {kpi}:")
            lines.append(f"      - N_optimo Tendencia Central (Media y Mediana <= {self.threshold}%): {str_opt_tc}")
            lines.append(f"      - N_optimo Dispersion        (Std, RMSD y MAD <= {self.threshold}%):   {str_opt_disp}")
            lines.append("\n")

        return "\n".join(lines)

    def run_complete_analysis(self, batch_sizes=None, mode: str = "both", k_fixed: int = 10,
                              detailed_kpi: str = DETAILED_KPI, detailed_m: int = DETAILED_BATCH_SIZE,
                              save_plots: bool = SAVE_PLOTS):
        """
        Ejecuta el pipeline completo de análisis, imprime en consola y guarda los reportes.
        """
        if batch_sizes is None:
            batch_sizes = BATCH_SIZES

        modes_to_run = ["fixed_k", "exhaustive"] if mode == "both" else [mode]
        scenario_label = self.csv_path.stem

        print("=" * 85)
        print("  MONTE CARLO BATCH STABILITY ANALYSIS")
        print("=" * 85)
        print(f"  Archivo CSV:     {self.csv_path}")
        print(f"  Simulaciones N:  {self.n_total:,}")
        if self.pen_selected is not None:
            print(f"  Penetracion:     {self.pen_selected}%")
        print(f"  Umbral (X%):     <= {self.threshold}%")
        print(f"  Lotes (m):       {batch_sizes}")
        print(f"  Salida:          {self.output_dir}/")
        print("=" * 85 + "\n")

        results = {}

        for m_mode in modes_to_run:
            mode_name = "Perspectiva 1: Fijando k=10 Lotes Constantes" if m_mode == "fixed_k" else "Perspectiva 2: Particion Exhaustiva de Todas las Muestras"
            print(f"\n######################################################################")
            print(f"  MODO: {mode_name.upper()}")
            print(f"######################################################################\n")

            # 1. Tabla 2 (Frontera Multi-KPI)
            df_frontier = self.analyze_stability_frontier(batch_sizes=batch_sizes, mode=m_mode, k_fixed=k_fixed)
            print("--- TABLA 2: FRONTERA DE ESTABILIDAD MULTI-KPI (CV_inter % vs Tamaño de Lote m) ---")
            print(df_frontier.to_string(index=False))
            print("\n" + "-" * 85 + "\n")

            # Guardar Tabla 2
            out_frontier = self.output_dir / f"tabla2_frontera_{scenario_label}_{m_mode}_X{int(self.threshold)}.csv"
            df_frontier.to_csv(out_frontier, index=False, encoding="utf-8")
            print(f"  [GUARDADO] {out_frontier}\n")

            # 2. Relatorio de Estabilidad Multi-Métrica por KPI (Desglose de Media, Mediana, Std, RMSD, MAD)
            df_breakdown = self.analyze_multi_kpi_breakdown(batch_sizes=batch_sizes, mode=m_mode, k_fixed=k_fixed)
            report_text = self.format_multi_kpi_report(df_breakdown, mode_name)
            print(report_text)

            # Guardar Relatorio (CSV y TXT)
            out_breakdown_csv = self.output_dir / f"relatorio_desglose_metricas_{scenario_label}_{m_mode}.csv"
            df_breakdown.to_csv(out_breakdown_csv, index=False, encoding="utf-8")
            print(f"  [GUARDADO] {out_breakdown_csv}")

            out_report_txt = self.output_dir / f"relatorio_estabilidad_{scenario_label}_{m_mode}.txt"
            with open(out_report_txt, "w", encoding="utf-8") as f:
                f.write(report_text)
            print(f"  [GUARDADO] {out_report_txt}\n")

            # Generar Gráficos de Visión Global (Fig 1, Fig 1 3-Métricas y Fig 3)
            if save_plots:
                figures_dir = self.output_dir / "figures"
                figures_dir.mkdir(parents=True, exist_ok=True)
                self.plot_fig1_frontera(df_frontier, batch_sizes, self.threshold, figures_dir, scenario_label, m_mode)
                self.plot_fig1_frontera_3metricas(df_breakdown, batch_sizes, self.threshold, figures_dir, scenario_label, m_mode)
                self.plot_fig3_heatmap(df_frontier, batch_sizes, self.threshold, figures_dir, scenario_label, m_mode)

            # 3. Tabla 1 (Detalle por lote para el KPI y m seleccionado)
            kpis_to_detail = [k[0] for k in self.kpis_info] if detailed_kpi == "all" else [detailed_kpi]
            
            for k_target in kpis_to_detail:
                if k_target in self.df.columns:
                    # Validar si detailed_m es valido para este modo
                    m_use = detailed_m
                    if m_mode == "fixed_k" and (m_use * k_fixed > self.n_total):
                        m_use = max([b for b in batch_sizes if b * k_fixed <= self.n_total], default=batch_sizes[0])

                    df_detail = self.analyze_batch_distribution(k_target, batch_size=m_use, mode=m_mode, k_fixed=k_fixed)
                    if not df_detail.empty:
                        print(f"\n--- TABLA 1: DETALLE POR LOTE PARA {k_target} (Lotes m = {m_use}, Modo = {m_mode}) ---")
                        # Formatear números para visualización limpia
                        df_display = df_detail.copy()
                        for c in df_display.columns:
                            if c not in ["Lote", "N"]:
                                df_display[c] = df_display[c].apply(lambda v: f"{v:,.2f}" if isinstance(v, (int, float)) and not np.isnan(v) else str(v))
                        print(df_display.to_string(index=False))

                        out_detail = self.output_dir / f"tabla1_detalle_{scenario_label}_{k_target}_m{m_use}_{m_mode}.csv"
                        df_detail.to_csv(out_detail, index=False, encoding="utf-8")
                        print(f"  [GUARDADO] {out_detail}\n")

                        # Generar Gráficos de Detalle Interno de Lotes (Fig 2 y Fig 4)
                        if save_plots:
                            figures_dir = self.output_dir / "figures"
                            figures_dir.mkdir(parents=True, exist_ok=True)
                            self.plot_fig4_detalle_lotes(df_detail, k_target, m_use, self.threshold, figures_dir, scenario_label, m_mode)
                            
                            # Gráfico 2: Comparativa Inestable (m=50) vs Estable (m_use)
                            m_min = min(batch_sizes)
                            if m_min < m_use and (m_min * 10 <= self.n_total):
                                vals_kpi = self.df[k_target].dropna().values
                                self.plot_fig2_comparativa(vals_kpi, m_min, m_use, self.threshold, figures_dir, scenario_label, k_target)

            results[m_mode] = df_frontier

        print("=" * 85)
        print("  ANALISIS COMPLETADO EXITOSAMENTE.")
        print(f"  Archivos generados en: {self.output_dir.resolve()}")
        if save_plots:
            print(f"  Figuras guardadas en:  {(self.output_dir / 'figures').resolve()}")
        print("=" * 85 + "\n")

        return results

    # =========================================================================
    # FUNCIONES GRÁFICAS EXPLICATIVAS (IEEE / PUBLICATION QUALITY)
    # =========================================================================

    def plot_fig1_frontera(self, df_frontier, batch_sizes, threshold, out_dir, scenario_name, mode_name):
        """
        GRAFICO 1: Curvas de Frontera de Estabilidad (CV_inter % vs Tamano de Lote m)
        Muestra como decae el error relativo y donde cada KPI cruza el umbral X%.
        """
        kpi_rows = df_frontier[df_frontier["KPI"] != "SISTEMA_GLOBAL"]
        x_indices = np.arange(len(batch_sizes))
        x_labels = [f"m={m}" for m in batch_sizes]
        
        tech_colors = {
            "B_VminVmax":           "#1F77B4",
            "Sev_VminVmax_pct":     "#2CA02C",
            "Energy_Losses":        "#FF7F0E",
            "Min_Fluxo_Subestacao": "#9467BD",
            "Trafo_Loading_pct":    "#D62728",
        }
        
        fig, ax = plt.subplots(figsize=(5.5, 3.6), dpi=300)
        max_y = threshold * 2.0

        for _, row in kpi_rows.iterrows():
            kpi = row["KPI"]
            y_vals = []
            for m in batch_sizes:
                col = f"m={m}"
                raw_v = row[col] if col in row and pd.notnull(row[col]) else np.nan
                try:
                    val = float(raw_v)
                except (ValueError, TypeError):
                    val = np.nan
                y_vals.append(val)
                if not np.isnan(val):
                    max_y = max(max_y, val * 1.15)
            
            color = tech_colors.get(kpi, "#555555")
            kpi_desc = {k[0]: k[1] for k in self.kpis_info}
            label = kpi_desc.get(kpi, kpi)
            ax.plot(x_indices, y_vals, marker="o", markersize=4, linewidth=1.3,
                    color=color, label=f"{label} ({kpi})", zorder=4)

        # Zona sombreada de estabilidad
        ax.axhspan(0, threshold, color="#D4EDDA", alpha=0.5, zorder=1, label=f"Zona de Estabilidad (<= {threshold}%)")
        ax.axhline(threshold, color="#DC3545", linestyle="--", linewidth=1.0, zorder=2)
        ax.text(x_indices[-1], threshold + 0.15, f"Umbral X = {threshold}%", color="#DC3545",
                fontsize=7, ha="right", va="bottom", fontweight="bold")

        # N_optimo global
        sys_row = df_frontier[df_frontier["KPI"] == "SISTEMA_GLOBAL"]
        if not sys_row.empty:
            n_opt = sys_row.iloc[0].get(f"N_optimo (X<={threshold}%)")
            if n_opt in batch_sizes:
                idx_opt = batch_sizes.index(n_opt)
                ax.axvline(idx_opt, color="#28A745", linestyle=":", linewidth=1.2, zorder=2)
                ax.annotate(f"N_optimo = {n_opt}\n(Estabilidad Global)",
                            xy=(idx_opt, threshold),
                            xytext=(idx_opt + 0.15, threshold + max_y * 0.25),
                            arrowprops=dict(arrowstyle="->", color="#28A745", lw=0.9),
                            fontsize=6.5, fontweight="bold", color="#155724",
                            bbox=dict(boxstyle="round,pad=0.2", facecolor="#E8F5E9", edgecolor="#A5D6A7"))

        ax.set_xticks(x_indices)
        ax.set_xticklabels(x_labels)
        ax.set_xlabel("Tamano de Lote m (Numero de Simulaciones por Grupo)")
        ax.set_ylabel("Coeficiente de Variacion Inter-Grupos CV_inter (%)")
        ax.set_ylim(0, min(max_y, 25.0))
        ax.set_title(f"Frontera de Estabilidad Monte Carlo (Modo: {mode_name})\nEscenario: {scenario_name}", pad=6)
        ax.legend(loc="upper right", frameon=True, framealpha=0.9, facecolor="white", edgecolor="#CCCCCC")

        fig.tight_layout()
        out_base = Path(out_dir) / f"fig1_frontera_estabilidad_{scenario_name}_{mode_name}"
        fig.savefig(f"{out_base}.png", dpi=300, bbox_inches="tight")
        fig.savefig(f"{out_base}.pdf", bbox_inches="tight")
        plt.close(fig)
        print(f"  [GRAFICO 1] {out_base}.png/.pdf")

    def plot_fig1_frontera_3metricas(self, df_breakdown, batch_sizes, threshold, out_dir, scenario_name, mode_name):
        """
        GRAFICO 1-B: Curvas de Frontera de Estabilidad Desglosadas por Métrica:
        Genera un panel tríptico comparando (a) Media, (b) Mediana y (c) Desviación Estándar.
        También genera figuras individuales para cada métrica por separado.
        """
        x_indices = np.arange(len(batch_sizes))
        x_labels = [f"m={m}" for m in batch_sizes]

        tech_colors = {
            "B_VminVmax":           "#1F77B4",
            "Sev_VminVmax_pct":     "#2CA02C",
            "Energy_Losses":        "#FF7F0E",
            "Min_Fluxo_Subestacao": "#9467BD",
            "Trafo_Loading_pct":    "#D62728",
        }
        kpi_desc = {k[0]: k[1] for k in self.kpis_info}
        active_kpis = [k[0] for k in self.kpis_info if k[0] in self.df.columns]

        # 1. Tríptico Comparativo (1 fila x 3 columnas)
        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(13.0, 3.8), dpi=300)
        panels = [
            (ax1, "CV_Media_%",   "(a) Estabilidad de la Media (CV_Media %)",               12.0),
            (ax2, "CV_Mediana_%", "(b) Estabilidad de la Mediana (CV_Mediana %)",           12.0),
            (ax3, "CV_StdTrad_%", "(c) Estabilidad de la Desviacion Estandar (CV_StdTrad %)", 45.0)
        ]

        for ax, metric_col, title, max_y in panels:
            ax.axhspan(0, threshold, color="#D4EDDA", alpha=0.55, zorder=1)
            ax.axhline(threshold, color="#DC3545", linestyle="--", linewidth=1.0, zorder=2)
            ax.text(x_indices[-1], threshold + max_y * 0.02, f"Umbral X = {threshold}%", color="#DC3545",
                    fontsize=7, ha="right", va="bottom", fontweight="bold")

            for kpi in active_kpis:
                sub = df_breakdown[df_breakdown["KPI"] == kpi]
                y_vals = []
                for m in batch_sizes:
                    row_m = sub[sub["m"] == m]
                    v = row_m[metric_col].values[0] if not row_m.empty else np.nan
                    y_vals.append(v)

                color = tech_colors.get(kpi, "#555555")
                label = f"{kpi_desc.get(kpi, kpi)} ({kpi})"
                ax.plot(x_indices, y_vals, marker="o", markersize=4, linewidth=1.3,
                        color=color, label=label, zorder=4)

            ax.set_xticks(x_indices)
            ax.set_xticklabels(x_labels, fontsize=7.5)
            ax.set_xlabel("Tamano de Lote m (Simulaciones)", fontsize=8)
            ax.set_ylabel("CV_inter (%)", fontsize=8)
            ax.set_ylim(0, max_y)
            ax.set_title(title, fontsize=8.5, fontweight="bold", pad=8)
            ax.grid(True, linestyle=":", alpha=0.5, color="#CCCCCC")

        handles, labels = ax1.get_legend_handles_labels()
        handles.append(Rectangle((0, 0), 1, 1, facecolor="#D4EDDA", edgecolor="#28A745", label=f"Zona Estable (<= {threshold}%)"))
        labels.append(f"Zona Estable (<= {threshold}%)")
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.05), ncol=3, fontsize=7.5, frameon=True)

        fig.tight_layout()
        out_base = Path(out_dir) / f"fig1_frontera_estabilidad_3metricas_{scenario_name}_{mode_name}"
        fig.savefig(f"{out_base}.png", dpi=300, bbox_inches="tight")
        fig.savefig(f"{out_base}.pdf", bbox_inches="tight")
        plt.close(fig)
        print(f"  [GRAFICO 1-B TRIPTICO 3 METRICAS] {out_base}.png/.pdf")

        # 2. Figuras Individuales para Media, Mediana y Desviación Estándar
        metric_configs = [
            ("CV_Media_%",   "media",   "Estabilidad de la Media (CV_Media %)",               12.0),
            ("CV_Mediana_%", "mediana", "Estabilidad de la Mediana (CV_Mediana %)",           12.0),
            ("CV_StdTrad_%", "stdtrad", "Estabilidad de la Desviacion Estandar (CV_Std %)",   45.0)
        ]

        for m_col, suffix, title, max_y in metric_configs:
            fig_ind, ax_ind = plt.subplots(figsize=(5.5, 3.6), dpi=300)
            ax_ind.axhspan(0, threshold, color="#D4EDDA", alpha=0.55, zorder=1, label=f"Zona de Estabilidad (<= {threshold}%)")
            ax_ind.axhline(threshold, color="#DC3545", linestyle="--", linewidth=1.0, zorder=2)
            ax_ind.text(x_indices[-1], threshold + max_y * 0.02, f"Umbral X = {threshold}%", color="#DC3545",
                        fontsize=7, ha="right", va="bottom", fontweight="bold")

            for kpi in active_kpis:
                sub = df_breakdown[df_breakdown["KPI"] == kpi]
                y_vals = [sub[sub["m"] == m][m_col].values[0] if not sub[sub["m"] == m].empty else np.nan for m in batch_sizes]
                color = tech_colors.get(kpi, "#555555")
                label = f"{kpi_desc.get(kpi, kpi)} ({kpi})"
                ax_ind.plot(x_indices, y_vals, marker="o", markersize=4, linewidth=1.3,
                            color=color, label=label, zorder=4)

            ax_ind.set_xticks(x_indices)
            ax_ind.set_xticklabels(x_labels, fontsize=8)
            ax_ind.set_xlabel("Tamano de Lote m (Numero de Simulaciones)", fontsize=8)
            ax_ind.set_ylabel("Coeficiente de Variacion Inter-Grupos CV_inter (%)", fontsize=8)
            ax_ind.set_ylim(0, max_y)
            ax_ind.set_title(f"{title}\nEscenario: {scenario_name} | Modo: {mode_name}", pad=6, fontsize=9)
            ax_ind.legend(loc="upper right", frameon=True, framealpha=0.9, facecolor="white", edgecolor="#CCCCCC", fontsize=7)
            ax_ind.grid(True, linestyle=":", alpha=0.5, color="#CCCCCC")

            fig_ind.tight_layout()
            out_ind = Path(out_dir) / f"fig1_frontera_{suffix}_{scenario_name}_{mode_name}"
            fig_ind.savefig(f"{out_ind}.png", dpi=300, bbox_inches="tight")
            fig_ind.savefig(f"{out_ind}.pdf", bbox_inches="tight")
            plt.close(fig_ind)
            print(f"  [GRAFICO 1 INDIVIDUAL - {suffix.upper()}] {out_ind}.png/.pdf")

    def plot_fig2_comparativa(self, vals_array, m_small, m_large, threshold, out_dir, scenario_name, kpi_name):
        """
        GRAFICO 2: Comparativa de Consistencia Lotes Inestables vs Lotes Estables
        Panel A: m pequeno (Inestable)  vs  Panel B: m grande (Estable)
        """
        k_show = 10
        if len(vals_array) < k_show * m_large:
            k_show = len(vals_array) // m_large
        if k_show < 2:
            return

        g_small = [vals_array[i * m_small : (i + 1) * m_small] for i in range(k_show)]
        g_large = [vals_array[i * m_large : (i + 1) * m_large] for i in range(k_show)]

        means_s = [np.mean(g) for g in g_small]
        stds_s  = [np.std(g, ddof=1) for g in g_small]
        cv_s    = np.std(means_s, ddof=1) / abs(np.mean(means_s)) * 100 if abs(np.mean(means_s)) > 1e-6 else 0

        means_l = [np.mean(g) for g in g_large]
        stds_l  = [np.std(g, ddof=1) for g in g_large]
        cv_l    = np.std(means_l, ddof=1) / abs(np.mean(means_l)) * 100 if abs(np.mean(means_l)) > 1e-6 else 0

        global_mean = float(np.mean(vals_array[:k_show * m_large]))
        band_upper = global_mean * (1.0 + threshold / 100.0)
        band_lower = global_mean * (1.0 - threshold / 100.0)

        x_axis = np.arange(1, k_show + 1)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.5, 2.8), dpi=300, sharey=True)

        # Panel A: Inestable
        ax1.axhspan(band_lower, band_upper, color="#E2E3E5", alpha=0.6, label=f"Banda +- {threshold}%")
        ax1.axhline(global_mean, color="#6C757D", linestyle=":", linewidth=0.8)
        ax1.errorbar(x_axis, means_s, yerr=stds_s, fmt="o-", color="#DC3545", ecolor="#F8D7DA",
                     elinewidth=1.2, capsize=2, markersize=3.5, label="Media +- std")
        ax1.set_title(f"(a) Lote Inestable: m = {m_small}\nCV_inter = {cv_s:.2f}% (> {threshold}%)", color="#721C24")
        ax1.set_xlabel("Numero de Lote")
        ax1.set_ylabel(f"{kpi_name}")
        ax1.set_xticks(x_axis)
        ax1.legend(loc="lower left", framealpha=0.8)

        # Panel B: Estable
        ax2.axhspan(band_lower, band_upper, color="#D4EDDA", alpha=0.6, label=f"Banda +- {threshold}%")
        ax2.axhline(global_mean, color="#28A745", linestyle=":", linewidth=0.8)
        ax2.errorbar(x_axis, means_l, yerr=stds_l, fmt="s-", color="#28A745", ecolor="#C3E6CB",
                     elinewidth=1.2, capsize=2, markersize=3.5, label="Media +- std")
        ax2.set_title(f"(b) Lote Estable: m = {m_large}\nCV_inter = {cv_l:.2f}% (<= {threshold}%)", color="#155724")
        ax2.set_xlabel("Numero de Lote")
        ax2.set_xticks(x_axis)
        ax2.legend(loc="lower left", framealpha=0.8)

        fig.tight_layout()
        out_base = Path(out_dir) / f"fig2_comparativa_consistencia_{scenario_name}_{kpi_name}"
        fig.savefig(f"{out_base}.png", dpi=300, bbox_inches="tight")
        fig.savefig(f"{out_base}.pdf", bbox_inches="tight")
        plt.close(fig)
        print(f"  [GRAFICO 2] {out_base}.png/.pdf")

    def plot_fig3_heatmap(self, df_frontier, batch_sizes, threshold, out_dir, scenario_name, mode_name):
        """
        GRAFICO 3: Matriz Termica / Semaforo de Estabilidad (Heatmap Multi-KPI x m)
        """
        kpi_rows = df_frontier[df_frontier["KPI"] != "SISTEMA_GLOBAL"].copy()
        kpis = kpi_rows["KPI"].values
        kpi_desc = {k[0]: k[1] for k in self.kpis_info}
        kpi_names = [f"{kpi_desc.get(k, k)} ({k})" for k in kpis]

        cols_m = [f"m={m}" for m in batch_sizes]
        matrix = kpi_rows[cols_m].apply(pd.to_numeric, errors="coerce").values.astype(float)

        fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=300)
        norm = plt.Normalize(vmin=0, vmax=threshold * 2.5)
        cmap = plt.cm.RdYlGn_r

        im = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")

        for i in range(len(kpis)):
            for j in range(len(batch_sizes)):
                val = matrix[i, j]
                if not np.isnan(val):
                    txt_color = "white" if val > threshold * 1.5 or val < threshold * 0.3 else "black"
                    mark = " [OK]" if val <= threshold else ""
                    ax.text(j, i, f"{val:.2f}%{mark}", ha="center", va="center",
                            fontsize=6.5, color=txt_color, fontweight="bold" if val <= threshold else "normal")
                else:
                    ax.text(j, i, "N/A", ha="center", va="center", fontsize=6.5, color="#888888")

        sys_row = df_frontier[df_frontier["KPI"] == "SISTEMA_GLOBAL"]
        if not sys_row.empty:
            n_opt = sys_row.iloc[0].get(f"N_optimo (X<={threshold}%)")
            if n_opt in batch_sizes:
                j_opt = batch_sizes.index(n_opt)
                rect = Rectangle((j_opt - 0.48, -0.48), 0.96, len(kpis) - 0.04,
                                 linewidth=2.0, edgecolor="#1B5E20", facecolor="none", linestyle="-")
                ax.add_patch(rect)
                ax.text(j_opt, -0.7, f"N_optimo = {n_opt}", ha="center", va="bottom",
                        fontsize=7, color="#1B5E20", fontweight="bold")

        ax.set_xticks(np.arange(len(batch_sizes)))
        ax.set_xticklabels([f"m={m}" for m in batch_sizes])
        ax.set_yticks(np.arange(len(kpis)))
        ax.set_yticklabels(kpi_names)
        ax.set_xlabel("Tamano de Lote (m)")
        ax.set_title(f"Semaforo de Estabilidad Multi-KPI (Umbral <= {threshold}%)\nEscenario: {scenario_name} | Modo: {mode_name}", pad=14)

        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label("CV_inter (%)")

        fig.tight_layout()
        out_base = Path(out_dir) / f"fig3_heatmap_estabilidad_{scenario_name}_{mode_name}"
        fig.savefig(f"{out_base}.png", dpi=300, bbox_inches="tight")
        fig.savefig(f"{out_base}.pdf", bbox_inches="tight")
        plt.close(fig)
        print(f"  [GRAFICO 3] {out_base}.png/.pdf")

    def plot_fig4_detalle_lotes(self, df_table1, kpi_name, m_size, threshold, out_dir, scenario_name, mode_name):
        """
        GRAFICO 4: Detalle Lote a Lote con Mediana, MAD/IQR y P95 (Visualizacion de Tabla 1)
        """
        lote_rows = df_table1[df_table1["Lote"].str.startswith("Lote_")].copy()
        if lote_rows.empty:
            return

        k = len(lote_rows)
        x = np.arange(1, k + 1)

        meds  = lote_rows["Mediana"].values.astype(float)
        means = lote_rows["Media"].values.astype(float)
        mads  = lote_rows["MAD"].values.astype(float)
        p95s  = lote_rows["P95"].values.astype(float)

        prom_row = df_table1[df_table1["Lote"] == "PROMEDIO_GLOBAL"]
        global_med = float(prom_row["Mediana"].values[0]) if not prom_row.empty else float(np.mean(meds))

        band_hi = global_med * (1.0 + threshold / 100.0)
        band_lo = global_med * (1.0 - threshold / 100.0)

        fig, ax = plt.subplots(figsize=(6.0, 3.2), dpi=300)

        ax.axhspan(band_lo, band_hi, color="#E8F5E9", alpha=0.7, label=f"Tolerancia Global +- {threshold}%")
        ax.axhline(global_med, color="#2E7D32", linestyle=":", linewidth=1.0, label="Mediana Global de Referencia")

        ax.errorbar(x, meds, yerr=mads, fmt="o", color="#1565C0", ecolor="#90CAF9",
                    elinewidth=2.5, capsize=3, capthick=1.2, markersize=4.5, label="Mediana +- MAD (Dispersion Robusta)", zorder=4)

        ax.scatter(x, means, marker="D", s=16, color="#E65100", label="Media del Lote", zorder=5)
        ax.scatter(x, p95s, marker="_", s=40, color="#C62828", linewidth=1.5, label="Percentil 95 (P95)", zorder=5)

        ax.set_xticks(x)
        ax.set_xticklabels([f"L{i}" for i in x], fontsize=6.5)
        ax.set_xlabel("Numero de Lote")
        ax.set_ylabel(f"{kpi_name}")
        ax.set_title(f"Detalle Lote a Lote: {kpi_name} (Lotes m = {m_size}, k = {k} lotes)\nEscenario: {scenario_name} | Modo: {mode_name}", pad=6)
        ax.legend(loc="upper right", framealpha=0.9, fontsize=6.5)

        fig.tight_layout()
        out_base = Path(out_dir) / f"fig4_detalle_lotes_{scenario_name}_{kpi_name}_m{m_size}_{mode_name}"
        fig.savefig(f"{out_base}.png", dpi=300, bbox_inches="tight")
        fig.savefig(f"{out_base}.pdf", bbox_inches="tight")
        plt.close(fig)
        print(f"  [GRAFICO 4] {out_base}.png/.pdf")


# =============================================================================
# ENTRADA DE LÍNEA DE COMANDOS (CLI)
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Analizador de Estabilidad y Tamaño Optimo de Monte Carlo por Lotes (Batch Means)."
    )
    parser.add_argument("--csv", type=str, default=CSV_FILE,
                        help=f"Ruta al archivo CSV de resultados (default: {CSV_FILE}).")
    parser.add_argument("--threshold", type=float, default=THRESHOLD_X,
                        help=f"Umbral de estabilidad en porcentaje X%% (default: {THRESHOLD_X}).")
    parser.add_argument("--pen", type=float, default=PENETRATION_LEVEL,
                        help="Nivel de penetracion a analizar (ej. 50.0). Por defecto auto-detecta.")
    parser.add_argument("--batches", type=int, nargs="+", default=BATCH_SIZES,
                        help=f"Lista de tamanos de lote m a evaluar (default: {' '.join(map(str, BATCH_SIZES))}).")
    parser.add_argument("--mode", type=str, choices=["exhaustive", "fixed_k", "both"], default=MODE,
                        help=f"Perspectiva de particion (default: {MODE}).")
    parser.add_argument("--k-fixed", type=int, default=K_FIXED,
                        help=f"Numero de lotes constantes para fixed_k (default: {K_FIXED}).")
    parser.add_argument("--detailed-kpi", type=str, default=DETAILED_KPI,
                        help=f"KPI para generar la Tabla 1 detallada (default: {DETAILED_KPI}).")
    parser.add_argument("--detailed-m", type=int, default=DETAILED_BATCH_SIZE,
                        help=f"Tamano de lote para la Tabla 1 (default: {DETAILED_BATCH_SIZE}).")
    parser.add_argument("--output-dir", type=str, default=OUTPUT_DIR,
                        help=f"Carpeta de salida para reportes CSV (default: {OUTPUT_DIR}).")
    parser.add_argument("--no-plots", action="store_true",
                        help="Desactiva la generacion automatica de figuras explicativas PNG/PDF.")
    return parser.parse_args()


def main():
    args = parse_args()

    analyzer = BatchStabilityAnalyzer(
        csv_path=args.csv,
        penetration_level=args.pen,
        threshold_pct=args.threshold,
        output_dir=args.output_dir
    )

    analyzer.run_complete_analysis(
        batch_sizes=args.batches,
        mode=args.mode,
        k_fixed=args.k_fixed,
        detailed_kpi=args.detailed_kpi,
        detailed_m=args.detailed_m,
        save_plots=not args.no_plots
    )


if __name__ == "__main__":
    main()
