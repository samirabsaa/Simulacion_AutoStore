# Actualización M2 — 5 mejoras del motor para el modelo 3D (M3)

**Audiencia:** desarrolladores de M2 (motor), M3 (Omniverse) y Bus/Persistencia que
necesitan entender qué cambió en el motor y cómo consumirlo.

**Base de lectura previa:** este documento asume la `docs/evaluacion_tecnica_m2.md`
(arquitectura y máquina de estados de M2) y adapta el diseño de
`docs/spec_handoff_mente_colmena.md` (Mente Colmena/handoff) a las clases reales.

**Estado:** implementado y probado. Suite completa: **119 tests** (103 previos +
16 nuevos en `tests/test_motor_m3_actualizaciones.py`).

**Commits relevantes:**
- `bus: extender contrato para M3 (orientación, estaciones, anillo)` — cambios al
  contrato compartido del bus (ver §7).
- `motor: implementar 5 actualizaciones M3 (...)` — toda la lógica del motor.

---

## 0. Principio de diseño: aditivo y configurable

Las 5 features son **aditivas y opt-in vía `config.json`**. Con la config previa
(sin campos nuevos) el motor se comporta exactamente como antes — por eso los 103
tests originales siguen pasando sin tocarse. Las features se activan declarando:

```json
{
  "grilla": { "x": 7, "y": 7, "z": 3 },
  "robots": 4,
  "ocupacion_inicial": 70,
  "anillo_transito": true,
  "estaciones": [
    { "id": "CINTA1", "x": 0, "y": 3, "tipo": "cinta",    "orientacion": "O" },
    { "id": "CARR1",  "x": 6, "y": 3, "tipo": "carrusel", "orientacion": "E" }
  ]
}
```

- Sin `estaciones` → entrega clásica en el puerto más cercano (instantánea, sin
  capacidad ni orientación). Features 2/3/4 quedan inertes.
- Sin `anillo_transito` (o `false`) → la grilla almacena en todo el plano como antes.

---

## 1. Resumen de cambios por archivo

| Archivo | Acción | Qué cambió |
|---|---|---|
| `bus_persistencia/models/state.py` | **modificado** (contrato) | + enum `Orientacion`, + enum `TipoEstacion`, + dataclass `Estacion`; `Robot` gana `orientacion`; `RobotEstado` gana `ROTANDO/NECESITA_HANDOFF/EN_TRANSITO_ANILLO`; `Config` gana `anillo_transito` y `estaciones` |
| `bus_persistencia/persistence/config_loader.py` | modificado | parsea `estaciones` y `anillo_transito` (`_parse_estaciones`) |
| `api/serializers.py` | modificado | mapea nuevos `RobotEstado` a M1; expone `orientacion.value` |
| `motor/colmena.py` | **creado** | `ReservationTable`, `WaitForGraph`, `orientacion_hacia`, constantes |
| `motor/grilla.py` | modificado | anillo perimetral de tránsito |
| `motor/despachador.py` | modificado | estaciones, orientación, handoff (Mente Colmena) |
| `motor/simulador.py` | modificado | condición de término por ola |
| `tests/test_motor_m3_actualizaciones.py` | **creado** | 16 tests de las 5 features |

> **Nada se eliminó.** Todos los cambios preservan las firmas públicas existentes
> (`Despachador.tick(...)`, `Grilla.agregar/iog/...`, `AutoStoreSimulator.avanzar_tick/
> ha_terminado`). Lo único con semántica nueva es `Grilla.iog()` (denominador ahora
> excluye el anillo) y `Grilla.agregar()` (lanza `ValueError` si la celda es tránsito).

---

## 2. Feature 1 — Grilla extendida (anillo perimetral de tránsito)

**Qué se pidió:** un anillo perimetral de columnas exclusivas para el tránsito de
robots, donde no se pueden almacenar cajas.

**Abstracción.** La grilla sigue siendo un `dict[(x,y,z) → Caja]`. El anillo se
modela como un **conjunto de columnas** `_transito: set[(x,y)]` (el borde del plano
XY). Una columna de tránsito no tiene niveles almacenables: es corredor puro. La
zona almacenable es el interior `(1..x-2, 1..y-2)`.

**Clases/funciones (en `motor/grilla.py`):**

