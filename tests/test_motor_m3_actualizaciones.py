"""tests/test_motor_m3_actualizaciones.py — Tests de las 5 actualizaciones M3.

Cubren:
  1. Grilla extendida (anillo perimetral de tránsito).
  2. Estaciones Cinta/Carrusel (capacidad por tick).
  3. Restricción de orientación (rotación + preservación).
  4. Mente Colmena (handoff de orientación, wait-for graph, reservation table).
  5. Condición de término por ola completa.

Ejecutar:  ./venv/bin/python3 -m pytest tests/test_motor_m3_actualizaciones.py -v
"""
from __future__ import annotations

import pytest

from bus_persistencia.bus.state_bus import StateBus
from bus_persistencia.models.state import (
    Caja,
    Config,
    Estacion,
    GrillaDimensions,
    Orientacion,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
    TipoEstacion,
)
from motor.colmena import (
    COSTO_ROTACION_TICKS,
    ReservationTable,
    WaitForGraph,
    orientacion_hacia,
)
from motor.despachador import Despachador, Tarea
from motor.grilla import Grilla
from motor.kpis import Acumuladores
from motor.simulador import AutoStoreSimulator


# ======================================================================
# Feature 1 — Grilla extendida (anillo perimetral)
# ======================================================================

def test_anillo_marca_perimetro_como_transito():
    cfg = Config(GrillaDimensions(5, 5, 3), robots=2, ocupacion_inicial=0,
                 anillo_transito=True)
    g = Grilla(cfg)
    assert g.es_transito(0, 0)
    assert g.es_transito(4, 4)
    assert g.es_transito(2, 0)      # borde inferior
    assert not g.es_transito(2, 2)  # interior


def test_anillo_capacidad_almacenable_excluye_transito():
    cfg = Config(GrillaDimensions(5, 5, 3), robots=2, ocupacion_inicial=0,
                 anillo_transito=True)
    g = Grilla(cfg)
    # 5x5 = 25 columnas; anillo = 16; interior = 9; × z(3) = 27
    assert g.capacidad_almacenable == 27
    assert g.config.grilla.capacidad_total == 75


def test_anillo_rechaza_cajas_en_transito():
    cfg = Config(GrillaDimensions(5, 5, 2), robots=1, ocupacion_inicial=0,
                 anillo_transito=True)
    g = Grilla(cfg)
    g.agregar(Caja("OK", "S", 1, 2, 2, 0))           # interior: válido
    with pytest.raises(ValueError):
        g.agregar(Caja("BAD", "S", 1, 0, 0, 0))       # anillo: rechazado


def test_anillo_inactivo_preserva_comportamiento_previo():
    cfg = Config(GrillaDimensions(5, 5, 3), robots=2, ocupacion_inicial=0)
    g = Grilla(cfg)
    assert not g.es_transito(0, 0)
    assert g.capacidad_almacenable == g.config.grilla.capacidad_total


# ======================================================================
# Feature 2 — Estaciones Cinta/Carrusel
# ======================================================================

def test_capacidad_por_tipo_de_estacion():
    assert Estacion("a", 0, 0, TipoEstacion.CINTA).capacidad_tick == 1
    assert Estacion("b", 0, 0, TipoEstacion.CARRUSEL).capacidad_tick == 2


def _grilla_con_estacion(tipo: TipoEstacion, orient: Orientacion) -> tuple[Grilla, Estacion]:
    est = Estacion("EST1", 0, 2, tipo, orient)
    cfg = Config(GrillaDimensions(5, 5, 2), robots=2, ocupacion_inicial=0,
                 estaciones=(est,))
    g = Grilla(cfg)
    g.agregar(Caja("CAJA1", "SKU-A", 1, 2, 2, 0))
    return g, est


def _tarea_lista_para_entregar(est: Estacion) -> Tarea:
    return Tarea(
        pedido=Pedido("P1", "SKU-A", 1, "dest"),
        caja_objetivo=Caja("CAJA1", "SKU-A", 1, 2, 2, 0),
        ruta_entrada=[], ruta_salida=[], puerto=(est.x, est.y),
        estacion=est, fase="entregar",
    )


