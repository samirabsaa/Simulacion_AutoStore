"""Tests de unidad — Cálculo de KPIs (T-20).

Valida cálculos exactos de MTRP, TBR, TSP, IOG
con division-by-zero protegido.
"""
from __future__ import annotations

import pytest
from bus_persistencia.models.state import Config, GrillaDimensions
from motor.grilla import Grilla
from motor.kpis import Acumuladores, calcular_kpis


def _config(x=5, y=5, z=3, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _grilla_vacia(x=5, y=5, z=3) -> Grilla:
    return Grilla(_config(x=x, y=y, z=z))


# ------------------------------------------------------------------
# MTRP — Movimientos Robot por Pedido
# ------------------------------------------------------------------

def test_mtrp_calculo_correcto():
    """MTRP = total_desplazamientos / pedidos_completados."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(pedidos_completados=4, total_desplazamientos=20)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.MTRP == pytest.approx(5.0)


def test_mtrp_sin_completados():
    """MTRP = 0 cuando no hay pedidos completados."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(total_desplazamientos=20)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.MTRP == 0.0


# ------------------------------------------------------------------
# TBR — Tiempo Bloqueo Robots
# ------------------------------------------------------------------

def test_tbr_calculo_correcto():
    """TBR = (ticks_bloqueados / ticks_totales) * 100."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(ticks_bloqueados=25, ticks_totales=500)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TBR == pytest.approx(5.0)


def test_tbr_sin_ticks():
    """TBR = 0 cuando ticks_totales = 0."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(ticks_bloqueados=5)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TBR == 0.0


# ------------------------------------------------------------------
# TSP — Tasa Satisfacción Pedidos
# ------------------------------------------------------------------

def test_tsp_calculo_correcto():
    """TSP = (pedidos_completados / pedidos_demandados) * 100."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(pedidos_demandados=10, pedidos_completados=8)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TSP == pytest.approx(80.0)


def test_tsp_cien_por_ciento():
    """TSP = 100% cuando todos los pedidos se completan."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores(pedidos_demandados=10, pedidos_completados=10)
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TSP == pytest.approx(100.0)


def test_tsp_sin_demandados():
    """TSP = 0 cuando pedidos_demandados = 0."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores()
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.TSP == 0.0


# ------------------------------------------------------------------
# IOG — Índice Ocupación Grilla
# ------------------------------------------------------------------

def test_iog_vs_ocupacion_config():
    """IOG refleja correctamente cajas_presentes / capacidad_total."""
    cfg = _config(x=3, y=3, z=2)  # capacidad = 18
    grilla = _grilla_vacia(x=3, y=3, z=2)

    from bus_persistencia.models.state import Caja
    for i in range(9):  # 9 cajas = 50%
        grilla.agregar(Caja(id_caja=f"C{i}", id_sku="SKU001", cantidad=1,
                            x=i % 3, y=i // 3, z=0))

    acum = Acumuladores()
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.IOG == pytest.approx(50.0)


def test_iog_cero():
    """IOG = 0% para grilla vacía."""
    grilla = _grilla_vacia()
    cfg = _config()
    acum = Acumuladores()
    kpis = calcular_kpis(acum, grilla, cfg)
    assert kpis.IOG == 0.0
