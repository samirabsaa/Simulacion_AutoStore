"""Tests de unidad — Despachador (T-12, T-15, T-16, T-17).

Valida:
- Excavación multi-nivel (z=0..3, target en z=1)
- Conteo de ticks bloqueados para TBR
- Emisión de eventos por fase
- Acumulador de desplazamientos
- Delta solo con robots cambiados (bus contract)
"""
from __future__ import annotations

import pytest
from bus_persistencia.models.state import (
    Caja,
    Config,
    GrillaDimensions,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
)
from motor.despachador import Despachador
from motor.grilla import Grilla
from motor.kpis import Acumuladores


def _config(x=5, y=5, z=3, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _grilla_vacia(x=5, y=5, z=3) -> Grilla:
    return Grilla(_config(x=x, y=y, z=z))


def _robot(id=0, x=0, y=0) -> Robot:
    return Robot(id=id, x=x, y=y, z=0, estado=RobotEstado.INACTIVO, carga_id=None)


def _caja(id_caja="C001", id_sku="SKU001", x=2, y=2, z=0) -> Caja:
    return Caja(id_caja=id_caja, id_sku=id_sku, cantidad=1, x=x, y=y, z=z)


def _pedido(id_pedido="P001", id_sku="SKU001") -> Pedido:
    return Pedido(id_pedido=id_pedido, id_sku=id_sku, cantidad=1, destino="andén_1")


# ------------------------------------------------------------------
# Excavación multi-nivel
# ------------------------------------------------------------------

def test_despachador_excavacion_multi_level():
    """Excava caja en z=1 con cajas encima en z=2 y z=3."""
    grilla = _grilla_vacia(x=5, y=5, z=4)
    caja_obj = Caja(id_caja="OBJ", id_sku="SKU001", cantidad=1, x=2, y=2, z=1)
    caja_sup1 = Caja(id_caja="SUP1", id_sku="SKU999", cantidad=1, x=2, y=2, z=2)
    caja_sup2 = Caja(id_caja="SUP2", id_sku="SKU999", cantidad=1, x=2, y=2, z=3)
    grilla.agregar(caja_obj)
    grilla.agregar(caja_sup1)
    grilla.agregar(caja_sup2)
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {0: _robot(id=0, x=0, y=0)}
    pedidos = [_pedido(id_sku="SKU001")]
    acum = Acumuladores(pedidos_demandados=1)

    completados = []
    for _ in range(80):
        robots_upd, g_d, g_r, comp, evs = despachador.tick(
            robots, pedidos, PoliticaPicking.FIFO, acum
        )
        for r in robots_upd:
            robots[r.id] = r
        completados.extend(comp)
        if completados:
            break

    assert len(completados) == 1
    assert grilla.get(2, 2, 1) is None  # objetivo recuperado
    assert grilla.get(2, 2, 2) is None  # sup1 movida
    assert grilla.get(2, 2, 3) is None  # sup2 movida
    assert acum.cajas_recuperadas == 1


# ------------------------------------------------------------------
# Colisión — conteo de ticks bloqueados
# ------------------------------------------------------------------

def test_despachador_colision_bloqueo_conteo():
    """Dos robots convergen a la misma columna — se cuenta el tick bloqueado."""
    grilla = _grilla_vacia(x=5, y=5, z=3)
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=2, y=1, z=0))
    grilla.agregar(Caja(id_caja="C2", id_sku="SKU001", cantidad=1, x=2, y=1, z=1))
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {
        0: _robot(id=0, x=0, y=1),
        1: _robot(id=1, x=4, y=1),
    }
    pedidos = [_pedido(id_pedido="P001"), _pedido(id_pedido="P002")]
    acum = Acumuladores(pedidos_demandados=2)

    ticks_bloqueados_antes = acum.ticks_bloqueados

    for _ in range(60):
        robots_upd, _, _, comp, _ = despachador.tick(
            robots, pedidos, PoliticaPicking.FIFO, acum
        )
        for r in robots_upd:
            robots[r.id] = r

    # Al menos un tick de bloqueo debió ocurrir (ambos convergen a (2,1))
    assert acum.ticks_bloqueados > ticks_bloqueados_antes


