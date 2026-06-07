# Guía de integración M2 ↔ Bus — notas para Manuel

Este documento **no reemplaza** la documentación oficial del bus — esa la escribió
Martín y vive en [`bus_api.md`](bus_api.md) y [`integracion_grupo12.md`](integracion_grupo12.md)
(rama `bus-persistencia`). Este texto cumple un rol distinto: mostrar concretamente
**cómo `AutoStoreSimulator` (motor/simulador.py) consume ese contrato real**.

Una primera versión de esta guía dejaba abiertos 5 supuestos que tomamos al
escribir el esqueleto sin confirmación directa de Martín. Ya los revisamos con
él — quedaron resueltos en [`docs/acuerdos_diseno_m2.md`](acuerdos_diseno_m2.md)
y resumidos en la sección 3 más abajo.

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
| Procesar turno | `_procesar_turno_diurno(politica)` / `_procesar_turno_nocturno()` | Acumulan SOLO lo que cambió este tick en `_grilla_delta`/`_grilla_remove` (merge por celda `(x,y,z)`) y `_robots_delta` (merge por `robot.id` — confirmado y corregido, ver `docs/acuerdos_diseno_m2.md` punto 5); también `_pedidos_completados_add` y `_eventos_pendientes` |
| Cambiar de turno | `cambiar_modo(nuevo_modo)` | Pasa por `TickDelta.modo` — es M2 quien decide la transición según duración de fase, a diferencia de la política |
| Resolver colisiones | `_resolver_colisiones()` | Robot pasa a `RobotEstado.BLOQUEADO`; alimenta TBR y genera evento `bloqueo` |
| Recalcular KPIs | `_actualizar_kpis()` | Produce un `KPISet` (no un dict) para `TickDelta.kpis` |
| Emitir el tick | `_construir_delta()` + `bus.write_tick_delta(M2_WRITER_ID, delta)` | Empaqueta SOLO lo que cambió — el bus espera deltas reales (sus tests miden latencia P99 < 1ms) |
| Log de sesión y reportes | *(no existen métodos para esto en el esqueleto — a propósito)* | El `SessionLogger` interno del bus bufferea `TickDelta.eventos` y vuelca `sesion_X.csv`/`metadata_*.json` automáticamente. M2 solo debe usar el vocabulario correcto: `movimiento`, `excavacion`, `caja_recuperada`, `pedido_completado`, `bloqueo`, `kpi_update` |

---

## 3. Decisiones confirmadas con Martín

Los 5 puntos que dejamos abiertos en la primera versión de esta guía (y en el PR
de `test-integracion-m2-bus`) ya están resueltos — ver el detalle completo en
[`docs/acuerdos_diseno_m2.md`](acuerdos_diseno_m2.md). Resumen:

| # | Tema | Decisión |
|---|---|---|
| 1 | `pedidos_cola` | Reemplazo completo cuando se incluye (mandar la cola entera reordenada); omitir (`None`) si no cambió. Completados van por `pedidos_completados_add` |
| 2 | Transiciones de `modo` | Sin validación en el bus — M1 fija el modo inicial vía `set_modo()` antes de Play, M2 decide las transiciones en runtime vía `TickDelta.modo` |
| 3 | `Robot.carga_id` | Confirmado: `id_caja` de la `Caja` transportada, o `None` si va vacío. Al soltar la carga, M2 debe reportar el `Robot` con `carga_id=None` |
| 4 | `"prioridad_posicion"` | Confirmado como valor canónico — la corrección que hicimos en `CLAUDE.md` es correcta |
| 5 | `robots_delta` | **Era un bug real** (reemplazo total de la lista), no comportamiento intencional — Martín lo corrigió: ahora mergea por `robot.id`, igual que `grilla_delta` mergea por celda. M2 debe mandar solo los robots que cambiaron |

El punto 5 quedó además fijado como prueba de regresión permanente en
`tests/test_contrato_m2_bus.py::test_robots_delta_mergea_por_id_no_reemplaza_la_lista`
— si el comportamiento de reemplazo total reaparece alguna vez, esa prueba falla.

---

## 4. Qué NO está en este documento (y por qué)

No repetimos diagramas, tablas de roles, ni ejemplos de código de `bus_api.md` /
`integracion_grupo12.md` — Martín ya los mantiene actualizados y son la fuente de
verdad técnica del bus. Si algo de esta guía entra en conflicto con esos documentos,
gana lo que digan ellos — y hay que avisar para corregir esta guía.
