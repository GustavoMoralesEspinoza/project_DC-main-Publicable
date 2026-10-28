# project/modules/dc/dc_profiles.py
"""
Carga y sorteo de perfiles de workload para Data Centers.

Convenciones:
  - Los archivos gen_*.csv son perfiles del generador BTM — se excluyen del workload.
  - Los perfiles de workload se devuelven como listas de 24 floats (no numpy arrays).
  - Fallback automático si la carpeta está vacía o no existe.
"""

import os
import numpy as np
import pandas as pd

_FALLBACK_WORKLOAD = [0.90] * 24
_FALLBACK_WORKLOAD_NAME = "Fallback_Flat"

_FALLBACK_GEN = [0.95] * 24
_FALLBACK_GEN_NAME = "Fallback_Gen_Flat"


def load_dc_profiles(profiles_dir):
    """
    Lee CSVs de workload (24 valores) desde profiles_dir.
    Excluye archivos que empiecen con "gen_" (reservados para el generador BTM).

    Retorna
    -------
    profiles : list[list[float]] — cada elemento es una lista de 24 floats
    names    : list[str]         — nombre del archivo sin extensión
    """
    profiles, names = [], []

    if os.path.isdir(profiles_dir):
        for fname in sorted(os.listdir(profiles_dir)):
            if not fname.endswith(".csv"):
                continue
            if fname.startswith("gen_"):
                continue
            fpath = os.path.join(profiles_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    raw = f.read().replace("\n", ",").replace(" ", "")
                values = [float(v) for v in raw.split(",") if v.strip()]
                if len(values) != 24:
                    print(f"  [AVISO] dc_profiles: {fname}: se esperaban 24 valores, se encontraron {len(values)}. Ignorado.")
                    continue
                profiles.append(values)
                names.append(os.path.splitext(fname)[0])
            except Exception as e:
                print(f"  [AVISO] dc_profiles: {fname}: {e}. Ignorado.")

    if not profiles:
        print("  [INFO] dc_profiles: No hay curvas de workload en dc_profiles/ — usando fallback plano.")
        profiles.append(list(_FALLBACK_WORKLOAD))
        names.append(_FALLBACK_WORKLOAD_NAME)

    return profiles, names


def sample_dc_workload(profiles, names):
    """
    Sortea un perfil de workload aleatoriamente.

    Retorna
    -------
    profile : list[float] — copia del perfil de 24 valores sorteado
    name    : str         — nombre del arquetipo
    """
    idx = np.random.randint(0, len(profiles))
    return list(profiles[idx]), names[idx]


def load_dc_gen_profile(profiles_dir):
    """
    Busca el primer archivo gen_*.csv en profiles_dir.
    Usado para la curva del generador BTM opcional.

    Retorna
    -------
    profile : list[float] — lista de 24 floats
    name    : str         — nombre del archivo sin extensión
    """
    if os.path.isdir(profiles_dir):
        for fname in sorted(os.listdir(profiles_dir)):
            if not fname.endswith(".csv"):
                continue
            if not fname.startswith("gen_"):
                continue
            fpath = os.path.join(profiles_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    raw = f.read().replace("\n", ",").replace(" ", "")
                values = [float(v) for v in raw.split(",") if v.strip()]
                if len(values) != 24:
                    print(f"  [AVISO] dc_gen_profile: {fname}: se esperaban 24 valores, se encontraron {len(values)}. Ignorado.")
                    continue
                return values, os.path.splitext(fname)[0]
            except Exception as e:
                print(f"  [AVISO] dc_gen_profile: {fname}: {e}. Ignorado.")

    print("  [INFO] dc_profiles: No se encontró gen_*.csv — usando fallback plano para generador BTM.")
    return list(_FALLBACK_GEN), _FALLBACK_GEN_NAME


# =============================================================================
# Modelo GT&D 2027: arquetipos y temperaturas (independiente del modulo PV)
# =============================================================================

def list_dc_archetypes(archetypes_dir):
    """Nombres de los arquetipos disponibles (archivos .csv de archetypes_dir, sin extension)."""
    if not os.path.isdir(archetypes_dir):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(archetypes_dir) if f.endswith(".csv"))


def get_workload_profile(archetype, archetypes_dir):
    """
    Lee la curva de utilizacion horaria (u_k(h) en el paper) del arquetipo
    desde <archetypes_dir>/<archetype>.csv.

    El CSV debe tener columnas Hora (0-23, las 24, sin repetir) y Utilizacion
    (entre 0 y 1). Los valores se usan tal cual, sin normalizar. Sin fallback:
    cualquier problema detiene la corrida.

    Retorna : list de 24 floats entre 0 y 1, ordenados por hora
    """
    path = os.path.join(archetypes_dir, f"{archetype}.csv")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Arquetipo DC {archetype!r} no encontrado: {path}. "
                                f"Disponibles: {list_dc_archetypes(archetypes_dir)}")
    df = pd.read_csv(path)
    for col in ("Hora", "Utilizacion"):
        if col not in df.columns:
            raise ValueError(f"{path}: falta la columna {col!r}")
    if sorted(df["Hora"].tolist()) != list(range(24)):
        raise ValueError(f"{path}: la columna Hora debe tener 0 a 23, una vez cada una")
    u = df.sort_values("Hora")["Utilizacion"].to_numpy(dtype=float)
    if not np.isfinite(u).all() or u.min() < 0 or u.max() > 1:
        raise ValueError(f"{path}: Utilizacion debe estar entre 0 y 1")
    return u.tolist()


def load_dc_temperature_matrix(csv_file, temp_col="T2m_mean"):
    """
    Lee las temperaturas ambiente horarias medias por mes para el modelo DC.

    Carga independiente del modulo PV (no usa load_irradiance_matrices).
    El CSV debe tener columnas Mes (1-12), Hora (0-23) y temp_col (grados Celsius).
    Si hay varias filas por (Mes, Hora), por ejemplo una por dia, se promedian.

    Retorna
    -------
    temp_matrix : np.ndarray shape (12, 24), grados Celsius
    """
    if not os.path.isfile(csv_file):
        raise FileNotFoundError(f"DC_TEMPERATURE_FILE no encontrado: {csv_file}")
    df = pd.read_csv(csv_file)
    for col in ("Mes", "Hora", temp_col):
        if col not in df.columns:
            raise ValueError(f"{csv_file}: falta la columna {col!r}")

    table = (df.groupby(["Mes", "Hora"])[temp_col].mean()
               .unstack("Hora")
               .reindex(index=range(1, 13), columns=range(24)))
    if table.isna().any().any():
        raise ValueError(f"{csv_file}: faltan pares (Mes, Hora) para completar 12x24")
    return table.to_numpy(dtype=float)
