# Handoff M2→M1: conectar `BusClientService` al bridge real (T-45)

> **De:** Vicente (M2 + Bus/Persistencia + bridge)
> **Para:** Alonso / Eliseo (M1 — Ionic/Angular)
> **Rama:** `integracion-m1-m2` (M2 + bus_persistencia + bridge ya mergeados,
> 103/103 tests en verde). `m1/` (rama `origin/m1`) **todavía no está
> mergeado** en esta rama — el primer paso es traerlo.

---

## 1. TL;DR — qué hay que hacer

El backend (M2 + Bus + bridge FastAPI) está terminado, testeado y corriendo.
`environment.ts` de M1 **ya apunta correctamente** a él
(`apiUrl: http://localhost:8000`, `wsUrl: ws://localhost:8000/ws/state`).

Lo único que falta del lado M1:

1. **`bus-client.service.ts`**: reemplazar el `BehaviorSubject` alimentado por
   `mulberry32` (PRNG) por una conexión real a `ws://localhost:8000/ws/state`
   que actualice `BusState` con cada mensaje `{type: "tick", ...}`.
2. **`sim-api.service.ts`**: reemplazar los métodos mock (que hoy solo llaman
   a `BusClientService` localmente) por `HttpClient` contra los endpoints REST
   del bridge (`/config`, `/policy`, `/control/*`, `/api/upload/*`).
3. Decidir qué hacer con los modelos **no usados** `state-bus-snapshot.model.ts`
   / `kpi-snapshot.model.ts` (ver §5) — no bloquean nada, pero generan
   confusión porque parecen un contrato distinto al que realmente usa la UI.

**Buena noticia:** `KpisComputed`, `BusState`, `GridConfig`/`GridConfigDTO`,
`CsvRowError`/`ValidationResultDTO`, `SimMode`, `PickingPolicy`, `SimStatus` y
`SimSpeed` — que son los tipos que **sí** usa toda la UI (dashboard, grilla,
config, reportes, simulación, bus-strip) — **calzan casi 1:1** con lo que el
bridge ya envía. Ver tabla de mapeo en §3.

---

## 2. Cómo levantar el backend para probar

```bash
# desde la raíz del repo, rama integracion-m1-m2
pip install -r requirements.txt   # incluye fastapi, uvicorn[standard], python-multipart
uvicorn api.server:app --reload --port 8000
```

- `GET  http://localhost:8000/snapshot` — snapshot actual (sin `type`/`status` extra de WS, mismo payload).
- `WS   ws://localhost:8000/ws/state` — push de `{type: "tick", ...}` en cada tick + 1 al conectar.
- CORS habilitado para `http://localhost:8100` (Ionic dev server).

Tests del bridge: `pytest tests/test_api_bridge.py -v` (6/6 OK).

---

## 3. Contrato del bridge ↔ tipos de M1

### 3.1 Mensaje WebSocket (`ws://localhost:8000/ws/state`)

Cada mensaje es un objeto plano (sin envoltorio `{type, payload}` — **distinto**
del `WsTickMessage`/`StateBusSnapshot` que hay en
`core/models/state-bus-snapshot.model.ts`, que NO se usa en ningún componente
hoy):

```jsonc
{
  "type": "tick",
  "tick": 12,
  "mode": "DIURNO",                 // SimMode
  "policy": "FIFO",                 // PickingPolicy
  "status": "RUNNING",              // SimStatus
  "velocidad": 1,                   // SimSpeed (1|2|5)
  "grid": { "x": 12, "y": 10, "z": 5 },   // o null si no se ha llamado /config
  "robots": [
    { "id": 0, "x": 3, "y": 2, "z": 0, "estado": "MOVING", "carga_id": null }
  ],
  "grilla": [
    { "id_caja": "C001", "id_sku": "SKU-A", "cantidad": 2, "x": 1, "y": 1, "z": 0 }
  ],
  "pedidos": {
    "cola": [ { "id_pedido": "P001", "id_sku": "SKU-A", "cantidad": 2, "destino": "Tienda_01" } ],
    "completados": []
  },
  "kpis": {
    "TSP": 0, "TPCP": 0, "MTRP": 0, "IOG": 0, "TR": 0, "TI": 0, "TBR": 0,
    "tsp": 0, "tpcp": 0, "mtrp": 0, "iog": 0, "tr": 0, "ti": 0, "tbr": 0,
    "completados": 0, "capacidad": 600, "cajasPresentes": 180
  }
}
```