# ------------------------------------------------------------------
# Eventos por fase
# ------------------------------------------------------------------

def test_despachador_eventos_emitidos():
    """Se emiten eventos de movimiento, excavación, recuperación y entrega."""
    grilla = _grilla_vacia(x=4, y=4, z=3)
    caja_obj = Caja(id_caja="OBJ", id_sku="SKU001", cantidad=1, x=2, y=2, z=0)
    caja_enc = Caja(id_caja="ENC", id_sku="SKU999", cantidad=1, x=2, y=2, z=1)
    grilla.agregar(caja_obj)
    grilla.agregar(caja_enc)
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {0: _robot(id=0, x=0, y=0)}
    pedidos = [_pedido(id_sku="SKU001")]
    acum = Acumuladores(pedidos_demandados=1)

    todos_eventos = []
    for _ in range(50):
        _, _, _, _, evs = despachador.tick(
            robots, pedidos, PoliticaPicking.FIFO, acum
        )
        todos_eventos.extend(evs)
        if acum.pedidos_completados > 0:
            break

    tipos = {e["tipo"] for e in todos_eventos}
    assert "movimiento" in tipos, "Debe emitir eventos de movimiento"
    assert "excavacion" in tipos, "Debe emitir eventos de excavación"
    assert "caja_recuperada" in tipos, "Debe emitir eventos de recuperación"
    assert "pedido_completado" in tipos, "Debe emitir eventos de entrega"


# ------------------------------------------------------------------
# Acumulador de desplazamientos
# ------------------------------------------------------------------

def test_despachador_acumulador_desplazamientos():
    """total_desplazamientos se incrementa en cada movimiento."""
    grilla = _grilla_vacia()
    grilla.agregar(_caja(x=2, y=2, z=0))
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {0: _robot(id=0, x=0, y=0)}
    pedidos = [_pedido()]
    acum = Acumuladores(pedidos_demandados=1)

    for _ in range(30):
        robots_upd, _, _, comp, _ = despachador.tick(
            robots, pedidos, PoliticaPicking.FIFO, acum
        )
        for r in robots_upd:
            robots[r.id] = r
        if comp:
            break

    # Robot se movió: entrada (3 pasos) + salida (3 pasos) + recuperar (1) = 7+
    assert acum.total_desplazamientos >= 6


# ------------------------------------------------------------------
# Delta solo con robots cambiados (bus contract)
# ------------------------------------------------------------------

def test_despachador_solo_robots_cambiados():
    """Solo los robots que cambiaron aparecen en robots_actualizados."""
    grilla = _grilla_vacia()
    grilla.agregar(_caja(x=2, y=2, z=0))
    grilla.agregar(_caja(id_caja="C2", id_sku="SKU002", x=3, y=3, z=0))
    grilla.flush_delta()

    despachador = Despachador(grilla)
    robots = {
        0: _robot(id=0, x=0, y=0),
        1: _robot(id=1, x=4, y=4),
    }
    pedidos = [
        _pedido(id_pedido="P001"),
        _pedido(id_pedido="P002", id_sku="SKU002"),
    ]
    acum = Acumuladores(pedidos_demandados=2)

    # Tick 1: ambos robots obtienen tarea
    robots_upd, _, _, _, _ = despachador.tick(
        robots, pedidos, PoliticaPicking.FIFO, acum
    )
    ids_primera = {r.id for r in robots_upd}
    assert len(ids_primera) >= 1

    # Tick 2: solo los que se movieron
    robots_upd2, _, _, _, _ = despachador.tick(
        robots, pedidos, PoliticaPicking.FIFO, acum
    )
    # robots_upd2 solo contiene robots que cambiaron este tick
    for r in robots_upd2:
        assert robots[r.id] != r, "Robot en delta debe ser distinto al anterior"
