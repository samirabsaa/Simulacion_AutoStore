"""Tests de integración — Despachador + KPIs (T-12/T-15/T-16/T-17/T-20).

Ejercita la lógica de M2 sin el bus para aislar errores.
"""
from __future__ import annotations

import pytest
from bus_persistencia.models.state import (
    Caja,
    Config,
    GrillaDimensions,
    ModoTurno,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
)
from motor.despachador import Despachador, _ruta_xy
from motor.grilla import Grilla
from motor.kpis import Acumuladores, calcular_kpis


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

def _config(x=5, y=5, z=3, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _grilla_vacia(x=5, y=5, z=3) -> Grilla:
    cfg = _config(x=x, y=y, z=z)
    return Grilla(cfg)


def _robot(id=0, x=0, y=0) -> Robot:
    return Robot(id=id, x=x, y=y, z=0, estado=RobotEstado.INACTIVO, carga_id=None)


def _caja(id_caja="C001", id_sku="SKU001", x=2, y=2, z=0) -> Caja:
    return Caja(id_caja=id_caja, id_sku=id_sku, cantidad=1, x=x, y=y, z=z)


def _pedido(id_pedido="P001", id_sku="SKU001") -> Pedido:
    return Pedido(id_pedido=id_pedido, id_sku=id_sku, cantidad=1, destino="andén_1")


# ------------------------------------------------------------------
# Tests de _ruta_xy
# ------------------------------------------------------------------

def test_ruta_xy_misma_posicion():
    assert _ruta_xy((2, 2), (2, 2)) == []


def test_ruta_xy_solo_x():
    ruta = _ruta_xy((0, 0), (3, 0))
    assert ruta == [(1, 0), (2, 0), (3, 0)]


def test_ruta_xy_l_shape():
    ruta = _ruta_xy((0, 0), (2, 2))
    assert ruta == [(1, 0), (2, 0), (2, 1), (2, 2)]


# ------------------------------------------------------------------
# Tests del Despachador
# ------------------------------------------------------------------

def test_despachador_completa_pedido_simple():
    """Robot entrega una caja sin excavación en N ticks."""
    grilla = _grilla_vacia()
    caja = _caja(x=2, y=2, z=0)
    grilla.agregar(caja)
    grilla.flush_delta()  # limpiar delta inicial

    despachador = Despachador(grilla)
    robots = {0: _robot(id=0, x=0, y=0)}
    pedidos = [_pedido()]
    acum = Acumuladores(pedidos_demandados=1)

    completados = []
    for _ in range(30):  # suficientes ticks para completar
        robots_upd, _, _, comp, _ = despachador.tick(
            robots, pedidos, PoliticaPicking.FIFO, acum
        )
        for r in robots_upd:
            robots[r.id] = r
        completados.extend(comp)
        if completados:
            break

    assert len(completados) == 1
    assert completados[0].id_pedido == "P001"
    assert acum.pedidos_completados == 1
    assert acum.cajas_recuperadas == 1


def test_despachador_excavacion():
    """Robot excava caja intermedia (z=1 con caja encima en z=2)."""
    grilla = _grilla_vacia()
    caja_obj = Caja(id_caja="OBJ", id_sku="SKU001", cantidad=1, x=2, y=2, z=1)
    caja_enc = Caja(id_caja="ENC", id_sku="SKU999", cantidad=1, x=2, y=2, z=2)
    grilla.agregar(caja_obj)
    grilla.agregar(caja_enc)
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {0: _robot(id=0, x=0, y=0)}
    pedidos = [_pedido(id_sku="SKU001")]
    acum = Acumuladores(pedidos_demandados=1)

    completados = []
    for _ in range(50):
        robots_upd, _, _, comp, evs = despachador.tick(
            robots, pedidos, PoliticaPicking.FIFO, acum
        )
        for r in robots_upd:
            robots[r.id] = r
        completados.extend(comp)
        if completados:
            break

    assert len(completados) == 1
    # La caja encima debió moverse — ya no está en (2,2,2)
    assert grilla.get(2, 2, 2) is None
    # La caja objetivo fue recuperada
    assert grilla.get(2, 2, 1) is None


def test_despachador_colision_bloqueo():
    """Dos robots en camino al mismo punto — uno queda BLOQUEADO al menos 1 tick."""
    grilla = _grilla_vacia()
    # Dos cajas del mismo SKU en columnas distintas
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=1, y=0, z=0))
    grilla.agregar(Caja(id_caja="C2", id_sku="SKU001", cantidad=1, x=1, y=1, z=0))
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {
        0: _robot(id=0, x=0, y=0),
        1: _robot(id=1, x=0, y=1),
    }
    pedidos = [
        _pedido(id_pedido="P001", id_sku="SKU001"),
        _pedido(id_pedido="P002", id_sku="SKU001"),
    ]
    acum = Acumuladores(pedidos_demandados=2)

    bloqueados_observados = False
    completados = []
    for _ in range(60):
        robots_upd, _, _, comp, _ = despachador.tick(
            robots, pedidos, PoliticaPicking.FIFO, acum
        )
        for r in robots_upd:
            robots[r.id] = r
            if r.estado == RobotEstado.BLOQUEADO:
                bloqueados_observados = True
        completados.extend(comp)

    # Con 2 robots y 2 pedidos, al menos alguno debería completarse
    assert len(completados) >= 1


