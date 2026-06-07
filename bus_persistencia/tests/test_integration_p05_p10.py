"""P05 y P10 — KPIs en sesión y reporte comparativo."""

import csv
from pathlib import Path

from bus_persistencia.integration.mock_modules import run_integration_demo
from bus_persistencia.models.state import KPI_NAMES
from bus_persistencia.persistence.execution_metadata import ExecutionMetadata, MetadataStore
from bus_persistencia.persistence.report_generator import generate_report


def test_p05_session_and_metadata(tmp_path: Path) -> None:
    result = run_integration_demo(tmp_path, semilla=42, num_ticks=25)
    session = Path(result["session_path"])
    assert session.exists()
    assert "movimiento" in session.read_text(encoding="utf-8")
    assert (tmp_path / "metadata" / "metadata_demo.json").exists()


def test_p10_comparative_report(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "metadata")
    kpis_a = {name: float(i * 10) for i, name in enumerate(KPI_NAMES)}
    kpis_b = {name: float(i * 12) for i, name in enumerate(KPI_NAMES)}

    for nombre, kpis in (("ejec_a", kpis_a), ("ejec_b", kpis_b)):
        meta = ExecutionMetadata(
            nombre_ejecucion=nombre,
            semilla=42,
            modo="diurno",
            politica="fifo",
            config_path="config.json",
            data_path="ola.csv",
            config_hash="abc",
            data_hash="def",
            kpis_finales=kpis,
        )
        store.save(meta)

    report = generate_report(
        "ejec_a", "ejec_b", tmp_path / "reporte_comp.csv", metadata_dir=tmp_path / "metadata"
    )

    with report.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 7
    assert all("Delta_%" in row for row in rows)
