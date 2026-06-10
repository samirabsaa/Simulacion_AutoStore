# Contrato de API — Bus de Estado Central

Documento de integración para equipos M1 (UI), M2 (Motor) y M3 (Visualización 3D).

## Principios

1. **Single-writer**: solo M2 escribe estado de simulación por tick.
2. **Multiple-reader**: M1 y M3 leen snapshots inmutables (copia profunda).
3. **Escritura delta**: M2 envía solo campos modificados por tick.
4. **Python puro**: sin dependencias de Omniverse en este módulo.

## Clase principal: `StateBus`

```python
from bus_persistencia import StateBus, TickDelta
from bus_persistencia.bus.state_bus import M2_WRITER_ID
```

### M1 — UI / Configuración

| Método | Descripción |
|--------|-------------|
| `set_config(config)` | Publica parámetros de grilla antes de Play |
| `set_modo(ModoTurno.DIURNO \| NOCTURNO)` | Selector de turno |
| `set_policy(PoliticaPicking.FIFO \| PRIORIDAD_POSICION)` | Política de picking |
| `set_pedidos_cola(list[Pedido])` | Carga ola de pedidos validada |
| `read_snapshot()` | Panel KPIs en vivo |
| `get_metadata()` | dict con tick, modo, política, kpis |

Validadores:

```python
from bus_persistencia.persistence import load_config, load_ola, load_reposicion

result = load_config("data/config.json")
if result.is_valid:
    bus.set_config(result.data)
```

### M2 — Motor de Simulación

| Método | Descripción |
|--------|-------------|
| `write_tick_delta(M2_WRITER_ID, delta)` | Único punto de escritura; retorna tick |
| `read_snapshot()` | Leer política/modo/pedidos |

`TickDelta` campos opcionales:

- `grilla_delta`, `grilla_remove`, `robots_delta`
- `pedidos_cola`, `pedidos_completados_add`
- `kpis` (`KPISet`), `modo`, `eventos`

Tipos de evento para sesión: `movimiento`, `caja_recuperada`, `pedido_completado`, `excavacion`, `bloqueo`, `kpi_update`.

### M3 — Visualización 3D

| Método | Descripción |
|--------|-------------|
| `read_snapshot()` | Grilla, robots, tick para interpolación 60 Hz |

## Persistencia

### Entrada

| Archivo | Función | Columnas / campos |
|---------|---------|-------------------|
| `config.json` | `load_config()` | grilla.{x,y,z}, robots, ocupacion_inicial |
| `ola.csv` | `load_ola()` | id_pedido, id_sku, cantidad, destino |
| `reposicion.csv` | `load_reposicion()` | id_caja, id_sku, cantidad |

### Salida

| Archivo | Componente |
|---------|------------|
| `sesion_*.csv` | `SessionLogger` — buffer en memoria, flush al final de tick |
| `metadata_*.json` | `MetadataStore` — semilla, hashes, KPIs finales |
| `reporte_comp.csv` | `generate_report()` — 7 KPIs con Δ% |

## KPIs (7)

TSP, TPCP, MTRP, IOG, TR, TI, TBR — en `snapshot.kpis` (`KPISet`).

## Concurrencia

- Escritura con `threading.Lock()`.
- Objetivo P99 escritura < 1 ms (validado en tests).
- Test de estrés: 1000 ticks con 2 lectores concurrentes.

## Mock de integración

```python
from bus_persistencia.integration import run_integration_demo

result = run_integration_demo("output", semilla=42, num_ticks=50)
```

## Casos de prueba cubiertos

| Caso | Tarea |
|------|-------|
| P01 | T-03 config.json |
| P02 | T-04 ola.csv |
| P05 | T-06 sesion CSV + KPIs |
| P10 | T-07 reporte_comp.csv |
