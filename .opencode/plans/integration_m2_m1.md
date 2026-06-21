# Integración M2 → M1 — Plan dividido OpenCode / Cursor

## Leyenda

| Marca | Quién lo hace |
|---|---|
| ✅ OPC | **OpenCode** — backend, data plumbing, modelos, servicios Angular |
| 🖌️ CUR | **Cursor** — componentes de UI, páginas, routing, diseño visual |

---

## ✅ Item 1 — Tipar `grilla` en el modelo WS

**Archivo:** `m1/src/app/core/models/state-bus-snapshot.model.ts`

Agregar interfaz `WsGrillaCell` y retipar el campo `grilla` en `WsTickPayload`.

La data ya llega desde el backend — solo falta declarar el tipo.

---

## ✅ Item 2 — Propagar `robots` y `grilla` en el BusState

**Archivo:** `m1/src/app/core/services/bus-client.service.ts`

- Agregar `robots: WsRobotState[]` y `grilla: WsGrillaCell[]` a la interfaz `BusState` y a `INITIAL_STATE`
- En `applyTick()`, propagar desde el mensaje WS:
  ```ts
  robots: msg.robots ?? s.robots,
  grilla: msg.grilla ?? s.grilla,
  ```

Esto hace que los datos estén disponibles en `bus.robots` / `bus.grilla` para cualquier componente.

---

## ✅ Item 3 — Endpoints de descarga de reportes (backend)

**Archivo:** `api/server.py`

Agregar `GET /report/comparativo` (sirve `output/reporte_comp.csv`) y `GET /report/sesion` (sirve el último `output/sesion_*.csv`).

---

## ✅ Item 4 — Métodos de descarga en SimApiService

**Archivo:** `m1/src/app/core/services/sim-api.service.ts`

Agregar:
```ts
downloadComparativo(): void {
  window.open(`${environment.apiUrl}/report/comparativo`, '_blank');
}
exportSesion(): void {
  window.open(`${environment.apiUrl}/report/sesion`, '_blank');
}
```

---

## 🖌️ Item 5 — Heatmap real con posiciones de robots

**Archivos:** `robot-grid.component.ts / .html / .scss`

- Reemplazar inputs fake (`numRobots`, `iog`) por inputs reales (`gridZ`, `grilla: WsGrillaCell[]`, `robots: WsRobotState[]`)
- `rebuildCells()`: contar cajas reales por columna desde `grilla[]`, posicionar robots desde `robots[]`
- Eliminar `setInterval` de animación local
- Agregar clases CSS por estado de robot (IDLE, MOVING, BLOCKED, PICKING, DEPOSITING) con colores

Ver `docs/integration_cursor_plan.md` para código de referencia.

---

## 🖌️ Item 6 — Panel de Estados (ex Dashboard)

**Archivos:** `dashboard.page.ts / .html / .scss`

- Remover ControlBarComponent, RobotGridComponent, toggle mode/policy
- Agregar tabla "Estado de la Flota" (id, x, y, z, estado, carga_id)
- Agregar grid "Estado del Bus Central" (tick, mode, policy, status, 7 KPIs)
- Mantener las 7 tarjetas KPI + tarjeta de escenario

---

## 🖌️ Item 7 — Monitor Simulación (página nueva)

**Archivos:** `monitor.page.ts / .html / .scss`

- Nueva página en `src/app/pages/monitor/`
- BusStripComponent
- ControlBarComponent (play/pause/reset — sin speed si se decide ocultar)
- Tabs Vista 2D / Vista 3D
- 2D: RobotGridComponent con bindings reales
- 3D: Placeholder "Módulo M3 — Pendiente"

---

## 🖌️ Item 8 — Layout / Navegación

**Archivos:** `app.component.ts / .html / .scss`, `app.routes.ts`

- Eliminar `<header class="topbar">` de `app.component.html`
- Actualizar nav items: `Panel KPIs→Panel de Estados`, combinar rutas grilla+simulacion→`Monitor Simulación (2D/3D)`, `Datos y Reportes→Datos Estadísticos`
- Rutas: reemplazar `/grilla` y `/simulacion` por `/monitor`, redirigir viejas

---

## 🖌️ Item 9 — Configuración simplificada

**Archivos:** `config.page.ts / .html / .scss`

- Eliminar secciones: Validación de Parámetros, Estado del Sistema
- Eliminar campos: pedidos demandados (auto desde ola), política picking, velocidad
- Agregar indicador de ola cargada con nombre de archivo
- Auto-set pedidos demandados desde filas del CSV (frontend-only)

---

## 🖌️ Item 10 — Reportes: wirear descargas

**Archivos:** `reportes.page.ts / .html`

- Injectar `SimApiService`
- Llamar `downloadComparativo()` y `exportSesion()` desde los botones

---

## 🖌️ Item 11 — Limpiar páginas obsoletas

Eliminar `grilla.page.*` y `simulacion.page.*` (reemplazadas por monitor).

---

## Orden sugerido

```
OpenCode: Items 1 → 2 → 3 → 4  (pueden hacerse de una vez, sin dependencias)
Cursor:   Item 5 → 7 → 8 → 6 → 9 → 10 → 11
```
