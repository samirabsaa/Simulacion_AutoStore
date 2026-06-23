"""Tests de los helpers de footprint 1×2 (cuerpo + punta) del Robot.

El robot ocupa dos celdas: el cuerpo (ancla x,y) y la punta, derivada de la
orientación fija. La punta es donde excava/pickea y transporta la caja.
"""
from bus_persistencia.models.state import (
    Orientacion,
    Robot,
    RobotEstado,
    celdas_desde,
    celdas_robot,
    punta,
    punta_desde,
)


def _robot(x: int, y: int, ori: Orientacion) -> Robot:
    return Robot(id=0, x=x, y=y, z=0, estado=RobotEstado.INACTIVO, orientacion=ori)


def test_punta_norte():
    assert punta(_robot(3, 4, Orientacion.NORTE)) == (3, 5)


def test_punta_este():
    assert punta(_robot(3, 4, Orientacion.ESTE)) == (4, 4)


def test_punta_oeste():
    assert punta(_robot(3, 4, Orientacion.OESTE)) == (2, 4)


def test_celdas_robot_incluye_cuerpo_y_punta():
    r = _robot(3, 4, Orientacion.NORTE)
    assert celdas_robot(r) == [(3, 4), (3, 5)]


def test_celdas_robot_dos_celdas_distintas_todas_orientaciones():
    for ori in (Orientacion.NORTE, Orientacion.ESTE, Orientacion.OESTE):
        celdas = celdas_robot(_robot(5, 5, ori))
        assert len(celdas) == 2
        assert celdas[0] != celdas[1]


def test_punta_desde_equivale_a_punta():
    for ori in (Orientacion.NORTE, Orientacion.ESTE, Orientacion.OESTE):
        assert punta_desde(7, 2, ori) == punta(_robot(7, 2, ori))


def test_celdas_desde_equivale_a_celdas_robot():
    for ori in (Orientacion.NORTE, Orientacion.ESTE, Orientacion.OESTE):
        assert celdas_desde(7, 2, ori) == celdas_robot(_robot(7, 2, ori))
