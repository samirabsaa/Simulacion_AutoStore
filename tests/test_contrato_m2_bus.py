# tests/test_contrato_m2_bus.py
#
# Prueba de contrato M2 <-> Bus — NO valida la lógica de simulación de Manuel
# (la mayoría de los métodos de AutoStoreSimulator son NotImplementedError a
# propósito todavía). Lo que valida es que los SUPUESTOS sobre el contrato real
# de Martín (bus_persistencia) que tomamos al escribir el esqueleto son
# correctos: tipos, nombres de métodos, forma del TickDelta, y que el bus
# acepta y refleja lo que el motor produce.
#
# Ejecutar con: pytest tests/test_contrato_m2_bus.py -v
# (ruta explícita — pytest.ini de Martín fija testpaths = bus_persistencia/tests)

from pathlib import Path

import pytest

from bus_persistencia.bus.state_bus import M2_WRITER_ID, StateBus, WriterNotAuthorizedError
from bus_persistencia.models.state import (
    Caja,
    KPISet,
    ModoTurno,
    Robot,
    RobotEstado,
    TickDelta,
)
from bus_persistencia.persistence.config_loader import load_config
from motor.simulador import AutoStoreSimulator

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "config.json"


@pytest.fixture
def bus_configurado() -> StateBus:
    resultado = load_config(CONFIG_PATH)
    assert resultado.is_valid, f"config.json de ejemplo inválido: {resultado.errors}"

    bus = StateBus()
    bus.set_config(resultado.data)
    return bus


def test_instanciacion_simulador(bus_configurado: StateBus):
    """El simulador se construye solo con el bus — no recibe config ni
    pedidos por constructor (los configura M1 antes de Play)."""
    simulador = AutoStoreSimulator(bus_configurado)

    assert simulador.bus is bus_configurado
    assert simulador.modo == ModoTurno.DIURNO
    assert simulador.tick == 0
    assert simulador.kpis == KPISet()


def test_construir_delta_empaqueta_solo_lo_que_cambio(bus_configurado: StateBus):
    """`_construir_delta` arma un TickDelta parcial a partir de los buffers
    internos del simulador — y los vacía después. Es el único método del
    esqueleto (junto al __init__) que ya tiene lógica real, así que es lo
    que esta prueba puede ejercitar sin que Manuel haya implementado nada."""
    simulador = AutoStoreSimulator(bus_configurado)

    caja = Caja(id_caja="C1", id_sku="SKU1", cantidad=5, x=0, y=0, z=0)
    robot = Robot(id=1, x=0, y=0, z=0, estado=RobotEstado.DESPLAZANDOSE, carga_id=None)
    kpis = KPISet(TSP=50.0, TBR=5.0)
    evento = {"tipo": "movimiento", "robot_id": 1, "x": 0, "y": 0}

    simulador._grilla_delta.append(caja)
    simulador._robots_delta.append(robot)
    simulador._eventos_pendientes.append(evento)
    simulador.kpis = kpis
    simulador.cambiar_modo(ModoTurno.DIURNO)

    delta = simulador._construir_delta()

    assert isinstance(delta, TickDelta)
    assert delta.grilla_delta == [caja]
    assert delta.robots_delta == [robot]
    assert delta.kpis == kpis
    assert delta.modo == ModoTurno.DIURNO
    assert delta.eventos == [evento]

    # Los buffers se vacían tras empaquetar — el próximo delta parte limpio
    assert simulador._grilla_delta == []
    assert simulador._robots_delta == []
    assert simulador._eventos_pendientes == []
    assert simulador._modo_pendiente is None


def test_bus_acepta_y_refleja_el_delta_de_m2(bus_configurado: StateBus):
    """El bus debe aceptar un TickDelta producido por `_construir_delta`,
    incrementar el tick, y reflejar los cambios en `read_snapshot()` —
    confirma que nuestra lectura de TickDelta/StateSnapshot/KPISet es
    compatible con la implementación real de Martín."""
    simulador = AutoStoreSimulator(bus_configurado)

    caja = Caja(id_caja="C1", id_sku="SKU1", cantidad=5, x=1, y=1, z=0)
    robot = Robot(id=1, x=1, y=1, z=0, estado=RobotEstado.RECUPERANDO, carga_id="C1")
    kpis = KPISet(TSP=100.0)

    simulador._grilla_delta.append(caja)
    simulador._robots_delta.append(robot)
    simulador.kpis = kpis

    delta = simulador._construir_delta()
    nuevo_tick = bus_configurado.write_tick_delta(M2_WRITER_ID, delta)

    snap = bus_configurado.read_snapshot()
    assert nuevo_tick == 1
    assert snap.tick == 1
    assert caja in snap.grilla
    assert robot in snap.robots
    assert snap.kpis == kpis


def test_solo_m2_puede_escribir(bus_configurado: StateBus):
    """El single-writer ya no es solo convención: el bus lo hace cumplir
    activamente con `WriterNotAuthorizedError` si el writer_id no es M2."""
    delta = TickDelta(kpis=KPISet())

    with pytest.raises(WriterNotAuthorizedError):
        bus_configurado.write_tick_delta("M1", delta)
