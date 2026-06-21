"""motor/grilla.py — Grilla 3D de almacenamiento (T-09, T-10, T-11).

Modelo: una Caja exacta por celda (x, y, z), alineado con el contrato del bus
(grilla_delta / grilla_remove identifican cambios por celda individual).
Los puertos son las celdas del borde del plano XY (z=0 de la superficie).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from bus_persistencia.models.state import Caja, Config

if TYPE_CHECKING:
    pass


class Grilla:
    """Grilla 3D de almacenamiento con acceso O(1) por coordenada (x, y, z).

    Internamente mantiene:
    - `_celdas`: dict[(x,y,z) -> Caja] — fuente de verdad del estado actual
    - `_delta` / `_remove`: buffers de cambios desde el último flush — se vacían
      al llamar a `flush_delta()` y se entregan al simulador para armar el TickDelta
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._celdas: dict[tuple[int, int, int], Caja] = {}
        self._delta: list[Caja] = []
        self._remove: list[tuple[int, int, int]] = []
        # Anillo perimetral de tránsito (Feature 1): columnas (x,y) del borde
        # reservadas exclusivamente para el desplazamiento de robots. No admiten
        # cajas. Vacío si config.anillo_transito es False (comportamiento previo).
        self._transito: set[tuple[int, int]] = self._calcular_anillo()
        self._puertos: list[tuple[int, int]] = self._calcular_puertos()

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------

    def inicializar_aleatoria(self, seed: int | None = None) -> None:
        """Puebla la grilla aleatoriamente hasta `config.ocupacion_inicial`.
        Genera IDs de caja sintéticos. Usa `seed` para reproducibilidad."""
        rng = random.Random(seed)
        cap = self.config.grilla.capacidad_total
        n_cajas = int(cap * self.config.ocupacion_inicial / 100
                      if self.config.ocupacion_inicial > 1
                      else cap * self.config.ocupacion_inicial)

        gx, gy, gz = self.config.grilla.x, self.config.grilla.y, self.config.grilla.z
        # Solo celdas almacenables: el anillo de tránsito (si existe) se excluye.
        todas_celdas = [
            (x, y, z)
            for x in range(gx) for y in range(gy) for z in range(gz)
            if not self.es_transito(x, y)
        ]
        # Recalcular n_cajas sobre la capacidad almacenable real (no la bruta).
        n_cajas = min(n_cajas, len(todas_celdas))
        rng.shuffle(todas_celdas)

        skus = [f"SKU{i:03d}" for i in range(1, 11)]
        for i, (x, y, z) in enumerate(todas_celdas[:n_cajas]):
            caja = Caja(
                id_caja=f"C{i:05d}",
                id_sku=rng.choice(skus),
                cantidad=rng.randint(1, 10),
                x=x, y=y, z=z,
            )
            self._celdas[(x, y, z)] = caja
        # La inicialización no genera delta — es el estado base desde el que parte
        # el bus (StateBus.set_config no conoce cajas, las recibe en el primer TickDelta)
        self._delta = list(self._celdas.values())
        self._remove = []

    # ------------------------------------------------------------------
    # Operaciones CRUD — O(1) por celda
    # ------------------------------------------------------------------

    def agregar(self, caja: Caja) -> None:
        """Coloca una caja en su celda (x,y,z). Si había una caja anterior la
        reemplaza (comportamiento de merge-by-cell del bus).

        Lanza ValueError si la celda pertenece al anillo de tránsito: el anillo
        es exclusivo para desplazamiento de robots (Feature 1)."""
        if self.es_transito(caja.x, caja.y):
            raise ValueError(
                f"Celda ({caja.x},{caja.y}) es de tránsito (anillo): no admite cajas."
            )
        key = (caja.x, caja.y, caja.z)
        self._celdas[key] = caja
        self._delta.append(caja)

    def remover(self, x: int, y: int, z: int) -> Caja | None:
        """Vacía la celda (x,y,z). Retorna la caja que había, o None."""
        key = (x, y, z)
        caja = self._celdas.pop(key, None)
        if caja is not None:
            self._remove.append(key)
        return caja

    def get(self, x: int, y: int, z: int) -> Caja | None:
        """Retorna la caja en la celda, o None si está vacía."""
        return self._celdas.get((x, y, z))

    def ocupada(self, x: int, y: int, z: int) -> bool:
        return (x, y, z) in self._celdas

    # ------------------------------------------------------------------
    # Consultas de columna (para excavación y reposición)
    # ------------------------------------------------------------------

    def columna(self, x: int, y: int) -> list[Caja]:
        """Cajas de la columna (x,y) ordenadas de menor a mayor z."""
        gz = self.config.grilla.z
        return [self._celdas[(x, y, z)] for z in range(gz) if (x, y, z) in self._celdas]

    def celdas_libres_en_columna(self, x: int, y: int) -> list[int]:
        """Niveles z disponibles (sin caja) en la columna (x,y), de menor a mayor.
        Una columna de tránsito (anillo) nunca tiene niveles almacenables."""
        if self.es_transito(x, y):
            return []
        gz = self.config.grilla.z
        return [z for z in range(gz) if (x, y, z) not in self._celdas]

    def columnas_adyacentes(self, x: int, y: int) -> list[tuple[int, int]]:
        """Columnas vecinas en el plano XY (hasta 4 vecinas ortogonales)."""
        gx, gy = self.config.grilla.x, self.config.grilla.y
        candidatas = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
        return [(cx, cy) for cx, cy in candidatas if 0 <= cx < gx and 0 <= cy < gy]

    # ------------------------------------------------------------------
    # Búsqueda por SKU (T-10) — para el despachador
    # ------------------------------------------------------------------

    def buscar_por_sku(self, id_sku: str) -> list[Caja]:
        """Retorna todas las cajas con el SKU dado, ordenadas por z ascendente
        (las más accesibles primero en cada columna)."""
        resultados = [c for c in self._celdas.values() if c.id_sku == id_sku]
        return sorted(resultados, key=lambda c: c.z)

    def primera_caja_accesible(self, id_sku: str) -> Caja | None:
        """La caja de ese SKU con z más bajo en su columna (menor excavación)."""
        candidatas = self.buscar_por_sku(id_sku)
        if not candidatas:
            return None
        # Ordenar por cuántas cajas hay encima en su columna (costo de excavación)
        def costo_excavacion(c: Caja) -> int:
            gz = self.config.grilla.z
            return sum(1 for z in range(c.z + 1, gz) if (c.x, c.y, z) in self._celdas)
        return min(candidatas, key=costo_excavacion)

    # ------------------------------------------------------------------
    # Puertos (T-11) — bordes del plano XY
    # ------------------------------------------------------------------

    def _calcular_puertos(self) -> list[tuple[int, int]]:
        """Puertos = celdas del borde perimetral del plano XY.

        Cuando el anillo de tránsito está activo, los puertos coinciden con el
        anillo (los robots entregan desde el corredor perimetral)."""
        gx, gy = self.config.grilla.x, self.config.grilla.y
        puertos = set()
        for x in range(gx):
            puertos.add((x, 0))
            puertos.add((x, gy - 1))
        for y in range(gy):
            puertos.add((0, y))
            puertos.add((gx - 1, y))
        return sorted(puertos)

    # ------------------------------------------------------------------
    # Anillo perimetral de tránsito (Feature 1)
    # ------------------------------------------------------------------

    def _calcular_anillo(self) -> set[tuple[int, int]]:
        """Columnas (x,y) del borde reservadas para tránsito, si está activo.

        Requiere un interior no vacío (grilla ≥ 3×3); en grillas más pequeñas
        el anillo se desactiva para no dejar la zona almacenable en cero."""
        if not getattr(self.config, "anillo_transito", False):
            return set()
        gx, gy = self.config.grilla.x, self.config.grilla.y
        if gx < 3 or gy < 3:
            return set()
        anillo: set[tuple[int, int]] = set()
        for x in range(gx):
            anillo.add((x, 0))
            anillo.add((x, gy - 1))
        for y in range(gy):
            anillo.add((0, y))
            anillo.add((gx - 1, y))
        return anillo

    def es_transito(self, x: int, y: int) -> bool:
        """True si la columna (x,y) pertenece al anillo de tránsito (sin cajas)."""
        return (x, y) in self._transito

    @property
    def anillo(self) -> list[tuple[int, int]]:
        """Celdas (x,y) del anillo de tránsito, ordenadas (vacío si inactivo)."""
        return sorted(self._transito)

    @property
    def capacidad_almacenable(self) -> int:
        """Capacidad real para cajas: capacidad bruta menos las columnas de
        tránsito × Z. Igual a capacidad_total cuando no hay anillo."""
        gz = self.config.grilla.z
        return self.config.grilla.capacidad_total - len(self._transito) * gz

    @property
    def puertos(self) -> list[tuple[int, int]]:
        return self._puertos

    def puerto_mas_cercano(self, x: int, y: int) -> tuple[int, int]:
        """Puerto con menor distancia Manhattan a la columna (x, y)."""
        return min(self._puertos, key=lambda p: abs(p[0] - x) + abs(p[1] - y))

    # ------------------------------------------------------------------
    # KPI — IOG
    # ------------------------------------------------------------------

    def iog(self) -> float:
        """Índice de Ocupación de Grilla: cajas_presentes / capacidad_almacenable * 100.

        El denominador excluye el anillo de tránsito (Feature 1): el IOG mide
        ocupación de la zona que realmente puede almacenar cajas."""
        cap = self.capacidad_almacenable
        return len(self._celdas) / cap * 100 if cap > 0 else 0.0

    @property
    def total_cajas(self) -> int:
        return len(self._celdas)

    # ------------------------------------------------------------------
    # Delta para el TickDelta del bus
    # ------------------------------------------------------------------

    def flush_delta(self) -> tuple[list[Caja], list[tuple[int, int, int]]]:
        """Retorna (grilla_delta, grilla_remove) acumulados desde el último flush
        y limpia los buffers. Llamar una vez por tick, justo antes de armar el
        TickDelta."""
        delta, remove = self._delta, self._remove
        self._delta = []
        self._remove = []
        return delta or [], remove or []