| Símbolo | Acción | Descripción |
|---|---|---|
| `Grilla.__init__` | modificado | calcula `self._transito = self._calcular_anillo()` |
| `Grilla._calcular_anillo()` | **nuevo** | devuelve el borde si `config.anillo_transito`; vacío si la grilla es < 3×3 (evita interior nulo) |
| `Grilla.es_transito(x, y)` | **nuevo** | `True` si la columna es del anillo |
| `Grilla.anillo` (property) | **nuevo** | celdas `(x,y)` del anillo ordenadas — lo consume M3 para pintar el corredor |
| `Grilla.capacidad_almacenable` (property) | **nuevo** | `capacidad_total − len(anillo)·z` |
| `Grilla.inicializar_aleatoria` | modificado | solo puebla celdas no-tránsito; recorta `n_cajas` a la capacidad real |
| `Grilla.agregar` | modificado | lanza `ValueError` si `(x,y)` es tránsito |
| `Grilla.celdas_libres_en_columna` | modificado | `[]` para columnas de tránsito |
| `Grilla.iog` | modificado | denominador = `capacidad_almacenable` (mide la zona real) |

**Conexión con M3 (Omniverse):** `Grilla.anillo` y `Grilla.es_transito()` dan a M3 la
geometría para renderizar el corredor perimetral distinto de las celdas de
almacenamiento. Como el anillo nunca recibe cajas, M3 puede tratarlo como una capa
de piso/transporte sin instanciar pilas USD ahí.

---

## 3. Feature 2 — Estaciones de ingreso Cinta / Carrusel

**Qué se pidió:** dos tipos de puerto — Cinta (1 producto/tick) y Carrusel
(2 productos/tick).

**Abstracción.** Una estación es un punto de servicio con **capacidad por tick**
(teoría de colas: el "servidor" admite N llegadas por unidad de tiempo). Se modela
como `Estacion(id, x, y, tipo, orientacion_requerida)` con `capacidad_tick` derivada
del tipo. El despachador lleva un contador `_servidos[estacion_id]` que se **reinicia
cada tick** y se incrementa en cada entrega.

**Clases/funciones:**

| Símbolo | Ubicación | Acción |
|---|---|---|
| `TipoEstacion` (enum CINTA/CARRUSEL) | `state.py` (bus) | **nuevo** |
| `Estacion` (dataclass frozen) + `capacidad_tick` | `state.py` (bus) | **nuevo** |
| `_parse_estaciones()` | `config_loader.py` | **nuevo** |
| `Tarea.estacion` | `despachador.py` | **nuevo campo** |
| `Despachador.estaciones`, `_estaciones_por_pos`, `_servidos`, `usa_estaciones` | `despachador.py` | **nuevo** |
| `Despachador._estacion_mas_cercana(x, y)` | `despachador.py` | **nuevo** |
| `Despachador._crear_tarea` | `despachador.py` | modificado: destino = estación más cercana |
| `Despachador.tick` | `despachador.py` | modificado: `self._servidos = {e.id: 0 ...}` por tick |
| `Despachador._fase_entregar` | `despachador.py` | modificado: si `_servidos[est] >= capacidad_tick` → robot espera (evento `estacion_saturada`, cuenta en TBR) |

**Conexión con M3:** las estaciones llegan a M3 vía `config` (no como estado dinámico
del bus), así que su layout es estático y se renderiza una sola vez. La diferencia
visual Cinta vs. Carrusel es de modelo/animación; el ritmo de despacho ya viene
correcto en el stream de eventos `pedido_completado` (que ahora incluye `"estacion"`).

---

## 4. Feature 3 — Restricción de orientación (N / E / O)

**Qué se pidió:** propiedad de orientación en los robots, restringida a Norte, Este y
Oeste (alineada con los puertos físicos), que afecte el desplazamiento.

**Abstracción.** `Orientacion ∈ {N, E, O}` — el **Sur se excluye a propósito**
(restricción física del puerto). La orientación importa en la **entrega**: el robot
debe encarar `estacion.orientacion_requerida`. Girar cuesta `COSTO_ROTACION_TICKS`
ticks (constante configurable), modelado como un retardo discreto.

**Clases/funciones:**

| Símbolo | Ubicación | Acción |
|---|---|---|
| `Orientacion` (enum N/E/O) | `state.py` (bus) | **nuevo** |
| `Robot.orientacion` (default `NORTE`) | `state.py` (bus) | **nuevo campo** |
| `RobotEstado.ROTANDO` | `state.py` (bus) | **nuevo** |
| `orientacion_hacia(origen, destino)` | `colmena.py` | **nuevo** — devuelve N/E/O, o `None` si exigiría Sur |
| `COSTO_ROTACION_TICKS` | `colmena.py` | **nuevo** (default 1) |
| `Tarea.ticks_rotando` | `despachador.py` | **nuevo campo** |
| `_cambiar_estado(...)` | `despachador.py` | modificado: ahora **preserva/propaga `orientacion`** (antes la reseteaba a default) |
| construcciones de `Robot` en fases de movimiento/swap/yield | `despachador.py` | modificadas: pasan `orientacion=robot.orientacion` |
| `_fase_entregar` | `despachador.py` | modificado: si `robot.orientacion != requerida` → estado `ROTANDO` durante `COSTO_ROTACION_TICKS`, luego fija la orientación y entrega |

