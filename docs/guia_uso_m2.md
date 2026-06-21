# Guía de uso — Motor M2 (simulación sin UI ni Omniverse)

## Requisitos

```bash
pip install -r requirements.txt
```

Solo necesita Python 3.10+ y pytest. **No requiere NVIDIA Omniverse ni ninguna GPU.**

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
| `--realtime`, `-r` | — | Modo en vivo: muestra dashboard actualizado cada tick |
| `--delay` | `0` | Milisegundos de espera entre ticks en modo realtime |
| `--no-rich` | — | Usa ANSI puro en lugar de rich (más ligero, compatible sin rich) |
| `--no-clear` | — | No limpia la pantalla entre ticks (útil para depuración) |
| `--matrix` | — | Incluye vista de matriz 2D de la grilla en tiempo real |

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

# Modo en vivo con dashboard Rich (si rich está instalado)
python -m motor.run --policy fifo --ticks 50 --realtime --delay 200

# Modo en vivo con matriz 2D de la grilla
python -m motor.run --policy fifo --ticks 50 --realtime --matrix --delay 200

# Modo en vivo con ANSI (sin rich, o forzado con --no-rich)
python -m motor.run --policy prioridad_posicion --ticks 50 -r --delay 100 --no-rich

# Modo DEBUG: no limpia pantalla entre ticks
python -m motor.run --policy fifo --ticks 30 --realtime --no-clear
```

### Modo en vivo (realtime)

El flag `--realtime` (o `-r`) muestra un **dashboard animado** que se actualiza cada tick:

- **Con Rich** (default si `rich` está instalado): tabla formateada con colores, barra de progreso, KPIs en línea
- **Con ANSI** (fallback automático, o forzado con `--no-rich`): misma información, formato de texto simple con códigos ANSI
- `--matrix` agrega una representación 2D de la grilla mostrando posiciones de robots y cajas
- La pantalla se limpia entre ticks (excepto con `--no-clear`)
- `--delay` controla la velocidad de actualización en milisegundos

Para instalar Rich (opcional):
```bash
pip install rich
```

### Salida esperada

Al ejecutar `python -m motor.run --policy fifo --ticks 50 --seed 42`:

```
Grilla: 10×10×5
  Cajas iniciales: 354
  Robots: 4
  Pedidos: 4
  Política: fifo
  Semilla: 42

  Tick   10 | TSP=100.00%  MTRP=   5.00  TBR=  7.50%  IOG= 70.0%
  [+] Sesión completada en 10 ticks

  -------- RESULTADOS --------
  Ticks:        11
  Pedidos:      4/4
  Tiempo:       0.09s

  KPI      Valor
  -------- ------------
  TSP      100.00
  TPCP     4.50
  MTRP     5.00
  IOG      70.00
  TR       0.40
  TI       0.00
  TBR      7.50

  Salida: output/sesion_fifo_s42.csv
