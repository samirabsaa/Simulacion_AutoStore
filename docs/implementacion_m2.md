# Implementación del Motor de Simulación (M2)

> **Audiencia:** equipo Grupo 12, profesor evaluador.
> **Estado:** implementación completa en rama `test-integracion-m2-bus`.
> **Tests:** 18/18 pasan (`pytest tests/`).

---

## 1. Visión general — ciclo de tick

M2 es el **único escritor del Bus de Estado**. Su ciclo de vida completo:

```
M1 llama bus.set_config() + bus.set_pedidos_cola()
              │
              ▼
  simulador.inicializar_desde_bus(seed)
    ├─ lee Config del bus
    ├─ construye Grilla 3D y la puebla aleatoriamente
    ├─ posiciona robots en puertos del borde
    └─ emite TickDelta inicial (grilla + robots)
              │
              ▼
  ┌─── while not simulador.ha_terminado() ─────────────────┐
  │                                                         │
  │   simulador.avanzar_tick()                              │
  │     1. lee snap.politica del bus                        │
  │     2. procesar_turno (diurno o nocturno)               │
  │     3. _resolver_colisiones()   ← conteo TBR            │
  │     4. _actualizar_kpis()       ← KPISet por tick       │
  │     5. bus.write_tick_delta()   ← único punto escritura │
  │                                                         │
  └─────────────────────────────────────────────────────────┘
              │
              ▼
  ha_terminado() → cola vacía AND todos los robots INACTIVO
```

Cada módulo opera sobre estructuras de datos Python puras. No hay GPU ni
Omniverse en M2 — eso es M3, que solo lee el bus.

---

## 2. `motor/grilla.py` — Grilla 3D

### Estructura interna

```python
_celdas: dict[tuple[int, int, int], Caja]
```

Una caja por celda `(x, y, z)`. Acceso O(1) en todas las operaciones clave.
No hay listas por columna: la vista de columna se construye bajo demanda.

### Operaciones principales

| Método | Complejidad | Descripción |
|--------|-------------|-------------|
| `agregar(caja)` | O(1) | Coloca la caja en su celda `(x,y,z)` |
| `remover(x,y,z)` | O(1) | Vacía la celda, retorna la caja |
| `get(x,y,z)` | O(1) | Retorna la caja o None |
| `ocupada(x,y,z)` | O(1) | Bool de ocupación |
| `columna(x,y)` | O(z) | Cajas de la columna ordenadas por z asc |
| `celdas_libres_en_columna(x,y)` | O(z) | Niveles z disponibles |
| `buscar_por_sku(id_sku)` | O(n) | Todas las cajas del SKU dado, por z asc |
| `primera_caja_accesible(id_sku)` | O(n·z) | Caja con mínimo costo de excavación |

### Puertos (T-11)

Los puertos son todas las celdas del **borde perimetral del plano XY**:
fila 0, fila `y-1`, columna 0, columna `x-1`. Se calculan una vez en `__init__`.

`puerto_mas_cercano(x, y)` aplica distancia Manhattan a la lista de puertos.

### Inicialización aleatoria

`inicializar_aleatoria(seed)` puebla la grilla hasta `config.ocupacion_inicial`
(porcentaje de celdas ocupadas). Los SKUs son sintéticos (`SKU001`…`SKU010`),
suficientes para probar las políticas de picking.

### Delta para el Bus

Los buffers `_delta` y `_remove` acumulan cambios desde el último `flush_delta()`.
El simulador llama `flush_delta()` una vez por tick, justo antes de `write_tick_delta`.

```python
grilla_delta, grilla_remove = self._grilla.flush_delta()
# grilla_delta  → list[Caja]              (celdas agregadas/modificadas)
# grilla_remove → list[tuple[int,int,int]] (celdas vaciadas)
```

---

## 3. `motor/politicas.py` — Políticas de picking (T-13, T-14)

### Patrón Selector

Cada política es una **función pura** con la misma firma:

```python
Selector = Callable[[list[Pedido], Grilla, list[tuple[int,int]]], Pedido | None]
```

El despachador recibe la función directamente — no usa if/elif para distinguir modos:

```python
politica_fn = POLITICAS[snap.politica]   # PoliticaPicking → función
pedido = politica_fn(pedidos, grilla, puertos)
```

El cambio de política lo activa M1 (`bus.set_policy()`). M2 solo lee `snap.politica`
al inicio de cada tick. El cambio es efectivo en el siguiente tick sin reiniciar.

### FIFO (`PoliticaPicking.FIFO`)

Devuelve el **primer pedido de la cola** para el que existe al menos una caja del
SKU requerido en la grilla. Si ningún pedido tiene caja disponible, retorna None.

