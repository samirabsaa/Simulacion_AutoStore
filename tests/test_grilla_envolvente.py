"""Tests del modelo de grilla envolvente: anillo de tránsito + estaciones E/O."""
import pytest

from bus_persistencia.models.state import (
    Caja,
    Config,
    GrillaDimensions,
    Orientacion,
)
from motor.grilla import Grilla


def _grilla(x=5, y=4, z=3, ocupacion=0.0) -> Grilla:
    cfg = Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=3,
        ocupacion_inicial=ocupacion,
    )
    return Grilla(cfg)


def test_superficie_total_es_interior_mas_dos():
    g = _grilla(5, 4)
    assert g.ancho_total == 7
    assert g.alto_total == 6


def test_interior_y_transito():
    g = _grilla(5, 4)
    # Esquina interior
    assert g.es_interior(1, 1)
    assert g.es_interior(5, 4)
    # Borde = tránsito
    assert g.es_transito(0, 1)
    assert g.es_transito(6, 1)
    assert g.es_transito(1, 0)
    assert g.es_transito(1, 5)
    assert not g.es_transito(3, 3)
    assert not g.es_interior(0, 0)


def test_agregar_caja_en_anillo_falla():
    g = _grilla(5, 4)
    with pytest.raises(ValueError):
        g.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=0, y=2, z=0))


def test_agregar_caja_interior_ok():
    g = _grilla(5, 4)
    g.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=3, y=2, z=0))
    assert g.get(3, 2, 0) is not None


def test_inicializacion_no_puebla_anillo():
    g = _grilla(5, 4, 3, ocupacion=1.0)  # 100% del interior
    g.inicializar_aleatoria(seed=42)
    for (x, y, z) in g._celdas:
        assert g.es_interior(x, y), f"caja en celda no interior {(x, y, z)}"
    # Capacidad almacenable = interior
    assert g.capacidad_almacenable == 5 * 4 * 3
    assert g.total_cajas == g.capacidad_almacenable


def test_estaciones_oeste_y_este():
    g = _grilla(5, 4)
    oeste = g.estaciones_compatibles(Orientacion.OESTE)
    este = g.estaciones_compatibles(Orientacion.ESTE)
    norte = g.estaciones_compatibles(Orientacion.NORTE)
    # Una estación por fila interior en cada borde
    assert len(oeste) == 4
    assert len(este) == 4
    assert norte == []  # NORTE no entrega: colabora
    # Oeste en x=0, Este en x=gx+1=6
    assert all(e.x == 0 for e in oeste)
    assert all(e.x == 6 for e in este)


def test_estacion_compatible_mas_cercana():
    g = _grilla(5, 4)
    # Robot ESTE cerca del borde este (x=5)
    est = g.estacion_compatible_mas_cercana(5, 2, Orientacion.ESTE)
    assert est is not None and est.x == 6
    # Robot NORTE no tiene estación compatible
    assert g.estacion_compatible_mas_cercana(3, 2, Orientacion.NORTE) is None


def test_columnas_adyacentes_solo_interior():
    g = _grilla(5, 4)
    # Columna interior pegada al borde oeste (x=1)
    ady = g.columnas_adyacentes(1, 2)
    assert (0, 2) not in ady  # no incluye anillo
    assert (2, 2) in ady