```

La simulación se detiene automáticamente al completar todos los pedidos de la ola
(condición de término por ola completa) o al alcanzar el límite de ticks.

---

## 2. Archivos de salida

| Archivo | Contenido |
|---|---|
| `output/sesion_*.csv` | Registro cronológico de eventos (timestamp, tick, tipo, payload) |
| `output/sesion_*.meta.json` | Metadatos de la ejecución (semilla, hashes, política, KPIs finales) |
| `output/metadata/metadata_*.json` | Metadatos adicionales para reproducibilidad |
| `output/reporte_comp.csv` | Reporte comparativo entre políticas (solo con `--compare`) |

### Tipos de eventos en sesion_*.csv

| Evento | Descripción |
|---|---|
| `movimiento` | Robot se desplazó a una nueva celda XY |
| `bloqueo` | Robot no pudo avanzar (celda destino ocupada) |
| `excavacion` | Robot movió una caja superior a columna adyacente |
| `caja_recuperada` | Robot recogió la caja objetivo de la grilla |
| `pedido_completado` | Robot entregó la caja en un puerto/estación |
| `reruta` | Robot recalculó su ruta (BFS) tras bloqueo persistente |
| `tarea_cancelada` | Robot canceló su tarea (sin ruta alternativa viable) |
| `rotacion` | Robot rotó para alinearse con la orientación de una estación |
| `handoff` | Robot transfirió carga a un vecino mejor orientado |
| `estacion_saturada` | Robot esperó porque la estación alcanzó su capacidad por tick |
| `ola_completada` | Todos los pedidos de la ola fueron completados |

---

## 3. Resolución de colisiones y bloqueo

El despachador implementa 5 mecanismos (en orden de ejecución por tick) para evitar
que los robots queden bloqueados indefinidamente:

### 3.1 Cesión de paso (Paso 2.5)

Cuando un robot con tarea está `BLOQUEADO` porque un robot `INACTIVO` sin tarea ocupa
su siguiente celda, el robot ocioso se mueve a una celda adyacente libre.

**Cascada de 2 niveles:** si el robot ocioso no tiene celda libre (porque sus vecinos
también son ociosos), empuja a un vecino primero para liberar espacio. Esto permite
desbloquear clusters de robots inactivos.

### 3.2 Swap de interbloqueo (Paso 2.6)

Cuando dos robots `BLOQUEADO` quieren la celda del otro (deadlock mutuo), intercambian
posiciones en un solo tick.

### 3.3 BFS reruta

Si un robot lleva **3 ticks consecutivos bloqueado** (`UMBRAL_RERUTA = 3`), el
despachador recalcula su ruta usando BFS que rodea las celdas ocupadas por otros
robots. La nueva ruta puede ser no-lineal (a diferencia de la ruta L-shaped original).

- Profundidad máxima: 2× la distancia Manhattan al destino.
- Si el BFS encuentra una ruta diferente a la actual, la reemplaza y el robot avanza.

### 3.4 Cancelación de tarea

Si el BFS no encuentra ruta alternativa (ej: el destino mismo está ocupado), la tarea
se cancela: el robot vuelve a `INACTIVO`, la caja se libera, y el pedido vuelve a la
cola para reasignación en un tick futuro.

**Solo aplica en fase `mover_a_objetivo`** (el robot aún no ha recogido la caja). En
`mover_a_puerto` el robot ya carga la caja, así que espera en lugar de cancelar.

### 3.5 Exclusión de columnas

Al asignar una tarea, `_caja_disponible` excluye cajas en columnas donde otro robot
ya está excavando o recuperando. Esto previene que dos robots compitan por la misma
columna.

---

## 4. Features opcionales (config avanzada)

El motor soporta 5 features adicionales activables vía `config.json`. Todas son
**opt-in**: sin los campos extra, el motor se comporta como antes.

```json
{
  "x": 7, "y": 7, "z": 3,
  "robots": 4,
  "ocupacion": 70,
  "anillo_transito": true,
  "estaciones": [
    { "id": "CINTA1", "x": 0, "y": 3, "tipo": "cinta", "orientacion": "O" },
    { "id": "CARR1",  "x": 6, "y": 3, "tipo": "carrusel", "orientacion": "E" }
  ]
}
```

| Feature | Campo config | Efecto |
|---|---|---|
| Anillo de tránsito | `anillo_transito: true` | Columnas del perímetro son solo tránsito (no almacenan cajas) |
| Estaciones Cinta/Carrusel | `estaciones: [...]` | Entrega en estaciones con capacidad (Cinta=1/tick, Carrusel=2/tick) |
| Orientación de robots | (activa con estaciones) | Robots deben rotar para alinearse con la estación antes de entregar |
| Mente Colmena / Handoff | (activa con estaciones) | Robot mal orientado transfiere carga a vecino ya orientado |
| Término por ola completa | (siempre activa) | Simulación se detiene al completar todos los pedidos |

Documentación técnica completa en `docs/actualizacion_m2.md`.

---

## 5. Ejecutar los tests

### Todos los tests (motor + bus + bridge + persistencia)

```bash
python -m pytest tests/ bus_persistencia/tests/ -v
```

119 tests en total: 88 tests de motor/bridge + 31 tests de bus/persistencia.

### Solo tests del motor M2

```bash
python -m pytest tests/ -v
```

88 tests que validan:

| Archivo | Tests | Qué valida |
|---|---|---|
| `test_contrato_m2_bus.py` | 5 | Contrato M2 ↔ Bus (single-writer, delta, snapshots) |
| `test_despachador_kpis.py` | 14 | Despachador + KPIs (rutas, excavación, colisiones) |
| `test_motor_grilla.py` | 5 | Grilla 3D (SKU search, excavación, puertos) |
| `test_motor_politicas.py` | 5 | Políticas FIFO y Prioridad por Posición |
| `test_motor_kpis.py` | 9 | Cálculo de los 7 KPIs (TSP, MTRP, TBR, etc.) |
| `test_motor_despachador.py` | 5 | Excavación multi-nivel, colisiones, eventos |
| `test_motor_modos.py` | 6 | Turno nocturno, reposición, grilla llena |
| `test_motor_simulador.py` | 6 | Sesión completa, cambio de modo, reproducibilidad |
| `test_p09_demo.py` | 3 | **P09**: FIFO @ 75%, Prioridad @ 90%, reporte comparativo |
| `test_motor_m3_actualizaciones.py` | 16 | Anillo, estaciones, orientación, colmena, ola completa |
| `test_simulador_completa_pedidos.py` | 8 | Completitud de pedidos (ola corta y larga) |
| `test_api_bridge.py` | 6 | Bridge FastAPI (REST + WebSocket) |

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

## 6. Organización del proyecto

```
motor/
├── run.py                         # Standalone runner (CLI)
├── simulador.py                   # Orquestador central
├── grilla.py                      # Grilla 3D con anillo de tránsito
├── despachador.py                 # Despachador de robots (BFS, cesión, swap)
├── politicas.py                   # Políticas FIFO / Prioridad
├── kpis.py                        # Cálculo de KPIs
├── modos.py                       # Turno diurno/nocturno
├── colmena.py                     # Mente Colmena (reservation table, wait-for graph)
├── dashboard.py                   # Dashboard en vivo (Rich / ANSI)

