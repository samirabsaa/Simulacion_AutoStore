# Diagrama de integración — Simulador AutoStore (Grupo 12)

Documento para alinear al equipo M1, M2, M3 y Bus + Persistencia sobre **cómo se conectan los módulos**.

**Responsables Bus + Persistencia:** Martín Vásquez, Guadalupe Marín  
**Contrato técnico detallado:** [bus_api.md](bus_api.md)

---

## 1. Arquitectura general

El simulador replica el almacén AutoStore de Forus S.A.: grilla 3D, robots, picking diurno y reposición nocturna. La solución se divide en **3 módulos funcionales** y **2 capas transversales**.

```mermaid
flowchart TB
    subgraph operador [Operador]
        User[Investigador / Operador]
    end

    subgraph m1 [M1 - UI Configuracion]
        UI[Pantalla config, Play/Pause, KPIs]
    end

    subgraph transversal [Capas transversales - Bus + Persistencia]
        Bus[StateBus - memoria compartida]
        Persist[Loaders + SessionLogger + Reportes]
    end

    subgraph m2 [M2 - Motor Simulacion - Python puro]
        Motor[Grilla, robots, despachador, KPIs]
    end

    subgraph m3 [M3 - Visualizacion 3D - Omniverse]
        Render[USD, animacion, camara]
    end

    subgraph archivos [Archivos planos]
        IN[(config.json\nola.csv\nreposicion.csv)]
        OUT[(sesion_X.csv\nmetadata.json\nreporte_comp.csv)]
    end

    User --> UI
    UI -->|configura y lee| Bus
    UI -->|valida CSV| Persist
    Motor -->|unico escritor por tick| Bus
    Render -->|solo lectura| Bus
    Bus --> Persist
    Persist --> IN
    Persist --> OUT
    Motor -.->|sin dependencia| Render
```

**Principio clave:** M2 no depende de Omniverse. Si M3 falla, M2 sigue calculando ticks y generando `sesion_X.csv`.

---

## 2. Roles por módulo

| Módulo | Equipo | Escribe en Bus | Lee del Bus | Archivos |
|--------|--------|----------------|-------------|----------|
| **M1** UI | Alonso, Eliseo | Config, modo, política, pedidos (antes de Play) | KPIs, tick, estado | Usa `load_config`, `load_ola`, `load_reposicion` |
| **M2** Motor | Manuel, Vicente | **Todo el estado por tick** (grilla, robots, KPIs, eventos) | Política, modo, pedidos al inicio de tick | Emite eventos → `sesion_X.csv` |
| **M3** 3D | Alex, Samira | — | Grilla, robots, tick | — |
| **Bus + Persistencia** | Martín, Guadalupe | — (infraestructura) | — | Entrada/salida CSV y JSON |

---

## 3. Reglas del Bus (obligatorias)

```mermaid
flowchart LR
    M2[M2 Motor] -->|write_tick_delta| Bus[StateBus]
    M1[M1 UI] -->|read_snapshot| Bus
    M3[M3 3D] -->|read_snapshot| Bus

    M1 -.->|PROHIBIDO escribir ticks| Bus
    M3 -.->|PROHIBIDO escribir| Bus
```

| Regla | Detalle |
|-------|---------|
| Single-writer | Solo M2 llama `write_tick_delta("M2", delta)` |
| Multiple-reader | M1 y M3 llaman `read_snapshot()` (copia inmutable) |
| Escritura delta | M2 envía solo campos que cambiaron en ese tick |
| Concurrencia | Escritura protegida con `threading.Lock()` |
| Latencia | Objetivo P99 escritura < 1 ms |

---

## 4. Flujo de una simulación completa

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operador
    participant M1 as M1 UI
    participant P as Persistencia
    participant Bus as StateBus
    participant M2 as M2 Motor
    participant M3 as M3 3D

    Op->>M1: Configura grilla, turno, politica
    M1->>P: load_config / load_ola o load_reposicion
    P-->>M1: datos validados o errores por fila
    M1->>Bus: set_config, set_modo, set_policy, set_pedidos_cola
    Op->>M1: Play
    M1->>M2: Iniciar loop de simulacion

    loop Cada tick
        M2->>Bus: read_snapshot politica/modo
        M2->>M2: Calcular movimientos, colisiones, KPIs
        M2->>Bus: write_tick_delta M2, delta
        Note over Bus: Lock, aplicar delta, buffer eventos
        Bus->>P: flush sesion CSV al final del tick
        M1->>Bus: read_snapshot KPIs en vivo
        M3->>Bus: read_snapshot animacion 60 Hz
    end

    Op->>M1: Fin / comparar ejecuciones
    M1->>P: generate_report ejec_A, ejec_B
    P-->>Op: reporte_comp.csv
```

---

## 5. Ciclo de un tick (vista M2)

```mermaid
flowchart TD
    Start[Inicio tick N] --> Read[Leer snapshot: politica, modo, pedidos]
    Read --> Logic[Logica M2: despachador, movimiento, excavacion]
    Logic --> Delta[Armar TickDelta]
    Delta --> Write["write_tick_delta(M2, delta)"]
    Write --> Lock[Adquirir Lock]
    Lock --> Apply[Aplicar delta al estado]
    Apply --> Events[Buffer eventos en memoria]
    Events --> Snap[Actualizar snapshot lectores]
    Snap --> Unlock[Liberar Lock]
    Unlock --> Flush[SessionLogger flush tick N]
    Flush --> End[Fin tick N]
