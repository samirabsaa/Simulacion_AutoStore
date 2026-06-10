"""Tests de unidad — Grilla 3D (T-09, T-10, T-11).

Valida:
- buscar_por_sku ordena por z ascendente (más accesibles primero)
- primera_caja_accesible selecciona por menor costo de excavación
- puerto_mas_cercano calcula distancia Manhattan correcta
"""
from __future__ import annotations

import pytest
from bus_persistencia.models.state import Caja, Config, GrillaDimensions
from motor.grilla import Grilla


def _config(x=5, y=5, z=3, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _grilla_vacia(x=5, y=5, z=3) -> Grilla:
    return Grilla(_config(x=x, y=y, z=z))


# ------------------------------------------------------------------
# buscar_por_sku
# ------------------------------------------------------------------

def test_grilla_buscar_por_sku_orden_z():
    """buscar_por_sku retorna cajas ordenadas por z ascendente."""
    grilla = _grilla_vacia()
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=2, y=2, z=2))
    grilla.agregar(Caja(id_caja="C2", id_sku="SKU001", cantidad=1, x=2, y=2, z=0))
    grilla.agregar(Caja(id_caja="C3", id_sku="SKU001", cantidad=1, x=2, y=2, z=1))

    resultados = grilla.buscar_por_sku("SKU001")

    assert [c.id_caja for c in resultados] == ["C2", "C3", "C1"]


def test_grilla_buscar_por_sku_no_encontrado():
    """Retorna lista vacía si no hay cajas del SKU."""
    grilla = _grilla_vacia()
    assert grilla.buscar_por_sku("SKU_INEXISTENTE") == []


# ------------------------------------------------------------------
# primera_caja_accesible
# ------------------------------------------------------------------

def test_grilla_primera_caja_accesible_excavacion():
    """Selecciona la caja con menor costo de excavación (menos cajas encima)."""
    grilla = _grilla_vacia()
    # C1 en z=0 sin nada encima → costo 0
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=0, y=0, z=0))
    # C2 en z=1 con caja encima → costo 1
    grilla.agregar(Caja(id_caja="C2", id_sku="SKU001", cantidad=1, x=1, y=1, z=1))
    grilla.agregar(Caja(id_caja="ENC", id_sku="SKU999", cantidad=1, x=1, y=1, z=2))

    caja = grilla.primera_caja_accesible("SKU001")
    assert caja is not None
    assert caja.id_caja == "C1"


def test_grilla_primera_caja_accesible_no_encontrado():
    """Retorna None si no hay cajas del SKU."""
    grilla = _grilla_vacia()
    assert grilla.primera_caja_accesible("SKU_INEXISTENTE") is None


# ------------------------------------------------------------------
# puerto_mas_cercano
# ------------------------------------------------------------------

def test_grilla_puerto_mas_cercano_manhattan():
    """Retorna el puerto con menor distancia Manhattan."""
    grilla = _grilla_vacia(x=5, y=5, z=3)
    # Columna (0, 0) — más cercana al puerto (0, 0) con distancia 0
    px0, py0 = grilla.puerto_mas_cercano(0, 0)
    assert (px0, py0) == (0, 0)

    # Columna (4, 4) — más cercana al puerto (4, 4) con distancia 0
    px4, py4 = grilla.puerto_mas_cercano(4, 4)
    assert (px4, py4) == (4, 4)

    # Columna (2, 2) — en una grilla 5x5, los puertos están en bordes
    # Distancias: (0,2)=2, (2,0)=2, (4,2)=2, (2,4)=2
    # El mínimo es cualquiera del borde a distancia 2
    px, py = grilla.puerto_mas_cercano(2, 2)
    assert abs(px - 2) + abs(py - 2) == 2
