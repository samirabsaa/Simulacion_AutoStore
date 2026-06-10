# Coordinación de tráfico de robots — M2

## Problema

Los robots del AutoStore operan sobre una grilla en el plano XY. Cada robot ocupa
una celda `(x, y)` en la superficie, y se mueve paso a paso siguiendo una ruta
L-shaped (X primero, luego Y). Cuando dos robots necesitan la misma celda, se
produce una colisión que el despachador resuelve con cesión de paso: uno espera
mientras el otro pasa.

Hoy ese mecanismo tiene tres deficiencias que, combinadas, provocan
estancamientos evitables:

1. **Sin prioridad** — el orden en que los robots se mueven es el orden del
   `dict` de Python (≈ arbitrary insertion order). Un robot que vuelve vacío
   puede ocupar una celda que necesita un robot que viene cargado con un pedido.
   El vacío avanza primero, el cargado espera. La métrica TPCP (tiempo de ciclo
   por pedido) se degrada sin razón.

2. **Cesión pasiva** — solo los robots `INACTIVO` ceden el paso (se mueven a una
   columna adyacente para despejar). Los robots activos (`DESPLAZANDOSE`,
   `EXCAVANDO`, etc.) nunca se apartan aunque estén bloqueando a alguien de mayor
   prioridad. Un robot vacío yendo hacia su objetivo puede estorbar a uno cargado
   que vuelve al puerto, y no hay mecanismo para que el vacío se corra.

3. **Distancia cero** — los robots se forman en cadena pegada. El robot A se
   detiene en `(3, 0)`, B avanza a `(2, 0)` inmediatamente detrás. Si A no se
   mueve por varios ticks, B queda atrapado sin celdas adyacentes libres para
   maniobrar (no puede apartarse porque las únicas celdas libres son `(1,0)` que
   ya está ocupada por C, o columna lateral ocupada). No hay distancia de
   seguridad entre robots.

Estos tres problemas son independientes de la ruta que los robots tomen. Incluso
con rutas alternativas (X-first vs Y-first), si dos robots convergen al mismo
punto y no saben quién tiene prioridad, se bloquean mutuamente.

---

## Cambio 1 — Arbitraje por prioridad de fase

### Idea

Cada fase de una tarea de picking tiene una prioridad numérica. Cuando dos robots
compiten por la misma celda, el de mayor prioridad avanza y el otro espera (o se
aparta). La prioridad refleja cuánto cuesta al sistema que ese robot se retrase.

### Tabla de prioridades

| Fase                 | Prioridad | Razón                                        |
|----------------------|-----------|----------------------------------------------|
| `entregar`           | 50        | Está en puerto; entregar completa el pedido  |
| `mover_a_puerto`     | 40        | Lleva caja; cada tick extra alarga TPCP      |
| `recuperar`          | 30        | Acaba de tomar caja; necesita salir          |
| `excavar`            | 20        | Sin carga; puede esperar                     |
| `mover_a_objetivo`   | 10        | Sin carga; máxima flexibilidad               |

Robots sin tarea (INACTIVO) tienen prioridad 0 — siempre ceden.

### Implementación

En `despachador.py`, método `tick()`, paso 3 (avanzar robots), **ordenar los
robots por prioridad de su fase actual descendente** antes de procesarlos:

```python
# Paso 3: avanzar robots ordenados por prioridad
def _prioridad_fase(fase: str) -> int:
    return {"entregar": 50, "mover_a_puerto": 40, "recuperar": 30,
            "excavar": 20, "mover_a_objetivo": 10}.get(fase, 0)

robots_ordenados = sorted(
    robots_estado.values(),
    key=lambda r: _prioridad_fase(self._tareas.get(r.id, None).fase if self._tareas.get(r.id) else ""),
    reverse=True,
)
for robot in robots_ordenados:
    ...
```

Esto asegura que en cada tick:

- Si dos robots quieren la misma celda, el cargado entra y el vacío espera
- Los robots en puerto (entregar) se procesan primero, liberan su celda, y los
  que esperan ese puerto pueden avanzar en el mismo tick (si la prioridad no
  existía, el que esperaba el puerto se procesaba antes que el que estaba
  entregando — y se bloqueaba porque la celda seguía ocupada)

### Efecto colateral positivo

La cesión de paso existente (paso 2.5, INACTIVO se aparta) se vuelve más
efectiva porque ahora los INACTIVOS se procesan al final — cuando ya todos los
robots activos se movieron y liberaron celdas. Hay más espacio para que el
INACTIVO se aparte.

### Archivo a modificar

- `motor/despachador.py` — método `tick()`, paso 3

---

## Cambio 2 — Cesión activa entre robots activos

### Idea

Hoy el paso 2.5 (líneas 118-150) solo mueve robots `INACTIVO` cuando bloquean.
Extenderlo para que **cualquier robot activo de menor prioridad** que esté
bloqueando a uno de mayor prioridad se aparte a una columna adyacente.

### Regla

```
Si robot A (prioridad PA) está BLOQUEADO y su celda destino
está ocupada por robot B (prioridad PB), y PA > PB:
  → B se aparta a una columna adyacente libre
  → la ruta de B se recalcula desde su nueva posición
  → A avanza
```

"Se aparta" significa:

1. Encontrar una celda `(ax, ay)` adyacente a `(B.x, B.y)` que esté libre y no
   sea la celda destino de A
2. Mover a B a esa celda (sin costo de tick extra — es un reubicación forzada)
3. Recalcular `ruta_entrada` o `ruta_salida` de B desde la nueva posición
   (llamando a `_ruta_xy(nueva_pos, destino_original)`)
