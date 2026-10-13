# project/modules/ev_cs/ev_profiles.py
"""
Carga las curvas de carga de estaciones EV/CS desde data/ev_profiles/.
En cada iteración cada estación sortea una curva independientemente,
igual que los perfiles de despacho BESS.

Para agregar una curva de carga personalizada:
  1. Crea un archivo CSV en data/ev_profiles/ con 24 valores (uno por hora),
     separados por coma, representando la carga normalizada (0..1).
  2. El framework la detecta y la incluye automáticamente en el sorteo.

Formato del CSV (ejemplo — curva_residencial.csv):
    0.10,0.10,0.10,0.10,0.10,0.15,0.20,0.30,...,0.85,0.90,0.80,0.50

Si la carpeta está vacía, se usa una curva de fallback interna
para que el framework no falle si aún no se han cargado curvas propias.
"""

import os
import numpy as np


# Curva de fallback interna — perfil genérico de estación de carga
# Curva genérica de respaldo — se reemplaza automáticamente al agregar CSVs en data/ev_profiles/.
_FALLBACK_CURVE = [
    0.10, 0.10, 0.10, 0.10, 0.10, 0.15,
    0.30, 0.60, 0.80, 0.70, 0.50, 0.40,
    0.40, 0.50, 0.60, 0.70, 0.80, 0.90,
    1.00, 0.95, 0.80, 0.60, 0.40, 0.20,
]
_FALLBACK_NAME = "Fallback_Generic"


def load_ev_profiles(ev_profiles_dir):
    """
    Lee todos los archivos CSV de la carpeta ev_profiles_dir.
    Cada archivo debe tener 24 valores separados por coma (una sola fila).

    Retorna
    -------
    profiles : list de lists — cada elemento es una lista de 24 floats normalizados
    names    : list de str   — nombre de archivo de cada perfil (sin extensión)
    """
    profiles, names = [], []

    if os.path.isdir(ev_profiles_dir):
        for fname in sorted(os.listdir(ev_profiles_dir)):
            if not fname.endswith(".csv"):
                continue
            fpath = os.path.join(ev_profiles_dir, fname)
            try:
                with open(fpath, "r") as f:
                    content = f.read().strip()
                values = [float(v) for v in content.replace("\n", ",").split(",") if v.strip()]
                if len(values) != 24:
                    print(f"  [AVISO] {fname}: se esperaban 24 valores, tiene {len(values)}. Ignorado.")
                    continue
                # Normalizar para que el máximo sea 1.0
                maximo = max(values)
                if maximo <= 0:
                    print(f"  [AVISO] {fname}: todos los valores son 0. Ignorado.")
                    continue
                profiles.append([v / maximo for v in values])
                names.append(os.path.splitext(fname)[0])
            except Exception as e:
                print(f"  [AVISO] No se pudo leer {fname}: {e}. Ignorado.")

    # Si no se encontró ningún perfil válido → usar fallback
    if not profiles:
        print("  [INFO] No hay curvas en ev_profiles/ — usando curva de fallback interna.")
        profiles.append(list(_FALLBACK_CURVE))
        names.append(_FALLBACK_NAME)

    return profiles, names


def sample_ev_profile(profiles, names):
    """
    Sortea aleatoriamente uno de los perfiles de carga disponibles.
    Llamar una vez por unidad EV/CS por iteración.

    Retorna
    -------
    profile : list de 24 floats normalizados (0..1, max=1)
    name    : str — nombre del perfil sorteado (para registro)
    """
    idx = np.random.randint(0, len(profiles))
    return list(profiles[idx]), names[idx]
