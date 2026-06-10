# Diagnóstico de Integración M1↔M2

> **Fecha:** 2026-06-08
> **Autor:** Vicente Rosales (Responsable General)
> **Estado M1:** rama `origin/m1` — Ionic 8 + Angular 20, UI completa
> **Estado M2:** rama `test-integracion-m2-bus` — motor completo, 18/18 tests

---

## 1. Hallazgo: M1 no está conectado al StateBus de Python

El módulo M1 implementa una UI completa (dashboard de KPIs, configuración,
vista de grilla), pero su capa de datos es **completamente sintética**.

Archivo clave: `m1/src/app/core/services/bus-client.service.ts`

```
BusClientService
  └─ BehaviorSubject<BusState>
       └─ estado generado internamente con mulberry32 PRNG
            (no hay HTTP fetch, WebSocket, ni conexión a Python)
```

M1 simula el comportamiento del bus localmente para desarrollar la UI de forma
independiente — decisión correcta en esta etapa. Ahora hay que conectarlos.

---

## 2. Por qué no se pueden conectar directamente

M2 (Python) y M1 (Angular en browser) viven en entornos de ejecución distintos:

```
M2: proceso Python  ──  StateBus (en memoria)  ──  bus_persistencia
M1: browser/Ionic   ──  Angular Service         ──  JavaScript/TypeScript
```

M1 no puede importar `bus_persistencia` directamente porque:
- Es TypeScript corriendo en el browser, no Python.
- El `StateBus` vive en el proceso del motor, no en el frontend.

Necesitan una **capa de transporte** entre ambos.

---

## 3. Opciones de integración

| Opción | Descripción | Complejidad | Adecuado para PoC |
|--------|------------|-------------|-------------------|
| **A — HTTP polling** | Python expone `/snapshot` vía FastAPI; M1 hace fetch periódico | Baja | ✅ Recomendada |
| **B — WebSocket** | FastAPI + WebSocket push en cada tick; M1 suscribe | Media | ✅ Viable |
| **C — Archivos JSON** | M2 escribe `state.json`; M1 hace polling del archivo | Muy baja | ⚠️ Frágil |

---

## 4. Solución implementada: bridge FastAPI con WebSocket (Opción B)

> **Actualizado 2026-06-09** — Alonso confirmó que `BusClientService` ya espera un
> WebSocket (`ws://localhost:8000/ws/state`) que empuja un mensaje `{type: "tick",
> ...}` por cada tick, no solo polling de `/snapshot`. La Opción B del diagnóstico
> original es la elegida; `GET /snapshot` se mantiene como fallback de
> debug/lectura puntual. Implementado en `api/server.py`, `api/serializers.py` y
> `api/loop_worker.py` (T-45).

### Arquitectura con bridge

```
┌──────────────────┐   WS  ws://localhost:8000/ws/state   ┌─────────────────────────────┐
│   M1 · Angular   │ ◀──────────── push por tick ───────── │  api/server.py  (FastAPI)   │
│  BusClientService│                                       │  GET  /snapshot             │
│  (puerto 8100)   │ ───────────── HTTP/JSON ────────────▶ │  POST /config               │
└──────────────────┘                                       │  POST /policy               │
                                                            │  POST /control/play|pause   │
                                                            │       |reset|speed          │
                                                            │  POST /api/upload/{ola|     │
                                                            │       reposicion}           │
                                                            └──────────────┬──────────────┘
                                                                           │ lee/escribe
                                                                           ▼
                                                                 StateBus (Python)
                                                                           │
                                                                 AutoStoreSimulator (M2)
                                                              en threading.Thread (loop_worker)
```

### Contrato de los endpoints (implementado)

```
GET  /snapshot
     → mismo payload que el WS (sin "type"), para lectura puntual/debug

WS   /ws/state
     → al conectar, envía el snapshot actual; luego un mensaje por tick:
       { type: "tick", tick, mode: "DIURNO"|"NOCTURNO",
         policy: "FIFO"|"PRIORIDAD_POSICION", status: "IDLE"|"RUNNING"|"PAUSED"|"FINISHED",
         velocidad, grid: {x,y,z} | null, robots: [...], grilla: [...],
         pedidos: { cola: [...], completados: [...] },
         kpis: { tsp, tpcp, mtrp, iog, tr, ti, tbr, completados, capacidad, cajasPresentes } }

POST /config
     body (GridConfigDTO): { x, y, z, num_robots, occupancy_pct, mode, policy,
                              session_name?, semilla?, pedidos_demandados? }
     → bus.reset(config) + reaplica modo/política/pedidos + inicializa el simulador

POST /policy
     body: { policy: "FIFO" | "PRIORIDAD_POSICION" }
     → cambia la política activa (se preserva en /control/reset)

POST /control/play   → inicia/reanuda el loop de simulación (hilo separado)
POST /control/pause  → pausa el loop
POST /control/reset  → vuelve al tick inicial con la config/política/pedidos vigentes
POST /control/speed  body: { velocidad: 1|2|5 } → ajusta ticks/seg

POST /api/upload/ola         multipart "file" → { valid, errors: [{row, column, value, reason}] }
POST /api/upload/reposicion  multipart "file" → { valid, errors: [{row, column, value, reason}] }
```

