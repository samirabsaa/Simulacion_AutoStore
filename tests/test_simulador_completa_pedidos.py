"""Tests: M2 complete todos los pedidos si hay cajas suficientes.

Casos:
- 2 pedidos, 2 cajas → todo completado
- olalarga.csv (100 pedidos) → todo completado
- Ambas políticas completan todo
- ha_terminado() post-completado
- 2 robots, 1 SKU compartido, 2 cajas → ambos completados (reservas)
- Sin caja disponible: no crashea
"""
from __future__ import annotations

from pathlib import Path

import pytest
from bus_persistencia.bus.state_bus import StateBus
from bus_persistencia.models.state import (
    Caja,
    Config,
    GrillaDimensions,
    Pedido,
    PoliticaPicking,
)
from bus_persistencia.persistence.config_loader import load_config
from bus_persistencia.persistence.ola_loader import load_ola
from motor.simulador import AutoStoreSimulator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _config(x=4, y=4, z=3, robots=2, ocupacion=0.0) -> Config:
    return Config(
        grilla=GrillaDimensions(x=x, y=y, z=z),
        robots=robots,
        ocupacion_inicial=ocupacion,
    )


def _sim_con_pedidos_y_cajas(
    pedidos: list[Pedido],
    cajas: list[Caja] | None = None,
    cfg: Config | None = None,
    seed: int = 42,
) -> AutoStoreSimulator:
    if cfg is None:
        cfg = _config(x=4, y=4, z=3, robots=2, ocupacion=0.0)
    bus = StateBus()
    bus.set_config(cfg)
    bus.set_pedidos_cola(pedidos)
    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=seed)
    if cajas is not None:
        for c in cajas:
            sim._grilla.agregar(c)
    return sim


def _ejecutar_hasta_completar(
    sim: AutoStoreSimulator,
    max_ticks: int = 300,
) -> int:
    for i in range(1, max_ticks + 1):
        sim.avanzar_tick()
        if sim.ha_terminado():
            return i
    return max_ticks


# ------------------------------------------------------------------
# 2 pedidos simples, 2 cajas, grilla vacía
# ------------------------------------------------------------------

def test_simulador_completa_dos_pedidos():
    """2 pedidos con cajas en z=0 → ambos completados."""
    sim = _sim_con_pedidos_y_cajas(
        pedidos=[
            Pedido(id_pedido="P001", id_sku="SKU-A", cantidad=1, destino="A"),
            Pedido(id_pedido="P002", id_sku="SKU-B", cantidad=1, destino="B"),
        ],
        cajas=[
            Caja(id_caja="C001", id_sku="SKU-A", cantidad=1, x=0, y=0, z=0),
            Caja(id_caja="C002", id_sku="SKU-B", cantidad=1, x=3, y=3, z=0),
        ],
    )
    ticks = _ejecutar_hasta_completar(sim)

    assert sim.ha_terminado() is True
    assert len(sim.pedidos_completados) == 2
    assert len(sim.pedidos_cola) == 0
    assert ticks < 300, f"No completó en 300 ticks (tomó {ticks})"


# ------------------------------------------------------------------
# 4 pedidos desde ola.csv — multi-robot
# ------------------------------------------------------------------

def test_simulador_completa_ola_desde_archivos():
    """4 pedidos de ola.csv completados con 3 robots."""
    ola = load_ola(str(DATA_DIR / "ola.csv"))
    assert ola.is_valid
    pedidos = ola.data
    # Cajas en distintas posiciones para minimizar bloqueos
    cajas = [
        Caja(id_caja=f"C{i:03d}", id_sku=p.id_sku, cantidad=1,
             x=i * 2, y=2, z=0)
        for i, p in enumerate(pedidos)
    ]
    cfg = _config(x=8, y=5, z=3, robots=3, ocupacion=0.0)
    sim = _sim_con_pedidos_y_cajas(pedidos, cajas, cfg=cfg)

    ticks = _ejecutar_hasta_completar(sim)

    assert sim.ha_terminado() is True
    assert len(sim.pedidos_completados) == len(pedidos)
    assert ticks < 200


# ------------------------------------------------------------------
# 100 pedidos desde olalarga.csv — escalabilidad con multi-robot
# ------------------------------------------------------------------

