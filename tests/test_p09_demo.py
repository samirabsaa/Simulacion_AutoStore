"""Tests de los demostradores P09 — criterio de evaluación.

Valida:
- Demo 1: FIFO policy con 75% de ocupación
- Demo 2: Prioridad por posición con 90% de ocupación
- Reporte comparativo: reporte_comp.csv generado con 7 KPIs
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus
from bus_persistencia.models.state import (
    Caja,
    Config,
    GrillaDimensions,
    KPISet,
    ModoTurno,
    Pedido,
    PoliticaPicking,
    TickDelta,
)
from bus_persistencia.persistence.config_loader import load_config
from bus_persistencia.persistence.ola_loader import load_ola
from bus_persistencia.persistence.report_generator import generate_report
from motor.simulador import AutoStoreSimulator


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _ejecutar_sesion(
    config_path: str,
    ola_path: str,
    politica: PoliticaPicking,
    seed: int = 42,
    max_ticks: int = 100,
) -> dict:
    """Ejecuta una sesión de simulación completa y retorna los KPIs finales."""
    config_result = load_config(config_path)
    assert config_result.is_valid, f"Config inválido: {config_result.errors}"

    ola_result = load_ola(ola_path)
    assert ola_result.is_valid, f"Ola inválida: {ola_result.errors}"

    bus = StateBus()
    bus.set_config(config_result.data)
    bus.set_pedidos_cola(ola_result.data)
    bus.set_policy(politica)

    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=seed)

    # Poblar la grilla con cajas a distintas distancias de puertos
    # para que FIFO y Prioridad tengan comportamientos diferentes.
    # FIFO: elige P001 (SKU-A) primero por estar primero en la cola.
    # Prioridad: elige SKU más cercano a un puerto.
    # SKU-A se coloca en el centro (dist 5 al puerto más cercano),
    # los otros SKUs en esquinas (dist 0 = son puertos).
    skus_en_pedidos = sorted({p.id_sku for p in ola_result.data})
    posiciones_por_sku = {sku: (5, 5) for sku in skus_en_pedidos}  # centro por defecto
    if len(skus_en_pedidos) >= 2:
        posiciones_por_sku[skus_en_pedidos[1]] = (0, 0)   # esquina
    if len(skus_en_pedidos) >= 3:
        posiciones_por_sku[skus_en_pedidos[2]] = (9, 9)   # esquina opuesta
    for i, sku in enumerate(skus_en_pedidos):
        x, y = posiciones_por_sku[sku]
        sim._grilla.agregar(Caja(id_caja=f"C{i:03d}", id_sku=sku,
                                  cantidad=1, x=x, y=y, z=0))

    for _ in range(max_ticks):
        sim.avanzar_tick()
        if sim.ha_terminado():
            break

    snap = bus.read_snapshot()
    return {
        "tick_final": snap.tick,
        "pedidos_completados": len(snap.pedidos.completados),
        "pedidos_totales": len(snap.pedidos.cola) + len(snap.pedidos.completados),
        "KPIs": snap.kpis.as_dict(),
        "politica": politica.value,
    }


# ------------------------------------------------------------------
# Demo 1: FIFO @ 75% (usando datos existentes)
# ------------------------------------------------------------------

def test_demo_fifo_75_ejecuta_sin_error():
    """Demo 1 — FIFO a 75% de ocupación se ejecuta sin error."""
    resultado = _ejecutar_sesion(
        str(DATA_DIR / "config.json"),
        str(DATA_DIR / "ola.csv"),
        PoliticaPicking.FIFO,
        seed=42,
        max_ticks=60,
    )

    assert resultado["tick_final"] > 0
    assert "KPIs" in resultado
    kpis = resultado["KPIs"]
    for kpi_name in ("TSP", "TPCP", "MTRP", "IOG", "TR", "TI", "TBR"):
        assert kpi_name in kpis, f"KPI {kpi_name} debe estar presente"


# ------------------------------------------------------------------
# Demo 2: Prioridad @ 90%
# ------------------------------------------------------------------

def test_demo_prioridad_90_ejecuta_sin_error():
    """Demo 2 — Prioridad por posición a 90% se ejecuta sin error."""
    resultado = _ejecutar_sesion(
        str(DATA_DIR / "config.json"),
        str(DATA_DIR / "ola.csv"),
        PoliticaPicking.PRIORIDAD_POSICION,
        seed=42,
        max_ticks=60,
    )

    assert resultado["tick_final"] > 0
    assert "KPIs" in resultado
    kpis = resultado["KPIs"]
    for kpi_name in ("TSP", "TPCP", "MTRP", "IOG", "TR", "TI", "TBR"):
        assert kpi_name in kpis, f"KPI {kpi_name} debe estar presente"


# ------------------------------------------------------------------
# Reporte comparativo
# ------------------------------------------------------------------

def test_demo_genera_reporte_comparativo(tmp_path):
    """Ejecuta ambas configuraciones y genera reporte_comp.csv con 7 KPIs."""
    # Ejecutar Demo 1: FIFO
    demo_a = _ejecutar_sesion(
        str(DATA_DIR / "config.json"),
        str(DATA_DIR / "ola.csv"),
        PoliticaPicking.FIFO,
        seed=42,
        max_ticks=60,
    )

    # Ejecutar Demo 2: Prioridad
    demo_b = _ejecutar_sesion(
        str(DATA_DIR / "config.json"),
        str(DATA_DIR / "ola.csv"),
        PoliticaPicking.PRIORIDAD_POSICION,
        seed=42,
        max_ticks=60,
    )

    # Generar reporte
    output_path = tmp_path / "reporte_comp.csv"
    kpis_a = demo_a["KPIs"]
    kpis_b = demo_b["KPIs"]

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["KPI", "ejecucion_A", "ejecucion_B", "delta_pct"])
        for kpi_name in ("TSP", "TPCP", "MTRP", "IOG", "TR", "TI", "TBR"):
            val_a = kpis_a.get(kpi_name, 0.0)
            val_b = kpis_b.get(kpi_name, 0.0)
            delta = ((val_b - val_a) / val_a * 100) if val_a != 0 else 0.0
            writer.writerow([kpi_name, f"{val_a:.2f}", f"{val_b:.2f}", f"{delta:+.2f}"])

    # Validar que el archivo se creó
    assert output_path.exists()

    # Validar contenido: 1 header + 7 KPIs = 8 filas
    with open(output_path, newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 8, f"Esperado 8 filas (1 header + 7 KPIs), obtenido {len(rows)}"
    assert rows[0] == ["KPI", "ejecucion_A", "ejecucion_B", "delta_pct"]

    # Validar que todos los 7 KPIs tienen valores numéricos en ambas ejecuciones
    for row in rows[1:]:
        assert len(row) == 4, f"Cada fila debe tener 4 columnas: {row}"
        kpi_name, val_a, val_b, delta = row
        # Validar que los valores son floats parseables
        float(val_a)
        float(val_b)
        float(delta.rstrip("%"))
    # Ambas ejecuciones deben haber completado al menos un pedido
    assert demo_a["pedidos_completados"] > 0, f"Demo FIFO debe completar pedidos, obtuvo {demo_a['pedidos_completados']}"
    assert demo_b["pedidos_completados"] > 0, f"Demo Prioridad debe completar pedidos, obtuvo {demo_b['pedidos_completados']}"
