# Handoff M2 → M3: resolución de bloqueo persistente de robots

> **Rama:** `fix-integracion-m1-review`
> **Commit:** `motor: resolver bloqueo persistente de robots (...)`
> **Tests:** 119/119 en verde (`./venv/bin/python3 -m pytest tests/ bus_persistencia/tests/ -q`)

---

## 1. TL;DR

Se corrigió un bug donde un robot quedaba **bloqueado indefinidamente** al intentar
acceder a una columna ocupada por otro robot activo. El fix combina 3 mecanismos:

| Mecanismo | Qué hace |
|---|---|
| **Exclusión de columnas** | Al asignar tarea, evita columnas donde otro robot ya está excavando |
| **Cesión de paso cascada** | Robots INACTIVOS se empujan en cadena (2 niveles) para dejar pasar |
| **BFS reruta + cancelación** | Tras 3 ticks bloqueado, busca ruta alternativa; si no hay, cancela la tarea |

**Impacto en KPIs** (seed 42, FIFO, 4 pedidos):

| KPI | Antes | Después |
|---|---|---|
| TSP | 75% (3/4 pedidos) | **100%** (4/4) |
| TBR | 23.5% | **7.5%** |
| Ticks | 51 (no terminó) | **11** |

---

## 2. Nuevos eventos del bus

M3 lee los eventos desde `TickDelta.eventos` (vía snapshot del bus). Los siguientes
eventos son **nuevos** — no existían antes de este fix:

| Evento | Campos | Cuándo se emite |
|---|---|---|
| `reruta` | `robot_id`, `motivo` (`"bloqueo_persistente"`), `fase` (`"mover_a_objetivo"` o `"mover_a_puerto"`) | Robot recalculó su ruta con BFS después de 3 ticks bloqueado |
| `tarea_cancelada` | `robot_id`, `motivo` (`"bloqueo_persistente_sin_reruta"`), `id_pedido` | Robot canceló su tarea porque el BFS no encontró ruta alternativa viable |

Ejemplo de cómo aparecen en el CSV de sesión:

```json
{"tipo": "reruta", "robot_id": 2, "motivo": "bloqueo_persistente", "fase": "mover_a_objetivo"}
{"tipo": "tarea_cancelada", "robot_id": 3, "motivo": "bloqueo_persistente_sin_reruta", "id_pedido": "P004"}
```

Los eventos existentes (`movimiento`, `bloqueo`, `excavacion`, `caja_recuperada`,
`pedido_completado`) **no cambiaron formato**.

---

## 3. Cambios en comportamiento de robots (lo que M3 ve en el snapshot)

### 3.1 Cesión de paso en cascada

**Antes:** un robot INACTIVO solo se movía si tenía una celda adyacente libre.
**Ahora:** si todas las celdas adyacentes están ocupadas por otros robots INACTIVOS,
el despachador empuja al vecino primero (hasta 2 niveles de profundidad).

**Resultado visual:** en un mismo tick, 2 robots INACTIVOS pueden cambiar de posición
simultáneamente (ambos aparecen como eventos `movimiento` en el mismo tick).

### 3.2 BFS reruta

**Antes:** las rutas eran L-shaped fijas (X primero, Y después). Si el camino estaba
bloqueado, el robot esperaba indefinidamente.
**Ahora:** tras 3 ticks bloqueado (`UMBRAL_RERUTA = 3`), el robot recalcula su ruta
usando BFS que rodea las celdas ocupadas. La nueva ruta puede ser no-lineal.

**Resultado visual:** un robot que estaba yendo en línea recta puede cambiar de
dirección abruptamente (el snapshot muestra una nueva posición que no sigue la ruta
L-shaped original).

### 3.3 Cancelación de tarea

**Antes:** una tarea asignada siempre se completaba (o el robot se quedaba bloqueado
para siempre intentándolo).
**Ahora:** si el BFS no encuentra ruta alternativa, la tarea se cancela durante la
fase `mover_a_objetivo`. El robot vuelve a `INACTIVO` y la caja queda en su lugar.
El pedido vuelve a la cola y puede reasignarse en un tick futuro.

**Importante:** la cancelación **nunca** ocurre en `mover_a_puerto` (el robot ya carga
la caja — cancelar la perdería). En esa fase, el robot simplemente espera.

---

## 4. Qué NO cambió

- La **máquina de estados** del robot es la misma (mismos estados y transiciones).
- El **contrato del bus** (`bus_persistencia/models/state.py`) no se modificó.
- Los **estados de robot** (`INACTIVO`, `DESPLAZANDOSE`, `EXCAVANDO`, `RECUPERANDO`,
  `BLOQUEADO`, `ENTREGANDO`, `ROTANDO`, `NECESITA_HANDOFF`, `EN_TRANSITO_ANILLO`)
  no cambiaron.
- Las **5 features M3** documentadas en `docs/actualizacion_m2.md` (anillo de tránsito,
  estaciones, orientación, mente colmena, término por ola) siguen intactas.
- La estructura del snapshot que M3 lee sigue exactamente igual.

---

## 5. Cómo reproducir y verificar

```bash
# Levantar la simulación con la sesión que antes fallaba
./venv/bin/python3 -m motor.run --policy fifo --ticks 50 --seed 42

# Esperar: "Sesión completada en 10 ticks", TSP=100%, TBR=7.5%

# Ver eventos de reruta en la sesión
grep '"reruta"' output/sesion_fifo_s42.csv

# Ver eventos de tarea_cancelada
grep '"tarea_cancelada"' output/sesion_fifo_s42.csv

# Ver cesión de paso (múltiples movimientos de robots INACTIVOS en el mismo tick)
grep '"movimiento"' output/sesion_fifo_s42.csv
```

