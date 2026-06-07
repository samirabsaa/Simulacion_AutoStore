"""Generación de reporte_comp.csv comparativo (T-07)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from bus_persistencia.models.state import KPI_NAMES
from bus_persistencia.persistence.execution_metadata import MetadataStore


def _format_delta(value_a: float, value_b: float) -> str:
    if value_a == 0:
        if value_b == 0:
            return "0.00%"
        return "N/A"
    delta = ((value_b - value_a) / value_a) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.2f}%"


def _kpis_from_metadata(store: MetadataStore, nombre: str) -> dict[str, float]:
    meta = store.load(nombre)
    return meta.kpis_finales


def _kpis_from_session(session_path: Path) -> dict[str, float]:
    """Extrae último evento kpi_update de sesion CSV."""
    if not session_path.exists():
        raise FileNotFoundError(f"Sesión no encontrada: {session_path}")

    last_kpis: dict[str, float] = {name: 0.0 for name in KPI_NAMES}
    with session_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("tipo_evento") == "kpi_update":
                payload = json.loads(row.get("payload_json", "{}"))
                for name in KPI_NAMES:
                    if name in payload:
                        last_kpis[name] = float(payload[name])
    return last_kpis


def generate_report(
    ejecucion_a: str,
    ejecucion_b: str,
    output_path: str | Path,
    metadata_dir: str | Path | None = None,
    session_dir: str | Path | None = None,
    kpis_a: dict[str, float] | None = None,
    kpis_b: dict[str, float] | None = None,
) -> Path:
    """
    Genera reporte_comp.csv con tabla KPI | Ejecución A | Ejecución B | Δ%.

    Puede leer KPIs desde MetadataStore o desde sesion_*.csv.
    """
    out = Path(output_path)

    if kpis_a is None or kpis_b is None:
        if metadata_dir is not None:
            store = MetadataStore(metadata_dir)
            kpis_a = kpis_a or _kpis_from_metadata(store, ejecucion_a)
            kpis_b = kpis_b or _kpis_from_metadata(store, ejecucion_b)
        elif session_dir is not None:
            session_base = Path(session_dir)
            kpis_a = kpis_a or _kpis_from_session(
                session_base / f"sesion_{ejecucion_a}.csv"
            )
            kpis_b = kpis_b or _kpis_from_session(
                session_base / f"sesion_{ejecucion_b}.csv"
            )
        else:
            raise ValueError(
                "Debe proveer kpis_a/kpis_b o metadata_dir/session_dir"
            )

    rows = []
    for kpi in KPI_NAMES:
        val_a = kpis_a.get(kpi, 0.0)
        val_b = kpis_b.get(kpi, 0.0)
        rows.append(
            {
                "KPI": kpi,
                f"Ejecucion_{ejecucion_a}": f"{val_a:.4f}",
                f"Ejecucion_{ejecucion_b}": f"{val_b:.4f}",
                "Delta_%": _format_delta(val_a, val_b),
            }
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "KPI",
        f"Ejecucion_{ejecucion_a}",
        f"Ejecucion_{ejecucion_b}",
        "Delta_%",
    ]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out
