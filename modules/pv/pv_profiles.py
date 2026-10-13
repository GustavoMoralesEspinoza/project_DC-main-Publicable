# project/modules/pv/pv_profiles.py
"""
Lee el archivo Geracao_Solar.csv y retorna matrices de irradiancia
y temperatura con forma (12 meses, 24 horas).
"""

import numpy as np
import pandas as pd


def load_irradiance_matrices(csv_file):
    """
    Lee el CSV de irradiancia/temperatura y retorna dos matrices numpy.

    El CSV debe tener columnas: Mes (1-12), Hora (0-23), Gt(i)_mean, T2m_mean

    Retorna
    -------
    irradiance_matrix  : np.ndarray shape (12, 24) — W/m²
    temperature_matrix : np.ndarray shape (12, 24) — °C
    """
    df = pd.read_csv(csv_file)

    irr_mean  = df.groupby(["Mes", "Hora"])["Gt(i)_mean"].mean().reset_index()
    temp_mean = df.groupby(["Mes", "Hora"])["T2m_mean"].mean().reset_index()

    irradiance_matrix  = np.zeros((12, 24))
    temperature_matrix = np.zeros((12, 24))

    for month in range(1, 13):
        for hour in range(24):
            irr_val = irr_mean[
                (irr_mean["Mes"] == month) & (irr_mean["Hora"] == hour)
            ]["Gt(i)_mean"].values
            temp_val = temp_mean[
                (temp_mean["Mes"] == month) & (temp_mean["Hora"] == hour)
            ]["T2m_mean"].values

            if irr_val.size > 0:
                irradiance_matrix[month - 1, hour] = irr_val[0]
            if temp_val.size > 0:
                temperature_matrix[month - 1, hour] = temp_val[0]

    return irradiance_matrix, temperature_matrix


def sample_monthly_profile(irradiance_matrix, temperature_matrix):
    """
    Sortea un mes aleatorio (0-11) y retorna el perfil de ese mes.

    Retorna
    -------
    irrad_pu : list de 24 floats — irradiancia normalizada (0..1), max=1 cuando irrad=1000 W/m²
    temp_c   : list de 24 floats — temperatura en °C
    psh      : float — peak sun hours del perfil sorteado
    mes      : int   — mes sorteado (1-12, para registro)
    """
    idx       = np.random.randint(0, 12)
    irrad_wm2 = irradiance_matrix[idx]
    temp_c    = list(temperature_matrix[idx])

    irrad_pu = [v / 1000.0 for v in irrad_wm2]
    psh      = float(np.sum(irrad_pu))

    if psh <= 0:
        raise ValueError(
            f"El perfil de irradiancia del mes {idx + 1} tiene PSH=0. "
            "Revise el archivo Geracao_Solar.csv."
        )

    return irrad_pu, temp_c, psh, idx + 1
