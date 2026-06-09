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

## 4. Propuesta recomendada: HTTP polling (Opción A)

### Arquitectura con bridge

```
┌──────────────────┐    HTTP/JSON    ┌────────────────────────────────┐
│   M1 · Angular   │ ◀────────────── │  api/server.py  (FastAPI)      │
│  BusClientService│ ──────────────▶ │  GET  /snapshot                │
│  (reemplazar     │                 │  POST /config                  │
│   lógica PRNG)   │                 │  POST /control/play            │
└──────────────────┘                 │  POST /control/pause           │
                                     │  POST /control/reset           │
                                     └──────────────┬─────────────────┘
                                                    │ lee/escribe
                                                    ▼
                                          StateBus (Python)
                                                    │
                                          AutoStoreSimulator (M2)
```

### Contrato de los endpoints

```
GET  /snapshot
     → StateSnapshot serializado a JSON
       { tick, modo, politica, grilla: [...], robots: [...],
         pedidos: { cola: [...], completados: [...] }, kpis: {...} }

POST /config
     body: { x, y, z, robots, ocupacion_inicial }
     → 200 OK

POST /control/play   → inicia el loop de simulación (hilo separado)
POST /control/pause  → pausa el loop
POST /control/reset  → resetea el simulador y el bus

POST /policy
     body: { politica: "fifo" | "prioridad_posicion" }
     → llama bus.set_policy(PoliticaPicking(value))
```

### Cambios necesarios en M1

Solo en `bus-client.service.ts`:
1. Reemplazar el `setInterval` con PRNG por `setInterval` que llama `GET /snapshot`.
2. Mapear la respuesta JSON al tipo `BusState` que ya usa la UI.
3. Los métodos de control (`setRunning`, `setMode`, `setPolicy`) pasan a llamar
   los endpoints `POST /control/...` y `POST /policy`.

La UI (dashboard, config, grilla view) **no necesita cambios** — solo cambia
de dónde viene el dato.

### Archivos a crear en M2

```
api/
├── server.py        # FastAPI app + endpoints
├── serializers.py   # StateSnapshot → dict JSON (camelCase para Angular)
└── loop.py          # loop de simulación en hilo separado
```

Dependencia adicional: `fastapi` + `uvicorn` (agregar a `requirements.txt`).

---

## 5. Preguntas abiertas para coordinar con Alonso

1. **Puerto del servidor**: ¿`localhost:8000`? ¿Necesita CORS habilitado para el dev server de Ionic?
2. **Frecuencia de polling en M1**: ¿cada 500ms? ¿Cada tick del motor?
3. **Formato de fechas y enums**: ¿M1 espera `"fifo"` o `"FIFO"`? Revisar el tipo `BusState` de M1.
4. **Autenticación**: Para el PoC académico no es necesaria. Confirmar.
5. **Manejo de errores en M1**: ¿Qué muestra la UI si el servidor Python no está corriendo?

---

## 6. Próximos pasos recomendados

| Prioridad | Tarea | Responsable |
|-----------|-------|-------------|
| Alta | Crear `api/server.py` con FastAPI (endpoints básicos) | Vicente |
| Alta | Actualizar `BusClientService` para consumir HTTP | Alonso |
| Media | Definir formato JSON de `StateSnapshot` (serializers.py) | Vicente + Alonso |
| Media | Test de integración completo: M2 corriendo + M1 conectado | Vicente + Alonso |
| Baja | Migrar a WebSocket si el polling resulta demasiado lento | — |
