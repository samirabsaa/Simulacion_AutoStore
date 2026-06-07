"""Integración mock M1/M2/M3."""

import time
from pathlib import Path

from bus_persistencia.integration.mock_modules import run_integration_demo


def test_full_integration_flow(tmp_path):
    result = run_integration_demo(tmp_path, semilla=42, num_ticks=50)

    assert result["ticks_written"] == 50
    assert result["final_tick"] == 50
    assert result["m1_reads"] > 0
    assert result["m3_frames"] > 0

    session_path = Path(result["session_path"])
    assert session_path.exists()
    assert session_path.stat().st_size > 0

    meta_path = tmp_path / "metadata" / "metadata_demo.json"
    assert meta_path.exists()


def test_integration_with_concurrent_readers(tmp_path):
    start = time.perf_counter()
    result = run_integration_demo(tmp_path, semilla=7, num_ticks=100)
    elapsed = time.perf_counter() - start

    assert result["final_tick"] == 100
    assert elapsed < 30