def test_cinta_satura_a_1_por_tick():
    g, est = _grilla_con_estacion(TipoEstacion.CINTA, Orientacion.NORTE)
    d = Despachador(g)
    tarea = _tarea_lista_para_entregar(est)
    robot = Robot(0, est.x, est.y, 0, RobotEstado.ENTREGANDO,
                  carga_id="CAJA1", orientacion=Orientacion.NORTE)

    # Estación saturada este tick → espera, no completa.
    d._servidos = {est.id: 1}
    _, _, _, comp, evs = d._fase_entregar(robot, tarea, Acumuladores())
    assert comp is None
    assert evs[0]["tipo"] == "estacion_saturada"

    # Estación libre → entrega y consume capacidad.
    d._servidos = {est.id: 0}
    _, _, _, comp, _ = d._fase_entregar(robot, tarea, Acumuladores())
    assert comp is not None
    assert d._servidos[est.id] == 1


def test_carrusel_permite_2_por_tick():
    g, est = _grilla_con_estacion(TipoEstacion.CARRUSEL, Orientacion.NORTE)
    d = Despachador(g)
    tarea = _tarea_lista_para_entregar(est)
    robot = Robot(0, est.x, est.y, 0, RobotEstado.ENTREGANDO,
                  carga_id="CAJA1", orientacion=Orientacion.NORTE)
    d._servidos = {est.id: 1}  # ya sirvió 1, capacidad 2
    _, _, _, comp, _ = d._fase_entregar(robot, tarea, Acumuladores())
    assert comp is not None  # 1 < 2 → entrega


# ======================================================================
# Feature 3 — Restricción de orientación
# ======================================================================

def test_orientacion_hacia_excluye_sur():
    assert orientacion_hacia((2, 2), (4, 2)) == Orientacion.ESTE
    assert orientacion_hacia((2, 2), (0, 2)) == Orientacion.OESTE
    assert orientacion_hacia((2, 2), (2, 4)) == Orientacion.NORTE
    assert orientacion_hacia((2, 2), (2, 0)) is None  # Sur prohibido


def test_robot_rota_antes_de_entregar():
    g, est = _grilla_con_estacion(TipoEstacion.CINTA, Orientacion.OESTE)
    d = Despachador(g)
    tarea = _tarea_lista_para_entregar(est)
    robot = Robot(0, est.x, est.y, 0, RobotEstado.ENTREGANDO,
                  carga_id="CAJA1", orientacion=Orientacion.NORTE)
    d._servidos = {est.id: 0}

    # Primer intento: mal orientado → rota (no entrega).
    nuevo, _, _, comp, evs = d._fase_entregar(robot, tarea, Acumuladores())
    assert comp is None
    assert nuevo.estado == RobotEstado.ROTANDO
    assert evs[0]["tipo"] == "rotacion"
    assert tarea.ticks_rotando == COSTO_ROTACION_TICKS

    # Segundo intento: ya rotó → entrega con la orientación correcta.
    nuevo2, _, _, comp2, _ = d._fase_entregar(nuevo, tarea, Acumuladores())
    assert comp2 is not None


def test_movimiento_preserva_orientacion():
    cfg = Config(GrillaDimensions(5, 5, 2), robots=1, ocupacion_inicial=0)
    g = Grilla(cfg)
    d = Despachador(g)
    robot = Robot(0, 0, 0, 0, RobotEstado.DESPLAZANDOSE,
                  orientacion=Orientacion.ESTE)
    tarea = Tarea(Pedido("P", "S", 1, "d"), Caja("c", "S", 1, 2, 0, 0),
                  ruta_entrada=[(1, 0), (2, 0)], ruta_salida=[], puerto=(0, 0))
    nuevo, _, _, _, _ = d._fase_mover_a_objetivo(robot, tarea, {(0, 0): 0},
                                                  Acumuladores())
    assert nuevo.x == 1 and nuevo.orientacion == Orientacion.ESTE


# ======================================================================
# Feature 4 — Mente Colmena (handoff, reservation table, wait-for graph)
# ======================================================================

