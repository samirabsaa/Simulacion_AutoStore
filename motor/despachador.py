"""motor/despachador.py — Despachador central de M2 (T-12, T-15, T-16, T-17).
STUB para Manuel.

Responsabilidades:
  - T-12: asignar ruta a cada robot INACTIVO según la política activa
  - T-15: acceso arbitrario a cajas (cualquier z de la columna, no solo la superior)
  - T-16: excavación — mover cajas superiores a columnas adyacentes libres
  - T-17: cesión de paso — robot espera 1 tick si celda destino ocupada por otro robot

Este archivo lo implementa Manuel Aguilera.
Ver docs/guia_inicio_m2.md y docs/acuerdos_diseno_m2.md para el contexto.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from bus_persistencia.models.state import Caja, Pedido, PoliticaPicking, Robot

if TYPE_CHECKING:
    from motor.grilla import Grilla
    from motor.kpis import Acumuladores


class Despachador:
    """Cerebro central de M2: asigna y ejecuta rutas de robots por tick.

    El simulador instancia un único Despachador y lo llama en cada tick del
    turno diurno. Los robots no toman decisiones propias — el despachador
    asigna la ruta completa y ellos solo la ejecutan paso a paso.

    Retorno de `tick()`:
        robots_actualizados  — lista de Robot con posición/estado nuevo
        grilla_delta         — Cajas agregadas/modificadas este tick
        grilla_remove        — Coordenadas de celdas vaciadas este tick
        pedidos_completados  — Pedidos entregados en puerto este tick
        eventos              — Lista de dicts con vocabulario del bus:
                               movimiento | excavacion | caja_recuperada |
                               pedido_completado | bloqueo
    """

    def __init__(self, grilla: "Grilla") -> None:
        self.grilla = grilla
        # Estado interno de rutas asignadas: robot_id -> lista de (x,y,z) pendientes
        self._rutas: dict[int, list[tuple[int, int, int]]] = {}

    def tick(
        self,
        robots: dict[int, Robot],
        pedidos_cola: list[Pedido],
        politica: PoliticaPicking,
        acum: "Acumuladores",
    ) -> tuple[
        list[Robot],
        list[Caja],
        list[tuple[int, int, int]],
        list[Pedido],
        list[dict],
    ]:
        """Ejecuta un paso de simulación para todos los robots en turno diurno."""
        raise NotImplementedError("Manuel implementa Despachador.tick()")
