# AutoStore Simulator — Contexto del proyecto para Claude Code

## Qué es este proyecto

Simulación funcional del sistema de almacenamiento automatizado AutoStore operado por
Forus S.A. en Santiago, gestionado por Neogística. El sistema real es una caja negra:
no expone su lógica interna. Esta simulación permite experimentar con políticas de
picking y niveles de ocupación mediante indicadores de desempeño cuantificables, sin
interferir con el sistema productivo.

Plataforma: NVIDIA Omniverse + Python 3.10. Esto es un PoC académico (PUCV, Taller
de Ingeniería de Software, Grupo 12), NO un gemelo digital ni un sistema de producción.

---

## Arquitectura — 3 módulos desacoplados + Bus

```
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│   M1 · UI       │    │   M2 · Motor         │    │  M3 · Omniverse  │
│  (tkinter)      │    │   (Python puro)      │    │  (USD / Kit SDK) │
│  config, KPIs   │    │   lógica completa    │    │  solo renderiza  │
│  controles      │    │   sin GPU            │    │  GPU RTX req.    │
└────────┬────────┘    └──────────┬───────────┘    └────────┬─────────┘
         │  lee                   │  escribe (único)        │  lee
         └────────────────────────▼─────────────────────────┘
                    ┌─────────────────────────────┐
                    │    Bus de Estado Central     │
                    │ bus_persistencia.bus.state_bus│
                    │  single-writer: solo M2      │
                    │  threading.Lock() por tick   │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │    Capa de Persistencia      │
                    │  config.json  ola.csv        │
                    │  reposicion.csv              │
                    │  sesion_X.csv  reporte.csv   │
                    └─────────────────────────────┘
```

**Regla crítica:** M2 es el ÚNICO escritor del Bus. M1 y M3 solo leen.
Si M3 falla, M2 sigue operando — el motor no depende de Omniverse.

---

## Estructura de carpetas

> **Actualizado** — la estructura `bus/` + `persistencia/` separados quedó obsoleta:
> Martín (Bus + Persistencia) implementó todo unificado en `bus_persistencia/`. Ver
> contrato técnico completo en `docs/bus_api.md` y `docs/integracion_grupo12.md`.

```
Simulacion_AutoStore/
├── bus_persistencia/      # Bus + Persistencia — implementación real (Martín, Guadalupe)
│   ├── bus/state_bus.py   # StateBus: write_tick_delta / read_snapshot
│   ├── models/state.py    # TickDelta, StateSnapshot, KPISet, enums, dataclasses
│   ├── persistence/       # loaders (config/ola/reposicion), SessionLogger, reportes
│   ├── integration/       # mocks M1/M2/M3 para probar el flujo end-to-end
│   └── tests/
├── motor/
│   ├── simulador.py       # AutoStoreSimulator — orquestador central de M2
│   ├── grilla.py          # Matriz 3D, O(1) por (x,y,z)
│   ├── despachador.py     # Cerebro central — asigna rutas a robots
│   ├── politicas.py       # FIFO y Prioridad por posición (funciones intercambiables)
│   ├── kpis.py            # Cálculo de los 7 KPIs por tick
│   └── modos.py           # Turno diurno (picking) y nocturno (reposición)
├── ui/
│   └── app.py             # App tkinter independiente de Omniverse
├── omniverse/
│   └── scene.py           # Grilla procedural USD, animación robots
├── data/
│   ├── config.json        # Parámetros de ejemplo (datos sintéticos)
│   ├── ola.csv            # Ola de pedidos de ejemplo (datos sintéticos)
│   └── reposicion.csv     # Cajas a reponer de ejemplo (datos sintéticos)
└── docs/
    ├── bus_api.md             # Contrato técnico del bus (Martín)
    └── integracion_grupo12.md # Diagrama de integración M1/M2/M3/Bus (Martín)
```

---

## Contrato del Bus de Estado

> **Actualizado tras la implementación real de Martín** (rama `bus-persistencia`,
> paquete `bus_persistencia`) — el contrato que sigue es DISTINTO al boceto inicial
> de este documento. Esta sección queda como resumen orientador; el contrato técnico
> exhaustivo vive en `docs/bus_api.md` y `docs/integracion_grupo12.md` — no se duplica
> aquí para evitar que ambos textos se desalineen.

```python
from bus_persistencia.bus.state_bus import StateBus, M2_WRITER_ID
from bus_persistencia.models.state import TickDelta, StateSnapshot, KPISet

# Lectura — M1 y M3 (snapshot inmutable, copia profunda, no bloqueante)
snap: StateSnapshot = bus.read_snapshot()
snap.tick, snap.modo, snap.politica, snap.grilla, snap.robots, snap.pedidos, snap.kpis

# Escritura — SOLO M2, una vez por tick, con un delta real (solo lo que cambió)
delta = TickDelta(
    grilla_delta=[...],            # Cajas agregadas/actualizadas
    grilla_remove=[(x, y, z), ...],# celdas a vaciar
    robots_delta=[...],
    pedidos_completados_add=[...],
    kpis=KPISet(TSP=..., IOG=..., ...),
    modo=None,                     # solo si M2 decide cambiar de turno
    eventos=[{"tipo": "movimiento", ...}, ...],
)
bus.write_tick_delta(M2_WRITER_ID, delta)  # lanza WriterNotAuthorizedError si no es M2
```