---

## 6. Incrementos sugeridos para Omniverse (M3)

Implementaciones concretas para reflejar los nuevos comportamientos en la
visualización 3D, ordenadas de menor a mayor dificultad.

### 6.1 Animación de cesión de paso en cascada — Dificultad: 2/5

Cuando el snapshot de un tick muestra 2+ robots INACTIVOS que cambiaron de posición
(eventos `movimiento` consecutivos de robots sin tarea), animarlos **simultáneamente**
en vez de secuencialmente para reflejar la cascada.

**Implementación:** usar interpolación paralela de las posiciones USD de ambos robots.
Ya existe lógica de movimiento de robots entre ticks — solo hay que asegurar que el
interpolador mueva >1 robot a la vez en el mismo frame range.

```
Tick N:  Robot A en (1,0), Robot B en (2,0)
Tick N+1: Robot A en (2,0), Robot B en (3,0)   ← ambos se movieron
         → animar ambos desplazamientos en paralelo
```

### 6.2 Indicador de tarea cancelada — Dificultad: 2/5

Al recibir evento `tarea_cancelada`, mostrar un indicador visual breve sobre el robot.

**Implementación:** cambiar temporalmente el material del mesh del robot a rojo
durante 2-3 frames, o crear un `Cube` prim pequeño y rojo sobre el robot que se
elimina después. El robot transiciona a INACTIVO — reutilizar la animación idle
existente.

```python
# Pseudocódigo Omniverse
if evento["tipo"] == "tarea_cancelada":
    robot_prim = stage.GetPrimAtPath(f"/World/Robots/Robot_{evento['robot_id']}")
    # Cambiar material a rojo por 3 frames
    set_material_override(robot_prim, "red_flash", duration_frames=3)
```

### 6.3 Indicador de bloqueo persistente — Dificultad: 3/5

Mostrar un indicador progresivo mientras un robot lleva ticks consecutivos bloqueado.
El indicador desaparece al tick 3 (cuando el robot reruta o cancela).

**Implementación:** crear un `Sphere` prim semitransparente como hijo del robot cuyo
radio o opacidad escala con el conteo de bloqueo (1→2→3). No necesita shaders custom
— un material `OmniPBR` con opacidad baja es suficiente.

```
tick_bloqueado=1 → esfera naranja, opacidad 0.3, radio 0.3
tick_bloqueado=2 → esfera naranja, opacidad 0.6, radio 0.5
tick_bloqueado=3 → desaparece (robot reruta o cancela)
```

Para saber cuántos ticks lleva bloqueado, contar eventos `bloqueo` consecutivos del
mismo robot en los últimos ticks del snapshot.

### 6.4 Visualización de reruta BFS — Dificultad: 4/5

Al recibir evento `reruta`, dibujar un path highlight efímero mostrando la nueva
trayectoria del robot.

**Implementación:** crear un `BasisCurves` prim USD con material emissivo (glow)
trazando los puntos de la nueva ruta. Eliminar el prim tras N frames. La parte
difícil es convertir las coordenadas de grilla `(x, y)` a posiciones world-space
de la escena y gestionar el ciclo de vida del prim (crear → mostrar → eliminar).

```python
# Pseudocódigo
if evento["tipo"] == "reruta":
    robot = snapshot.robots[evento["robot_id"]]
    # La ruta está en tarea.ruta_entrada (no expuesta al bus),
    # pero se puede inferir de los movimientos subsiguientes del robot.
    # Alternativa: dibujar solo un flash en el robot indicando "cambio de ruta".
```

**Alternativa más simple (3/5):** en vez de dibujar la curva completa, solo hacer un
flash de color en el robot (similar a 6.2) cuando llega el evento `reruta`.

### 6.5 Efecto de ocupación de columna — Dificultad: 5/5

Cuando un robot está excavando en una columna, highlight visual de esa columna como
"en uso" en la grilla 3D.

**Implementación:** identificar los prims de las celdas de la columna `(x, y)` en
el scene graph, aplicar un material overlay o outline, y revertirlo cuando la columna
se libera. Requiere traversal del scene graph USD y gestión dinámica de materiales.

**Nota:** este incremento es opcional y de alto esfuerzo. Solo tiene valor si la
simulación se ejecuta con grillas grandes donde no es obvio visualmente qué columna
está ocupada.

---

## 7. Referencia técnica rápida

| Elemento | Ubicación | Descripción |
|---|---|---|
| `UMBRAL_RERUTA` | `motor/despachador.py:42` | Constante = 3. Ticks bloqueado antes de intentar BFS reruta |
| `_ruta_xy_evitando()` | `motor/despachador.py` (helpers) | BFS con profundidad 2× Manhattan. Evita celdas ocupadas, permite llegar al destino. Retorna `None` si no hay ruta |
| `_intentar_ceder_paso()` | `motor/despachador.py` (helpers) | Mueve un robot INACTIVO a celda libre. Con `depth=2`, puede empujar un vecino primero (cascada) |
| `Tarea.ticks_bloqueado_consecutivos` | `motor/despachador.py:61` | Contador que se incrementa por tick bloqueado, se resetea al avanzar o cancelar |