tests/
├── test_contrato_m2_bus.py        # Contrato M2-Bus (5 tests)
├── test_despachador_kpis.py       # Despachador + KPIs (14 tests)
├── test_motor_grilla.py           # Grilla 3D (5 tests)
├── test_motor_politicas.py        # Políticas de picking (5 tests)
├── test_motor_kpis.py             # KPIs (9 tests)
├── test_motor_despachador.py      # Despachador avanzado (5 tests)
├── test_motor_modos.py            # Turno nocturno (6 tests)
├── test_motor_simulador.py        # Simulador completo (6 tests)
├── test_p09_demo.py               # P09 demo (3 tests)
├── test_motor_m3_actualizaciones.py # Actualizaciones M3 (16 tests)
├── test_simulador_completa_pedidos.py # Completitud de pedidos (8 tests)
├── test_api_bridge.py             # Bridge FastAPI (6 tests)
```

---

## 7. Notas para la evaluación (P09)

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

### Requisitos para la demo

- Los archivos `data/config.json` y `data/ola.csv` deben existir (ya incluidos)
- El directorio `output/` se crea automáticamente
- No se necesita ninguna dependencia externa más que pytest
- No se necesita NVIDIA Omniverse ni GPU
- No se necesita interfaz gráfica (tkinter, etc.)

---

## 8. Solución de problemas

### "pytest no encontrado"

```bash
pip install pytest
```

### "UnicodeEncodeError" en consola Windows

El dashboard usa emojis y caracteres Unicode. Si tu consola no los soporta:
- Usa `--no-rich` para forzar modo ANSI (menos caracteres especiales)
- Usa `--quiet` para silenciar toda la salida del dashboard
- O configura la consola con `chcp 65001` para UTF-8

### Los KPIs no coinciden entre ejecuciones

Usa el mismo valor de `--seed` para obtener resultados reproducibles.
Diferentes semillas producen diferentes distribuciones iniciales de cajas.
