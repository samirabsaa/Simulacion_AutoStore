"""T-06 / P05 — SessionLogger con buffer diferido."""

import csv
import json
import time
from pathlib import Path

from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus
from bus_persistencia.models.state import TickDelta
from bus_persistencia.persistence.session_logger import SessionLogger


def test_events_buffered_without_immediate_disk_write(tmp_path):
    session_path = tmp_path / "sesion_test.csv"
    logger = SessionLogger(session_path, defer_io=True)

    logger.buffer_event(1, {"tipo": "movimiento", "robot_id": 1})
    buffered = logger.get_buffered_events()
    assert len(buffered) >= 1
    assert not session_path.exists()


def test_flush_writes_csv_with_all_events(tmp_path):
    session_path = tmp_path / "sesion_test.csv"
    logger = SessionLogger(session_path, defer_io=False)
    bus = StateBus(session_logger=logger)

    for i in range(5):
        bus.write_tick_delta(
            M2_WRITER_ID,
            TickDelta(eventos=[{"tipo": "movimiento", "robot_id": i}]),
        )

    logger.flush_all()
    time.sleep(0.1)

    assert session_path.exists()
    events = logger.read_all_events()
    assert len(events) == 5
    assert events[0]["tipo_evento"] == "movimiento"


def test_kpi_events_in_session(tmp_path):
    session_path = tmp_path / "sesion_kpi.csv"
    logger = SessionLogger(session_path, defer_io=False)
    bus = StateBus(session_logger=logger)

    bus.write_tick_delta(
        M2_WRITER_ID,
        TickDelta(
            eventos=[
                {
                    "tipo": "kpi_update",
                    "TSP": 95.0,
                    "TPCP": 12.5,
                    "MTRP": 8.0,
                    "IOG": 72.0,
                    "TR": 15.0,
                    "TI": 0.0,
                    "TBR": 5.0,
                }
            ]
        ),
    )
    logger.flush_all()

    with session_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    kpi_row = rows[0]
    payload = json.loads(kpi_row["payload_json"])
    assert payload["TSP"] == 95.0
    assert len([k for k in payload if k in ("TSP", "TPCP", "MTRP", "IOG", "TR", "TI", "TBR")]) == 7


def test_tick_cycle_not_blocked_by_io(tmp_path):
    """Escritura a disco no debe agregar latencia medible al ciclo de tick."""
    session_path = tmp_path / "sesion_perf.csv"
    logger = SessionLogger(session_path, defer_io=True)
    bus = StateBus(session_logger=logger)

    latencies = []
    for i in range(100):
        start = time.perf_counter()
        bus.write_tick_delta(
            M2_WRITER_ID,
            TickDelta(eventos=[{"tipo": "movimiento", "tick": i}]),
        )
        latencies.append((time.perf_counter() - start) * 1000)

    logger.flush_all()
    avg = sum(latencies) / len(latencies)
    assert avg < 2.0, f"Latencia promedio de tick {avg:.2f} ms excede 2 ms"
