# RITQ1310 — Contexto de la red y plan de simulación

Alimentador real de media tensión de la subestación ITQ, usado para el paper DC (IEEE PES GT&D LatAm 2027).
Este documento reúne lo que se sabe de la red, la configuración de partida y el orden de las corridas.

Fecha: 2026-10-27. Estado: `config.py` preparado para la **Etapa A, caso A1** (sin multiplicador de carga, PV + DC inference 25 %). Todavía no se corrió ninguna campaña.

---

## 1. La red

| Dato | Valor |
|---|---|
| Carpeta | `data/networks/ITQ_D/RITQ1310/` (dentro de la subestación ITQ, no directamente en `networks/`) |
| Master usado | `DU_1_Master_391_ITQ_RITQ1310.dss` (día útil, mes 1). Hay también `DO` (domingo) y los meses 6, 7 y 12 |
| Tensión | 13.8 kV; las 866 barras MT trifásicas están en 13.8 kV (7.967 kV fase-neutro) |
| Cabecera | `busA` (fuente, 1.0 pu) → regulador `REG_busA` de 60 MVA, `vreg = 102` (1.02 pu), banda 2 → `MT8563902ID` |
| Transformador de la subestación | 60 MVA, 88/13.8 kV, compartido con los otros 15 alimentadores de ITQ (`DU_1_Master_substation_391_ITQ.dss`) |
| Cargas | 8 830 BT + 48 MT, curvas típicas `RES-TIPOx_DU`, `MT-TIPOx_DU` |
| Capacitores | 3 bancos (600 + 600 + 1200 kvar) con control por tensión |
| Generación existente | 4 PV BT de menos de 1 kW cada uno (`GeradoresBT`, activo en el master). Despreciable |
| Líneas | Tienen `normamps`, así que se puede calcular la carga térmica |

### 1.1 Caso base (sin DER)

| | `LOAD_MULT = 1.0` | `LOAD_MULT = 1.40` |
|---|---|---|
| Energía diaria (E_base) | 101.8 MWh/día | 141.6 MWh/día |
| Pico | 5.52 MW a las 19 h (6.11 MVA) | 7.65 MW a las 19 h (8.52 MVA) |
| Mínima | 3.27 MW a las 5 h | — |
| Tensión mín. / máx. en MT | 0.977 / 1.017 pu | 0.961 / 1.017 pu |
| Pérdidas | 2.05 % | 2.39 % |
| Línea más cargada | 70 % de `normamps` | 97.9 % |

`CONTROL_MODE` `off` y `static` dan el mismo caso base.

### 1.2 Por qué 1.40

Barrido del multiplicador sobre el caso base:

| Multiplicador | E_base (MWh/día) | Pico (MW) | Vmin (pu) | Línea más cargada | Líneas sobrecargadas |
|---|---|---|---|---|---|
| 1.00 | 101.8 | 5.52 | 0.977 | 70 % | 0 |
| 1.30 | 131.7 | 7.12 | 0.965 | 91 % | 0 |
| 1.40 | 141.6 | 7.65 | 0.961 | 97.9 % | 0 |
| 1.45 | 146.5 | 7.91 | 0.959 | 101.4 % | 2 |
| 1.50 | 151.5 | 8.18 | 0.957 | 104.8 % | 2 |
| 2.00 | 200.5 | 10.76 | 0.936 | 139 % | 90 |

**Criterio:** el mayor valor, en pasos de 0.05, con el que el caso base cumple a la vez la tensión (0.95–1.05 pu) y la capacidad de las líneas (≤ 100 % de `normamps`). El límite lo pone la capacidad térmica, no la tensión.

### 1.3 Cómo se aplica el multiplicador

- `LOAD_MULT` ejecuta `set loadmult` de OpenDSS en el caso base y en cada iteración (`core/network.py`).
- Las cargas que agrega el framework (DC y estaciones EV) se escriben con `status=exempt`: OpenDSS no les aplica `loadmult` pero sí su curva diaria. Esto está verificado.
- El multiplicador **sube E_base**, y por eso también el tamaño del PV y del DC, que se dimensionan como fracción de E_base. Por ejemplo, el DC al 50 % pasa de 3.35 a 4.5 MW.
- Si `LOAD_MULT ≠ 1.0`, el CSV de resultados lleva el sufijo `_LM140`. Así las etapas A y B no se pisan.

