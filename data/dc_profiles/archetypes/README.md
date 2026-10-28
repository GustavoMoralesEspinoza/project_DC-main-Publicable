# Arquetipos de carga de trabajo DC (modelo gtd2027)

Cada archivo `<nombre>.csv` es un arquetipo. `DC_ARCHETYPE = "<nombre>"` en `config.py` lo selecciona.
Esta carpeta la usa solo el modelo `gtd2027`; el modelo legacy lee los CSV sueltos de `data/dc_profiles/`.

Formato: columnas `Hora` (0 a 23, las 24 presentes, sin repetir) y `Utilizacion`
(utilizacion de TI, u_k(h) en el paper, entre 0 y 1). Los valores se usan tal cual, sin normalizar.

| Archivo | Descripcion | Fuente |
|---|---|---|
| `inference.csv` | Servicio a usuarios: sigue el ciclo diario, pico 1.00 a las 20 h | Zhang et al., IET (mismo perfil que `../IET_Zhang.csv`) |
| `training.csv` | Entrenamiento de modelos: carga casi constante, 0.85 todo el dia | Supuesto del modelo GT&D 2027 (DC_03) |