**Importante:**
- `politica` la fija el operador vía M1 (`bus.set_policy`) — M2 **solo la lee**, nunca
  la escribe (no es parte de `TickDelta`).
- El `SessionLogger` interno del bus bufferea los `eventos` del delta y los vuelca a
  `sesion_X.csv` / `metadata_*.json` automáticamente — M2 no escribe esos archivos.
- `WriterNotAuthorizedError` hace cumplir el single-writer **en código**, no solo
  por convención.

---

## Dataclasses (definidas en `bus_persistencia.models.state`)

```python
class ModoTurno(str, Enum):
    DIURNO = "diurno"
    NOCTURNO = "nocturno"

class PoliticaPicking(str, Enum):
    FIFO = "fifo"
    PRIORIDAD_POSICION = "prioridad_posicion"

class RobotEstado(str, Enum):
    INACTIVO = "inactivo"; DESPLAZANDOSE = "desplazandose"; EXCAVANDO = "excavando"
    RECUPERANDO = "recuperando"; BLOQUEADO = "bloqueado"
    ENTREGANDO = "entregando"; REPONIENDO = "reponiendo"

@dataclass(frozen=True)
class Robot:
    id: int
    x: int
    y: int
    z: int
    estado: RobotEstado
    carga_id: str | None = None   # id de la Caja que transporta, si aplica

@dataclass(frozen=True)
class Caja:
    id_caja: str
    id_sku: str
    cantidad: int
    x: int
    y: int
    z: int

@dataclass(frozen=True)
class Pedido:
    id_pedido: str
    id_sku: str
    cantidad: int
    destino: str
```

**Cambios importantes respecto a la versión original de este documento:**
- `Pedido` **ya no tiene campo `estado`**. El bus rastrea pendientes vs. completados
  como colecciones separadas — `PedidosState(cola, completados)` — no por el estado
  del objeto. El ciclo `pendiente → en_proceso → completado` que describía este
  documento es ahora responsabilidad interna de M2 (si lo necesita); hacia el bus
  solo se reportan altas a `pedidos_completados_add`.
- `Robot` ahora tiene **`z`** (la grilla es 3D también para los robots dentro del
  bus) y el campo se llama `carga_id`, no `tarea_id`.
- `Caja` pasó de `(sku, cantidad)` a una entidad posicionada e identificable
  individualmente: `(id_caja, id_sku, cantidad, x, y, z)`.
- `modo`/`politica` son **Enums** (`ModoTurno`, `PoliticaPicking`), no strings sueltos
  — la política `"posicion"` se llama en realidad `PoliticaPicking.PRIORIDAD_POSICION`
  (`"prioridad_posicion"`).

Estos nombres y valores son el contrato entre módulos. No cambiarlos sin avisar a
todos los responsables — y sin coordinar con Martín, que es quien los define en
`bus_persistencia.models.state`.

---

## Los 7 KPIs — fórmulas exactas

| ID | Nombre | Fórmula | Meta |
|---|---|---|---|
| TSP | Tasa Satisfacción Pedidos | pedidos_completados / pedidos_demandados × 100 | ≥ 95% |
| TPCP | Tiempo Ciclo por Pedido | Σ(t_despacho − t_orden) / N_pedidos | Minimizar |
| MTRP | Movimientos Robot/Pedido | total_desplazamientos / pedidos_completados | Minimizar |
| IOG | Índice Ocupación Grilla | cajas_presentes / capacidad_total × 100 | 60–90% |
| TR | Throughput Recuperación | cajas_recuperadas / duración_turno_min | Maximizar |
| TI | Throughput Ingreso | cajas_ingresadas / duración_fase_ingreso_min | Maximizar |
| TBR | Tiempo Bloqueo Robots | tiempo_bloqueado / tiempo_total × 100 | ≤ 10% |

---

## Archivos de entrada y salida

| Archivo | Dirección | Campos clave |
|---|---|---|
| config.json | Entrada | x, y, z, robots, ocupacion |
| ola.csv | Entrada | id_pedido, id_sku, cantidad, destino |
| reposicion.csv | Entrada | id_caja, id_sku, cantidad |
| sesion_X.csv | Salida | timestamp, tick, tipo_evento, payload_json |
| metadata_X.json | Salida | semilla, hashes, modo, política, kpis_finales (nuevo — `MetadataStore`) |
| reporte_comp.csv | Salida | KPI, ejecucion_A, ejecucion_B, delta_pct |

