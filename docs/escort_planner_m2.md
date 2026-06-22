# EscortPlanner — coordinación de celdas libres en excavación (M2)

> Anexo técnico al soporte de la "Mente Colmena" (`motor/colmena.py`). Resuelve el
> **livelock** de la excavación a alta ocupación (≈95%). Código:
> `motor/escorts.py` + integración en `motor/despachador.py`.

## Problema

A 95% de ocupación la simulación entraba en un ciclo degenerativo (**livelock**,
no deadlock): los robots seguían moviendo cajas pero el trabajo neto era ~0. La
defensa previa de `_fase_excavar` (preferir columnas "neutrales" al descargar)
**no bastaba**: cuando casi no quedan celdas libres, varios robots competían
greedy por las mismas ~30 celdas y, como último recurso, descargaban en columnas
que eran objetivo de otra tarea o escaneaban toda la grilla eligiendo la primera
libre en orden row-major → se re-enterraban cajas y ninguna columna bajaba.

**Reproducción (baseline, `data/config_95.json`, seed 42, prioridad_posicion):**

| Métrica | Baseline (sin fix) | Con EscortPlanner |
|---|---|---|
| Pedidos completados | **3 / 24** | **24 / 24** |
| TSP | 12.5 % (congelado desde ~tick 180) | **100 %** |
| MTRP | 678 y subiendo linealmente | **11.7** |
| TBR | 12.3 % | 6.25 % |
| Ticks hasta completar | nunca (>400) | **52** |

## 1. Abstracción matemática

Basado en *Puzzle-Based Storage Systems* (Gue & Kim, 2007): las celdas libres son
**escorts** — un recurso que se *planifica con dueño y destino*, no espacio que
cualquiera toma por cercanía. Resultado clave de esa literatura: bastan 4-5
escorts bien planificados sin importar el tamaño de grilla → al 95% de 600 celdas
hay ~30 libres, **sobran**; el problema es la coordinación, no la cantidad.

- **Asignación conjunta** (escort-flow) por **horizonte rodante**: cada
  `HORIZONTE_REPLANIFICACION = 10` ticks (o antes si hay estancamiento) se asignan
  columnas-escort a las excavaciones activas, ordenadas por `profundidad_inicial`
  ascendente (las más cortas terminan antes y liberan celdas).
- **Progreso neto** por tarea = `profundidad_inicial − cajas_sobre_objetivo`. Si no
  aumenta durante `UMBRAL_ESTANCAMIENTO = 4` ticks → estancamiento → replanificación.
- **Serialización**: si hay más excavaciones que regiones abiertas, algunas tareas
  quedan **sin escort y esperan**. Esto rompe la competencia: un subconjunto
  termina, libera celdas, y las que esperaban retoman. Es el mecanismo central
  anti-livelock (el baseline nunca serializaba: siempre descargaba greedy).
- **Movimiento físico del escort** (un salto de columna por tick):
  - *3 pasos (directo)*: salto a la columna adyacente —no protegida, no reservada
    por otra tarea— que más acerca la caja a su columna-escort.
  - *5 pasos (rodeo)*: si ninguna adyacente sirve, se deposita en la columna-escort
    reservada de la tarea. La caja **nunca** se deposita en una columna-objetivo →
    re-enterrar es imposible.

## 2. Arquitectura de software

- **`motor/escorts.py`** (nuevo): `Escort`, `EscortPlanner`
  (`planificar`, `_mejor_columna`, `_trayectoria_cruza` vía `_camino_l`,
  `mover_escort_un_paso`), `StagnationDetector`, constantes `K`/`T`. Reutiliza
  `distancia_manhattan` de `motor/colmena.py`.
- **`motor/despachador.py`**:
  - `Tarea` extendida con `profundidad_inicial`, `ultimo_progreso_medido`,
    `ticks_sin_progreso`, `escort_asignado` (los campos que el spec llama
    `TareaExcavacion`; **no** se duplica la clase).
  - `__init__`: instancia `escort_planner` / `stagnation_detector` (junto a
    `reservation_table` / `wait_for_graph`).
  - `tick()` Paso 2.9 (antes de avanzar robots): actualiza el detector y
    replanifica por horizonte rodante / estancamiento / tareas sin escort; refresca
    `_cols_protegidas` y `_cols_reservadas`.
  - `_fase_excavar`: reescrito. Sin escort → ESPERAR; con escort → un salto vía
    `mover_escort_un_paso`.
- **Determinismo**: toda iteración es por orden estable (ids / row-major).
  Verificado: dos corridas con la misma semilla producen `sesion_X.csv` y
  `kpis_finales` idénticos (RNF-04).

## 3. Cambio de contrato de eventos hacia M3 (⚠ coordinar con Alex / Samira)

La excavación pasa de **1 evento instantáneo** a **N eventos** consecutivos (uno
por salto de columna). **Se mantiene el vocabulario existente** — `tipo:
"excavacion"` con `de` / `a` por salto — de modo que el parser de M3 no cambia;
solo se reciben más eventos `excavacion` por caja, y la animación muestra la caja
**deslizándose columna a columna** en vez de saltar instantáneamente. Se agrega un
evento nuevo `tipo: "espera_escort"` (robot en cola por serialización) que M3
puede ignorar o usar para indicar "esperando".

## 4. Calibración y límites

- `HORIZONTE_REPLANIFICACION` (K) y `UMBRAL_ESTANCAMIENTO` (T) son **constantes
  configurables** en `motor/escorts.py`, calibradas contra el escenario 95%
  (K=10, T=4). Recalibrar contra datos reales de Forus antes de producción.
- Es una **heurística**, no óptimo garantizado: el problema combinado (escorts +
  ruteo + colisiones) generaliza problemas NP-difíciles (BRP / MAPF). El objetivo
  es **eliminar el ciclo degenerativo**, cumplido.
- No introduce dependencias de GPU ni Kit SDK: toda la lógica vive en M2 puro y es
  testeable sin Omniverse (`tests/test_motor_escorts.py`).

## 5. Verificación

- `pytest tests/` → **96 passed** (88 previos + 8 nuevos en
  `tests/test_motor_escorts.py`), sin regresiones.
- Demos P09 intactos: FIFO-75% (30/30) y Prioridad-90% (30/30) completan normal.
- Escenario 95% (`data/config_95.json`): de **3/24 → 24/24** pedidos, TSP
  12.5 % → 100 %, MTRP 678 → 11.7.