def test_handoff_transfiere_carga_a_vecino_orientado():
    g, est = _grilla_con_estacion(TipoEstacion.CINTA, Orientacion.OESTE)
    d = Despachador(g)
    tarea = _tarea_lista_para_entregar(est)
    emisor = Robot(0, est.x, est.y, 0, RobotEstado.ENTREGANDO,
                   carga_id="CAJA1", orientacion=Orientacion.NORTE)  # mal orientado
    receptor = Robot(1, est.x, est.y + 1, 0, RobotEstado.INACTIVO,
                     orientacion=Orientacion.OESTE)  # vecino bien orientado
    d._tareas[emisor.id] = tarea
    robots_estado = {0: emisor, 1: receptor}

    mods: list = []
    evs: list = []
    d._handoff_prepass(robots_estado, mods, evs)

    assert any(e["tipo"] == "handoff" for e in evs)
    assert robots_estado[1].carga_id == "CAJA1"      # receptor recibió la carga
    assert robots_estado[0].carga_id is None         # emisor quedó libre
    assert 1 in d._tareas and 0 not in d._tareas      # tarea reasignada


def test_handoff_no_ocurre_sin_vecino_orientado():
    g, est = _grilla_con_estacion(TipoEstacion.CINTA, Orientacion.OESTE)
    d = Despachador(g)
    tarea = _tarea_lista_para_entregar(est)
    emisor = Robot(0, est.x, est.y, 0, RobotEstado.ENTREGANDO,
                   carga_id="CAJA1", orientacion=Orientacion.NORTE)
    # vecino mal orientado → no es candidato
    receptor = Robot(1, est.x, est.y + 1, 0, RobotEstado.INACTIVO,
                     orientacion=Orientacion.NORTE)
    d._tareas[emisor.id] = tarea
    robots_estado = {0: emisor, 1: receptor}
    evs: list = []
    d._handoff_prepass(robots_estado, [], evs)
    assert not any(e["tipo"] == "handoff" for e in evs)
    assert 0 in d._tareas  # tarea sigue con el emisor


def test_wait_for_graph_detecta_ciclo():
    wfg = WaitForGraph()
    wfg.agregar_espera(1, 2)
    wfg.agregar_espera(2, 1)
    assert set(wfg.detectar_ciclo()) == {1, 2}

    wfg2 = WaitForGraph()
    wfg2.agregar_espera(1, 2)
    wfg2.agregar_espera(2, 3)
    assert wfg2.detectar_ciclo() is None


def test_reservation_table_conflicto_intercambio():
    rt = ReservationTable()
    assert rt.reservar((1, 1), 0) is True
    assert rt.reservar((1, 1), 1) is False  # ya reservada por otro
    assert rt.hay_conflicto_intercambio((0, 0), (1, 0), (1, 0), (0, 0)) is True
    assert rt.hay_conflicto_intercambio((0, 0), (1, 0), (5, 5), (5, 6)) is False


# ======================================================================
# Feature 5 — Condición de término por ola completa
# ======================================================================

def test_simulacion_se_detiene_al_completar_la_ola():
    cfg = Config(GrillaDimensions(6, 6, 2), robots=3, ocupacion_inicial=0)
    bus = StateBus()
    bus.set_config(cfg)
    pedidos = [
        Pedido("P1", "SKU-A", 1, "d"),
        Pedido("P2", "SKU-B", 1, "d"),
    ]
    bus.set_pedidos_cola(pedidos)
    bus.set_policy(PoliticaPicking.FIFO)

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=1)
    # Garantizar cajas para los SKUs demandados (interior).
    sim._grilla.agregar(Caja("CA", "SKU-A", 1, 2, 2, 0))
    sim._grilla.agregar(Caja("CB", "SKU-B", 1, 3, 3, 0))

    assert sim.total_ola == 2
    assert not sim.ola_completa()

    terminado_en = None
    for t in range(1, 300):
        sim.avanzar_tick()
        if sim.ha_terminado():
            terminado_en = t
            break

    assert terminado_en is not None, "la simulación no terminó"
    assert sim.ola_completa()
    assert len(sim.pedidos_completados) == 2


def test_ola_completa_falsa_si_quedan_pedidos():
    cfg = Config(GrillaDimensions(5, 5, 2), robots=1, ocupacion_inicial=0)
    bus = StateBus()
    bus.set_config(cfg)
    bus.set_pedidos_cola([Pedido("P1", "SKU-A", 1, "d")])
    bus.set_policy(PoliticaPicking.FIFO)
    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=1)
    assert sim.total_ola == 1
    assert sim.ola_completa() is False
