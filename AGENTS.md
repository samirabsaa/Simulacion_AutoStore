# AGENTS.md — AutoStore Simulator

Compact reference for AI coding agents. See `CLAUDE.md` for full project context and `docs/` for contracts.

## Entrypoints

| Purpose | Command |
|---|---|
| Standalone simulation | `python -m motor.run --policy fifo --ticks 100` |
| P09 demo (both policies, report) | `python -m motor.run --compare --ticks 100` |
| All 88 tests | `python -m pytest tests/ bus_persistencia/tests/ -v` |
| Motor tests only | `python -m pytest tests/ -v` |
| Bus tests only | `python -m pytest bus_persistencia/tests/ -v` |
| FastAPI bridge (backend) | `uvicorn api.server:app --reload --port 8000` |
| Frontend (M1 Angular/Ionic) | `cd m1/ && npm start` |

## Architecture rules

- **Single writer**: Only `M2_WRITER_ID = "M2"` can call `bus.write_tick_delta()`. M1/M3 only read via `bus.read_snapshot()`. `WriterNotAuthorizedError` is enforced in code.
- **Delta writes**: M2 writes `TickDelta` (only changed fields per tick). Bus applies merge-by-id for robots, merge-by-cell for grilla.
- **Policy**: Set by M1 via `bus.set_policy()`. M2 **reads only** — never writes policy.
- **Config + pedidos**: M1 writes them to bus (`set_config`, `set_pedidos_cola`). M2 calls `inicializar_desde_bus()` to consume them.
- **M2 runs standalone**: no GPU, no Omniverse, no UI required. M3 failure does not block M2.

## Project layout (key dirs)

```
motor/          # M2 engine — pure Python, no GPU
  simulador.py  # AutoStoreSimulator (orchestrator)
  despachador.py# Central dispatcher (all robot intelligence)
  grilla.py     # 3D grid, O(1) by (x,y,z)
  politicas.py  # FIFO / PRIORIDAD_POSICION
  kpis.py       # 7 KPIs per tick
  modos.py      # Day/night shift processing
  run.py        # Standalone CLI runner
  colmena.py    # Mente Colmena (traffic coordination)
  escorts.py    # Excavation coordination (anti-livelock)
api/            # FastAPI bridge (:8000)
  server.py     # Routes, WebSocket /ws/state
  loop_worker.py# SimulationLoop — runs M2 in daemon thread
bus_persistencia/ # Bus + Persistence (single package)
  bus/state_bus.py  # StateBus (threading.Lock)
  models/state.py   # TickDelta, StateSnapshot, enums, dataclasses
  persistence/      # Loaders, SessionLogger, MetadataStore, report generator
tests/              # 57 motor tests
bus_persistencia/tests/  # 31 bus/persistence tests
m1/                 # Angular/Ionic frontend (:8100)
data/               # config.json, ola.csv, reposicion.csv
output/             # Runtime output (gitignored) — sesion_*.csv, metadata, reporte_comp.csv
```

## Critical models (from `bus_persistencia/models/state.py`)

- `ModoTurno.DIURNO="diurno"`, `ModoTurno.NOCTURNO="nocturno"`
- `PoliticaPicking.FIFO="fifo"`, `PoliticaPicking.PRIORIDAD_POSICION="prioridad_posicion"`
- `RobotEstado`: inactive, desplazandose, excavando, recuperando, bloqueado, entregando, reponiendo, rotando, necesita_handoff, en_transito_anillo
- `Orientacion`: NORTE="N", ESTE="E", OESTE="O" (no SUR)
- 7 KPIs: TSP, TPCP, MTRP, IOG, TR, TI, TBR

## Conventions

- **Commits**: `WIP:` prefix for work-in-progress; module prefix for ready code (`motor:`, `bus:`, `ui:`, `m3:`)
- **Test naming**: `pytest` only (no unittest). Fixtures in `bus_persistencia/tests/fixtures/`.
- **pytest.ini** sets `pythonpath = .`, `testpaths = bus_persistencia/tests`
- **`conftest.py`** in bus_persistencia/tests/ inserts root into sys.path (motor tests rely on running from root, not conftest)

## Dependencies

```
pytest>=8.0.0, fastapi>=0.110.0, uvicorn[standard]>=0.29.0, httpx>=0.27.0, python-multipart>=0.0.9
```

Not required: Omniverse, GPU, `rich` (optional for dashboard).

## Testing quirks

- `python -m` is required for `motor.run` (uses relative imports)
- Tests call `load_config` / `load_ola` from `bus_persistencia.persistence`
- Integration demo: `python -m bus_persistencia.integration` (mock M1/M2/M3)
- P09 demo test: `python -m pytest tests/test_p09_demo.py -v`
- `output/` is gitignored; created at runtime if missing

## What is OUT OF SCOPE

- No sorter/classifier to loading docks
- No external optimization algorithm injection
- No real-time communication with physical AutoStore
- No intelligent night-shift reordering
- No more than 2 picking policies in this version
