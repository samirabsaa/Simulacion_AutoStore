"""Tests de unidad — Turno nocturno (T-19).

Valida:
- procesar_nocturno coloca cajas de la cola en la grilla
- Grilla llena: no coloca y emite advertencia
"""
from __future__ import annotations

import pytest
from bus_persistencia.models.state import Caja, Config, GrillaDimensions, Robot, RobotEstado
from motor.grilla import Grilla
from motor.kpis import Acumuladores
from motor.modos import procesar_nocturno, _primera_celda_libre


def _config(x=5, y=5, z=3, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _grilla_vacia(x=5, y=5, z=3) -> Grilla:
    return Grilla(_config(x=x, y=y, z=z))


# ------------------------------------------------------------------
# Nocturno — coloca cajas en grilla
# ------------------------------------------------------------------

def test_procesar_nocturno_coloca_cajas():
    """Robots toman cajas de reposicion y las colocan en celdas libres."""
    grilla = _grilla_vacia(x=3, y=3, z=2)
    robots = {0: Robot(id=0, x=0, y=0, z=0, estado=RobotEstado.INACTIVO, carga_id=None)}
    cola_reposicion = [
        Caja(id_caja="R001", id_sku="SKU-A", cantidad=10, x=0, y=0, z=0),
        Caja(id_caja="R002", id_sku="SKU-B", cantidad=5, x=0, y=0, z=0),
    ]
    acum = Acumuladores()

    robots_upd, g_delta, g_remove, eventos = procesar_nocturno(
        grilla, robots, cola_reposicion, acum
    )

    assert len(g_delta) == 1, "Debe colocar 1 caja (1 robot inactivo)"
    assert len(g_remove) == 0, "No debe remover celdas"
    assert len(robots_upd) == 1, "El robot debe actualizarse"
    assert robots_upd[0].estado == RobotEstado.REPONIENDO
    assert acum.cajas_ingresadas == 1

    # Verificar que la caja está en la grilla
    cajas_en_grilla = sum(1 for _ in grilla._celdas.values())
    assert cajas_en_grilla == 1


def test_procesar_nocturno_coloca_varias_cajas():
    """Dos robots inactivos colocan dos cajas."""
    grilla = _grilla_vacia(x=3, y=3, z=2)
    robots = {
        0: Robot(id=0, x=0, y=0, z=0, estado=RobotEstado.INACTIVO, carga_id=None),
        1: Robot(id=1, x=0, y=1, z=0, estado=RobotEstado.INACTIVO, carga_id=None),
    }
    cola_reposicion = [
        Caja(id_caja="R001", id_sku="SKU-A", cantidad=10, x=0, y=0, z=0),
        Caja(id_caja="R002", id_sku="SKU-B", cantidad=5, x=0, y=0, z=0),
    ]
    acum = Acumuladores()

    robots_upd, g_delta, g_remove, eventos = procesar_nocturno(
        grilla, robots, cola_reposicion, acum
    )

    assert len(g_delta) == 2, "Debe colocar 2 cajas (2 robots inactivos)"
    assert acum.cajas_ingresadas == 2
    assert acum.total_desplazamientos == 2


# ------------------------------------------------------------------
# Nocturno — grilla llena
# ------------------------------------------------------------------

def test_procesar_nocturno_grilla_llena():
    """Cuando la grilla está llena, no coloca la caja y emite advertencia."""
    grilla = _grilla_vacia(x=1, y=1, z=1)  # capacidad = 1
    grilla.agregar(Caja(id_caja="EXISTENTE", id_sku="SKU999", cantidad=1, x=0, y=0, z=0))
    grilla.flush_delta()

    robots = {0: Robot(id=0, x=0, y=0, z=0, estado=RobotEstado.INACTIVO, carga_id=None)}
    cola_reposicion = [
        Caja(id_caja="R001", id_sku="SKU-A", cantidad=10, x=0, y=0, z=0),
    ]
    acum = Acumuladores()

    robots_upd, g_delta, g_remove, eventos = procesar_nocturno(
        grilla, robots, cola_reposicion, acum
    )

    assert len(g_delta) == 0, "No debe colocar cajas si la grilla está llena"
    assert len(robots_upd) == 0, "Robot no debe actualizarse"
    assert acum.cajas_ingresadas == 0

    # Debe emitir evento de advertencia
    tipos = [e["tipo"] for e in eventos]
    assert "advertencia" in tipos


# ------------------------------------------------------------------
# _primera_celda_libre
# ------------------------------------------------------------------

def test_primera_celda_libre_vacia():
    """En grilla vacía, la primera celda libre es (0, 0, 0)."""
    grilla = _grilla_vacia(x=3, y=3, z=2)
    celda = _primera_celda_libre(grilla)
    assert celda == (0, 0, 0)


def test_primera_celda_libre_parcial():
    """Primera celda libre cuando (0,0,0) ya está ocupada."""
    grilla = _grilla_vacia(x=3, y=3, z=2)
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=0, y=0, z=0))
    grilla.flush_delta()
    celda = _primera_celda_libre(grilla)
    assert celda == (0, 0, 1), "Debe ser z=1 de la misma columna"


def test_primera_celda_libre_llena():
    """Retorna None cuando la grilla está completamente llena."""
    grilla = _grilla_vacia(x=1, y=1, z=1)
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=0, y=0, z=0))
    grilla.flush_delta()
    celda = _primera_celda_libre(grilla)
    assert celda is None
