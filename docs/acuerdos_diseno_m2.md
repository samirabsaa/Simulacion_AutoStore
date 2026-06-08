# Acuerdos de Diseño y Convenciones para M2

> Documento de Martín Vásquez (Bus + Persistencia) en respuesta a los 5 puntos
> abiertos planteados en `docs/guia_integracion_m2_bus.md` y en el PR de
> `test-integracion-m2-bus`. Se versiona aquí para que quede como referencia
> citable del equipo — reemplaza la sección "Puntos a confirmar con Martín" de
> esa guía, ahora resuelta.

Este documento recopila las decisiones tomadas sobre el comportamiento del bus,
las transiciones de modo, el manejo de robots y las colas de pedidos para el
hito M2.

## 1. `TickDelta.pedidos_cola` — ¿Cola completa o deltas puntuales?

**Cola completa cuando el campo viene en el delta.** Si `pedidos_cola` no es
`None`, el bus hace un reemplazo total (`self._pedidos_cola = list(delta.pedidos_cola)`).
No hay merge ni altas/bajas parciales.

Convenciones para M2:
- **Cola cambió:** mandar la lista entera ya reordenada.
- **Cola sin cambios:** omitir el campo (`None`).
- **Completados:** usar `pedidos_completados_add` (append, no reemplazo).

Mandar la cola completa cada tick (como hace el esqueleto hoy) sigue siendo
válido; se puede optimizar después omitiendo el campo cuando no haya cambios.

## 2. Transiciones de modo — ¿Validación o libertad de M2?

**Sin validación en el bus.** M2 puede mandar `DIURNO` o `NOCTURNO` en cualquier
tick vía `TickDelta.modo`.

División acordada:

| Momento | Quién | Cómo |
|---|---|---|
| Antes de Play | M1 | `bus.set_modo()` — modo inicial elegido en la UI |
| Durante la simulación | M2 | `TickDelta.modo` — transiciones según la lógica del motor |

`config.json` no define reglas de turno. Por convención, M1 no llama a
`set_modo()` en runtime una vez arrancada la simulación.

## 3. `Robot.carga_id` — ¿Es el `id_caja` transportado?

**Sí.** Es el `id_caja` de la `Caja` que lleva el robot, o `None` si va vacío.
No tiene relación con el `tarea_id` del boceto original.

Cuando el robot suelta la caja, M2 debe mandar `carga_id=None` en el `Robot`
actualizado.

## 4. Valor `"prioridad_posicion"`

**Confirmado.** El valor canónico es `PoliticaPicking.PRIORIDAD_POSICION = "prioridad_posicion"`.

M1 debe usar el enum. En la UI se puede mostrar una etiqueta legible, pero el
valor enviado al bus es `"prioridad_posicion"`. La corrección en `CLAUDE.md` es
correcta.

## 5. `robots_delta` — ¿Reemplazo total o merge por id?

**Corregido en `bus-persistencia`.** El comportamiento original
(`self._robots = list(delta.robots_delta)`) era un bug — no era intencional.
`StateBus._apply_delta` ahora hace merge por `robot.id`, alineado con
`MutableState.apply_delta` y con la semántica de `grilla_delta`.

Comportamiento vigente:
- M2 manda solo los robots que cambiaron en ese tick.
- Si ningún robot cambió → omitir el campo (`None`).
- Los robots no incluidos en el delta permanecen intactos en el snapshot.

No hace falta volcar el estado de todos los robots cada tick. El esqueleto puede
acumular en `_robots_delta` únicamente los robots modificados, igual que con
`_grilla_delta`.

## Resumen de Decisiones

| # | Tema | Respuesta |
|---|---|---|
| 1 | `pedidos_cola` | Reemplazo completo si se incluye; `None` si no cambió |
| 2 | `modo` | Sin validación; M1 fija inicio, M2 decide transiciones |
| 3 | `carga_id` | `id_caja` transportada, o `None` |
| 4 | Política posición | `"prioridad_posicion"` / `PoliticaPicking.PRIORIDAD_POSICION` |
| 5 | `robots_delta` | Merge por `id` — delta parcial seguro (bug corregido) |

Los 5 puntos quedan cerrados. Ya se puede construir la lógica de M2 sobre el
esqueleto con estos supuestos confirmados.
