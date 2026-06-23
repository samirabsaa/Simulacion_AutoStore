"""motor/politicas.py — Políticas de picking intercambiables (T-13, T-14).

Cada política es una función pura con la misma firma. El despachador las llama
a través del dict POLITICAS sin saber cuál está activa — el simulador solo le
pasa la función correcta según `snap.politica`.

Valor canónico confirmado con Martín:
  PoliticaPicking.FIFO              = "fifo"
  PoliticaPicking.PRIORIDAD_POSICION = "prioridad_posicion"  (NO "posicion")
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from bus_persistencia.models.state import Pedido, PoliticaPicking

if TYPE_CHECKING:
    from motor.grilla import Grilla

# Tipo de todas las funciones de política
Selector = Callable[
    [list[Pedido], "Grilla", list[tuple[int, int]]],
    Pedido | None,
]


# ------------------------------------------------------------------
# FIFO — orden de llegada estricto
# ------------------------------------------------------------------

def fifo(
    pedidos: list[Pedido],
    grilla: "Grilla",
    puertos: list[tuple[int, int]],
) -> Pedido | None:
    """Despacha el primer pedido de la cola (orden de llegada).
    Retorna None si la cola está vacía o si ningún pedido tiene caja
    disponible en la grilla."""
    for pedido in pedidos:
        if grilla.buscar_por_sku(pedido.id_sku):
            return pedido
    return None


# ------------------------------------------------------------------
# Prioridad por posición — menor costo Manhattan
# ------------------------------------------------------------------

def prioridad_posicion(
    pedidos: list[Pedido],
    grilla: "Grilla",
    puertos: list[tuple[int, int]],
) -> Pedido | None:
    """Selecciona el pedido cuya caja candidata tiene menor distancia Manhattan
    hasta el puerto más cercano. Cajas con el mismo costo desempatan por el z
    más bajo (menor excavación). Retorna None si no hay cajas disponibles."""
    mejor_pedido: Pedido | None = None
    mejor_costo = float("inf")

    for pedido in pedidos:
        caja = grilla.primera_caja_accesible(pedido.id_sku)
        if caja is None:
            continue
        px, py = grilla.puerto_mas_cercano(caja.x, caja.y)
        costo = abs(caja.x - px) + abs(caja.y - py)
        if costo < mejor_costo:
            mejor_costo = costo
            mejor_pedido = pedido

    return mejor_pedido


# ------------------------------------------------------------------
# Registro — el despachador accede a la función via este dict
# ------------------------------------------------------------------

POLITICAS: dict[str, Selector] = {
    "fifo": fifo,
    "prioridad_posicion": prioridad_posicion,
}


BUILTIN_KEYS = frozenset({"fifo", "prioridad_posicion"})


def register_politica(nombre: str, fn: Selector) -> None:
    """Registra una politica externa. Sobreescribe si ya existe (excepto built-ins)."""
    if nombre in BUILTIN_KEYS:
        raise ValueError(f"No se puede sobreescribir la politica built-in '{nombre}'")
    POLITICAS[nombre] = fn


def list_politicas() -> list[str]:
    """Retorna los nombres de todas las politicas disponibles (built-in + plugins)."""
    return sorted(POLITICAS.keys())


def get_politica(politica: str) -> Selector:
    """Retorna la función de política activa. Lanza KeyError si el valor
    no está registrado."""
    return POLITICAS[politica]
