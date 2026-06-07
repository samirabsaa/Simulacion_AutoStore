# Guía de integración M2 ↔ Bus — notas para Manuel y puntos a confirmar con Martín

Este documento **no reemplaza** la documentación oficial del bus — esa la escribió
Martín y vive en [`bus_api.md`](bus_api.md) y [`integracion_grupo12.md`](integracion_grupo12.md)
(rama `bus-persistencia`). Este texto cumple un rol distinto: mostrar concretamente
**cómo `AutoStoreSimulator` (motor/simulador.py) consume ese contrato real**, y dejar
una lista de supuestos que tomamos al escribir el esqueleto y que conviene confirmar
con Martín antes de que Manuel construya la lógica completa sobre ellos.

> Nota: una versión anterior de este documento (`guia_bus_para_martin.md`) intentaba
> anticiparle a Martín los cambios que veníamos a pedirle. Quedó obsoleta — Martín ya
> construyó el bus, con un contrato bastante distinto al boceto original del CLAUDE.md
> (y más completo: enums tipados, deltas reales, `SessionLogger` integrado, etc.).
> Este documento parte de su implementación real, no al revés.

---

## 1. Contrato vigente — referencia, no duplicado

El contrato técnico completo está en `docs/bus_api.md`. Resumen de lo esencial para M2:

- Escribir: `bus.write_tick_delta(M2_WRITER_ID, delta: TickDelta)` — único punto de
  entrada, una vez por tick, valida el `writer_id` (`WriterNotAuthorizedError` si no
  es `"M2"`).
- Leer: `bus.read_snapshot() -> StateSnapshot` — copia inmutable y profunda.
- Tipos: `TickDelta`, `KPISet`, `StateSnapshot`, `PedidosState`, y los enums
  `ModoTurno`, `PoliticaPicking`, `RobotEstado` — todos en `bus_persistencia.models.state`.

---

## 2. Cómo `AutoStoreSimulator` lo consume — mapeo concreto

| Paso del flujo de simulación | En el esqueleto (`motor/simulador.py`) | Contrato real que usa |
|---|---|---|
| Inicialización | `inicializar_desde_bus()` | Lee `bus.read_snapshot()` — **NO** recibe `config`/`pedidos` por constructor; M1 ya configuró el bus (`set_config`, `set_pedidos_cola`) antes de Play |
| Releer política cada tick | `avanzar_tick()` lee `snap.politica` al inicio | M2 nunca cambia la política — la fija el operador vía M1 (`bus.set_policy`); no es campo de `TickDelta` |
| Procesar turno | `_procesar_turno_diurno(politica)` / `_procesar_turno_nocturno()` | Acumulan cambios en buffers internos (`_grilla_delta`, `_grilla_remove`, `_robots_delta`, `_pedidos_completados_add`, `_eventos_pendientes`) |
| Cambiar de turno | `cambiar_modo(nuevo_modo)` | Pasa por `TickDelta.modo` — es M2 quien decide la transición según duración de fase, a diferencia de la política |
| Resolver colisiones | `_resolver_colisiones()` | Robot pasa a `RobotEstado.BLOQUEADO`; alimenta TBR y genera evento `bloqueo` |
| Recalcular KPIs | `_actualizar_kpis()` | Produce un `KPISet` (no un dict) para `TickDelta.kpis` |
| Emitir el tick | `_construir_delta()` + `bus.write_tick_delta(M2_WRITER_ID, delta)` | Empaqueta SOLO lo que cambió — el bus espera deltas reales (sus tests miden latencia P99 < 1ms) |
| Log de sesión y reportes | *(no existen métodos para esto en el esqueleto — a propósito)* | El `SessionLogger` interno del bus bufferea `TickDelta.eventos` y vuelca `sesion_X.csv`/`metadata_*.json` automáticamente. M2 solo debe usar el vocabulario correcto: `movimiento`, `excavacion`, `caja_recuperada`, `pedido_completado`, `bloqueo`, `kpi_update` |

---

## 3. Puntos a confirmar con Martín

Supuestos que tomamos al escribir el esqueleto, sin tener su confirmación directa —
vale la pena revisarlos juntos antes de que se conviertan en costumbre dentro de M2:

1. **`TickDelta.pedidos_cola`** — en `MutableState.apply_delta` vimos que hace
   `self._pedidos_cola = list(delta.pedidos_cola)`, es decir, **reemplaza la cola
   completa**. Asumimos que M2 debe reenviar la cola entera (reordenada según la
   política) cada vez que cambia, no solo deltas de altas/bajas puntuales. ¿Es así
   como lo pensaste, o esperabas otra forma de reportar cambios en la cola?

2. **Transiciones de `modo`** — `TickDelta.modo` permite que M2 cambie de turno en
   cualquier tick. ¿Hay alguna validación o expectativa sobre cuándo es válido
   mandar `NOCTURNO` (p. ej. ¿debe coincidir con algo de `config`, o el motor decide
   libremente según su propia lógica de duración de turno)?

3. **`Robot.carga_id`** — asumimos que es el `id_caja` de la `Caja` que el robot
   transporta (por el nombre del campo, ya que no tiene tipo explícito ni ejemplo en
   el mock de integración). ¿Confirmas esa lectura? Queremos evitar confundirlo con
   el `tarea_id` que describía el CLAUDE.md original (campo que ya no existe).

4. **Valor de la política de posición** — el CLAUDE.md original decía `"posicion"`;
   tu enum usa `PoliticaPicking.PRIORIDAD_POSICION = "prioridad_posicion"`. Ya
   actualizamos el CLAUDE.md para reflejar el valor real — avísanos si M1 espera
   otra convención de nombres para mostrarlo en la UI.

---

## 4. Qué NO está en este documento (y por qué)

No repetimos diagramas, tablas de roles, ni ejemplos de código de `bus_api.md` /
`integracion_grupo12.md` — Martín ya los mantiene actualizados y son la fuente de
verdad técnica del bus. Si algo de esta guía entra en conflicto con esos documentos,
gana lo que digan ellos — y hay que avisar para corregir esta guía.
