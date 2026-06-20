"""motor/colmena.py — Soporte de la "Mente Colmena" (Feature 4).

Estructuras y utilidades que el Despachador (el orquestador central real, que
hace el rol del `HiveMindOrchestrator` del spec `docs/spec_handoff_mente_colmena.md`)
usa para coordinar orientación, handoff y resolución de bloqueos por tick.

Mapeo respecto al spec (clases propuestas → implementación real):
  HiveMindOrchestrator  → se fusiona con `motor.despachador.Despachador`
                          (ya era el cerebro central; no se duplica).
  Station               → `bus_persistencia.models.state.Estacion`.
  Orientacion/EstadoRobot → enums en `bus_persistencia.models.state`.
  ReservationTable, WaitForGraph → este módulo (clases de soporte nuevas).

Todas las estructuras de este módulo son de vida-de-un-tick: se reinician al
inicio de cada tick para preservar el determinismo (clave para que M3/Omniverse
reproduzca la animación).
"""
from __future__ import annotations

from bus_persistencia.models.state import Orientacion

# Constantes configurables (no hardcodear en la lógica — calibrables con datos
# reales de Forus, según nota 5 del spec).
COSTO_ROTACION_TICKS = 1       # ticks que tarda un robot en girar a otra orientación
UMBRAL_REDIRECCION_ANILLO = 5  # ticks esperando handoff antes de redirigir al anillo
RADIO_HANDOFF = 1              # radio (Manhattan) de búsqueda de receptor de handoff


def distancia_manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def orientacion_hacia(origen: tuple[int, int], destino: tuple[int, int]) -> Orientacion | None:
    """Orientación (N/E/O) que un robot en `origen` necesita para encarar `destino`.

    Devuelve None si encarar `destino` exigiría mirar al Sur (dy < 0 dominante),
    que está prohibido por restricción física del puerto (Feature 3)."""
    dx = destino[0] - origen[0]
    dy = destino[1] - origen[1]
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy):
        return Orientacion.ESTE if dx > 0 else Orientacion.OESTE
    # eje Y dominante
    return Orientacion.NORTE if dy > 0 else None  # dy < 0 → Sur → prohibido


class ReservationTable:
    """Reservas de celdas (x,y) válidas solo durante el tick actual.

    Formaliza el `posiciones_actuales` que el despachador ya usaba: una celda
    reservada por un robot no puede ser tomada por otro en el mismo tick. Incluye
    detección de conflictos de intercambio (swap)."""

    def __init__(self) -> None:
        self._reservas: dict[tuple[int, int], int] = {}

    def reset(self) -> None:
        self._reservas.clear()

    def sembrar(self, posiciones: dict[tuple[int, int], int]) -> None:
        """Inicializa la tabla con las posiciones actuales de los robots."""
        self._reservas = dict(posiciones)

    def reservar(self, celda: tuple[int, int], robot_id: int) -> bool:
        """Reserva `celda` para `robot_id`. False si ya la tiene otro robot."""
        ocupante = self._reservas.get(celda)
        if ocupante is not None and ocupante != robot_id:
            return False
        self._reservas[celda] = robot_id
        return True

    def liberar(self, celda: tuple[int, int]) -> None:
        self._reservas.pop(celda, None)

    def esta_reservada(self, celda: tuple[int, int], por: int | None = None) -> bool:
        ocupante = self._reservas.get(celda)
        if ocupante is None:
            return False
        return ocupante != por if por is not None else True

    def hay_conflicto_intercambio(
        self,
        celda_origen_a: tuple[int, int], celda_destino_a: tuple[int, int],
        celda_origen_b: tuple[int, int], celda_destino_b: tuple[int, int],
    ) -> bool:
        """True si A quiere ir a la celda de B y B a la de A en el mismo tick."""
        return celda_destino_a == celda_origen_b and celda_destino_b == celda_origen_a


class WaitForGraph:
    """Grafo dirigido de espera: A → B significa 'A espera a que B se mueva'.

    Mecanismo anti-deadlock para bloqueos inducidos por orientación/handoff
    (patrón wait-for graph de MAPF-rot)."""

    def __init__(self) -> None:
        self._aristas: dict[int, set[int]] = {}

    def reset(self) -> None:
        self._aristas.clear()

    def agregar_espera(self, robot_que_espera: int, robot_esperado: int) -> None:
        self._aristas.setdefault(robot_que_espera, set()).add(robot_esperado)

    def detectar_ciclo(self) -> list[int] | None:
        """Retorna la lista de robot_ids de un ciclo si existe, None si no.

        DFS con marcado de tres colores; orden de visita determinista (ids
        ordenados) para reproducibilidad."""
        BLANCO, GRIS, NEGRO = 0, 1, 2
        color: dict[int, int] = {}
        pila: list[int] = []

        def dfs(n: int) -> list[int] | None:
            color[n] = GRIS
            pila.append(n)
            for m in sorted(self._aristas.get(n, ())):
                c = color.get(m, BLANCO)
                if c == GRIS:
                    # ciclo: desde la primera aparición de m en la pila
                    return pila[pila.index(m):]
                if c == BLANCO:
                    r = dfs(m)
                    if r is not None:
                        return r
            color[n] = NEGRO
            pila.pop()
            return None

        for nodo in sorted(self._aristas):
            if color.get(nodo, BLANCO) == BLANCO:
                ciclo = dfs(nodo)
                if ciclo is not None:
                    return ciclo
        return None
