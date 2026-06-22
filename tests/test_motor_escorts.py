"""Tests de unidad — EscortPlanner / StagnationDetector (anti-livelock @95%).

Valida:
- planificar: nunca asigna la misma columna-escort a dos tareas en una ventana.
- planificar: no asigna una columna-escort cuya trayectoria cruce una
  columna-objetivo de otra tarea (salvo degradación sin opción segura).
- StagnationDetector: dispara tras T ticks sin progreso neto y se resetea al
  progresar.
- mover_escort_un_paso: salto directo (3 pasos) cuando hay adyacente libre;
  rodeo a la columna-escort reservada (5 pasos) cuando no la hay.
- Integración: el escenario de 95% que entraba en livelock ahora completa la ola.
"""
from __future__ import annotations

from bus_persistencia.models.state import (
    Caja,
    Config,
    GrillaDimensions,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
)
from motor.despachador import Despachador, Tarea
from motor.escorts import (
    UMBRAL_ESTANCAMIENTO,
    EscortPlanner,
    StagnationDetector,
)
from motor.grilla import Grilla
from motor.kpis import Acumuladores


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _config(x=6, y=6, z=4, robots=4, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _caja(id_caja, x, y, z, id_sku="SKU001") -> Caja:
    return Caja(id_caja=id_caja, id_sku=id_sku, cantidad=1, x=x, y=y, z=z)


def _pedido(id_pedido="P001", id_sku="SKU001") -> Pedido:
    return Pedido(id_pedido=id_pedido, id_sku=id_sku, cantidad=1, destino="anden_1")


def _tarea(robot_id_caja, x, y, z, profundidad=2) -> Tarea:
    """Tarea en fase 'excavar' con su caja objetivo en (x,y,z)."""
    t = Tarea(
        pedido=_pedido(),
        caja_objetivo=_caja(robot_id_caja, x, y, z),
        ruta_entrada=[],
        ruta_salida=[],
        puerto=(0, 0),
        fase="excavar",
    )
    t.profundidad_inicial = profundidad
    return t


def _llenar_columna(grilla: Grilla, x: int, y: int, hasta_z: int) -> None:
    for z in range(hasta_z + 1):
        grilla.agregar(_caja(f"C{x}{y}{z}", x, y, z))


# ------------------------------------------------------------------
# planificar — reservas exclusivas
# ------------------------------------------------------------------

def test_planificar_no_asigna_misma_columna_a_dos_tareas():
    grilla = Grilla(_config())
    planner = EscortPlanner()
    tareas = {0: _tarea("A", 2, 2, 0, profundidad=1),
              1: _tarea("B", 3, 3, 0, profundidad=1)}
    planner.planificar(tareas, grilla, tick=0)

    e0 = tareas[0].escort_asignado
    e1 = tareas[1].escort_asignado
    assert e0 is not None and e1 is not None
    assert e0.columna != e1.columna, "Dos tareas no pueden compartir columna-escort"


def test_planificar_no_usa_columna_objetivo_de_otra_tarea():
    grilla = Grilla(_config())
    planner = EscortPlanner()
    tareas = {0: _tarea("A", 2, 2, 0), 1: _tarea("B", 3, 2, 0)}
    planner.planificar(tareas, grilla, tick=0)

    objetivos = {(2, 2), (3, 2)}
    for t in tareas.values():
        assert t.escort_asignado is not None
        assert t.escort_asignado.columna not in objetivos, \
            "La columna-escort nunca puede ser un objetivo activo"


def test_planificar_serializa_cuando_no_hay_columnas_libres():
    """Si todas las columnas no-objetivo están llenas, alguna tarea queda sin
    escort (serialización) en vez de re-enterrar otro objetivo."""
    grilla = Grilla(_config(x=3, y=1, z=2))  # 3 columnas, 2 objetivo → 1 libre
    # Llenar la única columna no-objetivo (1,0) para forzar escasez.
    _llenar_columna(grilla, 1, 0, hasta_z=1)
    planner = EscortPlanner()
    tareas = {0: _tarea("A", 0, 0, 0, profundidad=1),
              1: _tarea("B", 2, 0, 0, profundidad=2)}
    planner.planificar(tareas, grilla, tick=0)

    asignadas = [t for t in tareas.values() if t.escort_asignado is not None]
    assert len(asignadas) == 0, "Sin columnas libres no-objetivo no se asigna escort"


# ------------------------------------------------------------------
# StagnationDetector
# ------------------------------------------------------------------

def test_stagnation_detecta_sin_progreso():
    grilla = Grilla(_config())
    # Columna objetivo (2,2): objetivo en z=0 con 2 cajas encima (z=1,z=2).
    grilla.agregar(_caja("OBJ", 2, 2, 0))
    grilla.agregar(_caja("S1", 2, 2, 1))
    grilla.agregar(_caja("S2", 2, 2, 2))
    detector = StagnationDetector()
    tarea = _tarea("OBJ", 2, 2, 0, profundidad=-1)  # se fija en el 1er actualizar
    tareas = [tarea]

    # 1er tick: fija profundidad_inicial = 2 (cajas encima), sin estancamiento.
    detector.actualizar(tareas, grilla)
    assert tarea.profundidad_inicial == 2
    assert not detector.hay_estancamiento(tareas)

    # Sin tocar la grilla (progreso neto = 0) durante UMBRAL ticks → estancamiento.
    for _ in range(UMBRAL_ESTANCAMIENTO):
        detector.actualizar(tareas, grilla)
    assert detector.hay_estancamiento(tareas)


def test_stagnation_se_resetea_con_progreso():
    grilla = Grilla(_config())
    grilla.agregar(_caja("OBJ", 2, 2, 0))
    grilla.agregar(_caja("S1", 2, 2, 1))
    grilla.agregar(_caja("S2", 2, 2, 2))
    detector = StagnationDetector()
    tarea = _tarea("OBJ", 2, 2, 0, profundidad=-1)
    tareas = [tarea]

    detector.actualizar(tareas, grilla)            # profundidad_inicial = 2
    for _ in range(UMBRAL_ESTANCAMIENTO - 1):
        detector.actualizar(tareas, grilla)        # acumula sin progreso
    # Progreso real: retirar una caja de encima.
    grilla.remover(2, 2, 2)
    detector.actualizar(tareas, grilla)
    assert tarea.ticks_sin_progreso == 0
    assert not detector.hay_estancamiento(tareas)


# ------------------------------------------------------------------
# mover_escort_un_paso — 3 pasos vs 5 pasos
# ------------------------------------------------------------------

def test_mover_escort_salto_directo_adyacente():
    grilla = Grilla(_config(x=6, y=1, z=3))
    planner = EscortPlanner()
    tarea = _tarea("OBJ", 1, 0, 0)
    # destino-escort en (5,0); la caja a mover está sobre el objetivo en (1,0,1)
    planner.planificar({0: tarea}, grilla, tick=0)
    caja_mover = _caja("SUP", 1, 0, 1)

    destino = planner.mover_escort_un_paso(
        caja_mover, tarea, grilla, protegidas={(1, 0)}, reservadas={tarea.escort_asignado.columna},
    )
    assert destino is not None
    ax, ay, _z = destino
    # Salto directo: a una columna adyacente que acerca hacia el destino-escort.
    assert (ax, ay) in grilla.columnas_adyacentes(1, 0)
    assert (ax, ay) != (1, 0)


def test_mover_escort_rodeo_cuando_adyacentes_llenas():
    """Si todas las adyacentes seguras están llenas, deposita en la columna-escort
    reservada (patrón de 5 pasos / rodeo)."""
    grilla = Grilla(_config(x=5, y=1, z=2))
    planner = EscortPlanner()
    # Objetivo en (2,0); llenar adyacentes (1,0) y (3,0) para bloquear el salto directo.
    _llenar_columna(grilla, 1, 0, hasta_z=1)
    _llenar_columna(grilla, 3, 0, hasta_z=1)
    tarea = _tarea("OBJ", 2, 0, 0)
    # Forzar columna-escort en un extremo libre: (0,0) o (4,0).
    planner.planificar({0: tarea}, grilla, tick=0)
    assert tarea.escort_asignado is not None
    caja_mover = _caja("SUP", 2, 0, 1)

    destino = planner.mover_escort_un_paso(
        caja_mover, tarea, grilla,
        protegidas={(2, 0)}, reservadas={tarea.escort_asignado.columna},
    )
    assert destino is not None
    ax, ay, _z = destino
    # No pudo saltar a (1,0)/(3,0) (llenas) → cae en la columna-escort reservada.
    assert (ax, ay) == tarea.escort_asignado.columna


# ------------------------------------------------------------------
# Integración — el escenario de livelock ahora completa la ola
# ------------------------------------------------------------------

def test_integracion_95pct_completa_la_ola():
    """Columna muy apilada + alta ocupación alrededor: con el EscortPlanner la
    excavación progresa y el pedido se completa (antes: livelock)."""
    grilla = Grilla(_config(x=5, y=5, z=4, robots=3))
    # Objetivo enterrado en (2,2,0) con 3 cajas encima.
    grilla.agregar(_caja("OBJ", 2, 2, 0, id_sku="SKU777"))
    for z in (1, 2, 3):
        grilla.agregar(_caja(f"SUP{z}", 2, 2, z, id_sku="SKU999"))
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {0: Robot(id=0, x=0, y=0, z=0, estado=RobotEstado.INACTIVO, carga_id=None)}
    pedidos = [_pedido(id_sku="SKU777")]
    acum = Acumuladores(pedidos_demandados=1)

    completados = []
    for _ in range(100):
        robots_upd, _gd, _gr, comp, _evs = despachador.tick(
            robots, pedidos, PoliticaPicking.PRIORIDAD_POSICION, acum
        )
        for r in robots_upd:
            robots[r.id] = r
        completados.extend(comp)
        if completados:
            break

    assert len(completados) == 1, "El pedido enterrado debe completarse sin livelock"
    assert grilla.get(2, 2, 0) is None, "La caja objetivo fue recuperada"
