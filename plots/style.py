# project/plots/style.py
"""
Hoja de estilo centralizada para todas las figuras del proyecto.
Los 8 módulos activos de plots/ importan STYLE/TECH_COLORS/SCENARIO_META y
llaman apply_style() (figuras finales del paper) o apply_style_diagnostic()
(figuras de diagnóstico de verify.py) — no vuelven a definir colores ni
tipografía por su cuenta.
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ─── Estilo tipográfico y de figura — figuras finales del paper (IEEE 1 col) ────
STYLE = {
    "dpi":                  300,
    "figsize_single":       (3.5, 2.8),   # una columna IEEE
    "figsize_double":       (7.16, 3.5),  # doble columna IEEE
    "font_family":          "Times New Roman",
    "font_serif_fallback":  ["Times New Roman", "Times", "DejaVu Serif"],
    "font_size_axis":       8,
    "font_size_title":      9,
    "font_size_legend":     7,
    "grid_color":           "#E0E0E0",
    "grid_alpha":           0.5,
    "grid_style":           "--",
    "band_alpha":           0.15,
    "export_formats":       ["png", "pdf"],
}

# Figuras de diagnóstico (verify.py -> plot_system.py / plot_voltage.py).
# Deliberadamente más grandes para legibilidad en pantalla — no son figuras
# finales del paper, por eso mantienen su propio tamaño de fuente (ver
# STYLE_DIAGNOSTIC_PASO_A.md, decisión del usuario para la pregunta 3).
DIAG_STYLE = {
    "font_size_axis":    12,
    "axes_labelsize":    11,
    "tick_labelsize":    10,
    "font_size_legend":  9,
}

# ─── Paleta por tecnología — única fuente de verdad ─────────────────────────
TECH_COLORS = {
    "PV":      "#2166AC",
    "DC":      "#B2182B",
    "BESS":    "#35978F",
    "EVCS":    "#BF812D",
    "Load":    "#555555",
    "Trafo":   "#E08214",
    "Reverse": "#762A83",
    "Limit":   "black",
}

# ─── Paleta por escenario del paper ──────────────────────────────────────────
# S_PV/S_DC/S_DC25/S_DC50/S_DC100: claves y colores SIN CAMBIOS respecto al
# original duplicado en violines.py/curvas_multiescenario.py — otros papers
# del proyecto pueden depender de estos valores exactos.
# E1_PV/E2_EV/E3_Combined/E4_BESS: escenarios nuevos del paper actual, color
# derivado de TECH_COLORS (no inventado), salvo E3_Combined que usa un gris
# neutro reservado para superposición multi-tecnología.
SCENARIO_META = {
    "S_PV":    {"label": "Solo PV",        "color": "#2166AC", "ls": "-",  "pen_col": "Pen_PV"},
    "S_DC":    {"label": "Solo DC",        "color": "#B2182B", "ls": "-",  "pen_col": "Pen_DC"},
    "S_DC25":  {"label": "PV + DC×0.25",   "color": "#1B7837", "ls": "-",  "pen_col": "Pen_PV"},
    "S_DC50":  {"label": "PV + DC×0.50",   "color": "#762A83", "ls": "-",  "pen_col": "Pen_PV"},
    "S_DC100": {"label": "PV + DC×1.00",   "color": "#E08214", "ls": "--", "pen_col": "Pen_PV"},

    "E1_PV":       {"label": "E1 — PV",       "color": TECH_COLORS["PV"],   "ls": "-", "pen_col": "Pen_PV"},
    "E2_EV":       {"label": "E2 — EV/CS",    "color": TECH_COLORS["EVCS"], "ls": "-", "pen_col": "Pen_EV"},
    "E3_Combined": {"label": "E3 — Combined", "color": "#4D4D4D",           "ls": "-", "pen_col": "Pen_PV"},
    "E4_BESS":     {"label": "E4 — BESS",     "color": TECH_COLORS["BESS"], "ls": "-", "pen_col": "Pen_BESS"},
}

# ─── Detección de columna de barrido (sweep) ─────────────────────────────────
SWEEP_LABELS = {
    "Penetration_Level": "Penetration level (%)",
    "Pen_PV":   "PV penetration (%)",
    "Pen_BESS": "BESS penetration (%)",
    "Pen_EV":   "EV/CS penetration (%)",
    "Pen_DC":   "DC penetration (%)",
}

# Short form, for compact inline annotations (e.g. "PV = 50%  |  DC = 20%")
SWEEP_SHORT_LABELS = {
    "Penetration_Level": "Level",
    "Pen_PV":   "PV",
    "Pen_BESS": "BESS",
    "Pen_EV":   "EV",
    "Pen_DC":   "DC",
}


def detect_sweep_col(df):
    """
    Retorna (primary_sweep_col, secondary_col) — la columna a usar como
    eje X (y, si aplica, el eje X secundario/superior) para un CSV de
    resultados u horario de este proyecto.

    Prefiere la columna "Penetration_Level" (el nivel de barrido crudo
    que escribe core.monte_carlo, presente en CSVs generados después del
    fix de detección de barrido) cuando realmente varía. Si no está
    presente, cae a la que tenga más valores distintos entre
    Pen_PV/Pen_BESS/Pen_EV/Pen_DC, para CSVs viejos sin esa columna.

    Antes de este fix, la detección solo comparaba Pen_PV vs Pen_DC, lo
    que colapsaba escenarios con PV desactivado (solo EV, solo BESS) a
    un único punto de 0%, porque Pen_PV y Pen_DC quedaban constantes en
    0 durante todo el barrido en esos casos.
    """
    if "Penetration_Level" in df.columns and df["Penetration_Level"].nunique() > 1:
        primary = "Penetration_Level"
    else:
        candidates = [c for c in ("Pen_PV", "Pen_BESS", "Pen_EV", "Pen_DC") if c in df.columns]
        primary = max(candidates, key=lambda c: df[c].nunique())

    secondary_candidates = [c for c in ("Pen_PV", "Pen_DC") if c in df.columns and c != primary]
    secondary = secondary_candidates[0] if secondary_candidates else "Pen_DC"
    return primary, secondary


def apply_style():
    """Aplica el estilo de las figuras finales del paper (IEEE una columna)."""
    plt.rcParams.update({
        "font.family":       "serif",
        "font.serif":        STYLE["font_serif_fallback"],
        "font.size":         STYLE["font_size_axis"],
        "axes.titlesize":    STYLE["font_size_title"],
        "axes.labelsize":    STYLE["font_size_axis"],
        "xtick.labelsize":   STYLE["font_size_axis"] - 1,
        "ytick.labelsize":   STYLE["font_size_axis"] - 1,
        "legend.fontsize":   STYLE["font_size_legend"],
        "axes.linewidth":    0.6,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "xtick.major.size":  3,
        "ytick.major.size":  3,
        "axes.grid":         True,
        "grid.color":        STYLE["grid_color"],
        "grid.linewidth":    0.4,
        "grid.alpha":        STYLE["grid_alpha"],
        "grid.linestyle":    STYLE["grid_style"],
        "legend.framealpha": 0.88,
        "legend.edgecolor":  "0.7",
        "figure.dpi":        STYLE["dpi"],
        "savefig.dpi":       STYLE["dpi"],
    })


def apply_style_diagnostic():
    """
    Aplica el estilo de las figuras de diagnóstico (verify.py). Mismo
    font family/fallback que apply_style(), pero tamaño de fuente mayor a
    propósito para legibilidad en pantalla — no son figuras finales del
    paper (ver DIAG_STYLE).
    """
    plt.rcParams.update({
        "font.family":       "serif",
        "font.serif":        STYLE["font_serif_fallback"],
        "font.size":         DIAG_STYLE["font_size_axis"],
        "axes.labelsize":    DIAG_STYLE["axes_labelsize"],
        "xtick.labelsize":   DIAG_STYLE["tick_labelsize"],
        "ytick.labelsize":   DIAG_STYLE["tick_labelsize"],
        "legend.fontsize":   DIAG_STYLE["font_size_legend"],
        "lines.linewidth":   1.2,
        "axes.linewidth":    0.6,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "xtick.major.size":  3,
        "ytick.major.size":  3,
        "axes.grid":         True,
        "grid.linewidth":    0.4,
        "grid.alpha":        0.4,
        "legend.framealpha": 0.88,
        "legend.edgecolor":  "0.7",
        "figure.dpi":        STYLE["dpi"],
    })


def save_figure(fig, filepath_no_ext):
    """Guarda la figura en todos los formatos configurados en STYLE."""
    os.makedirs(os.path.dirname(str(filepath_no_ext)), exist_ok=True)
    for fmt in STYLE["export_formats"]:
        fig.savefig(f"{filepath_no_ext}.{fmt}", format=fmt, bbox_inches="tight")
    plt.close(fig)
