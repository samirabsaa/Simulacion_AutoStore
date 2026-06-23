"""motor/modos.py — Lógica de turno diurno y nocturno (T-18, T-19).

Turno diurno:  delega en Despachador (T-12/T-15/T-16/T-17 — Manuel).
Turno nocturno: implementado aquí — robots toman cajas de puertos y las
               ubican en celdas libres según el orden de reposicion.csv.
               Sin lógica inteligente de reordenamiento (fuera de alcance).
"""
from __future__ import annotations

from bus_persistencia.models.state import (
    Caja,
    ModoTurno,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
)
from motor.grilla import Grilla
from motor.kpis import Acumuladores


# ------------------------------------------------------------------
# Turno diurno — delega completamente en el Despachador (Manuel)
# ------------------------------------------------------------------

def procesar_diurno(
    despachador,           # motor.despachador.Despachador
    robots: dict[int, Robot],
    pedidos_cola: list[Pedido],
    politica: PoliticaPicking,
    acum: Acumuladores,
) -> tuple[list[Robot], list[Caja], list[tuple], list[Pedido], list[dict]]:
    """Delega el turno diurno al despachador central.

    Retorna:
        (robots_actualizados, grilla_delta, grilla_remove,
         pedidos_completados_add, eventos)
    """
    return despachador.tick(robots, pedidos_cola, politica, acum)


# ------------------------------------------------------------------
# Turno nocturno — reposición simple (T-19)
# ------------------------------------------------------------------

def procesar_nocturno(
    grilla: Grilla,
    robots: dict[int, Robot],
    cola_reposicion: list[Caja],
    acum: Acumuladores,
) -> tuple[list[Robot], list[Caja], list[tuple], list[dict]]:
    """Reposición nocturna: por cada robot inactivo, toma la próxima caja de
    `cola_reposicion` y la ubica en la primera celda libre de la grilla.

    Retorna:
        (robots_actualizados, grilla_delta, grilla_remove, eventos)
    """
    robots_actualizados: list[Robot] = []
    grilla_delta: list[Caja] = []
    grilla_remove: list[tuple] = []
    eventos: list[dict] = []

    if not cola_reposicion:
        return robots_actualizados, grilla_delta, grilla_remove, eventos

    idx_reposicion = 0  # puntero a la próxima caja de la cola

    for robot in robots.values():
        if robot.estado != RobotEstado.INACTIVO:
            continue
        if idx_reposicion >= len(cola_reposicion):
            break

        # La caja a reponer proviene del puerto más cercano al robot
        caja_origen = cola_reposicion[idx_reposicion]
        idx_reposicion += 1

        # Buscar celda libre en la grilla (columna con espacio disponible)
        celda_destino = _primera_celda_libre(grilla)
        if celda_destino is None:
            # Grilla llena — no hay dónde poner la caja
            eventos.append({
                "tipo": "advertencia",
                "mensaje": "grilla llena, caja no colocada",
                "id_caja": caja_origen.id_caja,
            })
            continue

        x, y, z = celda_destino
        caja_colocada = Caja(
            id_caja=caja_origen.id_caja,
            id_sku=caja_origen.id_sku,
            cantidad=caja_origen.cantidad,
            x=x, y=y, z=z,
        )
        grilla.agregar(caja_colocada)
        grilla_delta.append(caja_colocada)
        acum.cajas_ingresadas += 1
        acum.ticks_ingreso += 1
        acum.total_desplazamientos += 1

        # Robot 1×2: la reposición nocturna es deliberadamente simple (fuera de
        # alcance la coordinación inteligente). El robot NO se reubica sobre la
        # columna (evita solapar footprints 1×2 sin gestión de colisiones): se
        # mantiene en su posición y solo marca REPONIENDO, preservando orientación.
        robot_actualizado = Robot(
            id=robot.id,
            x=robot.x, y=robot.y, z=0,
            estado=RobotEstado.REPONIENDO,
            carga_id=None,
            orientacion=robot.orientacion,
        )
        robots_actualizados.append(robot_actualizado)

        eventos.append({
            "tipo": "caja_ingresada_por",
            "robot_id": robot.id,
            "x": x, "y": y, "z": z,
            "modo": ModoTurno.NOCTURNO.value,
        })
        eventos.append({
            "tipo": "caja_ingresada",
            "id_caja": caja_colocada.id_caja,
            "id_sku": caja_colocada.id_sku,
            "x": x, "y": y, "z": z,
        })

    return robots_actualizados, grilla_delta, grilla_remove, eventos


def _primera_celda_libre(grilla: Grilla) -> tuple[int, int, int] | None:
    """Retorna la primera celda interior (x,y,z) vacía, recorriendo columnas de
    menor z. Prioriza llenar desde abajo (z=0). El anillo de tránsito (borde) se
    excluye: solo las columnas almacenables [1..gx]×[1..gy] reciben cajas."""
    gx = grilla.config.grilla.x
    gy = grilla.config.grilla.y

    for x in range(1, gx + 1):
        for y in range(1, gy + 1):
            libres = grilla.celdas_libres_en_columna(x, y)
            if libres:
                return (x, y, libres[0])  # z más bajo disponible
    return None