**Decisión de diseño (documentada explícitamente):** la orientación se evalúa en el
punto de **entrega**, no en cada paso del ruteo. Mantener el ruteo XY ortogonal sin
tocar (L-shaped) preserva el determinismo y los KPIs previos; la orientación añade
costo solo donde el spec lo exige (alineación con el puerto + costo de rotación +
handoff). El corregir `_cambiar_estado` para propagar `orientacion` fue necesario:
antes cada cambio de estado reseteaba el robot a `NORTE`.

**Conexión con M3:** el evento `rotacion` (`{de, a, estacion}`) le da a M3 los
keyframes exactos para animar el giro del robot antes de depositar.

---

## 5. Feature 4 — Mente Colmena y Handoff

**Qué se pidió:** centro de control central (Mente Colmena) con handoff de carga
entre robots, conectado con las features 1, 2, 3 y 5.

**Mapeo del spec a las clases reales** (según `spec_handoff_mente_colmena.md` §7.1, no
duplicar lo que ya existe):

| Propuesto en el spec | Implementación real |
|---|---|
| `HiveMindOrchestrator` | **se fusiona con `motor.despachador.Despachador`** (ya era el cerebro único por tick; no se crea clase nueva) |
| `Station` | `bus_persistencia.models.state.Estacion` |
| `Orientacion`, `EstadoRobot` | enums en `state.py` (`Orientacion`, `RobotEstado`) |
| `Robot.ticks_esperando_handoff` | `Despachador._espera_handoff: dict[robot_id → int]` (aging fuera del dataclass frozen) |
| `ReservationTable` | `motor.colmena.ReservationTable` (formaliza el `posiciones_actuales` previo) |
| `WaitForGraph` | `motor.colmena.WaitForGraph` |
| `ejecutar_tick` | `Despachador.tick` (reset transitorio + handoff pre-pass + avance + colisiones) |
| `buscar_candidato_handoff` / `evaluar_handoff_tpts` | `Despachador._buscar_candidato_handoff` + criterio TPTS embebido en `_handoff_prepass` |

**Abstracción.** Patrón **Token Passing**: el `Despachador` es el único árbitro por
tick (el "token"). El handoff sigue **PDP-T** (transferencia de carga entre robots)
con criterio de aceptación **TPTS**: solo se acepta si mejora la situación. La
detección de deadlocks usa un **wait-for graph** (ciclos de espera), no solo una
heurística de distancia.

**Clases/funciones nuevas (en `motor/colmena.py`):**

- `ReservationTable` — reservas de celda válidas por tick (`reservar/liberar/
  esta_reservada/hay_conflicto_intercambio`). El `Despachador` la siembra con
  `posiciones_actuales` al inicio del tick.
- `WaitForGraph` — `agregar_espera`, `detectar_ciclo` (DFS de 3 colores, orden
  determinista por id), `romper`/`reset`. Para deadlocks por orientación/handoff.
- `distancia_manhattan`, `orientacion_hacia`, constantes `COSTO_ROTACION_TICKS`,
  `UMBRAL_REDIRECCION_ANILLO`, `RADIO_HANDOFF`.

**Handoff (en `Despachador._handoff_prepass`, `_buscar_candidato_handoff`):**
un robot **cargado y mal orientado, parado en su estación**, cede la carga a un
vecino (radio `RADIO_HANDOFF`) **ocioso y ya orientado** a la orientación requerida.
- **Criterio TPTS:** se acepta solo si la distancia del receptor a la estación
  `<= COSTO_ROTACION_TICKS` (entregar vía receptor no cuesta más que rotar el emisor).
- **Aging:** `_espera_handoff` cuenta ticks esperando; los emisores se ordenan por
  aging descendente (id como desempate) para reproducibilidad.
- **Efecto:** la `Tarea` se reasigna al receptor (con `ruta_salida` recalculada), el
  emisor queda `INACTIVO`, y se emite el evento `handoff` `{de_robot, a_robot,
  id_caja, estacion}`.

**Liveness / anti-deadlock.** Como la rotación siempre completa en
`COSTO_ROTACION_TICKS`, la entrega tiene progreso garantizado aunque no haya handoff
— el `WaitForGraph` es la red de seguridad para bloqueos mutuos de celdas entre
robots en espera. La resolución de colisiones previa (cesión de paso y swap de 2
robots, §7 de la evaluación técnica) se mantiene intacta.

