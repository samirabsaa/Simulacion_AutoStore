"""Tests de unidad — Políticas de picking (T-13, T-14).

Valida:
- FIFO vs Prioridad seleccionan pedidos DIFERENTES para mismos datos
- Prioridad selecciona por menor distancia Manhattan al puerto
"""
from __future__ import annotations

import pytest
from bus_persistencia.models.state import Caja, Config, GrillaDimensions, Pedido, PoliticaPicking
from motor.grilla import Grilla
from motor.politicas import fifo, prioridad_posicion, get_politica


def _config(x=5, y=5, z=3, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _grilla_vacia(x=5, y=5, z=3) -> Grilla:
    return Grilla(_config(x=x, y=y, z=z))


# ------------------------------------------------------------------
# FIFO vs Prioridad — selección diferente para P09
# ------------------------------------------------------------------

def test_fifo_vs_prioridad_diferente_seleccion():
    """FIFO elige el primero en cola; Prioridad elige el más cercano a un puerto."""
    grilla = _grilla_vacia(x=5, y=5, z=3)
    # SKU001 en el centro (2, 2) — distancia 2 al puerto más cercano
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=2, y=2, z=0))
    # SKU002 en un puerto (0, 0) — distancia 0
    grilla.agregar(Caja(id_caja="C2", id_sku="SKU002", cantidad=1, x=0, y=0, z=0))

    pedidos = [
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
        Pedido(id_pedido="P002", id_sku="SKU002", cantidad=1, destino="B"),
    ]
    puertos = grilla.puertos

    seleccion_fifo = fifo(pedidos, grilla, puertos)
    seleccion_prioridad = prioridad_posicion(pedidos, grilla, puertos)

    # FIFO siempre elige P001 (primero en la cola)
    assert seleccion_fifo is not None
    assert seleccion_fifo.id_pedido == "P001"

    # Prioridad elige P002 (SKU002 en (0,0) — distancia 0 al puerto)
    assert seleccion_prioridad is not None
    assert seleccion_prioridad.id_pedido == "P002"


def test_prioridad_selecciona_por_distancia():
    """Prioridad elige el pedido cuya caja está MÁS CERCA de un puerto."""
    grilla = _grilla_vacia(x=5, y=5, z=3)
    # SKU001 en (4, 0) — en el borde xy=0, distancia al puerto (4,0)=0
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=4, y=0, z=0))
    # SKU002 en (2, 2) — centro, distancia al puerto más cercano = 4
    grilla.agregar(Caja(id_caja="C2", id_sku="SKU002", cantidad=1, x=2, y=2, z=0))

    pedidos = [
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
        Pedido(id_pedido="P002", id_sku="SKU002", cantidad=1, destino="B"),
    ]
    puertos = grilla.puertos

    seleccion = prioridad_posicion(pedidos, grilla, puertos)
    assert seleccion is not None
    # SKU001 en (4,0) está más cerca de su puerto que SKU002 en (2,2)
    assert seleccion.id_pedido == "P001"


def test_prioridad_con_distancia_competitiva():
    """Cuando hay dos cajas del mismo SKU, elige la de menor distancia."""
    grilla = _grilla_vacia(x=5, y=5, z=3)
    # Ambas cajas son del mismo SKU
    # C1 en (0, 0) — en borde, distancia 0 al puerto
    grilla.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=0, y=0, z=0))
    # C2 en (2, 4) — en borde inferior, distancia al puerto (0,4)=2 o (4,4)=2
    grilla.agregar(Caja(id_caja="C2", id_sku="SKU001", cantidad=1, x=2, y=4, z=0))

    pedidos = [
        Pedido(id_pedido="P001", id_sku="SKU001", cantidad=1, destino="A"),
    ]
    puertos = grilla.puertos

    seleccion = prioridad_posicion(pedidos, grilla, puertos)
    assert seleccion is not None
    assert seleccion.id_pedido == "P001"


def test_get_politica_registry():
    """El registro POLITICAS retorna las funciones correctas."""
    fn_fifo = get_politica(PoliticaPicking.FIFO)
    fn_prioridad = get_politica(PoliticaPicking.PRIORIDAD_POSICION)

    assert fn_fifo == fifo
    assert fn_prioridad == prioridad_posicion


def test_get_politica_invalida():
    """Política no registrada lanza KeyError."""
    import pytest
    from motor.politicas import get_politica

    with pytest.raises(KeyError):
        get_politica("inexistente")  # type: ignore