### Prioridad por posición (`PoliticaPicking.PRIORIDAD_POSICION`)

Para cada pedido con caja disponible, calcula:

```
costo = |caja.x − puerto_más_cercano.x| + |caja.y − puerto_más_cercano.y|
```

Retorna el pedido con **menor costo Manhattan**. En caso de empate, gana el que
tenga menor z (menos excavación).

---

## 4. `motor/despachador.py` — Máquina de estados por robot (T-12, T-15, T-16, T-17)

### Diagrama de fases

```
  INACTIVO
     │ (politica_fn asigna pedido + ruta)
     ▼
 mover_a_objetivo  ──(llegó a columna)──▶  excavar
     │ (paso XY)                               │ (caja encima → adyacente)
     │ (si bloqueado: BLOQUEADO 1 tick)        │ (si sin cajas encima)
                                               ▼
                                           recuperar
                                               │ (remueve caja, set carga_id)
                                               ▼
                                        mover_a_puerto
                                               │ (paso XY)
                                               │ (si bloqueado: BLOQUEADO 1 tick)
                                               ▼
                                           entregar
                                               │ (1 tick, carga_id = None)
                                               ▼
                                           INACTIVO
                                   (pedido marcado como completado)
```

### Asignación de tareas (T-12)

Al inicio de cada tick, el despachador filtra robots INACTIVOS sin tarea activa
y les asigna un pedido usando `politica_fn`. Solo se asignan pedidos que no
estén ya comprometidos con otro robot.

La **ruta L-shaped** se genera en `_ruta_xy(origen, destino)`: mueve X primero,
luego Y. Esto produce rutas deterministas y predecibles.

### Acceso por ganchos (T-15)

`primera_caja_accesible(id_sku)` selecciona la caja de ese SKU con **mínimo número
de cajas encima** (no necesariamente z=0). El robot puede acceder a cualquier nivel
de la columna; simplemente debe excavar las cajas superiores primero.

### Excavación (T-16)

En fase `excavar`, cada tick:
1. Busca la **caja más alta** en la columna sobre el nivel objetivo.
2. Encuentra la primera **columna adyacente** (hasta 4 vecinas ortogonales) con celda libre.
3. Mueve la caja ahí: `grilla.remover()` + `grilla.agregar()`.
4. Acumula 1 en `total_desplazamientos`.

Si todas las columnas adyacentes están llenas, el robot espera en estado EXCAVANDO.

### Cesión de paso (T-17)

Antes de cada paso XY, el despachador verifica si la celda destino está ocupada
por otro robot mediante `_celda_ocupada(xy, robot_id, posiciones_actuales)`.

Si está ocupada: el robot pasa a **BLOQUEADO** ese tick y el simulador acumula
`ticks_bloqueados += 1` para el cálculo de TBR.

### Acumuladores actualizados por el despachador

| Campo | Cuándo se incrementa |
|-------|---------------------|
| `total_desplazamientos` | Cada paso XY + cada excavación |
| `cajas_recuperadas` | Al completar fase `recuperar` |
| `pedidos_completados` | Al completar fase `entregar` |
| `suma_tiempos_ciclo` | Al completar `entregar` (tick_actual − tick_inicio) |
| `ticks_bloqueados` | Al quedar BLOQUEADO por cesión de paso |

---

## 5. `motor/kpis.py` — Los 7 KPIs (T-20)

### `Acumuladores`

Dataclass mutable que el simulador mantiene durante toda la sesión y pasa a
`calcular_kpis()` cada tick. Se resetea parcialmente al cambiar de modo
(`ticks_turno_actual = 0`).

### Fórmulas

| KPI | Nombre | Fórmula | Meta |
|-----|--------|---------|------|
| TSP | Tasa Satisfacción Pedidos | `pedidos_completados / pedidos_demandados × 100` | ≥ 95% |
| TPCP | Tiempo Ciclo por Pedido | `suma_tiempos_ciclo / pedidos_completados` | Minimizar |
| MTRP | Movimientos Robot/Pedido | `total_desplazamientos / pedidos_completados` | Minimizar |
| IOG | Índice Ocupación Grilla | `cajas_presentes / capacidad_total × 100` | 60–90% |
| TR | Throughput Recuperación | `cajas_recuperadas / ticks_turno_actual` | Maximizar |
| TI | Throughput Ingreso | `cajas_ingresadas / ticks_ingreso` | Maximizar |
| TBR | Tiempo Bloqueo Robots | `ticks_bloqueados / ticks_totales × 100` | ≤ 10% |

Todos los denominadores están protegidos contra división por cero: retornan `0.0`
si no hay datos (inicio de sesión).