**Orden dentro de `tick()`** (relevante para entender el comportamiento): la
asignación de tareas (Paso 1) corre **antes** del handoff pre-pass (Paso 2.4); por eso
un robot ocioso suele recibir tarea propia antes de poder ser receptor — el handoff se
dispara sobre todo cuando ya no quedan pedidos que asignar pero sí robots
correctamente orientados disponibles.

**Conexión con M3:** el evento `handoff` es, para el render, un **reparenting
instantáneo** del asset de la caja entre dos anclas de robot (spec §7.4): no requiere
animar el movimiento de la caja, solo cambiar de "dueño".

---

## 6. Feature 5 — Condición de término por ola completa

**Qué se pidió:** detener la simulación automáticamente al completar el 100% de una
"ola" (lote predefinido de pedidos).

**Abstracción.** Una "ola" es el lote de pedidos cargado al inicializar. Se captura su
tamaño `total_ola` y se compara contra `len(pedidos_completados)`. La verificación se
hace **después** de aplicar las entregas del tick (spec §6), para no cortar un tick
antes de la última entrega.

**Clases/funciones (en `motor/simulador.py`):**

| Símbolo | Acción | Descripción |
|---|---|---|
| `AutoStoreSimulator.total_ola` | **nuevo** | tamaño del lote, fijado en `inicializar_desde_bus` |
| `AutoStoreSimulator._ola_completada_emitida` | **nuevo** | evita emitir el evento más de una vez |
| `AutoStoreSimulator.ola_completa()` | **nuevo** | `total_ola > 0 and len(completados) >= total_ola` |
| `AutoStoreSimulator.ha_terminado()` | modificado | termina si `ola_completa()`; conserva el fallback previo (cola vacía + robots inactivos) para olas con pedidos insatisfacibles |
| `AutoStoreSimulator.avanzar_tick()` | modificado | emite el evento `ola_completada` `{tick, pedidos, total_ola}` una sola vez |

**Por qué contra `total_ola` y no contra la cola:** un pedido cuyo SKU no tenga caja
disponible nunca se completa; medir contra el lote evita que la sesión cuelgue
esperando un pedido insatisfacible (el fallback de `ha_terminado` cierra ese caso).

**Conexión con M3:** el evento `ola_completada` es la señal para que M3 detenga la
animación / muestre el resumen final de la corrida.

---

## 7. Cambios al contrato del Bus (flagged)

Estos cambios tocan `bus_persistencia/models/state.py` — el **contrato compartido**
del que depende todo módulo. Van en un commit aparte (`bus: extender contrato...`):

- `Robot`: nuevo campo `orientacion: Orientacion = Orientacion.NORTE`.
- `RobotEstado`: nuevos miembros `ROTANDO`, `NECESITA_HANDOFF`, `EN_TRANSITO_ANILLO`.
- nuevo enum `Orientacion` (N/E/O) y nuevo enum `TipoEstacion` (CINTA/CARRUSEL).
- nuevo dataclass `Estacion` (frozen) con propiedad `capacidad_tick`.
- `Config`: nuevos campos `anillo_transito: bool = False` y
  `estaciones: tuple[Estacion, ...] = ()`.

**Compatibilidad:** todos los campos nuevos tienen default y `Robot`/`Config` se
construyen siempre por kwargs, así que el código existente no se rompe. El
`api/serializers.py` se actualizó para mapear los nuevos estados a los 5 de M1 y para
exponer `orientacion` como string (`"N"/"E"/"O"`). **Coordinar con Martín (Bus) y con
M1/M3** antes de extender más este contrato.

---

## 8. Nuevos eventos en el stream del bus (para M1/M3)

Todos viajan en `TickDelta.eventos` y los registra el `SessionLogger`:

| Evento | Campos | Origen |
|---|---|---|
| `rotacion` | `robot_id, de, a, estacion` | `_fase_entregar` |
| `estacion_saturada` | `robot_id, estacion, capacidad` | `_fase_entregar` |
| `handoff` | `de_robot, a_robot, id_caja, estacion` | `_handoff_prepass` |
| `pedido_completado` | (existente) + `estacion` | `_fase_entregar` |
| `ola_completada` | `tick, pedidos, total_ola` | `avanzar_tick` |

---

## 9. Cómo probar

```bash
# Tests de las 5 features (16 casos)
./venv/bin/python3 -m pytest tests/test_motor_m3_actualizaciones.py -v

# Suite completa (119 tests)
./venv/bin/python3 -m pytest tests/ bus_persistencia/tests/ -q
```

Para una corrida end-to-end con anillo + estaciones, declarar los campos en un
`config.json` (ver §0) y ejecutar `python -m motor.run --policy prioridad_posicion`.
Verificado: la ola de 6 pedidos sobre grilla 7×7×3 con anillo + 1 Cinta + 1 Carrusel
termina por `ola_completada`, sin cajas en el anillo.