4. Emitir evento de movimiento para B

### ¿Por qué funciona?

En una cadena de 3 robots:

```
Robot C (cargado, prioridad 40) → quiere celda en (0, 3)
  Robot B (vacío, prioridad 10) → en (0, 2), bloquea a C
    Robot A (vacío, prioridad 10) → en (0, 1), bloquea a B
```

Sin cambio: C espera a que B se mueva, B espera a que A se mueva, A espera a que
alguien lo mueva. Cadena infinita.

Con cambio: C tiene prioridad > B, entonces B se aparta. Si B se aparta, A ya no
bloquea a nadie (B ya no está detrás), y C avanza. La cadena se rompe desde
arriba (el robot cargado "empuja" la cesión hacia abajo).

### Archivo a modificar

- `motor/despachador.py` — paso 2.5, extender condición de `robot.estado == INACTIVO`
  a `robot.estado == INACTIVO or _prioridad_fase(otarea.fase) < _prioridad_fase(tarea.fase)`

---

## Cambio 3 — Distancia de seguridad

### Idea

Si la celda destino de un robot está ocupada por otro robot que está `BLOQUEADO`
o `INACTIVO`, el robot que se acerca no avanza a la celda **adyacente** al robot
detenido. Mantiene al menos 1 celda de distancia.

### Regla

```
Si robot A quiere avanzar de (x, y) a (x', y') y la celda destino está ocupada:
  → comportamiento normal (BLOQUEADO)
  → ADEMÁS: si robot B (el que ocupa el destino) está BLOQUEADO,
    A no avanza en siguiente tick aunque B se mueva — A espera
    hasta que la celda (x', y') esté libre CONFIRMADA
```

Esto se implementa con una pequeña modificación al chequeo de colisiones: cuando
un robot está BLOQUEADO y la celda destino está ocupada por otro BLOQUEADO, el
robot no intenta re-evaluar su ruta hasta que el bloqueo se resuelva. Es una
optimización simple — en vez de que A intente avanzar cada tick y se encuentre
con la celda ocupada (gastando recursos en el chequeo), A espera hasta que el
robot delante cambie de estado.

En la práctica, el efecto es que los robots mantienen distancia natural. Si A y B
están separados por una celda vacía, A tiene espacio para moverse a una columna
adyacente si necesita ceder el paso. Con la cadena pegada, A no tiene ese espacio.

### Alternativa más simple: contador de ticks bloqueados

Si un robot está `BLOQUEADO` por más de `MAX_BLOQUEO_TICKS` (ej: 10) hacia la
misma celda, el despachador fuerza que el robot y el obstáculo se resuelvan:

1. El robot bloqueado retrocede a la celda anterior
2. Recalcula su ruta
3. Si el obstáculo sigue ahí, reintenta en el próximo tick

Esto no requiere cambios en el modelo de celdas, solo un contador y un flag de
"backtrack".

### Archivo a modificar

- `motor/despachador.py` — `_celda_ocupada()` o contador en `_fase_mover_a_objetivo`

---

## Estrategia de verificación

### Test: prioridad cargado avanza

```python
def test_prioridad_cargado_avanza():
    """Dos robots convergen a la misma celda: el cargado (prioridad 40)
    avanza y el vacío (prioridad 10) espera."""
    # Setup: robot 1 DESPLAZANDOSE sin carga (mover_a_objetivo, prioridad 10)
    #         robot 2 ENTREGANDO con carga (mover_a_puerto, prioridad 40)
    #         ambos quieren la misma celda (3, 0)
    # Assert: robot 2 (cargado) ocupa la celda
    #         robot 1 (vacío) queda BLOQUEADO
```

### Test: cesión activa entre activos

```python
def test_cesion_activa_entre_activos():
    """Robot activo de menor prioridad se aparta si bloquea a uno de mayor."""
    # Setup: robot A (prioridad 10, mover_a_objetivo) en (2,0)
    #         robot B (prioridad 40, mover_a_puerto con carga) quiere (2,0)
    #         Hay celda libre en (3,0)
    # Assert: A se mueve a (3,0), B avanza a (2,0)
    #         Eventos de movimiento emitidos para ambos
```

### Test: 3-robot chain no se estanca

```python
def test_3_robot_chain_no_se_estanca():
    """Cadena de 3 robots: el cargado llega al puerto."""
    # Setup: 3 robots en línea en x=0, y=0,1,2
    #         Robot C (y=2) cargado volviendo al puerto
    #         Robot B (y=1) vacío yendo a su objetivo
    #         Robot A (y=0) vacío yendo a su objetivo
    # Assert: C completa su pedido
    #         B y A reanudan sus tareas
    #         Ningún robot queda bloqueado permanentemente
```

### Test: distancia de seguridad

```python
def test_distancia_seguridad():
    """Robot no avanza a celda adyacente a otro BLOQUEADO."""
    # Setup: robot A BLOQUEADO en (2,0) desde hace 5+ ticks
    #         robot B acercándose a (2,0) desde (0,0)
    # Assert: B se detiene en (1,0) o antes
    #         B no intenta entrar a (2,0) mientras A esté BLOQUEADO
```

---

## Resumen de archivos a modificar

| Archivo | Cambios | Líneas estimadas |
|---------|---------|------------------|
| `motor/despachador.py` | Prioridad en paso 3, cesión activa en paso 2.5, distancia de seguridad en `_celda_ocupada` | ~60 |
| `tests/test_motor_despachador.py` | 4 nuevos tests | ~120 |

No se modifican otros módulos. Los cambios son autocontenidos en el despachador.