```

---

## 6. Cómo conecta cada equipo (código mínimo)

### M1 — antes de Play

```python
from bus_persistencia import StateBus
from bus_persistencia.models.state import ModoTurno, PoliticaPicking
from bus_persistencia.persistence import load_config, load_ola, load_reposicion

bus = StateBus()  # instancia compartida del proceso

cfg = load_config("data/config.json")
if not cfg.is_valid:
    # mostrar error al usuario
    ...
else:
    bus.set_config(cfg.data)

if modo_diurno:
    ola = load_ola("data/ola.csv")
    if ola.is_valid:
        bus.set_pedidos_cola(ola.data)
else:
    rep = load_reposicion("data/reposicion.csv")
    ...

bus.set_modo(ModoTurno.DIURNO)
bus.set_policy(PoliticaPicking.FIFO)
```

### M1 — panel KPIs en vivo

```python
snap = bus.read_snapshot()
tsp = snap.kpis.TSP
tick_actual = snap.tick
```

### M2 — cada tick

```python
from bus_persistencia.bus.state_bus import M2_WRITER_ID
from bus_persistencia.models.state import TickDelta, KPISet

snap = bus.read_snapshot()
# usar snap.politica, snap.pedidos, snap.config

delta = TickDelta(
    grilla_delta=[...],
    robots_delta=[...],
    kpis=KPISet(TSP=95.0, IOG=72.0, ...),
    eventos=[
        {"tipo": "movimiento", "robot_id": 1, ...},
        {"tipo": "pedido_completado", "id_pedido": "P001"},
    ],
)
tick = bus.write_tick_delta(M2_WRITER_ID, delta)
```

### M3 — loop render

```python
snap = bus.read_snapshot()
for caja in snap.grilla:
    # actualizar USD en (caja.x, caja.y, caja.z)
for robot in snap.robots:
    # interpolar posicion entre snap.tick y frame anterior
```

---

## 7. Flujo de archivos

```mermaid
flowchart LR
    subgraph entrada [Entrada - M1 carga via Persistencia]
        C[config.json]
        O[ola.csv]
        R[reposicion.csv]
    end

    subgraph runtime [Runtime]
        Bus[StateBus]
        SL[SessionLogger]
    end

    subgraph salida [Salida - fin de sesion]
        S[sesion_X.csv]
        M[metadata_X.json]
        RC[reporte_comp.csv]
    end

    C --> Bus
    O --> Bus
    R --> Bus
    Bus --> SL
    SL --> S
    Bus --> M
    M --> RC
    S --> RC
```

| Archivo | Columnas / contenido |
|---------|----------------------|
| `config.json` | grilla.{x,y,z}, robots, ocupacion_inicial |
| `ola.csv` | id_pedido, id_sku, cantidad, destino |
| `reposicion.csv` | id_caja, id_sku, cantidad |
| `sesion_X.csv` | timestamp, tick, tipo_evento, payload_json |
| `metadata_X.json` | semilla, hashes, modo, politica, kpis_finales |
| `reporte_comp.csv` | KPI, Ejecucion_A, Ejecucion_B, Delta_% |

**Eventos que M2 debe registrar:** `movimiento`, `caja_recuperada`, `pedido_completado`, `excavacion`, `bloqueo`, `kpi_update`.

---

## 8. Instancia compartida del Bus

Hoy la implementación es **in-process** (mismo proceso Python, objeto en memoria).

```mermaid
flowchart TB
    subgraph opcion_recomendada [Opcion A - Recomendada para integracion inicial]
        Main[Proceso principal Python]
        Main --> BusInst[StateBus singleton]
        Main --> M1Thread[M1 UI thread]
        Main --> M2Thread[M2 Motor thread]
        Main --> M3Proc[M3 Omniverse - lee mismo bus o replica snapshot]
        M1Thread --> BusInst
        M2Thread --> BusInst
    end
```

**Acuerdo pendiente con el grupo:** quién crea `StateBus()` y cómo lo reciben M2 y M3 si corren en procesos separados (IPC futuro).

---

## 9. Qué desbloquea Bus + Persistencia

| Tarea | Equipos que dependen |
|-------|---------------------|
| T-01 Bus | M2 T-09, M1 T-24, M3 T-32 |
| T-02 Concurrencia | M1 T-27 Play/Pause |
| T-03–05 Validadores | M1 T-25, T-29 |
| T-06 SessionLogger | M2 T-21 logging |
| T-07 Reporte | M1 T-31 nombre ejecución |
| T-08 Semilla | RNF-04 reproducibilidad |

---

## 10. Demo de integración (ya disponible)

Para probar el flujo sin esperar a M2/M3 reales:

```bash
cd autostore-sim
pytest                                    # 28 tests
python -m bus_persistencia.integration    # mock M1+M2+M3
```

Código de referencia: `bus_persistencia/integration/mock_modules.py`

---

## 11. Checklist reunión de integración

- [ ] Acordar quién instancia `StateBus` y dónde vive
- [ ] M1 confirma uso de `load_config`, `load_ola`, `load_reposicion` (no parsear CSV propio)
- [ ] M2 confirma formato de `TickDelta` y tipos de evento
- [ ] M3 confirma lectura de `read_snapshot()` e interpolación por tick
- [ ] Definir valores por defecto Forus (grilla 10×10×5, 4 robots, 70% ocupación)
- [ ] Probar demo: `python -m bus_persistencia.integration`
- [ ] Revisar [bus_api.md](bus_api.md) y marcar dudas

---

## 12. Contacto módulo Bus + Persistencia

- **API:** `docs/bus_api.md`
- **Tests:** `bus_persistencia/tests/` (P01, P02, P05, P10)
- **Mocks:** `bus_persistencia/integration/mock_modules.py`
