# Guía de uso — Motor M2 (simulación sin UI ni Omniverse)

## Requisitos

```bash
pip install -r requirements.txt
```

Solo necesita Python 3.9+ y pytest. **No requiere NVIDIA Omniverse ni ninguna GPU.**

---

## 1. Ejecutar una simulación (standalone)

### Uso básico

```bash
python -m motor.run --policy fifo --ticks 100
```

### Opciones disponibles

| Argumento | Default | Descripción |
|---|---|---|
| `--policy` | `fifo` | Política de picking: `fifo` o `prioridad_posicion` |
| `--ticks` | `100` | Máximo de ticks a simular |
| `--seed` | `42` | Semilla para reproducibilidad |
| `--config` | `data/config.json` | Ruta al archivo de configuración |
| `--ola` | `data/ola.csv` | Ruta al archivo de pedidos |
| `--output` | `output/` | Directorio de salida |
| `--quiet` | — | Modo silencioso (solo muestra resultado final) |
| `--compare` | — | Ejecuta FIFO y Prioridad, genera reporte comparativo |

### Ejemplos

```bash
# Ejecución simple con FIFO
python -m motor.run --policy fifo --ticks 50

# Ejecución con Prioridad por Posición
python -m motor.run --policy prioridad_posicion --ticks 200 --seed 123

# Modo silencioso (útil para scripts)
python -m motor.run --policy fifo --ticks 100 --quiet

# Demo comparativa P09: ejecuta ambas políticas y genera reporte
python -m motor.run --compare --ticks 100
```

### Salida esperada

Al ejecutar `python -m motor.run --policy fifo --ticks 30`:

```
  Grilla: 10x10x5
  Cajas iniciales: 353
  Robots: 4
  Pedidos: 4
  Politica: fifo
  Semilla: 42

  Tick   10 | TSP= 25.00%  MTRP=  31.00  TBR=140.00%  IOG= 70.4%
  Tick   20 | TSP= 25.00%  MTRP=  51.00  TBR=170.00%  IOG= 70.4%
  Tick   30 | TSP= 25.00%  MTRP=  71.00  TBR=180.00%  IOG= 70.4%

  -------- RESULTADOS --------
  Ticks:        31
  Pedidos:      1/4
  Tiempo:       0.28s

  KPI      Valor
  -------- ------------
  TSP      25.00
  TPCP     8.00
  MTRP     71.00
  IOG      70.40
  TR       0.03
  TI       0.00
  TBR      180.00

  Salida: output/sesion_fifo_s42.csv
```

---

## 2. Archivos de salida

| Archivo | Contenido |
|---|---|
| `output/sesion_*.csv` | Registro cronológico de eventos (timestamp, tick, tipo, payload) |
| `output/sesion_*.meta.json` | Metadatos de la ejecución (semilla, hashes, política, KPIs finales) |
| `output/metadata/metadata_*.json` | Metadatos adicionales para reproducibilidad |
| `output/reporte_comp.csv` | Reporte comparativo entre políticas (solo con `--compare`) |

### Formato de `reporte_comp.csv`

```
KPI,FIFO_75,Prioridad_90,Delta_%
TSP,25.00,25.00,+0.00%
MTRP,64.00,64.00,+0.00%
TBR,186.67,186.67,+0.00%
```

---

## 3. Ejecutar los tests

### Todos los tests (motor + bus + persistencia)

```bash
python -m pytest tests/ bus_persistencia/tests/ -v
```

88 tests en total: 57 tests de motor + 31 tests de bus/persistencia.

### Solo tests del motor M2

```bash
python -m pytest tests/ -v
```

57 tests que validan:

| Archivo | Tests | Qué valida |
|---|---|---|
| `test_contrato_m2_bus.py` | 5 | Contrato M2 ↔ Bus (single-writer, delta, snapshots) |
| `test_despachador_kpis.py` | 13 | Despachador + KPIs (rutas, excavación, colisiones) |
| `test_motor_grilla.py` | 5 | Grilla 3D (SKU search, excavación, puertos) |
| `test_motor_politicas.py` | 5 | Políticas FIFO y Prioridad por Posición |
| `test_motor_kpis.py` | 8 | Cálculo de los 7 KPIs (TSP, MTRP, TBR, etc.) |
| `test_motor_despachador.py` | 5 | Excavación multi-nivel, colisiones, eventos |
| `test_motor_modos.py` | 6 | Turno nocturno, reposición, grilla llena |
| `test_motor_simulador.py` | 6 | Sesión completa, cambio de modo, reproducibilidad |
| `test_p09_demo.py` | 3 | **P09**: FIFO @ 75%, Prioridad @ 90%, reporte comparativo |

### Solo tests del bus + persistencia

```bash
python -m pytest bus_persistencia/tests/ -v
```

31 tests del bus de estado, loaders, logger, reportes.

### Solo tests P09 (para evaluación)

```bash
python -m pytest tests/test_p09_demo.py -v
```

---

## 4. Organización del proyecto

```
tests/
├── test_contrato_m2_bus.py        # Contrato M2-Bus (5 tests)
├── test_despachador_kpis.py       # Despachador + KPIs (13 tests)
├── test_motor_grilla.py           # Grilla 3D (5 tests)
├── test_motor_politicas.py        # Políticas de picking (5 tests)
├── test_motor_kpis.py             # KPIs (8 tests)
├── test_motor_despachador.py      # Despachador avanzado (5 tests)
├── test_motor_modos.py            # Turno nocturno (6 tests)
├── test_motor_simulador.py        # Simulador completo (6 tests)
├── test_p09_demo.py               # P09 demo (3 tests)

motor/
├── run.py                         # Standalone runner (CLI)
├── simulador.py                   # Orquestador central
├── grilla.py                      # Grilla 3D
├── despachador.py                 # Despachador de robots
├── politicas.py                   # Políticas FIFO / Prioridad
├── kpis.py                        # Cálculo de KPIs
├── modos.py                       # Turno diurno/nocturno
```

---

## 5. Notas para la evaluación (P09)

### Demostradores requeridos

| | Demo 1 | Demo 2 |
|---|---|---|
| Política | FIFO | Prioridad por posición |
| Resultado esperado | Referencia base | MTRP menor, TBR mayor |

### Cómo ejecutar la demo P09

```bash
# Opción 1: usando el runner standalone
python -m motor.run --compare --ticks 100

# Opción 2: usando los tests
python -m pytest tests/test_p09_demo.py -v
```

Ambos métodos generan `output/reporte_comp.csv` con los KPIs comparados.

### Requisitos para la demo corran sin errores

- Los archivos `data/config.json` y `data/ola.csv` deben existir (ya incluidos)
- El directorio `output/` se crea automáticamente
- No se necesita ninguna dependencia externa más que pytest
- No se necesita NVIDIA Omniverse ni GPU
- No se necesita interfaz gráfica (tkinter, etc.)

---

## 6. Solución de problemas

### "pytest no encontrado"

```bash
pip install pytest
```

### "UnicodeEncodeError" en consola Windows

El runner usa solo caracteres ASCII para compatibilidad con la consola de Windows.
Si ves caracteres extraños, usa `--quiet` para silenciar la salida.

### Los KPIs no coinciden entre ejecuciones

Usa el mismo valor de `--seed` para obtener resultados reproducibles.
Diferentes semillas producen diferentes distribuciones iniciales de cajas.
