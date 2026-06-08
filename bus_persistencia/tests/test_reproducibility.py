"""T-08 — Reproducibilidad determinista."""

import json
import random
from pathlib import Path

from bus_persistencia.integration.mock_modules import run_integration_demo
from bus_persistencia.persistence.execution_metadata import (
    MetadataStore,
    apply_seed,
    create_execution_metadata,
    file_hash,
)
from bus_persistencia.tests.conftest import DATA_DIR


def test_same_seed_produces_same_random_sequence():
    apply_seed(42)
    seq_a = [random.randint(0, 1000) for _ in range(20)]

    apply_seed(42)
    seq_b = [random.randint(0, 1000) for _ in range(20)]

    assert seq_a == seq_b


def test_metadata_records_seed_and_parameters(tmp_path):
    meta = create_execution_metadata(
        "test_run",
        12345,
        "diurno",
        "fifo",
        DATA_DIR / "config.json",
        DATA_DIR / "ola.csv",
    )
    store = MetadataStore(tmp_path)
    path = store.save(meta)

    loaded = store.load("test_run")
    assert loaded.semilla == 12345
    assert loaded.modo == "diurno"
    assert loaded.politica == "fifo"
    assert loaded.config_hash == file_hash(DATA_DIR / "config.json")
    assert path.exists()


def test_same_inputs_and_seed_produce_identical_session(tmp_path):
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    result_a = run_integration_demo(out_a, semilla=99, num_ticks=30)
    result_b = run_integration_demo(out_b, semilla=99, num_ticks=30)

    assert result_a["final_tick"] == result_b["final_tick"]

    events_a = Path(result_a["session_path"]).read_text(encoding="utf-8")
    events_b = Path(result_b["session_path"]).read_text(encoding="utf-8")
    assert events_a == events_b

    meta_a = json.loads((out_a / "metadata" / "metadata_demo.json").read_text())
    meta_b = json.loads((out_b / "metadata" / "metadata_demo.json").read_text())
    assert meta_a["semilla"] == meta_b["semilla"] == 99
    assert meta_a["config_hash"] == meta_b["config_hash"]