def test_simulador_completa_ola_larga():
    """100 pedidos de olalarga.csv completados con 4 robots."""
    ola = load_ola(str(DATA_DIR / "olalarga.csv"))
    assert ola.is_valid
    pedidos = ola.data
    total = len(pedidos)
    # Cajas distribuidas en grid 20x5 (todas z=0, sin excavación)
    cajas = [
        Caja(id_caja=f"C{i:04d}", id_sku=p.id_sku, cantidad=1,
             x=i % 20, y=(i // 20) % 5, z=0)
        for i, p in enumerate(pedidos)
    ]
    cfg = _config(x=20, y=5, z=2, robots=4, ocupacion=0.0)
    sim = _sim_con_pedidos_y_cajas(pedidos, cajas, cfg=cfg)

    ticks = _ejecutar_hasta_completar(sim, max_ticks=2000)

    assert sim.ha_terminado() is True
    assert len(sim.pedidos_completados) == total, (
        f"Completó {len(sim.pedidos_completados)}/{total} en {ticks} ticks"
    )


# ------------------------------------------------------------------
# Ambas políticas completan todo (multi-robot)
# ------------------------------------------------------------------

def test_ambas_politicas_completan():
    """FIFO y Prioridad completan todos los pedidos con 2 robots."""
    pedidos = [
        Pedido(id_pedido="P001", id_sku="SKU-A", cantidad=1, destino="A"),
        Pedido(id_pedido="P002", id_sku="SKU-B", cantidad=1, destino="B"),
        Pedido(id_pedido="P003", id_sku="SKU-C", cantidad=1, destino="C"),
    ]
    cajas = [
        Caja(id_caja="C001", id_sku="SKU-A", cantidad=1, x=0, y=0, z=0),
        Caja(id_caja="C002", id_sku="SKU-B", cantidad=1, x=1, y=1, z=0),
        Caja(id_caja="C003", id_sku="SKU-C", cantidad=1, x=2, y=2, z=0),
    ]

    # FIFO
    sim_a = _sim_con_pedidos_y_cajas(pedidos, cajas, seed=42,
                                     cfg=_config(robots=2))
    sim_a.bus.set_policy(PoliticaPicking.FIFO)
    ticks_a = _ejecutar_hasta_completar(sim_a)

    # Prioridad
    sim_b = _sim_con_pedidos_y_cajas(pedidos, cajas, seed=42,
                                     cfg=_config(robots=2))
    sim_b.bus.set_policy(PoliticaPicking.PRIORIDAD_POSICION)
    ticks_b = _ejecutar_hasta_completar(sim_b)

    for sim, nombre in [(sim_a, "FIFO"), (sim_b, "Prioridad")]:
        assert sim.ha_terminado() is True, f"{nombre} no terminó"
        assert len(sim.pedidos_completados) == 3, (
            f"{nombre} completó {len(sim.pedidos_completados)}/3"
        )

    assert ticks_a < 300, f"FIFO tomó {ticks_a} ticks"
    assert ticks_b < 300, f"Prioridad tomó {ticks_b} ticks"


# ------------------------------------------------------------------
# ha_terminado() post-completado
# ------------------------------------------------------------------

def test_ha_terminado_post_completado():
    """Después de completar todo, ha_terminado() es True y robots inactivos."""
    sim = _sim_con_pedidos_y_cajas(
        pedidos=[
            Pedido(id_pedido="P001", id_sku="SKU-A", cantidad=1, destino="A"),
        ],
        cajas=[
            Caja(id_caja="C001", id_sku="SKU-A", cantidad=1, x=0, y=0, z=0),
        ],
    )
    _ejecutar_hasta_completar(sim)

    assert sim.ha_terminado() is True
    for robot in sim.robots.values():
        assert robot.estado.value == "inactivo", (
            f"Robot {robot.id} en estado {robot.estado.value}"
        )


# ------------------------------------------------------------------
# Todos los pedidos completados están en snap.pedidos.completados
# ------------------------------------------------------------------

def test_completados_visibles_en_bus():
    """Los pedidos completados se reflejan en el snapshot del bus."""
    sim = _sim_con_pedidos_y_cajas(
        pedidos=[
            Pedido(id_pedido="P001", id_sku="SKU-A", cantidad=1, destino="A"),
            Pedido(id_pedido="P002", id_sku="SKU-B", cantidad=1, destino="B"),
        ],
        cajas=[
            Caja(id_caja="C001", id_sku="SKU-A", cantidad=1, x=0, y=0, z=0),
            Caja(id_caja="C002", id_sku="SKU-B", cantidad=1, x=3, y=3, z=0),
        ],
    )
    _ejecutar_hasta_completar(sim)

    snap = sim.bus.read_snapshot()
    assert len(snap.pedidos.completados) == 2
    ids = {p.id_pedido for p in snap.pedidos.completados}
    assert ids == {"P001", "P002"}
    assert len(snap.pedidos.cola) == 0


# ------------------------------------------------------------------
# Reserva: 2 robots, 1 SKU compartido, 2 cajas
# ------------------------------------------------------------------

def test_dos_robots_mismo_sku():
    """2 robots compiten por el mismo SKU (2 cajas) → ambos completan."""
    pedidos = [
        Pedido(id_pedido="P001", id_sku="SKU-A", cantidad=1, destino="A"),
        Pedido(id_pedido="P002", id_sku="SKU-A", cantidad=1, destino="B"),
    ]
    cajas = [
        Caja(id_caja="C001", id_sku="SKU-A", cantidad=1, x=1, y=1, z=0),
        Caja(id_caja="C002", id_sku="SKU-A", cantidad=1, x=6, y=1, z=0),
    ]
    cfg = _config(x=8, y=4, z=2, robots=2, ocupacion=0.0)
    sim = _sim_con_pedidos_y_cajas(pedidos, cajas, cfg=cfg)

    ticks = _ejecutar_hasta_completar(sim)

    assert sim.ha_terminado() is True
    assert len(sim.pedidos_completados) == 2, (
        f"Completó {len(sim.pedidos_completados)}/2 — falló reserva de SKU compartido"
    )
    assert len(sim.pedidos_cola) == 0


# ------------------------------------------------------------------
# Sin caja disponible: no se completa, pero no crashea
# ------------------------------------------------------------------

def test_sin_caja_no_completa():
    """Pedido sin caja correspondiente no se completa pero no crashea."""
    sim = _sim_con_pedidos_y_cajas(
        pedidos=[
            Pedido(id_pedido="P001", id_sku="SKU-X", cantidad=1, destino="A"),
        ],
        cajas=[],  # Sin cajas de SKU-X
    )
    # 50 ticks sin caja disponible
    for _ in range(50):
        sim.avanzar_tick()

    assert sim.ha_terminado() is False
    assert len(sim.pedidos_completados) == 0
    assert len(sim.pedidos_cola) == 1
    assert sim.robots  # Robots siguen existiendo