CORS habilitado para `http://localhost:8100` (`allow_methods=["*"]`,
`allow_headers=["*"]`).

### Mapeo de enums (M2 ↔ M1) — `api/serializers.py`

| M2 (`bus_persistencia.models.state`) | M1 (`sim.enums.ts`) |
|---|---|
| `ModoTurno.DIURNO` / `NOCTURNO` | `"DIURNO"` / `"NOCTURNO"` |
| `PoliticaPicking.FIFO` / `PRIORIDAD_POSICION` | `"FIFO"` / `"PRIORIDAD_POSICION"` |
| `RobotEstado` (7 valores) | `RobotState` (5 valores) — `excavando`/`recuperando`/`reponiendo` → `"PICKING"`, `desplazandose` → `"MOVING"`, `bloqueado` → `"BLOCKED"`, `inactivo` → `"IDLE"`, `entregando` → `"DEPOSITING"` |

### Cambios necesarios en M1

En `bus-client.service.ts`: reemplazar el `BehaviorSubject` con PRNG por una
conexión a `ws://localhost:8000/ws/state` (URLs en `environment.ts`), y mapear
los métodos de control (`setRunning`, `setMode`, `setPolicy`, subir CSVs) a los
endpoints `POST /control/...`, `/policy` y `/api/upload/...`. La UI (dashboard,
config, grilla view) no necesita cambios — solo cambia de dónde viene el dato.

### Archivos creados en M2

```
api/
├── __init__.py
├── server.py        # FastAPI app, CORS, endpoints REST + WS
├── serializers.py   # mapeos de enums + snapshot_to_payload
└── loop_worker.py   # SimulationLoop (hilo, play/pause/reset/speed)
```

Dependencias agregadas a `requirements.txt`: `fastapi`, `uvicorn[standard]`,
`httpx`, `python-multipart`.

---

## 5. Preguntas abiertas — respondidas por Alonso (2026-06-09)

1. **Puerto del servidor**: FastAPI en `:8000`, Ionic dev server en `:8100`. CORS
   habilitado para `http://localhost:8100`. ✅ Implementado en `api/server.py`.
2. **Frecuencia/transporte**: no es polling — M1 espera **WebSocket**
   (`ws://localhost:8000/ws/state`) con un push por cada tick del motor.
   ✅ Implementado (`SimulationLoop` notifica a los websockets conectados tras
   cada `avanzar_tick()`).
3. **Formato de enums**: M1 espera **mayúsculas** (`"FIFO"`, `"DIURNO"`,
   `"PRIORIDAD_POSICION"`, etc.) y `kpis` con claves en **minúscula** (`tsp`,
   `tpcp`, ...) más `completados`, `capacidad`, `cajasPresentes`. ✅ Mapeos en
   `api/serializers.py`.
4. **Autenticación**: no es necesaria para el PoC académico. Confirmado.
5. **Manejo de errores en M1**: fuera del alcance de M2 — responsabilidad de
   `BusClientService` (reconexión de WebSocket, estado "desconectado" en la UI).
6. **Carga de CSV**: `POST /api/upload/{ola|reposicion}` multipart, responde
   `{valid, errors: [{row, column, value, reason}]}`. ✅ Implementado reusando
   `load_ola`/`load_reposicion` de `bus_persistencia.persistence`.

---

## 6. Próximos pasos recomendados

| Prioridad | Tarea | Responsable | Estado |
|-----------|-------|-------------|--------|
| Alta | Crear `api/server.py` con FastAPI + WebSocket | Vicente | ✅ Hecho (T-45) |
| Alta | Actualizar `BusClientService` para consumir el WebSocket real | Alonso | Pendiente |
| Media | Definir formato JSON de `StateSnapshot` (serializers.py) | Vicente + Alonso | ✅ Hecho |
| Media | Test de integración completo: M2 corriendo + M1 conectado | Vicente + Alonso | Pendiente |
