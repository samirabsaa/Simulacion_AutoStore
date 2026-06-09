"""motor/kpis.py — Cálculo de los 7 KPIs (T-20). STUB para Manuel.

Fórmulas exactas en CLAUDE.md sección "Los 7 KPIs".
Este archivo lo implementa Manuel Aguilera.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bus_persistencia.models.state import Config, KPISet

if TYPE_CHECKING:
    from motor.grilla import Grilla


@dataclass
class Acumuladores:
    """Contadores acumulados a lo largo de la sesión, actualizados por tick.
    El simulador mantiene una instancia y la pasa a `calcular_kpis()` cada tick.
    """
    pedidos_demandados: int = 0       # total pedidos en ola.csv
    pedidos_completados: int = 0      # pedidos entregados en puerto
    suma_tiempos_ciclo: float = 0.0   # Σ(t_despacho - t_orden) en ticks
    total_desplazamientos: int = 0    # movimientos robot (incluyendo excavación)
    cajas_recuperadas: int = 0        # cajas sacadas de la grilla (diurno)
    cajas_ingresadas: int = 0         # cajas puestas en la grilla (nocturno)
    ticks_bloqueados: int = 0         # ticks donde algún robot estuvo BLOQUEADO
    ticks_totales: int = 0            # ticks transcurridos en la sesión
    ticks_turno_actual: int = 0       # ticks del turno en curso (reset al cambiar modo)
    ticks_ingreso: int = 0            # ticks del turno nocturno (para TI)


def calcular_kpis(acum: Acumuladores, grilla: "Grilla", config: Config) -> KPISet:
    """Aplica las 7 fórmulas y retorna un KPISet.

    | KPI  | Fórmula |
    |------|---------|
    | TSP  | pedidos_completados / pedidos_demandados * 100 |
    | TPCP | suma_tiempos_ciclo / pedidos_completados (0 si ninguno) |
    | MTRP | total_desplazamientos / pedidos_completados (0 si ninguno) |
    | IOG  | grilla.iog() |
    | TR   | cajas_recuperadas / ticks_turno_actual (en ticks) |
    | TI   | cajas_ingresadas / ticks_ingreso (en ticks) |
    | TBR  | ticks_bloqueados / ticks_totales * 100 |
    """
    raise NotImplementedError("Manuel implementa calcular_kpis()")
