"""api/serializers.py — mapeo entre el StateSnapshot de M2 y el contrato JSON de M1.

M1 (Angular/Ionic) define sus propios enums en `sim.enums.ts` con valores y
casing distintos a los de `bus_persistencia.models.state`. Estas tablas hacen
la traducción en ambos sentidos para que M2 no necesite conocer el formato de M1
y viceversa.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from bus_persistencia.models.state import (
    Caja,
    ModoTurno,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
    StateSnapshot,
)

# ModoTurno (M2, minúsculas) <-> SimMode (M1, mayúsculas)
MODO_TO_M1: dict[ModoTurno, str] = {
    ModoTurno.DIURNO: "DIURNO",
    ModoTurno.NOCTURNO: "NOCTURNO",
}
MODO_FROM_M1: dict[str, ModoTurno] = {v: k for k, v in MODO_TO_M1.items()}

# PoliticaPicking (M2) <-> PickingPolicy (M1)
POLITICA_TO_M1: dict[PoliticaPicking, str] = {
    PoliticaPicking.FIFO: "FIFO",
    PoliticaPicking.PRIORIDAD_POSICION: "PRIORIDAD_POSICION",
}
POLITICA_FROM_M1: dict[str, PoliticaPicking] = {v: k for k, v in POLITICA_TO_M1.items()}

# RobotEstado (M2, 7 estados) -> RobotState (M1, 5 estados)
ROBOT_ESTADO_TO_M1: dict[RobotEstado, str] = {
    RobotEstado.INACTIVO: "IDLE",
    RobotEstado.DESPLAZANDOSE: "MOVING",
    RobotEstado.EXCAVANDO: "PICKING",
    RobotEstado.RECUPERANDO: "PICKING",
    RobotEstado.REPONIENDO: "PICKING",
    RobotEstado.BLOQUEADO: "BLOCKED",
    RobotEstado.ENTREGANDO: "DEPOSITING",
    # Estados M3: el robot sigue parado/transitando, M1 los muestra como MOVING/BLOCKED
    RobotEstado.ROTANDO: "MOVING",
    RobotEstado.NECESITA_HANDOFF: "BLOCKED",
    RobotEstado.EN_TRANSITO_ANILLO: "MOVING",
}


def robot_to_dict(robot: Robot) -> dict[str, Any]:
    data = asdict(robot)
    data["estado"] = ROBOT_ESTADO_TO_M1.get(robot.estado, "IDLE")
    # orientacion es un str-Enum; exponer su valor ("N"/"E"/"O") para M1/M3
    if "orientacion" in data and hasattr(data["orientacion"], "value"):
        data["orientacion"] = data["orientacion"].value
    return data


def caja_to_dict(caja: Caja) -> dict[str, Any]:
    return asdict(caja)


def pedido_to_dict(pedido: Pedido) -> dict[str, Any]:
    return asdict(pedido)


def snapshot_to_payload(snapshot: StateSnapshot, status: str, velocidad: int) -> dict[str, Any]:
    """Construye el payload `{type: 'tick', ...}` que espera `ws/state`.

    `kpis` incluye tanto las claves en minúscula (tsp, tpcp, ...) como las
    claves originales en mayúscula (TSP, TPCP, ...) — esta última forma es la
    que ya usa `KpisComputed` en `bus-client.service.ts` (consumida por
    dashboard/reportes/etc.), así M1 no necesita refactorizar esos componentes.
    Además se agregan los campos auxiliares `completados`, `capacidad` y
    `cajasPresentes`, también parte de `KpisComputed`.
    """
    kpis_mayus = snapshot.kpis.as_dict()
    kpis = {**kpis_mayus, **{k.lower(): v for k, v in kpis_mayus.items()}}
    kpis["completados"] = len(snapshot.pedidos.completados)
    kpis["capacidad"] = snapshot.config.grilla.capacidad_total if snapshot.config else 0
    kpis["cajasPresentes"] = len(snapshot.grilla)

    grid = (
        {"x": snapshot.config.grilla.x, "y": snapshot.config.grilla.y, "z": snapshot.config.grilla.z}
        if snapshot.config
        else None
    )

    # Robots 1×2: el área almacenable es el interior [1..gx]×[1..gy]; el anillo de
    # tránsito envuelve la grilla (superficie total (gx+2)×(gy+2)). Las estaciones
    # de despacho están en el anillo Oeste (x=0, OESTE) y Este (x=gx+1, ESTE).
    estaciones: list[dict[str, Any]] = []
    grid_total = None
    if snapshot.config is not None:
        gx, gy = snapshot.config.grilla.x, snapshot.config.grilla.y
        grid_total = {"x": gx + 2, "y": gy + 2}
        for y in range(1, gy + 1):
            estaciones.append({"x": 0, "y": y, "orientacion": "O"})
            estaciones.append({"x": gx + 1, "y": y, "orientacion": "E"})

    return {
        "type": "tick",
        "tick": snapshot.tick,
        "mode": MODO_TO_M1[snapshot.modo],
        "policy": POLITICA_TO_M1[snapshot.politica],
        "status": status,
        "velocidad": velocidad,
        "grid": grid,
        "gridTotal": grid_total,
        "estaciones": estaciones,
        "robots": [robot_to_dict(r) for r in snapshot.robots],
        "grilla": [caja_to_dict(c) for c in snapshot.grilla],
        "pedidos": {
            "cola": [pedido_to_dict(p) for p in snapshot.pedidos.cola],
            "completados": [pedido_to_dict(p) for p in snapshot.pedidos.completados],
        },
        "kpis": kpis,
    }
