"""motor/grilla.py — Grilla 3D de almacenamiento con anillo de tránsito envolvente.

Modelo de coordenadas (robots 1×2 con orientación fija):
- `config.grilla.x/y` = área **almacenable** (interior). Las cajas viven en el
  interior desplazado +1: columnas `x ∈ [1..gx]`, `y ∈ [1..gy]`.
- El **anillo de tránsito** envuelve la grilla: celdas con `x=0`, `x=gx+1`,
  `y=0` o `y=gy+1`. No admite cajas; es solo para desplazamiento de robots y
  para alojar las estaciones de despacho.
- Superficie total transitable = `(gx+2) × (gy+2)`; robots y estaciones operan
  en `[0..gx+1] × [0..gy+1]`.
- **Estaciones** de despacho solo en Oeste (`x=0`, orientación OESTE) y Este
  (`x=gx+1`, orientación ESTE). Un robot NORTE nunca entrega: colabora vía handoff.

Una Caja exacta por celda (x, y, z), alineado con el contrato del bus.
"""
from __future__ import annotations

import random

from bus_persistencia.models.state import (
    Caja,
    Config,
    Estacion,
    Orientacion,
    TipoEstacion,
)


class Grilla:
    """Grilla 3D de almacenamiento con acceso O(1) por coordenada (x, y, z).

    El almacenamiento ocupa el interior `[1..gx] × [1..gy] × [0..gz)`; el borde
    exterior es anillo de tránsito (sin cajas) y aloja las estaciones E/O.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._celdas: dict[tuple[int, int, int], Caja] = {}
        self._delta: list[Caja] = []
        self._remove: list[tuple[int, int, int]] = []
        self._estaciones: tuple[Estacion, ...] = self._calcular_estaciones()
        self._estaciones_por_pos: dict[tuple[int, int], Estacion] = {
            (e.x, e.y): e for e in self._estaciones
        }
        # `puertos`: posiciones de entrega (celdas-estación del anillo W/E). Se
        # mantiene el nombre por compatibilidad con políticas/despachador.
        self._puertos: list[tuple[int, int]] = sorted(self._estaciones_por_pos)

    # ------------------------------------------------------------------
    # Dimensiones y geometría
    # ------------------------------------------------------------------

    @property
    def gx(self) -> int:
        """Ancho del área almacenable (interior)."""
        return self.config.grilla.x

    @property
    def gy(self) -> int:
        """Fondo del área almacenable (interior)."""
        return self.config.grilla.y

    @property
    def gz(self) -> int:
        return self.config.grilla.z

    @property
    def ancho_total(self) -> int:
        """Ancho de la superficie transitable, incluyendo el anillo: gx + 2."""
        return self.gx + 2

    @property
    def alto_total(self) -> int:
        """Fondo de la superficie transitable, incluyendo el anillo: gy + 2."""
        return self.gy + 2

    def es_interior(self, x: int, y: int) -> bool:
        """True si (x,y) es una columna almacenable (interior, no anillo)."""
        return 1 <= x <= self.gx and 1 <= y <= self.gy

    def es_transito(self, x: int, y: int) -> bool:
        """True si (x,y) pertenece al anillo de tránsito (borde, sin cajas)."""
        en_superficie = 0 <= x <= self.gx + 1 and 0 <= y <= self.gy + 1
        return en_superficie and not self.es_interior(x, y)

    def en_superficie(self, x: int, y: int) -> bool:
        """True si (x,y) está dentro de la superficie transitable total."""
        return 0 <= x <= self.gx + 1 and 0 <= y <= self.gy + 1

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------

    def inicializar_aleatoria(self, seed: int | None = None) -> None:
        """Puebla el interior aleatoriamente hasta `config.ocupacion_inicial`.
        El anillo de tránsito nunca recibe cajas. Usa `seed` para reproducibilidad."""
        rng = random.Random(seed)
        cap = self.capacidad_almacenable
        ocupacion = self.config.ocupacion_inicial
        n_cajas = int(cap * ocupacion / 100 if ocupacion > 1 else cap * ocupacion)

        gz = self.gz
        # Solo celdas interiores son almacenables.
        todas_celdas = [
            (x, y, z)
            for x in range(1, self.gx + 1)
            for y in range(1, self.gy + 1)
            for z in range(gz)
        ]
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
        self._delta = list(self._celdas.values())
        self._remove = []

    # ------------------------------------------------------------------
    # Operaciones CRUD — O(1) por celda
    # ------------------------------------------------------------------

    def agregar(self, caja: Caja) -> None:
        """Coloca una caja en su celda (x,y,z) del interior.

        Lanza ValueError si la celda no es interior (anillo de tránsito o fuera
        de la zona almacenable): el anillo es exclusivo para robots."""
        if not self.es_interior(caja.x, caja.y):
            raise ValueError(
                f"Celda ({caja.x},{caja.y}) no es interior almacenable "
                f"(anillo de tránsito o fuera de grilla): no admite cajas."
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
        gz = self.gz
        return [self._celdas[(x, y, z)] for z in range(gz) if (x, y, z) in self._celdas]

    def celdas_libres_en_columna(self, x: int, y: int) -> list[int]:
        """Niveles z disponibles (sin caja) en la columna interior (x,y).
        Una columna de tránsito (anillo) nunca tiene niveles almacenables."""
        if not self.es_interior(x, y):
            return []
        gz = self.gz
        return [z for z in range(gz) if (x, y, z) not in self._celdas]

    def columnas_adyacentes(self, x: int, y: int) -> list[tuple[int, int]]:
        """Columnas interiores vecinas (ortogonales) de (x,y), para reubicar cajas."""
        candidatas = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
        return [(cx, cy) for cx, cy in candidatas if self.es_interior(cx, cy)]

    # ------------------------------------------------------------------
    # Búsqueda por SKU (T-10) — para el despachador
    # ------------------------------------------------------------------

    def buscar_por_sku(self, id_sku: str) -> list[Caja]:
        """Retorna todas las cajas con el SKU dado, ordenadas por z ascendente."""
        resultados = [c for c in self._celdas.values() if c.id_sku == id_sku]
        return sorted(resultados, key=lambda c: c.z)

    def primera_caja_accesible(self, id_sku: str) -> Caja | None:
        """La caja de ese SKU con menor costo de excavación en su columna."""
        candidatas = self.buscar_por_sku(id_sku)
        if not candidatas:
            return None

        def costo_excavacion(c: Caja) -> int:
            gz = self.gz
            return sum(1 for z in range(c.z + 1, gz) if (c.x, c.y, z) in self._celdas)
        return min(candidatas, key=costo_excavacion)

    # ------------------------------------------------------------------
    # Estaciones de despacho (Oeste / Este) — en el anillo
    # ------------------------------------------------------------------

    def _calcular_estaciones(self) -> tuple[Estacion, ...]:
        """Estaciones de despacho en el anillo Oeste (x=0, orientación OESTE) y
        Este (x=gx+1, orientación ESTE), una por fila interior `y ∈ [1..gy]`.

        Si la config trae estaciones explícitas, se respetan tal cual."""
        if self.config.estaciones:
            return tuple(self.config.estaciones)
        estaciones: list[Estacion] = []
        for y in range(1, self.gy + 1):
            estaciones.append(Estacion(
                id=f"EST-O-{y}", x=0, y=y,
                tipo=TipoEstacion.CINTA,
                orientacion_requerida=Orientacion.OESTE,
            ))
            estaciones.append(Estacion(
                id=f"EST-E-{y}", x=self.gx + 1, y=y,
                tipo=TipoEstacion.CINTA,
                orientacion_requerida=Orientacion.ESTE,
            ))
        return tuple(estaciones)

    @property
    def estaciones(self) -> tuple[Estacion, ...]:
        return self._estaciones

    def estacion_en(self, x: int, y: int) -> Estacion | None:
        return self._estaciones_por_pos.get((x, y))

    def estaciones_compatibles(self, orientacion: Orientacion) -> list[Estacion]:
        """Estaciones que un robot con la orientación dada puede usar para entregar.

        Un robot entrega cuando su punta queda sobre la celda-estación; eso solo
        es posible si su orientación coincide con la requerida por la estación.
        Los robots NORTE no tienen estaciones compatibles (deben colaborar)."""
        return [e for e in self._estaciones if e.orientacion_requerida == orientacion]

    def estacion_compatible_mas_cercana(
        self, x: int, y: int, orientacion: Orientacion
    ) -> Estacion | None:
        """Estación compatible con `orientacion` más cercana (Manhattan) a (x,y)."""
        compatibles = self.estaciones_compatibles(orientacion)
        if not compatibles:
            return None
        return min(compatibles, key=lambda e: abs(e.x - x) + abs(e.y - y))

    # ------------------------------------------------------------------
    # Puertos (compatibilidad) — posiciones de entrega del anillo
    # ------------------------------------------------------------------

    @property
    def anillo(self) -> list[tuple[int, int]]:
        """Celdas (x,y) del anillo de tránsito, ordenadas."""
        gx1, gy1 = self.gx + 1, self.gy + 1
        celdas = set()
        for x in range(0, gx1 + 1):
            celdas.add((x, 0))
            celdas.add((x, gy1))
        for y in range(0, gy1 + 1):
            celdas.add((0, y))
            celdas.add((gx1, y))
        return sorted(celdas)

    @property
    def puertos(self) -> list[tuple[int, int]]:
        """Posiciones de entrega (celdas-estación del anillo W/E)."""
        return self._puertos

    def puerto_mas_cercano(self, x: int, y: int) -> tuple[int, int]:
        """Estación con menor distancia Manhattan a la columna (x, y)."""
        return min(self._puertos, key=lambda p: abs(p[0] - x) + abs(p[1] - y))

    # ------------------------------------------------------------------
    # Capacidad e IOG
    # ------------------------------------------------------------------

    @property
    def capacidad_almacenable(self) -> int:
        """Capacidad real para cajas: solo el interior (gx·gy·gz)."""
        return self.gx * self.gy * self.gz

    def iog(self) -> float:
        """Índice de Ocupación de Grilla: cajas / capacidad_almacenable * 100."""
        cap = self.capacidad_almacenable
        return len(self._celdas) / cap * 100 if cap > 0 else 0.0

    @property
    def total_cajas(self) -> int:
        return len(self._celdas)

    # ------------------------------------------------------------------
    # Delta para el TickDelta del bus
    # ------------------------------------------------------------------

    def flush_delta(self) -> tuple[list[Caja], list[tuple[int, int, int]]]:
        """Retorna (grilla_delta, grilla_remove) acumulados y limpia los buffers.
        Llamar una vez por tick, justo antes de armar el TickDelta."""
        delta, remove = self._delta, self._remove
        self._delta = []
        self._remove = []
        return delta or [], remove or []
