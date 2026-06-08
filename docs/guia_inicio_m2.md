# Guía de inicio para Manuel — construir M2 sobre el esqueleto

Manuel: esto es un resumen de lo que se preparó para que puedas arrancar a
construir la lógica real de M2 sin perder tiempo investigando el contrato del
bus desde cero. Todo lo que se describe acá ya está validado y listo para usar
como base.

---

## 1. Qué se preparó

| Qué | Dónde | Para qué sirve |
|---|---|---|
| Esqueleto de `AutoStoreSimulator` | `motor/simulador.py` | Clase orquestadora de M2 — ya alineada al contrato real del bus (no al boceto viejo del CLAUDE.md). Tiene la estructura completa de propiedades, buffers internos y el ciclo de tick listo; los métodos de lógica de simulación están como `NotImplementedError` a propósito, para que implementes ahí |
| Guía de integración M2 ↔ Bus | `docs/guia_integracion_m2_bus.md` | Mapeo concreto: qué método del esqueleto usa qué pieza del contrato real (`TickDelta`, `StateSnapshot`, enums, vocabulario de eventos, etc.) |
| Acuerdos de diseño confirmados | `docs/acuerdos_diseno_m2.md` | Las 5 dudas que teníamos sobre el contrato, ya resueltas con Martín — convenciones que debes seguir al construir los deltas |
| Prueba de contrato | `tests/test_contrato_m2_bus.py` | Confirma que el esqueleto se conecta correctamente con el bus real (instancia, construye deltas, escribe, el bus refleja los cambios). 5/5 tests pasan |
| Documentación oficial del bus (de Martín) | `docs/bus_api.md`, `docs/integracion_grupo12.md` | Contrato técnico exhaustivo — fuente de verdad para todo lo relacionado al bus |

---

## 2. Por dónde empezar

1. **Lee `docs/guia_integracion_m2_bus.md` primero** — tiene la tabla de mapeo
   completa entre el flujo de simulación y el contrato real. Te ahorra tener que
   cruzar referencias entre el esqueleto y `bus_api.md` cada vez.

2. **Corre la prueba de contrato** para confirmar que tu entorno está bien armado
   antes de empezar a programar:
   ```
   pip install -r requirements.txt
   pytest tests/test_contrato_m2_bus.py -v
   ```
   Si los 5 tests pasan, el esqueleto y el bus están bien conectados — cualquier
   problema que encuentres después es de la lógica que vayas agregando, no del
   contrato.

3. **Implementa los métodos `NotImplementedError`** de `motor/simulador.py`, en
   este orden sugerido (de menos a más dependencias):
   - `inicializar_desde_bus()` — construye la grilla y los robots desde
     `read_snapshot().config`
   - `_actualizar_kpis()` — delega en `motor.kpis` (las fórmulas ya están en el
     CLAUDE.md, sección "Los 7 KPIs")
   - `_resolver_colisiones()` — cesión de paso, alimenta TBR
   - `_procesar_turno_diurno(politica)` / `_procesar_turno_nocturno()` — el
     grueso de la lógica; delegan en `motor.despachador` / `motor.modos`
   - `ha_terminado()` — condición de término de sesión

   Cada uno tiene su docstring en el esqueleto explicando qué se espera y a qué
   buffers (`_grilla_delta`, `_robots_delta`, `_eventos_pendientes`, etc.) debe
   alimentar — esos buffers ya los arma `_construir_delta()` por ti.

4. **No necesitas tocar nada de persistencia ni logging** — el `SessionLogger`
   del bus bufferea los `eventos` del `TickDelta` y vuelca `sesion_X.csv` /
   `metadata_*.json` automáticamente. Solo usa el vocabulario correcto:
   `movimiento`, `excavacion`, `caja_recuperada`, `pedido_completado`, `bloqueo`,
   `kpi_update`.

---

## 3. Convenciones clave a seguir (resumen — detalle en `acuerdos_diseno_m2.md`)

Estas son las reglas que te van a evitar bugs sutiles al construir los `TickDelta`:

- **`pedidos_cola`**: si la cola cambió, manda la lista **completa** ya
  reordenada; si no cambió, omite el campo (`None`). Los completados van por
  `pedidos_completados_add` (solo altas).
- **`modo`**: tú decides las transiciones de turno en runtime — el bus no valida
  nada. M1 solo fija el modo inicial antes de Play.
- **`carga_id`**: es el `id_caja` que el robot transporta, o `None` si va vacío.
  Cuando un robot suelta la carga, manda el `Robot` actualizado con
  `carga_id=None` explícitamente — si no, el snapshot sigue mostrando la carga vieja.
- **`robots_delta`**: manda **solo los robots que cambiaron** este tick — el bus
  los mergea por `id` y deja intactos a los demás (esto era un bug que detectamos
  con el test de contrato; Martín ya lo corrigió). **No hace falta** mandar el
  estado de todos los robots cada vez.
- **`grilla_delta` / `grilla_remove`**: igual que `robots_delta` — solo lo que
  cambió, identificado por celda `(x, y, z)`.

---

## 4. Si encuentras algo que no calza con el contrato

Si mientras implementas te topas con algo del contrato que no está claro o que
no se comporta como esperarías (como nos pasó con el bug de `robots_delta`),
agrégalo a `tests/test_contrato_m2_bus.py` como caso de prueba — así queda
documentado de forma ejecutable y se puede discutir con Martín con evidencia
concreta en mano, no solo una sospecha.