`robots[].estado` ya viene mapeado a los 5 valores de `RobotState`
(`IDLE|MOVING|PICKING|DEPOSITING|BLOCKED`) — el motor internamente usa 7
estados, el bridge hace ese mapeo (ver `api/serializers.py::ROBOT_ESTADO_TO_M1`).

> **`kpis` trae las claves DUPLICADAS en mayúscula y minúscula** a propósito,
> para que `payload.kpis as KpisComputed` funcione sin tocar
> `dashboard.page.ts` (que lee `kpis.TSP`, `kpis.TPCP`, etc.), y para que
> cualquier código nuevo pueda usar minúsculas si se prefiere.

### 3.2 Mapeo `BusState` (lo que ya usa la UI) ← payload del bridge

| Campo `BusState` | De dónde sale |
|---|---|
| `tick` | `payload.tick` |
| `running` | `payload.status === 'RUNNING'` |
| `status` | `payload.status` (ya es `SimStatus`) |
| `velocidad` | `payload.velocidad` |
| `mode` | `payload.mode` (ya es `SimMode`) |
| `policy` | `payload.policy` (ya es `PickingPolicy`) |
| `grid` | `payload.grid` si no es `null`; si es `null`, mantener el valor anterior/`DEFAULT_GRID_CONFIG.grid` |
| `numRobots` | `payload.robots.length` |
| `kpis` | `payload.kpis` (cast directo a `KpisComputed`, ver 3.1) |
| `semilla`, `ocupacionInicial`, `pedidosDemandados`, `nombreEjecucion` | **NO vienen por WS** — son valores de configuración. Guardarlos en `BusClientService` cuando se llama `/config` (desde `applyConfig`/`sendConfig`) y mantenerlos hasta el próximo `/config` |
| `archivoOla`, `archivoReposicion` | **NO vienen por WS** — se setean localmente según la respuesta de `POST /api/upload/{ola,reposicion}` (`valid` → `'valido'`, si no `'errores'`) |
| `falloSistema` | **NO viene del bridge** — lógica de M1 (p.ej. `'motor'` si el WS se desconecta) |
| `omniverse` | Fuera de alcance de M2/M3 en este PoC — dejar `'headless'` |

`payload.robots` / `payload.grilla` / `payload.pedidos` no tienen hoy un campo
correspondiente en `BusState` (no los usa ningún componente — `RobotGridComponent`
genera su heatmap con un PRNG local a partir de `gridX/gridY/numRobots/iog/tick`).
**No es necesario agregarlos** para esta integración; quedan disponibles en el
payload si más adelante se quiere una grilla/robots reales en vez del heatmap
sintético.

### 3.3 Endpoints REST

| M1 (`SimApiService`) | Bridge | Body / respuesta |
|---|---|---|
| `sendConfig(cfg)` | `POST /config` | body = `toDTO(cfg)` (=`GridConfigDTO`, **ya coincide exactamente** con lo que espera `GridConfigDTO` de `api/server.py`) → `{ok: true}` |
| `setMode/setPolicy` (control) | `POST /policy` | `{"policy": "FIFO" \| "PRIORIDAD_POSICION"}` → `{ok: true}`. Nota: el bridge no tiene endpoint separado para `mode`; el modo se fija vía `/config` (`mode`). Si la UI permite cambiar modo en caliente sin reconfigurar, avisar — hoy no está soportado por el bridge. |
| `play()` | `POST /control/play` | sin body → `{ok: true, status: "RUNNING"}` (409 si no se ha llamado `/config` antes) |
| `pause()` | `POST /control/pause` | sin body → `{ok: true, status: "PAUSED"}` |
| `reset(cfg)` | `POST /control/reset` | sin body → `{ok: true, status: "IDLE"}`. Vuelve al tick inicial **con la config/política/pedidos vigentes** (no hace falta reenviar `/config`) |
| `setSpeed(s)` | `POST /control/speed` | `{"velocidad": 1 \| 2 \| 5}` → `{ok: true, velocidad: <n>}` |
| `uploadCsv(file, 'ola')` | `POST /api/upload/ola` (multipart, campo `file`) | → `ValidationResultDTO` = `{valid, errors: CsvRowError[]}` — **idéntico** a `csv-validation-error.model.ts`. Si `valid`, el bridge ya carga los pedidos al bus (no hace falta nada más) |
| `uploadCsv(file, 'reposicion')` | `POST /api/upload/reposicion` (multipart, campo `file`) | igual que arriba, para la cola de reposición del turno nocturno |