---

## 2. Pruebas exploratorias (orientativas)

Se hicieron con 3 a 6 iteraciones por nivel y con el **catálogo PV anterior** (1.2–3.2 MW). Solo sirven para ubicar los rangos; no son resultados.

**Etapa A (`LOAD_MULT = 1.0`)**

| PV | PV instalado | Vmax | Barras con sobretensión |
|---|---|---|---|
| 100 % | 20 MW | 1.024 | 0 |
| 150 % | 27–34 MW | 1.045–1.049 | 0 |
| 200 % | 37–63 MW | 1.054–1.069 | 156–555 |
| 300 % | 53–63 MW | 1.07–1.08 | 556–629 |

- El DC inference al 50 % (3.35 MW), sin PV, baja la tensión mínima a 0.959 pu, **sin violaciones**. Las pérdidas pasan de 2.1 a 3.8 MWh/día.
- En esta etapa, el efecto del DC sobre el HC se ve como un **corrimiento de la curva de sobretensión**, no como subtensión.

**Etapa B (`LOAD_MULT = 1.40`)**

| Caso | Primer nivel PV con sobretensión | Probabilidad de subtensión |
|---|---|---|
| C0 | 125 % | 0 |
| DC 25 % inference (2.3 MW) | 150 % | 0.17–0.83 |
| DC 50 % inference (4.5 MW) | 200 % | 0.67–1.0 |
| DC 50 % training (3.6 MW) | 150 % | 0.67–1.0 |

En esta etapa aparecen los dos efectos: subtensión por el DC desde el 25 %, y sobretensión por el PV entre 125 y 200 %.

**Tiempo:** 12 s por iteración en serie; 1.3–1.5 s con 14–16 workers.

---

## 3. Configuración de partida (Etapa A, ya cargada en `config.py`)

| Parámetro | Valor | Motivo |
|---|---|---|
| `NETWORK_NAME` | `"ITQ_D/RITQ1310"` | El CSV usa solo `RITQ1310` en el nombre |
| `NETWORK_FILE` | `"DU_1_Master_391_ITQ_RITQ1310.dss"` | Mismo criterio que RBRR1303 |
| `TRANSFORMER_MVA` | 60.0 | Trafo de la subestación. `Trafo_Loading_pct` queda en ~10 % y **no restringe** (ver §5) |
| `EXCLUDED_BUSES` | `["busA", "MT8563902ID"]` | Fuente y salida del regulador (cabecera eléctrica) |
| `LOAD_MULT` | **1.0** | Etapa A |
| `CONTROL_MODE` | `"off"` | Igual a `static` en el caso base, y más rápido |
| `ONLY_THREE_PHASE` / `ENABLE_ONLY_MT` | `True` / `True` | Sin cambios |
| `ENABLE_PV` / `ENABLE_DC` | `True` / `True` | BESS y EV apagados |
| `DC_MODEL` | `"gtd2027"` | |
| `DC_ARCHETYPE` | `"inference"` | Curva de Zhang (IET), `data/dc_profiles/archetypes/inference.csv` |
| `DC_ENERGY_SHARE` | 0.25 | Caso A1; cambiar según §4 |
| `PENETRATION_LEVELS_PV` | 0 a 240, en pasos de 20 (13 niveles) | La sobretensión empieza entre 150 y 200 %; 240 cierra la curva con DC |
| `NUM_ITERATIONS` | 1000 | ~4–5 h por caso con 16 workers. Subir si la convergencia lo pide |
| `RANDOM_SEED` | 1 | Las mismas semillas en todos los casos: la comparación entre casos es pareada |
| `ENABLE_PARALLEL` / `NUM_WORKERS` | `True` / `None` (16) | |

### 3.1 Catálogo PV

| Tamaño (kW) | 250 | 500 | 1000 | 1500 | 2000 | 3000 |
|---|---|---|---|---|---|---|
| Probabilidad | 0.15 | 0.25 | 0.25 | 0.15 | 0.12 | 0.08 |