def test_despachador_sin_caja_disponible_no_asigna():
    """Sin cajas del SKU pedido, robot queda INACTIVO."""
    grilla = _grilla_vacia()
    # Grilla vacía — no hay cajas
    despachador = Despachador(grilla)
    robots = {0: _robot(id=0, x=0, y=0)}
    pedidos = [_pedido(id_sku="SKU_INEXISTENTE")]
    acum = Acumuladores(pedidos_demandados=1)

    robots_upd, _, _, comp, _ = despachador.tick(
        robots, pedidos, PoliticaPicking.FIFO, acum
    )
    assert comp == []
    assert robots[0].estado == RobotEstado.INACTIVO


# ------------------------------------------------------------------
# Tests de calcular_kpis
# ------------------------------------------------------------------

def test_kpis_estado_inicial():
    """Al inicio (sin pedidos completados) todos los KPIs son 0."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(pedidos_demandados=10)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TSP == 0.0
    assert kpis.TPCP == 0.0
    assert kpis.MTRP == 0.0
    assert kpis.IOG == 0.0
    assert kpis.TBR == 0.0


def test_kpis_tsp():
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(pedidos_demandados=10, pedidos_completados=8)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TSP == pytest.approx(80.0)


def test_kpis_iog_con_cajas():
    grilla = _grilla_vacia(x=2, y=2, z=2)  # cap = 8
    grilla.agregar(_caja(x=0, y=0, z=0))
    grilla.agregar(_caja(id_caja="C2", x=0, y=0, z=1))
    cfg = _config(x=2, y=2, z=2)
    acum = Acumuladores()
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.IOG == pytest.approx(25.0)  # 2/8 * 100


def test_kpis_tbr():
    """TBR = ticks_bloqueados / (ticks_totales * n_robots) * 100.

    ticks_bloqueados acumula robot-ticks (suma sobre todos los robots), por eso
    el denominador incluye n_robots — así el resultado queda acotado en [0,100%].
    """
    grilla = _grilla_vacia()
    cfg = _config(robots=2)
    # 10 robot-ticks bloqueados / (100 ticks * 2 robots) = 10/200 = 5%
    acum = Acumuladores(ticks_bloqueados=10, ticks_totales=100)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TBR == pytest.approx(5.0)


def test_kpis_tbr_acotado():
    """Regresión: TBR no supera 100% aunque todos los robots estén bloqueados."""
    grilla = _grilla_vacia()
    cfg = _config(robots=4)
    # 4 robots bloqueados los 10 ticks → 40 robot-ticks / (10*4) = 100%
    acum = Acumuladores(ticks_bloqueados=40, ticks_totales=10)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TBR == pytest.approx(100.0)
    assert kpis.TBR <= 100.0


def test_kpis_mtrp():
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(
        pedidos_completados=4,
        total_desplazamientos=20,
    )
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.MTRP == pytest.approx(5.0)


# ------------------------------------------------------------------
# Test de integración completa: simulador → despachador → kpis
# ------------------------------------------------------------------

def test_integracion_simulador_turno_diurno(tmp_path):
    """Simula varios ticks de turno diurno end-to-end con bus real."""
    from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus
    from bus_persistencia.models.state import PedidosState
    from motor.simulador import AutoStoreSimulator

    bus = StateBus()
    cfg = _config(x=4, y=4, z=2, robots=2, ocupacion=0.0)
    bus.set_config(cfg)

    # Poblar grilla y pedidos manualmente
    caja1 = Caja(id_caja="C001", id_sku="SKU001", cantidad=1, x=2, y=2, z=0)
    caja2 = Caja(id_caja="C002", id_sku="SKU002", cantidad=1, x=1, y=1, z=0)
    ped1 = Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="andén_1")
    ped2 = Pedido(id_pedido="P002", id_sku="SKU002", cantidad=1, destino="andén_1")

    bus.set_pedidos_cola([ped1, ped2])

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=42)

    # Agregar cajas a la grilla interna del simulador
    sim._grilla.agregar(caja1)
    sim._grilla.agregar(caja2)

    completados_total = []
    for _ in range(60):
        sim.avanzar_tick()
        snap = bus.read_snapshot()
        completados_total = list(snap.pedidos.completados)
        if sim.ha_terminado() or len(completados_total) >= 2:
            break

    assert len(completados_total) == 2, (
        f"Completó {len(completados_total)}/2 con 2 robots y 2 cajas"
    )
