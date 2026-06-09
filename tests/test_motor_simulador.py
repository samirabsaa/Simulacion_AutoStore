"""Tests de unidad — Simulador (orquestador central).

Valida:
- Sesión diurna completa sin errores
- Cambio de modo diurno ↔ nocturno
- Reproducibilidad: misma semilla produce mismos resultados
- Single-writer: solo M2_WRITER_ID puede escribir
"""
from __future__ import annotations

import pytest
from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus, WriterNotAuthorizedError
from bus_persistencia.models.state import (
    Caja,
    Config,
    GrillaDimensions,
    ModoTurno,
    Pedido,
    PoliticaPicking,
    TickDelta,
)
from bus_persistencia.models.state import KPISet
from motor.simulador import AutoStoreSimulator


def _config(x=4, y=4, z=2, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


# ------------------------------------------------------------------
# Sesión diurna completa
# ------------------------------------------------------------------

def test_simulador_full_diurno_session():
    """Simula turno diurno completo sin errores."""
    bus = StateBus()
    cfg = _config(x=4, y=4, z=2, robots=2, ocupacion=0.0)
    bus.set_config(cfg)
    bus.set_pedidos_cola([
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
        Pedido(id_pedido="P002", id_sku="SKU002", cantidad=1, destino="B"),
    ])

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=42)

    sim._grilla.agregar(Caja(id_caja="C001", id_sku="SKU001", cantidad=1, x=2, y=2, z=0))
    sim._grilla.agregar(Caja(id_caja="C002", id_sku="SKU002", cantidad=1, x=1, y=1, z=0))

    ticks = 0
    for _ in range(80):
        sim.avanzar_tick()
        ticks += 1
        if sim.ha_terminado():
            break

    assert ticks > 0
    assert len(sim.pedidos_completados) == 2, (
        f"Completó {len(sim.pedidos_completados)}/2 con 2 robots y 2 cajas en z=0"
    )
    assert sim.tick > 0


# ------------------------------------------------------------------
# Cambio de modo diurno ↔ nocturno
# ------------------------------------------------------------------

def test_simulador_modo_switch():
    """Cambiar de diurno a nocturno limpia contadores de turno."""
    bus = StateBus()
    cfg = _config(x=4, y=4, z=2, robots=2, ocupacion=0.0)
    bus.set_config(cfg)
    bus.set_pedidos_cola([
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
    ])

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=42)
    sim._grilla.agregar(Caja(id_caja="C001", id_sku="SKU001", cantidad=1, x=2, y=2, z=0))

    # Algunos ticks diurnos
    for _ in range(5):
        sim.avanzar_tick()

    sim.cambiar_modo(ModoTurno.NOCTURNO)
    assert sim.modo == ModoTurno.NOCTURNO
    assert sim._acum.ticks_turno_actual == 0

    # El próximo delta debe incluir modo=NOCTURNO
    sim.avanzar_tick()
    snap = bus.read_snapshot()
    assert snap.modo == ModoTurno.NOCTURNO


# ------------------------------------------------------------------
# Reproducibilidad (misma semilla)
# ------------------------------------------------------------------

def test_simulador_reproducibilidad():
    """Misma semilla produce grilla inicial idéntica."""
    bus_a = StateBus()
    bus_a.set_config(_config(x=3, y=3, z=2, ocupacion=50.0))
    bus_a.set_pedidos_cola([
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
    ])

    bus_b = StateBus()
    bus_b.set_config(_config(x=3, y=3, z=2, ocupacion=50.0))
    bus_b.set_pedidos_cola([
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
    ])

    sim_a = AutoStoreSimulator(bus_a)
    sim_a.inicializar_desde_bus(seed=12345)

    sim_b = AutoStoreSimulator(bus_b)
    sim_b.inicializar_desde_bus(seed=12345)

    # Comparar grillas: misma seed → mismos contenidos
    ids_a = {c.id_caja for c in sim_a._grilla._celdas.values()}
    ids_b = {c.id_caja for c in sim_b._grilla._celdas.values()}
    assert ids_a == ids_b


# ------------------------------------------------------------------
# Single-writer — bus contract
# ------------------------------------------------------------------

def test_simulador_single_writer_bus():
    """Solo M2_WRITER_ID puede escribir en el bus."""
    bus = StateBus()
    bus.set_config(_config())
    bus.set_pedidos_cola([
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
    ])

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=42)
    sim._grilla.agregar(Caja(id_caja="C001", id_sku="SKU001", cantidad=1, x=2, y=2, z=0))

    # M2 escribe sin error
    sim.avanzar_tick()
    assert bus.read_snapshot().tick >= 1

    # Otro writer_id es rechazado
    with pytest.raises(WriterNotAuthorizedError):
        bus.write_tick_delta("M1", TickDelta(kpis=KPISet()))


# ------------------------------------------------------------------
# ha_terminado correcto
# ------------------------------------------------------------------

def test_simulador_terminado():
    """ha_terminado() retorna True cuando no hay pedidos ni robots activos."""
    bus = StateBus()
    cfg = _config(x=4, y=4, z=2, robots=1, ocupacion=0.0)
    bus.set_config(cfg)
    bus.set_pedidos_cola([])  # Sin pedidos

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=42)

    assert sim.ha_terminado() is True


def test_simulador_no_terminado_con_pedidos():
    """ha_terminado() retorna False cuando hay pedidos pendientes."""
    bus = StateBus()
    cfg = _config(x=4, y=4, z=2, robots=1, ocupacion=0.0)
    bus.set_config(cfg)
    bus.set_pedidos_cola([
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
    ])

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=42)

    assert sim.ha_terminado() is False