`IOG` se obtiene directamente de `grilla.iog()` → `len(_celdas) / capacidad_total × 100`.

---

## 6. `motor/modos.py` — Turno diurno y nocturno (T-18, T-19)

### Turno diurno

`procesar_diurno()` delega completamente en `Despachador.tick()`. Es una función
pass-through que mantiene la firma uniforme entre modos.

### Turno nocturno (T-19)

Lógica de reposición simple (el AutoStore real es opaco — no se replica):

```
Por cada robot INACTIVO:
  1. Tomar la próxima caja de cola_reposicion
  2. _primera_celda_libre(): recorre columnas de menor z buscando celda vacía
  3. grilla.agregar(caja en celda libre)
  4. Robot pasa a estado REPONIENDO
  5. Acumula cajas_ingresadas + ticks_ingreso
```

`_primera_celda_libre()` prioriza z=0 para mantener densidad baja en niveles altos
(facilita acceso futuro en turno diurno).

---

## 7. `motor/simulador.py` — Orquestador (T-22, T-23)

### `inicializar_desde_bus(seed)`

1. Lee `Config` del bus (lanzada por M1 antes de iniciar).
2. **T-23**: emite `RuntimeWarning` si la grilla supera 20×20×5 celdas o hay más
   de 10 robots (no aborta, solo avisa sobre posible degradación de rendimiento).
3. Construye `Grilla` y la puebla con `inicializar_aleatoria(seed)`.
4. Posiciona robots en puertos del borde (distribución round-robin).
5. Lee `pedidos_cola` que M1 cargó en el bus.
6. Instancia `Despachador(grilla)`.
7. Emite el TickDelta inicial (grilla completa + robots).

### `avanzar_tick()`

```python
snap = bus.read_snapshot()          # leer política activa (la fija M1)
ticks_totales += 1
ticks_turno_actual += 1

if modo == DIURNO:
    _procesar_turno_diurno(snap.politica)
else:
    _procesar_turno_nocturno()

_resolver_colisiones()              # consolida TBR de robots BLOQUEADO
_actualizar_kpis()                  # calcular_kpis() → KPISet
delta = _construir_delta()          # vacía buffers y empaqueta TickDelta
bus.write_tick_delta(M2_WRITER_ID, delta)   # único punto de escritura
```

### `ha_terminado()`

```python
return len(pedidos_cola) == 0 and all(r.estado == INACTIVO for r in robots.values())
```

### Modo degradado (T-22)

Si `Despachador` no está disponible, `_procesar_turno_diurno()` lanza
`NotImplementedError` con mensaje claro. El bus y M3 siguen funcionando
porque solo leen snapshots — la falla de M2 no los arrastra.

---

## 8. Tests

### `tests/test_contrato_m2_bus.py` (5 tests)

| Test | Qué valida |
|------|-----------|
| `test_instanciacion_simulador` | El simulador se instancia sin errores |
| `test_construir_delta_empaqueta_solo_lo_que_cambio` | El TickDelta solo incluye campos no nulos |
| `test_bus_acepta_y_refleja_el_delta_de_m2` | El bus aplica el delta y `read_snapshot()` lo refleja |
| `test_robots_delta_mergea_por_id_no_reemplaza_la_lista` | Regresión: merge por `robot.id`, no reemplazo de lista completa |
| `test_solo_m2_puede_escribir` | `WriterNotAuthorizedError` si otro módulo intenta escribir |

### `tests/test_despachador_kpis.py` (13 tests)

| Grupo | Tests |
|-------|-------|
| Rutas XY | `test_ruta_xy_misma_posicion`, `test_ruta_xy_solo_x`, `test_ruta_xy_l_shape` |
| Despachador | `test_despachador_completa_pedido_simple`, `test_despachador_excavacion`, `test_despachador_colision_bloqueo`, `test_despachador_sin_caja_disponible_no_asigna` |
| KPIs | `test_kpis_estado_inicial`, `test_kpis_tsp`, `test_kpis_iog_con_cajas`, `test_kpis_tbr`, `test_kpis_mtrp` |
| Integración | `test_integracion_simulador_turno_diurno` (bus real + simulador completo) |

---

## 9. Fuera del alcance de M2

Según el contrato del proyecto (ver `CLAUDE.md` raíz):

- **Clasificador / sorter** hacia andenes de carga.
- **Inyección de algoritmos externos** de optimización.
- **Comunicación en tiempo real** con el AutoStore físico.
- **Turno nocturno inteligente** de reordenamiento (la lógica real del AutoStore es opaca).
- **Más de 2 políticas** de picking en esta versión.
