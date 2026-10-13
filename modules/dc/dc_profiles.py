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
