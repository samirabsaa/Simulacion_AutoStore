"""T-01 — Bus de Estado Central."""

import pytest

from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus, WriterNotAuthorizedError
from bus_persistencia.models.state import (
    KPISet,
    ModoTurno,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
    TickDelta,
)


def test_read_snapshot_returns_all_fields():
    bus = StateBus()
    bus.set_modo(ModoTurno.NOCTURNO)
    bus.set_policy(PoliticaPicking.PRIORIDAD_POSICION)
    bus.set_pedidos_cola([
        Pedido("P1", "SKU-A", 1, "D1"),
    ])

    snap = bus.read_snapshot()
    assert snap.tick == 0
    assert snap.modo == ModoTurno.NOCTURNO
    assert snap.politica == PoliticaPicking.PRIORIDAD_POSICION
    assert len(snap.pedidos.cola) == 1
    assert snap.kpis.TSP == 0.0


def test_write_tick_delta_updates_state():
    bus = StateBus()
    robot = Robot(1, 3, 4, 0, RobotEstado.DESPLAZANDOSE)
    delta = TickDelta(
        robots_delta=[robot],
        kpis=KPISet(TSP=90.0, IOG=75.0),
    )
    tick = bus.write_tick_delta(M2_WRITER_ID, delta)
    assert tick == 1

    snap = bus.read_snapshot()
    assert snap.tick == 1
    assert snap.robots[0].x == 3
    assert snap.kpis.TSP == 90.0


def test_only_m2_can_write():
    bus = StateBus()
    with pytest.raises(WriterNotAuthorizedError):
        bus.write_tick_delta("M1", TickDelta())


def test_read_snapshot_returns_deep_copy():
    bus = StateBus()
    bus.write_tick_delta(M2_WRITER_ID, TickDelta(kpis=KPISet(TSP=50.0)))

    snap1 = bus.read_snapshot()
    snap2 = bus.read_snapshot()
    assert snap1 is not snap2
    assert snap1.kpis.TSP == snap2.kpis.TSP


def test_get_metadata():
    bus = StateBus()
    bus.set_policy(PoliticaPicking.FIFO)
    meta = bus.get_metadata()
    assert "tick" in meta
    assert meta["politica"] == "fifo"
