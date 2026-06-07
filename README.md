# Simulación AutoStore — Forus S.A. (Grupo 12)

Repositorio del simulador AutoStore. Remoto: `https://github.com/samirabsaa/Simulacion_AutoStore.git`

## Estructura del proyecto

```
Simulacion_AutoStore/
├── bus_persistencia/     # Módulo Bus + Persistencia — T-01 a T-08
├── data/                 # config.json, ola.csv, reposicion.csv
├── docs/                 # Contrato API e integración con M1/M2/M3
└── output/               # sesion_*.csv, metadata, reporte_comp (generado en runtime)
```

## Requisitos

- Python 3.9+
- `pip install -r requirements.txt`

## Módulo Bus + Persistencia

```bash
pip install -r requirements.txt
pytest
python -m bus_persistencia.integration
```

30 tests cubren T-01 a T-08 y casos P01, P02, P05, P10.

### Uso rápido

```python
from bus_persistencia import StateBus
from bus_persistencia.persistence import load_config, load_ola
from bus_persistencia.bus.state_bus import M2_WRITER_ID
from bus_persistencia.models.state import TickDelta, KPISet

bus = StateBus()
config = load_config("data/config.json")
if config.is_valid:
    bus.set_config(config.data)

snap = bus.read_snapshot()
bus.write_tick_delta(M2_WRITER_ID, TickDelta(kpis=KPISet(TSP=95.0)))
```

Documentación:
- [docs/bus_api.md](docs/bus_api.md) — contrato para M1, M2, M3
- [docs/integracion_grupo12.md](docs/integracion_grupo12.md) — diagrama de integración

### Migración desde `StateBuTemporal.py`

M1 usó un mock en la raíz. La implementación real está en `bus_persistencia/`:

```python
# Antes (mock)
from StateBuTemporal import bus

# Después (producción)
from bus_persistencia import StateBus
bus = StateBus()
```

## Tareas Bus + Persistencia

| ID | Descripción |
|----|-------------|
| T-01 | Bus de Estado Central |
| T-02 | Single-writer / multiple-reader + Lock |
| T-03 | config.json |
| T-04 | ola.csv |
| T-05 | reposicion.csv |
| T-06 | sesion_X.csv (buffer diferido) |
| T-07 | reporte_comp.csv |
| T-08 | Reproducibilidad (semilla) |
