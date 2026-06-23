"""Tests del modelo de grilla: corredores E·T·A, estaciones E/O y conveyors Norte."""
import pytest

from bus_persistencia.models.state import (
    Caja,
    Config,
    EstacionRol,
    GrillaDimensions,
    Orientacion,
)
from motor.grilla import Grilla, M_OESTE, M_ESTE, M_NORTE, M_SUR, _mitad


def _grilla(x=6, y=4, z=3, ocupacion=0.0) -> Grilla:
    cfg = Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=3,
        ocupacion_inicial=ocupacion,
    )
    return Grilla(cfg)


def test_dims_totales_con_margenes_asimetricos():
    g = _grilla(6, 4)
    assert g.ancho_total == 6 + M_OESTE + M_ESTE   # gx+4 = 10
    assert g.alto_total == 4 + M_NORTE + M_SUR      # gy+3 = 7


def test_interior_desplazado_por_margenes():
    g = _grilla(6, 4)
    assert g.interior_bounds == (M_OESTE, M_NORTE, M_OESTE + 6 - 1, M_NORTE + 4 - 1)
    # Esquinas interiores
    assert g.es_interior(2, 2)
    assert g.es_interior(7, 5)   # x0+gx-1=7, y0+gy-1=5
    # Carriles de tránsito (E·T·A): x=1 (oeste), x=gx+2=8 (este), y=1 (norte), y=gy+2=6 (sur)
    assert g.es_transito(1, 3) and not g.es_interior(1, 3)
    assert g.es_transito(8, 3)
    assert g.es_transito(3, 1)
    assert g.es_transito(3, 6)


def test_agregar_caja_en_transito_falla():
    g = _grilla(6, 4)
    with pytest.raises(ValueError):
        g.agregar(Caja(id_caja="C1", id_sku="SKU001", cantidad=1, x=1, y=3, z=0))


def test_inicializacion_no_puebla_transito():
    g = _grilla(6, 4, 3, ocupacion=1.0)
    g.inicializar_aleatoria(seed=42)
    for (x, y, z) in g._celdas:
        assert g.es_interior(x, y), f"caja fuera del interior {(x, y, z)}"
    assert g.capacidad_almacenable == 6 * 4 * 3
    assert g.total_cajas == g.capacidad_almacenable


def test_estaciones_eo_mitad_intercaladas():
    g = _grilla(6, 4)   # gy=4 → mitad=2 por lado
    oeste = g.estaciones_compatibles(Orientacion.OESTE)
    este = g.estaciones_compatibles(Orientacion.ESTE)
    assert len(oeste) == _mitad(4) == 2
    assert len(este) == _mitad(4) == 2
    # Oeste en x=0, Este en x=ancho_total-1
    assert all(e.x == 0 for e in oeste)
    assert all(e.x == g.ancho_total - 1 for e in este)
    # Intercaladas en filas de almacenaje (y=2, y=4)
    assert sorted(e.y for e in oeste) == [2, 4]
    # NORTE no tiene estación de salida compatible
    assert g.estaciones_compatibles(Orientacion.NORTE) == []


def test_conveyors_norte_mitad_intercaladas():
    g = _grilla(6, 4)   # gx=6 → mitad=3
    conv = g.conveyors_norte
    assert len(conv) == _mitad(6) == 3
    assert all(c.y == 0 for c in conv)
    assert all(c.rol == EstacionRol.INGRESO for c in conv)
    assert all(c.orientacion_requerida == Orientacion.NORTE for c in conv)
    # Intercaladas en columnas de almacenaje (x=2, 4, 6)
    assert sorted(c.x for c in conv) == [2, 4, 6]


def test_columnas_adyacentes_solo_interior():
    g = _grilla(6, 4)
    ady = g.columnas_adyacentes(2, 3)   # columna interior pegada al carril oeste
    assert (1, 3) not in ady   # no incluye tránsito
    assert (3, 3) in ady


def test_anillo_son_celdas_de_transito():
    g = _grilla(6, 4)
    assert all(g.es_transito(x, y) for (x, y) in g.anillo)
    assert all(not g.es_interior(x, y) for (x, y) in g.anillo)
