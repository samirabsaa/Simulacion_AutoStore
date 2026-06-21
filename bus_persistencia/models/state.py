"""Modelos de estado del Bus de Estado Central."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

WRITER_M2 = "M2"
M2_WRITER_ID = WRITER_M2


class ModoTurno(str, Enum):
    DIURNO = "diurno"
    NOCTURNO = "nocturno"


class PoliticaPicking(str, Enum):
    FIFO = "fifo"
    PRIORIDAD_POSICION = "prioridad_posicion"


class RobotEstado(str, Enum):
    INACTIVO = "inactivo"
    DESPLAZANDOSE = "desplazandose"
    EXCAVANDO = "excavando"
    RECUPERANDO = "recuperando"
    BLOQUEADO = "bloqueado"
    ENTREGANDO = "entregando"
    REPONIENDO = "reponiendo"
    # --- Estados M3 (Mente Colmena / handoff / orientación) ---
    ROTANDO = "rotando"                    # girando para alinearse con una estación
    NECESITA_HANDOFF = "necesita_handoff"  # cargado pero mal orientado, busca receptor
    EN_TRANSITO_ANILLO = "en_transito_anillo"  # redirigido al anillo de tránsito


class Orientacion(str, Enum):
    """Orientación del robot frente a una estación de entrega.

    Restringida a Norte / Este / Oeste — el Sur se excluye intencionalmente
    porque corresponde a la cara del puerto físico contra la que el robot no
    puede posicionarse (restricción del layout real de Forus, no del modelo).
    """
    NORTE = "N"
    ESTE = "E"
    OESTE = "O"


class TipoEstacion(str, Enum):
    """Tipo de estación de ingreso/entrega y su capacidad por tick."""
    CINTA = "cinta"        # procesa 1 producto por tick
    CARRUSEL = "carrusel"  # procesa 2 productos por tick


KPI_NAMES = ("TSP", "TPCP", "MTRP", "IOG", "TR", "TI", "TBR")


@dataclass(frozen=True)
class GrillaDimensions:
    x: int
    y: int
    z: int

    @property
    def capacidad_total(self) -> int:
        return self.x * self.y * self.z


@dataclass(frozen=True)
class Estacion:
    """Estación de ingreso/entrega ubicada en una celda del perímetro.

    `orientacion_requerida` es la orientación que el robot debe presentar para
    poder entregar. `capacidad_tick` se deriva del tipo (Cinta=1, Carrusel=2).
    """
    id: str
    x: int
    y: int
    tipo: TipoEstacion = TipoEstacion.CINTA
    orientacion_requerida: Orientacion = Orientacion.NORTE

    @property
    def capacidad_tick(self) -> int:
        return 2 if self.tipo == TipoEstacion.CARRUSEL else 1


@dataclass(frozen=True)
class Config:
    grilla: GrillaDimensions
    robots: int
    ocupacion_inicial: float
    # --- Extensiones M3 (opcionales — default preserva comportamiento previo) ---
    anillo_transito: bool = False          # anillo perimetral solo-tránsito (sin cajas)
    estaciones: tuple[Estacion, ...] = ()  # estaciones Cinta/Carrusel; () = sin restricción


SimConfig = Config


@dataclass(frozen=True)
class Caja:
    id_caja: str
    id_sku: str
    cantidad: int
    x: int
    y: int
    z: int


@dataclass(frozen=True)
class Robot:
    id: int
    x: int
    y: int
    z: int
    estado: RobotEstado
    carga_id: str | None = None
    orientacion: Orientacion = Orientacion.NORTE


@dataclass(frozen=True)
class Pedido:
    id_pedido: str
    id_sku: str
    cantidad: int
    destino: str


PedidoOla = Pedido


@dataclass(frozen=True)
class PedidosState:
    cola: tuple[Pedido, ...] = ()
    completados: tuple[Pedido, ...] = ()


@dataclass(frozen=True)
class KPISet:
    TSP: float = 0.0
    TPCP: float = 0.0
    MTRP: float = 0.0
    IOG: float = 0.0
    TR: float = 0.0
    TI: float = 0.0
    TBR: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in KPI_NAMES}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> KPISet:
        return cls(**{name: float(data.get(name, 0.0)) for name in KPI_NAMES})


def empty_kpis() -> KPISet:
    return KPISet()


@dataclass(frozen=True)
class StateSnapshot:
    """Snapshot inmutable para lectores M1/M3."""

    tick: int
    modo: ModoTurno
    politica: PoliticaPicking
    grilla: tuple[Caja, ...]
    robots: tuple[Robot, ...]
    pedidos: PedidosState
    kpis: KPISet
    config: Config | None = None
    paused: bool = False
    nombre_ejecucion: str = ""

    def copy(self) -> StateSnapshot:
        return deep_copy_snapshot(self)


@dataclass
class TickDelta:
    """Delta de escritura por tick (solo campos modificados)."""

    grilla_delta: list[Caja] | None = None
    grilla_remove: list[tuple[int, int, int]] | None = None
    robots_delta: list[Robot] | None = None
    pedidos_cola: list[Pedido] | None = None
    pedidos_completados_add: list[Pedido] | None = None
    kpis: KPISet | None = None
    modo: ModoTurno | None = None
    eventos: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MutableState:
    """Estado mutable interno del Bus (solo M2 escribe vía delta)."""

    tick: int = 0
    modo: ModoTurno = ModoTurno.DIURNO
    politica: PoliticaPicking = PoliticaPicking.FIFO
    config: Config | None = None
    paused: bool = False
    nombre_ejecucion: str = ""
    kpis: KPISet = field(default_factory=empty_kpis)
    _grilla: dict[tuple[int, int, int], Caja] = field(default_factory=dict)
    _robots: dict[int, Robot] = field(default_factory=dict)
    _pedidos_cola: list[Pedido] = field(default_factory=list)
    _pedidos_completados: list[Pedido] = field(default_factory=list)

    def apply_delta(self, delta: TickDelta) -> None:
        if delta.grilla_remove:
            for pos in delta.grilla_remove:
                self._grilla.pop(pos, None)
        if delta.grilla_delta:
            for caja in delta.grilla_delta:
                self._grilla[(caja.x, caja.y, caja.z)] = caja
        if delta.robots_delta:
            for robot in delta.robots_delta:
                self._robots[robot.id] = robot
        if delta.pedidos_cola is not None:
            self._pedidos_cola = list(delta.pedidos_cola)
        if delta.pedidos_completados_add:
            self._pedidos_completados.extend(delta.pedidos_completados_add)
        if delta.kpis is not None:
            self.kpis = delta.kpis
        if delta.modo is not None:
            self.modo = delta.modo
        self.tick += 1

    def to_snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            tick=self.tick,
            modo=self.modo,
            politica=self.politica,
            grilla=tuple(self._grilla.values()),
            robots=tuple(self._robots.values()),
            pedidos=PedidosState(
                cola=tuple(self._pedidos_cola),
                completados=tuple(self._pedidos_completados),
            ),
            kpis=self.kpis,
            config=self.config,
            paused=self.paused,
            nombre_ejecucion=self.nombre_ejecucion,
        )


def deep_copy_snapshot(snapshot: StateSnapshot) -> StateSnapshot:
    """Retorna copia profunda del snapshot para lectores."""
    return copy.deepcopy(snapshot)
