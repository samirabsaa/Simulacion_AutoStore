"""Mocks de M1/M2/M3 para pruebas de integración."""

from __future__ import annotations

import random
import threading
import time
from pathlib import Path

from bus_persistencia.bus.state_bus import StateBus
from bus_persistencia.models.state import (
    M2_WRITER_ID,
    KPISet,
    ModoTurno,
    PoliticaPicking,
    Robot,
    RobotEstado,
    TickDelta,
)
from bus_persistencia.persistence.config_loader import load_config
from bus_persistencia.persistence.execution_metadata import (
    MetadataStore,
    apply_seed,
    create_execution_metadata,
)
from bus_persistencia.persistence.ola_loader import load_ola
from bus_persistencia.persistence.session_logger import SessionLogger


class MockM2Motor:
    """Simula M2 escribiendo ticks sintéticos al Bus."""

    def __init__(self, bus: StateBus, num_ticks: int = 100) -> None:
        self._bus = bus
        self._num_ticks = num_ticks

    def run(self) -> list[int]:
        ticks_written = []
        for i in range(1, self._num_ticks + 1):
            robot = Robot(
                id=1,
                x=i % 10,
                y=(i * 2) % 10,
                z=0,
                estado=RobotEstado.DESPLAZANDOSE,
            )
            kpis = KPISet(
                TSP=min(100.0, i * 0.1),
                IOG=70.0 + (i % 5),
                MTRP=float(i),
            )
            delta = TickDelta(
                robots_delta=[robot],
                kpis=kpis,
                eventos=[
                    {
                        "tipo": "movimiento",
                        "robot_id": 1,
                        "tick": i,
                        "timestamp": f"2026-06-01T12:00:{i % 60:02d}Z",
                    },
                    {
                        "tipo": "kpi_update",
                        "timestamp": f"2026-06-01T12:00:{i % 60:02d}Z",
                        **kpis.as_dict(),
                    },
                ],
            )
            tick = self._bus.write_tick_delta(M2_WRITER_ID, delta)
            ticks_written.append(tick)
        return ticks_written


class MockM1UI:
    """Simula M1 leyendo snapshots y configurando el Bus."""

    def __init__(self, bus: StateBus) -> None:
        self._bus = bus
        self._snapshots_read: list[int] = []

    def configure_from_files(
        self, config_path: str, ola_path: str, modo: ModoTurno, politica: PoliticaPicking
    ) -> None:
        config_result = load_config(config_path)
        if not config_result.is_valid:
            raise ValueError("Config inválido")
        self._bus.set_config(config_result.data)
        self._bus.set_modo(modo)
        self._bus.set_policy(politica)

        ola_result = load_ola(ola_path)
        if not ola_result.is_valid:
            raise ValueError("Ola inválida")
        self._bus.set_pedidos_cola(ola_result.data)

    def poll_kpis(self, iterations: int = 10) -> list[dict]:
        results = []
        for _ in range(iterations):
            snap = self._bus.read_snapshot()
            self._snapshots_read.append(snap.tick)
            results.append(snap.kpis.as_dict())
            time.sleep(0.001)
        return results


class MockM3Renderer:
    """Simula M3 leyendo snapshots para render."""

    def __init__(self, bus: StateBus) -> None:
        self._bus = bus
        self._frames: list[int] = []

    def render_loop(self, frames: int = 10) -> list[int]:
        for _ in range(frames):
            snap = self._bus.read_snapshot()
            self._frames.append(snap.tick)
            time.sleep(0.001)
        return self._frames


def run_integration_demo(
    output_dir: str | Path,
    semilla: int = 42,
    num_ticks: int = 50,
) -> dict:
    """Ejecuta flujo completo mock M1→M2→M3 con persistencia."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    apply_seed(semilla)
    logger = SessionLogger(output / "sesion_demo.csv")
    bus = StateBus(session_logger=logger)

    m1 = MockM1UI(bus)
    data_dir = Path(__file__).resolve().parents[2] / "data"
    m1.configure_from_files(
        str(data_dir / "config.json"),
        str(data_dir / "ola.csv"),
        ModoTurno.DIURNO,
        PoliticaPicking.FIFO,
    )

    meta = create_execution_metadata(
        "demo", semilla, "diurno", "fifo",
        data_dir / "config.json", data_dir / "ola.csv",
    )
    MetadataStore(output / "metadata").save(meta)
    logger.write_metadata_header(meta.to_dict())

    m2 = MockM2Motor(bus, num_ticks=num_ticks)
    m3 = MockM3Renderer(bus)

    reader_m1 = threading.Thread(target=m1.poll_kpis, args=(20,))
    reader_m3 = threading.Thread(target=m3.render_loop, args=(20,))
    reader_m1.start()
    reader_m3.start()

    ticks = m2.run()
    reader_m1.join()
    reader_m3.join()

    logger.flush_all()

    final_snap = bus.read_snapshot()
    meta.kpis_finales = final_snap.kpis.as_dict()
    MetadataStore(output / "metadata").save(meta)

    return {
        "ticks_written": len(ticks),
        "final_tick": final_snap.tick,
        "m1_reads": len(m1._snapshots_read),
        "m3_frames": len(m3._frames),
        "session_path": str(logger.output_path),
    }
