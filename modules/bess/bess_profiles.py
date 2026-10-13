# project/modules/bess/bess_profiles.py
"""
Carga las curvas de despacho BESS desde data/bess_profiles/.
En cada iteración cada unidad BESS sortea una curva independientemente.

Para agregar una curva de despacho personalizada:
  1. Crea un archivo CSV en data/bess_profiles/ con 24 valores separados por coma.
     Convención: negativo = carga, positivo = descarga, rango -1..1
  2. El framework la detecta y la incluye automáticamente en el sorteo.

Formato del CSV (ejemplo — mi_perfil.csv):
    0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,-0.5,-1.0,-1.0,...,1.0,0.5,0.0

Si la carpeta está vacía, se usa una curva de fallback interna.
"""

import os
import numpy as np


# Curva de fallback — perfil genérico carga mediodía / descarga tarde
_FALLBACK_CURVE = [
     0.0,  0.0,  0.0,  0.0,  0.0,  0.0,
     0.0,  0.0,  0.0,
    -0.5, -1.0, -1.0, -0.5,
     0.0,  0.0,  0.0,  0.0,
     0.5,  1.0,  1.0,  0.5,
     0.0,  0.0,  0.0,
]
_FALLBACK_NAME = "Fallback_Generic"


def load_bess_profiles(bess_profiles_dir):
    """
    Lee todos los archivos CSV de la carpeta bess_profiles_dir.
    Cada archivo debe tener 24 valores separados por coma (una sola fila).
    Los valores pueden ser negativos (carga) o positivos (descarga).

    Retorna
    -------
    profiles : list de lists — cada elemento es una lista de 24 floats
    names    : list de str   — nombre de archivo de cada perfil (sin extensión)
    """
    profiles, names = [], []

    if os.path.isdir(bess_profiles_dir):
        for fname in sorted(os.listdir(bess_profiles_dir)):
            if not fname.endswith(".csv"):
                continue
            fpath = os.path.join(bess_profiles_dir, fname)
            try:
                with open(fpath, "r") as f:
                    content = f.read().strip()
                values = [float(v) for v in content.replace("\n", ",").split(",") if v.strip()]
                if len(values) != 24:
                    print(f"  [AVISO] {fname}: se esperaban 24 valores, tiene {len(values)}. Ignorado.")
                    continue
                profiles.append(values)
                names.append(os.path.splitext(fname)[0])
            except Exception as e:
                print(f"  [AVISO] No se pudo leer {fname}: {e}. Ignorado.")

    if not profiles:
        print("  [INFO] No hay curvas en bess_profiles/ — usando curva de fallback interna.")
        profiles.append(list(_FALLBACK_CURVE))
        names.append(_FALLBACK_NAME)

    return profiles, names


def sample_dispatch_profile(profiles, names):
    """
    Sortea aleatoriamente uno de los perfiles de despacho disponibles.
    Llamar una vez por unidad BESS por iteración.

    Retorna
    -------
    profile : list de 24 floats (negativo=carga, positivo=descarga)
    name    : str — nombre del perfil sorteado (para registro)
    """
    idx = np.random.randint(0, len(profiles))
    return list(profiles[idx]), names[idx]
