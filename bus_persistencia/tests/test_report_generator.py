"""T-07 / P10 — Reporte comparativo de KPIs."""

import csv
from pathlib import Path

from bus_persistencia.models.state import KPI_NAMES
from bus_persistencia.persistence.execution_metadata import (
    ExecutionMetadata,
    MetadataStore,
)
from bus_persistencia.persistence.report_generator import generate_report


def _save_metadata(tmp_path: Path, nombre: str, kpis: dict[str, float]) -> None:
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
    MetadataStore(tmp_path).save(meta)


def test_generate_report_with_seven_kpis(tmp_path):
    kpis_a = {name: float(i * 10) for i, name in enumerate(KPI_NAMES)}
    kpis_b = {name: float(i * 12) for i, name in enumerate(KPI_NAMES)}

    _save_metadata(tmp_path, "ejec_a", kpis_a)
    _save_metadata(tmp_path, "ejec_b", kpis_b)

    out = generate_report(
        "ejec_a",
        "ejec_b",
        tmp_path / "reporte_comp.csv",
        metadata_dir=tmp_path,
    )

    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 7
    kpi_names = [r["KPI"] for r in rows]
    assert kpi_names == list(KPI_NAMES)


def test_delta_percentage_calculation(tmp_path):
    _save_metadata(tmp_path, "A", {"TSP": 100.0, "TPCP": 0, "MTRP": 0, "IOG": 0, "TR": 0, "TI": 0, "TBR": 0})
    _save_metadata(tmp_path, "B", {"TSP": 110.0, "TPCP": 0, "MTRP": 0, "IOG": 0, "TR": 0, "TI": 0, "TBR": 0})

    out = generate_report("A", "B", tmp_path / "reporte.csv", metadata_dir=tmp_path)

    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    tsp_row = next(r for r in rows if r["KPI"] == "TSP")
    assert tsp_row["Delta_%"] == "+10.00%"


def test_report_legible_in_excel_format(tmp_path):
    kpis_a = {"TSP": 98.5, "TPCP": 12.0, "MTRP": 8.0, "IOG": 72.0, "TR": 15.0, "TI": 0.0, "TBR": 5.0}
    kpis_b = {"TSP": 95.2, "TPCP": 14.0, "MTRP": 6.0, "IOG": 75.0, "TR": 18.0, "TI": 0.0, "TBR": 3.0}

    out = generate_report(
        "fifo_run",
        "prioridad_run",
        tmp_path / "reporte_comp.csv",
        kpis_a=kpis_a,
        kpis_b=kpis_b,
    )

    content = out.read_text(encoding="utf-8")
    assert "KPI,Ejecucion_fifo_run,Ejecucion_prioridad_run,Delta_%" in content
    assert "TSP" in content
    assert "TBR" in content