**Regla de escritura:** sesion_X.csv se escribe con buffer diferido al final de cada
tick, nunca dentro del ciclo de cómputo (lo maneja el `SessionLogger` del bus
automáticamente a partir de `TickDelta.eventos`). reporte_comp.csv solo al finalizar
la sesión.

---

## Lógica de negocio crítica

### Grilla
- Indexable en O(1) por coordenadas (x, y, z)
- Máximo Z cajas por columna (x, y)
- Los robots circulan SOLO en el plano X-Y (superficie)
- **Modelo de intercambio con el bus** (actualizado): `bus_persistencia` representa la
  grilla como una `Caja` exacta por celda `(x, y, z)` — no como pila/lista por columna.
  El motor puede mantener internamente la representación que le sea más cómoda (p.ej.
  agrupar por columna para razonar sobre excavación), pero al reportar cambios al bus
  debe traducirlos a `grilla_delta` (cajas agregadas/actualizadas, identificadas por
  su celda) y `grilla_remove` (lista de coordenadas `(x,y,z)` a vaciar).

### Robots
- Controlados por el despachador central — NO toman decisiones propias
- Un robot = un objeto de datos (posición + estado + tarea asignada)
- Toda la inteligencia vive en el despachador
- Acceso a cajas por ganchos: puede acoplarse a CUALQUIER caja de la columna,
  no solo la superior
- Excavación: si caja objetivo tiene cajas encima, moverlas a columnas adyacentes
  libres antes de acceder. Cada movimiento de excavación cuenta en MTRP.
- Resolución de colisiones: cesión de paso — robot espera 1 tick si celda destino
  está ocupada. Ese tick cuenta en TBR.

### Despachador
- Revisa cola de pedidos pendientes cada tick
- Revisa robots en estado "inactivo"
- Aplica política activa para decidir asignación
- Asigna ruta completa al robot — el robot solo la ejecuta

### Políticas de picking (funciones intercambiables)
- **FIFO** (`PoliticaPicking.FIFO`, `"fifo"`): despacha pedidos en orden de llegada a la cola
- **Prioridad por posición** (`PoliticaPicking.PRIORIDAD_POSICION`, `"prioridad_posicion"`
  — *el valor real difiere del `"posicion"` que decía la versión anterior de este
  documento*): ordena por distancia Manhattan entre columna objetivo y puerto más
  cercano disponible. Selecciona la caja de menor costo.
- Cambio de política lo decide el operador vía M1 (`bus.set_policy`); efectivo en el
  siguiente tick sin reiniciar la simulación — M2 solo lee `read_snapshot().politica`

### Puertos
- Posiciones fijas en los bordes de la grilla
- Punto de entrega de cajas en turno diurno
- Punto de recepción de cajas en turno nocturno

### Turno nocturno
- Robots toman cajas desde puertos y las ubican en posiciones libres
  según el orden de reposicion.csv
- La lógica de reposición del AutoStore real es opaca — NO se replica.
  El simulador simplemente ubica cajas en posiciones disponibles.

---

## Responsables por módulo

| Módulo | Responsable | Apoyo |
|---|---|---|
| M1 — UI / Configuración | Alonso Bravo | Eliseo Guarda |
| M2 — Motor de Simulación | Vicente Rosales | Manuel Aguilera |
| M3 — Visualización 3D | Alex Alfaro | Samira Becerra |
| Bus + Persistencia | Martín Vásquez | Guadalupe Marín |

Vicente Rosales actúa también como responsable general con visibilidad sobre todos
los módulos.

---

## Config de ejemplo para desarrollo (datos sintéticos)

```json
{
  "x": 5,
  "y": 5,
  "z": 3,
  "robots": 3,
  "ocupacion": 0.75
}
```

---

## Convención de commits

- Código temporal o en progreso: prefijo `WIP:`
  - Ejemplo: `WIP: mock bus de estado para desarrollo paralelo`
- Código listo: prefijo del módulo en minúsculas
  - Ejemplos: `bus: implementar threading.Lock con escritura delta`
  - `motor: grilla 3D con operaciones O(1)`
  - `ui: panel KPIs conectado al bus`
  - `m3: grilla procedural USD desde config.json`

---

## Lo que está FUERA del alcance (no implementar)

- Clasificador / sorter hacia andenes de carga
- Inyección de algoritmos externos de optimización
- Comunicación en tiempo real con el AutoStore físico
- Turno nocturno con lógica inteligente de reordenamiento
- Más de 2 políticas de picking en esta versión

---

## Demostradores requeridos (P09 — criterio de evaluación)

| | Demo 1 | Demo 2 |
|---|---|---|
| Política | FIFO | Prioridad por posición |
| Ocupación | 75% | 90% |
| Resultado esperado | Referencia base | MTRP menor, TBR mayor |

Ambos demostradores deben ejecutarse de principio a fin sin errores y generar
reporte_comp.csv con los KPIs comparados.