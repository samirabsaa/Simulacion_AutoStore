"""motor/kpis.py — Cálculo de los 7 KPIs (T-20).

Fórmulas según CLAUDE.md (sección "Los 7 KPIs").
"""
from __future__ import annotations

from dataclasses import dataclass
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

    Denominadores protegidos contra división por cero — devuelven 0.0
    cuando no hay datos suficientes (inicio de sesión).
    """
    n_comp = acum.pedidos_completados
    n_dem = acum.pedidos_demandados

    tsp = n_comp / n_dem * 100 if n_dem > 0 else 0.0
    tpcp = acum.suma_tiempos_ciclo / n_comp if n_comp > 0 else 0.0
    mtrp = acum.total_desplazamientos / n_comp if n_comp > 0 else 0.0
    iog = grilla.iog()
    tr = acum.cajas_recuperadas / acum.ticks_turno_actual if acum.ticks_turno_actual > 0 else 0.0
    ti = acum.cajas_ingresadas / acum.ticks_ingreso if acum.ticks_ingreso > 0 else 0.0
    # TBR mide la fracción de tiempo-robot bloqueado. ticks_bloqueados acumula
    # robot-ticks (suma sobre TODOS los robots), así que el denominador debe ser
    # ticks_totales × n_robots para que el resultado quede acotado en [0, 100%].
    # (Dividir solo por ticks_totales daba TBR > 100% con varios robots.)
    robot_ticks = acum.ticks_totales * config.robots
    tbr = acum.ticks_bloqueados / robot_ticks * 100 if robot_ticks > 0 else 0.0

    return KPISet(TSP=tsp, TPCP=tpcp, MTRP=mtrp, IOG=iog, TR=tr, TI=ti, TBR=tbr)
