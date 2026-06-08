"""T-02 — Latencia P99 de escritura < 1 ms."""

import time

from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus
from bus_persistencia.models.state import KPISet, Robot, RobotEstado, TickDelta


def _percentile(values: list[float], pct: float) -> float:
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * pct / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def test_write_latency_p99_under_1ms():
    bus = StateBus()
    latencies: list[float] = []

    for i in range(1000):
        robot = Robot(1, i % 10, (i * 3) % 10, 0, RobotEstado.DESPLAZANDOSE)
        delta = TickDelta(
            robots_delta=[robot],
            kpis=KPISet(TSP=float(i), MTRP=float(i * 2)),
        )
        start = time.perf_counter()
        bus.write_tick_delta(M2_WRITER_ID, delta)
        latencies.append((time.perf_counter() - start) * 1000)

    p99 = _percentile(latencies, 99)
    assert p99 < 1.0, f"P99 latency {p99:.4f} ms excede 1 ms"
