"""T-02 — Concurrencia single-writer / multiple-reader."""

import threading

from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus
from bus_persistencia.models.state import KPISet, Robot, RobotEstado, TickDelta


def test_1000_ticks_with_concurrent_readers_no_exceptions():
    bus = StateBus()
    errors: list[Exception] = []
    ticks_seen_m1: list[int] = []
    ticks_seen_m3: list[int] = []
    stop = threading.Event()

    def reader_m1():
        try:
            while not stop.is_set():
                snap = bus.read_snapshot()
                ticks_seen_m1.append(snap.tick)
        except Exception as exc:
            errors.append(exc)

    def reader_m3():
        try:
            while not stop.is_set():
                snap = bus.read_snapshot()
                ticks_seen_m3.append(snap.tick)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=reader_m1)
    t2 = threading.Thread(target=reader_m3)
    t1.start()
    t2.start()

    for i in range(1, 1001):
        robot = Robot(1, i % 10, (i * 2) % 10, 0, RobotEstado.DESPLAZANDOSE)
        delta = TickDelta(
            robots_delta=[robot],
            kpis=KPISet(TSP=float(i % 100), IOG=70.0),
        )
        tick = bus.write_tick_delta(M2_WRITER_ID, delta)
        assert tick == i

    stop.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not errors, f"Errores de concurrencia: {errors}"
    assert len(ticks_seen_m1) > 0
    assert len(ticks_seen_m3) > 0

    final = bus.read_snapshot()
    assert final.tick == 1000