Todos los endpoints devuelven JSON; usar `HttpClient` de Angular normalmente
(`environment.apiUrl + '/config'`, etc.) y `FormData` para los uploads.

---

## 4. Cambios concretos sugeridos

### `bus-client.service.ts`

- Eliminar `mulberry32`, `computeKpis`, `startTick`/`stopTick`/`setInterval`.
- En el constructor (o en un método `connect()` llamado una vez desde
  `app.component.ts`), abrir un `WebSocketSubject<any>` (RxJS
  `webSocket(environment.wsUrl)`) y en cada mensaje hacer `patch(...)` con el
  mapeo de la tabla §3.2. Manejar reconexión simple (p.ej. `retry({delay: 1000})`).
- `setRunning`, `setSpeed`, `setMode`, `setPolicy`, `reset`, `applyConfig` ya
  NO deben mutar el estado localmente para simular — deben **delegar** en
  `SimApiService` (que llama al bridge); el estado real llega por WS. Pueden
  quedar como wrappers finos o moverse del todo a `SimApiService` (a discreción
  de Alonso, sin romper las llamadas existentes desde las páginas).
- Mantener en el servicio (no en el bridge) los campos "de sesión" que no
  vienen por WS: `semilla`, `ocupacionInicial`, `pedidosDemandados`,
  `nombreEjecucion`, `archivoOla`, `archivoReposicion`.

### `sim-api.service.ts`

- Inyectar `HttpClient`.
- Reemplazar cada método mock por la llamada HTTP correspondiente de §3.3.
- `uploadCsv`: `FormData` con `file`, `POST` a `environment.apiUrl + '/api/upload/' + tipo`.

---

## 5. Limpieza opcional (no bloqueante)

`core/models/state-bus-snapshot.model.ts` y `core/models/kpi-snapshot.model.ts`
(con `WsMessage`/`WsTickMessage`/`StateBusSnapshot`/`KpiSnapshot`/`Robot`)
**no son usados por ningún componente** — parecen un borrador anterior de
contrato que quedó sin conectar. Su forma (`{type, payload}`, `kpis` en
minúscula sin `completados/capacidad/cajasPresentes`, `Robot.robot_id`/`state`/
`assigned_task_id`) **no coincide** con lo que el bridge envía hoy (§3.1).
Sugerencia: eliminarlos o, si se prefiere usarlos como tipo del mensaje WS,
actualizarlos para que reflejen el payload real de §3.1 — pero no es necesario
para que la integración funcione, porque la UI usa `BusState`/`KpisComputed`.

---

## 6. Verificación end-to-end

1. Backend: `uvicorn api.server:app --reload --port 8000` (rama `integracion-m1-m2`).
2. Frontend: `cd m1 && ionic serve` (puerto 8100).
3. En la página de configuración, subir `ola.csv`/`reposicion.csv` de ejemplo
   (`data/ola.csv`, `data/reposicion.csv`), aplicar config y dar Play.
4. Verificar en devtools (Network → WS) que llegan mensajes `{"type":"tick",...}`
   sin errores de CORS, y que el dashboard/grilla reflejan `tick` y KPIs en
   movimiento.
5. Probar `/control/pause`, `/control/reset`, cambio de política — el estado
   debe reflejarse sin recargar la página.

---

## 7. Referencias

- `docs/diagnostico_integracion_m1_m2.md` — diagnóstico completo y respuestas
  previas de Alonso sobre el contrato.
- `docs/bus_api.md` — contrato interno del `StateBus` (M2 ↔ Bus).
- `api/server.py`, `api/serializers.py`, `api/loop_worker.py` — implementación
  del bridge (fuente de verdad del contrato).
- `tests/test_api_bridge.py` — ejemplos ejecutables de cada endpoint.
