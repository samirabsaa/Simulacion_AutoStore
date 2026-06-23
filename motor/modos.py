"""motor/modos.py — Lógica de turno diurno y nocturno (T-18, T-19).

Turno diurno:  delega en Despachador (T-12/T-15/T-16/T-17 — Manuel).
Turno nocturno: implementado aquí — robots toman cajas de puertos y las
               ubican en celdas libres según el orden de reposicion.csv.
               Sin lógica inteligente de reordenamiento (fuera de alcance).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bus_persistencia.models.state import (
    Caja,
    ModoTurno,
    Orientacion,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
    celdas_desde,
    celdas_robot,
    cuerpo_para_punta_en,
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
    politica: str,
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


# ------------------------------------------------------------------
# Turno nocturno por conveyors del Norte (ingreso) — robots NORTE
# ------------------------------------------------------------------

def _ruta_l(origen: tuple[int, int], destino: tuple[int, int]) -> list[tuple[int, int]]:
    """Ruta L-shaped en XY (X primero, luego Y); pasos del cuerpo sin el origen."""
    x, y = origen
    dx, dy = destino
    pasos: list[tuple[int, int]] = []
    while x != dx:
        x += 1 if dx > x else -1
        pasos.append((x, y))
    while y != dy:
        y += 1 if dy > y else -1
        pasos.append((x, y))
    return pasos


@dataclass
class _TareaIngreso:
    caja: Caja                      # caja a ingresar (coords finales se fijan al depositar)
    conveyor: tuple[int, int]       # celda conveyor de origen
    fase: str = field(default="ir_a_conveyor")
    ruta: list[tuple[int, int]] = field(default_factory=list)
    destino: tuple[int, int, int] | None = field(default=None)  # celda de almacenaje
    destino_cuerpo: tuple[int, int] = field(default=(0, 0))      # body objetivo de la pierna actual


class DespachadorNocturno:
    """Coordina el INGRESO nocturno: los robots NORTE recogen cajas de las conveyors
    del Norte y las llevan a celdas de almacenaje libres.

    Sólo participan robots NORTE (su punta apunta al Norte y alcanza las conveyors).
    Máquina de estados por robot: ir_a_conveyor → tomar → ir_a_celda → depositar.
    """

    def __init__(self) -> None:
        self._tareas: dict[int, _TareaIngreso] = {}

    def tick(
        self,
        grilla: Grilla,
        robots: dict[int, Robot],
        cola_reposicion: list[Caja],
        acum: Acumuladores,
    ) -> tuple[list[Robot], list[Caja], list[tuple], list[dict]]:
        robots_upd: list[Robot] = []
        g_delta: list[Caja] = []
        g_remove: list[tuple] = []
        eventos: list[dict] = []

        conveyors = grilla.conveyors_norte
        if not conveyors:
            return robots_upd, g_delta, g_remove, eventos

        robots_estado = dict(robots)
        ocupadas: dict[tuple[int, int], int] = {}
        for r in robots_estado.values():
            for celda in celdas_robot(r):
                ocupadas[celda] = r.id

        # Paso 1: asignar ingreso a robots NORTE ociosos mientras haya cola.
        # Cada tarea usa una conveyor distinta (si alcanza) para evitar que dos
        # robots compartan columna y se bloqueen de frente.
        for robot in robots_estado.values():
            if robot.id in self._tareas:
                continue
            if robot.orientacion != Orientacion.NORTE or robot.estado != RobotEstado.INACTIVO:
                continue
            if not cola_reposicion:
                break
            en_uso = {t.conveyor for t in self._tareas.values()}
            libres = [c for c in conveyors if (c.x, c.y) not in en_uso]
            pool = libres or list(conveyors)
            conv = min(pool, key=lambda c: abs(c.x - robot.x) + abs(c.y - robot.y))
            caja = cola_reposicion.pop(0)
            destino_cuerpo = cuerpo_para_punta_en(conv.x, conv.y, Orientacion.NORTE)
            self._tareas[robot.id] = _TareaIngreso(
                caja=caja, conveyor=(conv.x, conv.y),
                ruta=_ruta_l((robot.x, robot.y), destino_cuerpo),
                destino_cuerpo=destino_cuerpo,
            )

        # Paso 2: avanzar cada robot con tarea de ingreso (reruta footprint-aware
        # ante bloqueo). El livelock residual a alta contención es la misma clase
        # que el del turno diurno (lo aborda la robustez de la Parte 3).
        for robot in list(robots_estado.values()):
            tarea = self._tareas.get(robot.id)
            if tarea is None:
                continue
            nuevo, gd, gr, evs, hecho = self._avanzar(robot, tarea, grilla, ocupadas, acum)
            if nuevo is not None and nuevo != robot:
                # Actualizar ocupación (footprint) si se movió
                for celda in celdas_robot(robot):
                    if ocupadas.get(celda) == robot.id:
                        del ocupadas[celda]
                for celda in celdas_robot(nuevo):
                    ocupadas[celda] = nuevo.id
                robots_estado[robot.id] = nuevo
                robots_upd.append(nuevo)
            g_delta.extend(gd)
            g_remove.extend(gr)
            eventos.extend(evs)
            if hecho:
                del self._tareas[robot.id]

        return robots_upd, g_delta, g_remove, eventos

    def _footprint_libre(self, body, robot_id, ocupadas, grilla) -> bool:
        for cx, cy in celdas_desde(body[0], body[1], Orientacion.NORTE):
            if not grilla.en_superficie(cx, cy):
                return False
            occ = ocupadas.get((cx, cy))
            if occ is not None and occ != robot_id:
                return False
        return True

    def _avanzar(self, robot, tarea, grilla, ocupadas, acum):
        if tarea.fase in ("ir_a_conveyor", "ir_a_celda"):
            if not tarea.ruta:
                # Llegó: transición de fase.
                if tarea.fase == "ir_a_conveyor":
                    return self._tomar(robot, tarea, grilla)
                return self._depositar(robot, tarea, grilla, acum)
            siguiente = tarea.ruta[0]
            if not self._footprint_libre(siguiente, robot.id, ocupadas, grilla):
                # Bloqueado: intentar rodear (BFS footprint-aware) hacia el objetivo
                # de la pierna actual; si no hay ruta, esperar este tick.
                from motor.despachador import _ruta_xy_evitando
                nueva = _ruta_xy_evitando(
                    (robot.x, robot.y), tarea.destino_cuerpo, Orientacion.NORTE,
                    robot.id, ocupadas, grilla,
                )
                if nueva:
                    tarea.ruta = list(nueva)
                    siguiente = tarea.ruta[0]
                if not nueva or not self._footprint_libre(siguiente, robot.id, ocupadas, grilla):
                    bloq = _cambiar(robot, RobotEstado.BLOQUEADO)
                    return bloq, [], [], [], False
            tarea.ruta.pop(0)
            acum.total_desplazamientos += 1
            mov = Robot(id=robot.id, x=siguiente[0], y=siguiente[1], z=0,
                        estado=RobotEstado.REPONIENDO, carga_id=robot.carga_id,
                        orientacion=robot.orientacion)
            return mov, [], [], [{"tipo": "movimiento", "robot_id": robot.id,
                                  "x": mov.x, "y": mov.y, "z": 0,
                                  "modo": ModoTurno.NOCTURNO.value}], False
        return robot, [], [], [], False

    def _tomar(self, robot, tarea, grilla):
        """El robot toma la caja de la conveyor y rutea hacia una celda libre."""
        reservadas = {t.destino for t in self._tareas.values() if t.destino is not None}
        destino = _primera_celda_libre(grilla, excluir=reservadas)
        if destino is None:
            # Grilla llena: cancelar (la caja se pierde de esta sesión).
            libre = _cambiar(robot, RobotEstado.INACTIVO, carga_id=None)
            return libre, [], [], [{"tipo": "advertencia",
                                    "mensaje": "grilla llena, ingreso cancelado",
                                    "id_caja": tarea.caja.id_caja}], True
        tarea.destino = destino
        tarea.fase = "ir_a_celda"
        cuerpo = cuerpo_para_punta_en(destino[0], destino[1], Orientacion.NORTE)
        tarea.ruta = _ruta_l((robot.x, robot.y), cuerpo)
        tarea.destino_cuerpo = cuerpo
        cargado = Robot(id=robot.id, x=robot.x, y=robot.y, z=0,
                        estado=RobotEstado.REPONIENDO, carga_id=tarea.caja.id_caja,
                        orientacion=robot.orientacion)
        ev = {"tipo": "caja_tomada_conveyor", "robot_id": robot.id,
              "id_caja": tarea.caja.id_caja, "conveyor": list(tarea.conveyor)}
        return cargado, [], [], [ev], False

    def _depositar(self, robot, tarea, grilla, acum):
        """El robot deposita la caja en la celda destino y queda ocioso."""
        x, y, z = tarea.destino
        caja = Caja(id_caja=tarea.caja.id_caja, id_sku=tarea.caja.id_sku,
                    cantidad=tarea.caja.cantidad, x=x, y=y, z=z)
        grilla.agregar(caja)
        acum.cajas_ingresadas += 1
        acum.ticks_ingreso += 1
        acum.total_desplazamientos += 1
        libre = _cambiar(robot, RobotEstado.INACTIVO, carga_id=None)
        ev = {"tipo": "caja_ingresada", "id_caja": caja.id_caja,
              "id_sku": caja.id_sku, "x": x, "y": y, "z": z}
        return libre, [caja], [], [ev], True


def _cambiar(robot: Robot, estado: RobotEstado, carga_id: str | None = ...) -> Robot:  # type: ignore[assignment]
    cid = robot.carga_id if carga_id is ... else carga_id
    return Robot(id=robot.id, x=robot.x, y=robot.y, z=0,
                 estado=estado, carga_id=cid, orientacion=robot.orientacion)


def _primera_celda_libre(
    grilla: Grilla, excluir: set[tuple[int, int, int]] | None = None
) -> tuple[int, int, int] | None:
    """Retorna la primera celda interior (x,y,z) vacía, recorriendo columnas de
    menor z. Prioriza llenar desde abajo (z=0). El tránsito se excluye: solo las
    columnas almacenables reciben cajas. `excluir` salta celdas ya reservadas."""
    excluir = excluir or set()
    x0, y0, x1, y1 = grilla.interior_bounds
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in grilla.celdas_libres_en_columna(x, y):
                if (x, y, z) not in excluir:
                    return (x, y, z)
    return None