- **Rango de 250 kW a 3 MW**: es generación conectada en MT (minigeração), y 3 MW es el tope para solar no despachable según la Lei 14.300/2022.
- **Ordenado de menor a mayor**, con las unidades chicas más frecuentes, como ocurre en la práctica.
- **Media de 1.12 MW**, frente a 1.9 MW del catálogo anterior. `allocate_pv` deja de sortear en cuanto una unidad se pasa del objetivo, así que el PV instalado queda siempre un poco por debajo de la meta. Con unidades chicas, ese faltante es menor: al 20 % de PV (~4 MW en esta red) ya entran unas 3–4 unidades, en lugar de 1–2.
- El catálogo de RBRR1303 quedó como comentario en `config.py`.

---

## 4. Plan de campañas

Primero se trabaja solo con **inference**; training y la comparación entre ambos vienen después. Todas las corridas usan las mismas semillas y los mismos niveles PV.

### Etapa A — sin multiplicador (`LOAD_MULT = 1.0`)

| Caso | `ENABLE_DC` | `DC_ENERGY_SHARE` | `DC_ARCHETYPE` | CSV de resultados | Estado |
|---|---|---|---|---|---|
| **A0** — C0 | `False` | — | — | `results_RITQ1310_PV240_BESS0_EV0_DC0.csv` | pendiente |
| **A1** — C1-inf | `True` | 0.25 | `"inference"` | `..._DC25inference.csv` | **config listo** |
| **A2** — C2-inf | `True` | 0.50 | `"inference"` | `..._DC50inference.csv` | pendiente |
| A3 — C1-tra | `True` | 0.25 | `"training"` | `..._DC25training.csv` | después |
| A4 — C2-tra | `True` | 0.50 | `"training"` | `..._DC50training.csv` | después |

### Etapa B — con multiplicador (`LOAD_MULT = 1.40`)

Son los mismos casos, B0 a B4. Los CSV llevan el sufijo `_LM140`, por ejemplo `results_RITQ1310_PV240_BESS0_EV0_DC25inference_LM140.csv`. **Antes** de empezar la Etapa B conviene revisar el rango de niveles PV: con 1.40, la sobretensión de C0 aparece ya en 125 %.

### Orden recomendado

1. A0 → A1 → A2 (inference).
2. Analizar: curvas Pr(V) por nivel, ΔHC frente a C0, y perfiles horarios.
3. B0 → B1 → B2 (inference), y el mismo análisis.
4. Training: A3, A4, B3, B4.
5. Comparación entre inference y training, en cada etapa.

### Pasos para cada corrida

1. Ajustar en `config.py` los tres parámetros de la tabla (y `LOAD_MULT` en la Etapa B).
2. `python main.py`.
3. **Mover `results/hourly/` a `results/hourly_<caso>/`** antes de la siguiente corrida. Si no se mueve, la corrida siguiente lo sobrescribe (ver §5).

---

## 5. Advertencias y pendientes

| Tema | Impacto | Cuándo se resuelve |
|---|---|---|
| **Sin indicador de sobrecarga de líneas** en el CSV | Con 1.40 la red ya opera al 97.9 % de su capacidad térmica. El HC por tensión sobreestima el HC real, sobre todo con PV alto | Fase 1.5 (las líneas tienen `normamps`) |
| `Trafo_Loading_pct` con 60 MVA | Queda en ~10–15 % y no restringe nada. Es informativo | Definir una potencia de referencia del alimentador si se quiere usar |
| `results/hourly/` es la misma carpeta para todos los casos | La corrida siguiente sobrescribe los perfiles horarios | Mover a mano (§4). En la Fase 1.5, una carpeta por caso |
| PV instalado variable para un mismo nivel | Depende del mes sorteado (PSH) y del catálogo discreto | Fase 2 (PSH) |
| La carga es siempre la de un día útil de enero (`DU_1`) | El mes que sortea el PV y el DC no cambia la curva de carga | Documentarlo como supuesto; opcionalmente comparar con `DO` y otros meses |
| Las referencias de regresión en `results/regression/` usan el catálogo PV anterior | Para repetir la regresión hay que pasar `PV_SIZES_KW` y `PV_PROBS` antiguos | — |
| `NUM_ITERATIONS = 1000` | La convergencia todavía no está verificada | Fase 1.5 (convergencia) |
