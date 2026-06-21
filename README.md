# Simulación AutoStore — Forus S.A. (Grupo 12)

Repositorio del simulador AutoStore. Remoto: `https://github.com/samirabsaa/Simulacion_AutoStore.git`

## Estructura del proyecto

```
Simulacion_AutoStore/
├── api/                  # Bridge FastAPI — endpoints REST + WebSocket
├── bus_persistencia/     # Módulo Bus + Persistencia — T-01 a T-08
├── motor/                # Módulo M2 — Motor de Simulación
│   ├── simulador.py      # Orquestador central
│   ├── grilla.py         # Grilla 3D de almacenamiento
│   ├── despachador.py    # Despachador de robots
│   ├── politicas.py      # Políticas FIFO y Prioridad
│   ├── kpis.py           # Cálculo de los 7 KPIs
│   ├── modos.py          # Turno diurno y nocturno
│   └── run.py            # Standalone runner (CLI)
├── m1/                   # Módulo M1 — Frontend Angular/Ionic
├── tests/                # Tests del motor M2 (57 tests)
├── data/                 # config.json, ola.csv, reposicion.csv
├── docs/                 # Contrato API, guías de uso
└── output/               # sesion_*.csv, metadata, reporte_comp (runtime)
```

---

## Levantar el sistema completo (M1 + M2)

### Requisitos previos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Python | 3.9+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

---

### Backend (M2 + bridge FastAPI)

El backend expone la API REST y el WebSocket en `http://localhost:8000`.

#### Instalación (primera vez)

```bash
# Desde la raíz del repo: Simulacion_AutoStore/
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

#### Encender

```bash
# Desde Simulacion_AutoStore/ con el venv activo
source venv/bin/activate
uvicorn api.server:app --reload --port 8000
```

El servidor queda corriendo en `http://localhost:8000`. La bandera `--reload`
recarga automáticamente al guardar cambios en el código.

#### Apagar

Presiona `Ctrl + C` en la terminal donde corre uvicorn.

Para desactivar el entorno virtual:

```bash
deactivate
```

---

### Frontend (M1 — Angular/Ionic)

El frontend corre en `http://localhost:8100` y se conecta automáticamente al
backend en `localhost:8000`.

#### Instalación (primera vez)

```bash
cd m1/
npm install
```

#### Encender

```bash
cd m1/
npm start           # equivalente a: npx ionic serve
```

El navegador se abre solo en `http://localhost:8100`. El servidor recarga al
guardar cambios en el código fuente.

#### Apagar

Presiona `Ctrl + C` en la terminal donde corre el servidor de desarrollo.

---

### Orden recomendado al trabajar

```
1. Levantar backend  →  source venv/bin/activate && uvicorn api.server:app --reload --port 8000
2. Levantar frontend →  cd m1/ && npm start
3. Abrir navegador   →  http://localhost:8100
4. Apagar frontend   →  Ctrl+C en la terminal del frontend
5. Apagar backend    →  Ctrl+C en la terminal del backend, luego deactivate
```

> Si solo quieres probar la UI sin el backend, el frontend igual arranca y el
> heatmap anima localmente. Las llamadas HTTP/WS fallan en silencio hasta que
> el backend esté disponible.

---

## Requisitos previos (solo backend, sin frontend)

- Python 3.9+
- `pip install -r requirements.txt`

No requiere NVIDIA Omniverse, GPU, ni interfaz gráfica.

## Ejecutar una simulación (standalone)

```bash
# FIFO (predeterminado)
python -m motor.run --policy fifo --ticks 100

# Prioridad por Posición
python -m motor.run --policy prioridad_posicion --ticks 200 --seed 42

# Demo comparativa P09 (FIFO vs Prioridad + reporte)
python -m motor.run --compare --ticks 100

# Modo silencioso
python -m motor.run --policy fifo --ticks 50 --quiet
```

Documentación:
- [docs/guia_uso_m2.md](docs/guia_uso_m2.md) — guía completa de uso y tests
- [docs/bus_api.md](docs/bus_api.md) — contrato para M1, M2, M3
- [docs/integracion_grupo12.md](docs/integracion_grupo12.md) — diagrama de integración

## Ejecutar todos los tests

```bash
# Todos los tests (motor + bus)
python -m pytest tests/ bus_persistencia/tests/ -v
```

**88 tests total:** 57 tests del motor M2 + 31 tests del bus/persistencia.

### Solo motor M2

```bash
python -m pytest tests/ -v
```

### Solo bus + persistencia

```bash
python -m pytest bus_persistencia/tests/ -v
```

### Solo demo P09 (para evaluación)

```bash
python -m pytest tests/test_p09_demo.py -v
```

### Demo de integración (mock M1/M2/M3)

```bash
python -m bus_persistencia.integration
```

---

## Módulo Bus + Persistencia

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
