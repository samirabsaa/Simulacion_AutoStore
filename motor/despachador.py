"""motor/despachador.py — Despachador central de M2 (T-12, T-15, T-16, T-17).

Máquina de estados por robot. Cada tick:
  1. Asigna tarea a robots INACTIVOS (aplica política activa).
  2. Avanza cada robot un paso en su fase actual.
  3. Resuelve colisiones XY: cesión de paso (T-17).

Fases de una tarea de picking:
  mover_a_objetivo → excavar → recuperar → mover_a_puerto → entregar

Acceso por ganchos (T-15): el robot puede acceder a cualquier z de una columna.
Excavación (T-16): las cajas encima del objetivo se mueven a columnas adyacentes
libres, una por tick, antes de recuperar la caja objetivo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bus_persistencia.models.state import Caja, Pedido, PoliticaPicking, Robot, RobotEstado
from motor.politicas import POLITICAS

if TYPE_CHECKING:
    from motor.grilla import Grilla
    from motor.kpis import Acumuladores


# ------------------------------------------------------------------
# Tarea interna — una por robot activo
# ------------------------------------------------------------------

@dataclass
class Tarea:
    pedido: Pedido
    caja_objetivo: Caja
    ruta_entrada: list[tuple[int, int]]   # pasos XY restantes hacia columna objetivo
    ruta_salida: list[tuple[int, int]]    # pasos XY restantes hacia puerto
    puerto: tuple[int, int]
    fase: str = field(default="mover_a_objetivo")
    tick_inicio: int = field(default=0)
    # fases: mover_a_objetivo | excavar | recuperar | mover_a_puerto | entregar


# ------------------------------------------------------------------
# Despachador
# ------------------------------------------------------------------

class Despachador:
    """Cerebro central de M2: asigna y ejecuta rutas de robots por tick.

    El simulador instancia un único Despachador y lo llama en cada tick del
    turno diurno. Los robots no toman decisiones propias — el despachador
    asigna la ruta completa y ellos solo la ejecutan paso a paso.
    """

    def __init__(self, grilla: "Grilla") -> None:
        self.grilla = grilla
        self._tareas: dict[int, Tarea] = {}      # robot_id -> Tarea activa
        self._cajas_reservadas: set[tuple[int, int, int]] = set()  # celdas ya asignadas
        self._tick_actual: int = 0

    def tick(
        self,
        robots: dict[int, Robot],
        pedidos_cola: list[Pedido],
        politica: PoliticaPicking,
        acum: "Acumuladores",
    ) -> tuple[
        list[Robot],
        list[Caja],
        list[tuple[int, int, int]],
        list[Pedido],
        list[dict],
    ]:
        """Ejecuta un paso de simulación para todos los robots en turno diurno.

        Retorna:
            robots_actualizados  — robots que cambiaron este tick
            grilla_delta         — cajas agregadas/modificadas
            grilla_remove        — coordenadas de celdas vaciadas
            pedidos_completados  — pedidos entregados en puerto este tick
            eventos              — dicts con vocabulario del bus
        """
        self._tick_actual += 1

        grilla_delta: list[Caja] = []
        grilla_remove: list[tuple[int, int, int]] = []
        pedidos_completados: list[Pedido] = []
        eventos: list[dict] = []

        # Copia mutable del estado de robots para este tick
        robots_estado: dict[int, Robot] = dict(robots)

        # Paso 1: asignar tareas a robots INACTIVOS sin tarea
        politica_fn = POLITICAS[politica]
        pedidos_disponibles = [
            p for p in pedidos_cola
            if not any(t.pedido.id_pedido == p.id_pedido for t in self._tareas.values())
        ]
        for robot in robots_estado.values():
            if robot.estado == RobotEstado.INACTIVO and robot.id not in self._tareas:
                pedido = politica_fn(pedidos_disponibles, self.grilla, self.grilla.puertos)
                if pedido is None:
                    continue
                tarea = self._crear_tarea(robot, pedido)
                if tarea is None:
                    continue
                tarea.tick_inicio = self._tick_actual
                self._tareas[robot.id] = tarea
                pedidos_disponibles.remove(pedido)

        # Paso 2: posiciones actuales para detección de colisiones XY
        posiciones_actuales: dict[tuple[int, int], int] = {
            (r.x, r.y): r.id for r in robots_estado.values()
        }

        # Paso 2.5: Ceder paso — INACTIVOS se apartan si bloquean
        robots_modificados: list[Robot] = []
        for robot in list(robots_estado.values()):
            tarea = self._tareas.get(robot.id)
            if tarea is None or robot.estado != RobotEstado.BLOQUEADO:
                continue
            if tarea.fase == "mover_a_objetivo" and tarea.ruta_entrada:
                siguiente = tarea.ruta_entrada[0]
            elif tarea.fase == "mover_a_puerto" and tarea.ruta_salida:
                siguiente = tarea.ruta_salida[0]
            else:
                continue
            ocupante_id = posiciones_actuales.get(siguiente)
            if ocupante_id is None:
                continue
            ocupante = robots_estado.get(ocupante_id)
            if ocupante is None or ocupante.estado != RobotEstado.INACTIVO:
                continue
            if ocupante_id in self._tareas:
                continue
            for ax, ay in self.grilla.columnas_adyacentes(ocupante.x, ocupante.y):
                if (ax, ay) == (robot.x, robot.y):
                    continue
                if (ax, ay) not in posiciones_actuales:
                    posiciones_actuales.pop((ocupante.x, ocupante.y), None)
                    posiciones_actuales[(ax, ay)] = ocupante_id
                    nuevo = Robot(
                        id=ocupante_id, x=ax, y=ay, z=0,
                        estado=RobotEstado.INACTIVO, carga_id=None,
                    )
                    robots_estado[ocupante_id] = nuevo
                    robots_modificados.append(nuevo)
                    eventos.append(_ev_movimiento(nuevo))
                    break

        # Paso 2.6: Resolver interbloqueo — dos robots BLOQUEADOS que
        #           ocupan cada uno la celda destino del otro (swap)
        robots_movidos_swap: set[int] = set()
        for robot in list(robots_estado.values()):
            if robot.id in robots_movidos_swap:
                continue
            tarea = self._tareas.get(robot.id)
            if tarea is None or robot.estado != RobotEstado.BLOQUEADO:
                continue
            if tarea.fase == "mover_a_objetivo" and tarea.ruta_entrada:
                siguiente = tarea.ruta_entrada[0]
                ruta_robot = tarea.ruta_entrada
            elif tarea.fase == "mover_a_puerto" and tarea.ruta_salida:
                siguiente = tarea.ruta_salida[0]
                ruta_robot = tarea.ruta_salida
            else:
                continue
            ocupante_id = posiciones_actuales.get(siguiente)
            if ocupante_id is None or ocupante_id == robot.id:
                continue
            ocupante = robots_estado.get(ocupante_id)
            if ocupante is None or ocupante.estado != RobotEstado.BLOQUEADO:
                continue
            otarea = self._tareas.get(ocupante_id)
            if otarea is None:
                continue
            if otarea.fase == "mover_a_objetivo" and otarea.ruta_entrada:
                o_siguiente = otarea.ruta_entrada[0]
                ruta_ocupante = otarea.ruta_entrada
            elif otarea.fase == "mover_a_puerto" and otarea.ruta_salida:
                o_siguiente = otarea.ruta_salida[0]
                ruta_ocupante = otarea.ruta_salida
            else:
                continue
            if o_siguiente != (robot.x, robot.y):
                continue
            # Ambos quieren la posición del otro → intercambiar
            posiciones_actuales.pop((robot.x, robot.y), None)
            posiciones_actuales.pop((siguiente), None)
            posiciones_actuales[(robot.x, robot.y)] = ocupante_id
            posiciones_actuales[(siguiente)] = robot.id

            r_a = Robot(id=robot.id, x=siguiente[0], y=siguiente[1], z=robot.z,
                        estado=RobotEstado.DESPLAZANDOSE, carga_id=robot.carga_id)
            r_b = Robot(id=ocupante_id, x=robot.x, y=robot.y, z=0,
                        estado=RobotEstado.DESPLAZANDOSE, carga_id=ocupante.carga_id)
            robots_estado[robot.id] = r_a
            robots_estado[ocupante_id] = r_b
            robots_modificados.append(r_a)
            robots_modificados.append(r_b)
            eventos.append(_ev_movimiento(r_a))
            eventos.append(_ev_movimiento(r_b))
            ruta_robot.pop(0)
            ruta_ocupante.pop(0)
            acum.total_desplazamientos += 2
            robots_movidos_swap.update((robot.id, ocupante_id))

        # Paso 3: avanzar cada robot
        for robot in robots_estado.values():
            if robot.id in robots_movidos_swap:
                continue
            tarea = self._tareas.get(robot.id)
            if tarea is None:
                # Sin tarea: permanece INACTIVO sin cambios
                continue

            nuevo, g_d, g_r, completado, evs = self._avanzar(
                robot, tarea, posiciones_actuales, acum
            )

            if nuevo.id != robot.id or nuevo != robot:
                # Actualizar posición en el mapa de colisiones si se movió
                if (nuevo.x, nuevo.y) != (robot.x, robot.y):
                    posiciones_actuales.pop((robot.x, robot.y), None)
                    posiciones_actuales[(nuevo.x, nuevo.y)] = nuevo.id
                robots_estado[robot.id] = nuevo
                robots_modificados.append(nuevo)

            grilla_delta.extend(g_d)
            grilla_remove.extend(g_r)
            eventos.extend(evs)

            if completado is not None:
                pedidos_completados.append(completado)
                self._cajas_reservadas.discard(
                    (tarea.caja_objetivo.x, tarea.caja_objetivo.y, tarea.caja_objetivo.z)
                )
                del self._tareas[robot.id]

        return robots_modificados, grilla_delta, grilla_remove, pedidos_completados, eventos

    # ------------------------------------------------------------------
    # Creación de tareas
    # ------------------------------------------------------------------

    def _caja_disponible(self, id_sku: str) -> Caja | None:
        """Similar a grilla.primera_caja_accesible pero excluye celdas reservadas."""
        candidatas = self.grilla.buscar_por_sku(id_sku)
        candidatas = [c for c in candidatas if (c.x, c.y, c.z) not in self._cajas_reservadas]
        if not candidatas:
            return None

        def costo_excavacion(c: Caja) -> int:
            gz = self.grilla.config.grilla.z
            return sum(1 for z in range(c.z + 1, gz) if self.grilla.ocupada(c.x, c.y, z))
        return min(candidatas, key=costo_excavacion)

    def _crear_tarea(self, robot: Robot, pedido: Pedido) -> Tarea | None:
        """Busca una caja no reservada y genera la ruta. Retorna None si no hay."""
        caja = self._caja_disponible(pedido.id_sku)
        if caja is None:
            return None

        puerto = self.grilla.puerto_mas_cercano(caja.x, caja.y)
        ruta_entrada = _ruta_xy((robot.x, robot.y), (caja.x, caja.y))
        ruta_salida = _ruta_xy((caja.x, caja.y), puerto)

        self._cajas_reservadas.add((caja.x, caja.y, caja.z))

        return Tarea(
            pedido=pedido,
            caja_objetivo=caja,
            ruta_entrada=ruta_entrada,
            ruta_salida=ruta_salida,
            puerto=puerto,
        )

    # ------------------------------------------------------------------
    # Avance de un robot un paso (máquina de estados)
    # ------------------------------------------------------------------

    def _avanzar(
        self,
        robot: Robot,
        tarea: Tarea,
        posiciones_actuales: dict[tuple[int, int], int],
        acum: "Acumuladores",
    ) -> tuple[Robot, list[Caja], list[tuple], Pedido | None, list[dict]]:
        """Avanza el robot un tick según la fase actual de su tarea."""
        if tarea.fase == "mover_a_objetivo":
            return self._fase_mover_a_objetivo(robot, tarea, posiciones_actuales, acum)
        elif tarea.fase == "excavar":
            return self._fase_excavar(robot, tarea, acum)
        elif tarea.fase == "recuperar":
            return self._fase_recuperar(robot, tarea, acum)
        elif tarea.fase == "mover_a_puerto":
            return self._fase_mover_a_puerto(robot, tarea, posiciones_actuales, acum)
        elif tarea.fase == "entregar":
            return self._fase_entregar(robot, tarea, acum)
        # Estado desconocido: no hacer nada
        return robot, [], [], None, []

    def _fase_mover_a_objetivo(self, robot, tarea, posiciones_actuales, acum):
        if not tarea.ruta_entrada:
            # Ya estamos en la columna objetivo
            tarea.fase = "excavar"
            return self._fase_excavar(robot, tarea, acum)

        siguiente = tarea.ruta_entrada[0]
        if _celda_ocupada(siguiente, robot.id, posiciones_actuales):
            # Cesión de paso (T-17)
            nuevo = _cambiar_estado(robot, RobotEstado.BLOQUEADO)
            acum.ticks_bloqueados += 1
            return nuevo, [], [], None, [_ev_bloqueo(robot)]

        tarea.ruta_entrada.pop(0)
        acum.total_desplazamientos += 1
        nuevo = Robot(id=robot.id, x=siguiente[0], y=siguiente[1], z=robot.z,
                      estado=RobotEstado.DESPLAZANDOSE, carga_id=robot.carga_id)
        return nuevo, [], [], None, [_ev_movimiento(nuevo)]

    def _fase_excavar(self, robot, tarea, acum):
        col = self.grilla.columna(tarea.caja_objetivo.x, tarea.caja_objetivo.y)
        z_obj = tarea.caja_objetivo.z
        encima = [c for c in col if c.z > z_obj]

        if not encima:
            tarea.fase = "recuperar"
            return self._fase_recuperar(robot, tarea, acum)

        # Mover la caja más alta a una columna adyacente con espacio.
        #
        # Crítico: NO descargar en una columna que sea objetivo de otra tarea
        # activa. Si dos robots excavan columnas adyacentes y cada uno tira sus
        # cajas en la columna del otro, ninguna columna baja nunca (ping-pong
        # infinito → pedidos nunca se completan). Excluir las columnas-objetivo
        # garantiza que la columna que se excava SOLO pierde cajas → termina.
        caja_mover = max(encima, key=lambda c: c.z)
        columnas_objetivo = {
            (t.caja_objetivo.x, t.caja_objetivo.y) for t in self._tareas.values()
        }
        adyacentes = self.grilla.columnas_adyacentes(caja_mover.x, caja_mover.y)
        neutrales = [c for c in adyacentes if c not in columnas_objetivo]
        # Preferir columnas neutrales; las objetivo solo como último recurso.
        orden_adyacentes = neutrales + [c for c in adyacentes if c in columnas_objetivo]
        for ax, ay in orden_adyacentes:
            libres = self.grilla.celdas_libres_en_columna(ax, ay)
            if not libres:
                continue
            z_libre = libres[0]
            self.grilla.remover(caja_mover.x, caja_mover.y, caja_mover.z)
            caja_nueva = Caja(
                id_caja=caja_mover.id_caja,
                id_sku=caja_mover.id_sku,
                cantidad=caja_mover.cantidad,
                x=ax, y=ay, z=z_libre,
            )
            self.grilla.agregar(caja_nueva)
            acum.total_desplazamientos += 1
            g_d = [caja_nueva]
            g_r = [(caja_mover.x, caja_mover.y, caja_mover.z)]
            nuevo = _cambiar_estado(robot, RobotEstado.EXCAVANDO)
            ev = {"tipo": "excavacion", "robot_id": robot.id,
                  "de": [caja_mover.x, caja_mover.y, caja_mover.z],
                  "a": [ax, ay, z_libre]}
            return nuevo, g_d, g_r, None, [ev]

        # Adyacentes llenas: buscar en toda la grilla
        gx, gy = self.grilla.config.grilla.x, self.grilla.config.grilla.y
        for ax in range(gx):
            for ay in range(gy):
                if (ax, ay) == (caja_mover.x, caja_mover.y):
                    continue
                if (ax, ay) in self.grilla.columnas_adyacentes(caja_mover.x, caja_mover.y):
                    continue  # ya lo intentamos arriba
                libres = self.grilla.celdas_libres_en_columna(ax, ay)
                if not libres:
                    continue
                z_libre = libres[0]
                self.grilla.remover(caja_mover.x, caja_mover.y, caja_mover.z)
                caja_nueva = Caja(
                    id_caja=caja_mover.id_caja,
                    id_sku=caja_mover.id_sku,
                    cantidad=caja_mover.cantidad,
                    x=ax, y=ay, z=z_libre,
                )
                self.grilla.agregar(caja_nueva)
                acum.total_desplazamientos += 1
                g_d = [caja_nueva]
                g_r = [(caja_mover.x, caja_mover.y, caja_mover.z)]
                nuevo = _cambiar_estado(robot, RobotEstado.EXCAVANDO)
                ev = {"tipo": "excavacion", "robot_id": robot.id,
                      "de": [caja_mover.x, caja_mover.y, caja_mover.z],
                      "a": [ax, ay, z_libre]}
                return nuevo, g_d, g_r, None, [ev]

        # Toda la grilla llena: esperar un tick
        nuevo = _cambiar_estado(robot, RobotEstado.EXCAVANDO)
        return nuevo, [], [], None, []

    def _fase_recuperar(self, robot, tarea, acum):
        # Verificar que la caja objetivo sigue en su lugar
        caja = self.grilla.get(
            tarea.caja_objetivo.x, tarea.caja_objetivo.y, tarea.caja_objetivo.z
        )
        if caja is None:
            # La caja ya no está (caso edge): cancelar tarea y liberar robot
            self._cajas_reservadas.discard(
                (tarea.caja_objetivo.x, tarea.caja_objetivo.y, tarea.caja_objetivo.z)
            )
            del self._tareas[robot.id]
            nuevo = _cambiar_estado(robot, RobotEstado.INACTIVO, carga_id=None)
            return nuevo, [], [], None, []

        self.grilla.remover(caja.x, caja.y, caja.z)
        acum.cajas_recuperadas += 1
        acum.total_desplazamientos += 1

        # Actualizar ruta_salida desde la posición actual del robot
        tarea.ruta_salida = _ruta_xy((robot.x, robot.y), tarea.puerto)
        tarea.fase = "mover_a_puerto"

        nuevo = Robot(id=robot.id, x=robot.x, y=robot.y, z=robot.z,
                      estado=RobotEstado.RECUPERANDO, carga_id=caja.id_caja)
        g_r = [(caja.x, caja.y, caja.z)]
        ev = {"tipo": "caja_recuperada", "robot_id": robot.id,
              "id_caja": caja.id_caja, "id_sku": caja.id_sku,
              "x": caja.x, "y": caja.y, "z": caja.z}
        return nuevo, [], g_r, None, [ev]

    def _fase_mover_a_puerto(self, robot, tarea, posiciones_actuales, acum):
        if not tarea.ruta_salida:
            tarea.fase = "entregar"
            return self._fase_entregar(robot, tarea, acum)

        siguiente = tarea.ruta_salida[0]
        if _celda_ocupada(siguiente, robot.id, posiciones_actuales):
            nuevo = _cambiar_estado(robot, RobotEstado.BLOQUEADO, carga_id=robot.carga_id)
            acum.ticks_bloqueados += 1
            return nuevo, [], [], None, [_ev_bloqueo(robot)]

        tarea.ruta_salida.pop(0)
        acum.total_desplazamientos += 1
        nuevo = Robot(id=robot.id, x=siguiente[0], y=siguiente[1], z=robot.z,
                      estado=RobotEstado.ENTREGANDO, carga_id=robot.carga_id)
        return nuevo, [], [], None, [_ev_movimiento(nuevo)]

    def _fase_entregar(self, robot, tarea, acum):
        dt = self._tick_actual - tarea.tick_inicio
        acum.pedidos_completados += 1
        acum.suma_tiempos_ciclo += dt

        nuevo = Robot(id=robot.id, x=robot.x, y=robot.y, z=robot.z,
                      estado=RobotEstado.INACTIVO, carga_id=None)
        ev = {"tipo": "pedido_completado", "robot_id": robot.id,
              "id_pedido": tarea.pedido.id_pedido,
              "id_sku": tarea.pedido.id_sku,
              "ticks": dt}
        return nuevo, [], [], tarea.pedido, [ev]


# ------------------------------------------------------------------
# Helpers puros
# ------------------------------------------------------------------

def _ruta_xy(origen: tuple[int, int], destino: tuple[int, int]) -> list[tuple[int, int]]:
    """Ruta L-shaped en XY: mueve X primero, luego Y."""
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


def _celda_ocupada(
    xy: tuple[int, int],
    robot_id: int,
    posiciones: dict[tuple[int, int], int],
) -> bool:
    """Retorna True si la celda XY está ocupada por un robot distinto al dado."""
    ocupante = posiciones.get(xy)
    return ocupante is not None and ocupante != robot_id


def _cambiar_estado(
    robot: Robot,
    estado: RobotEstado,
    carga_id: str | None = ...,  # type: ignore[assignment]
) -> Robot:
    cid = robot.carga_id if carga_id is ... else carga_id
    return Robot(id=robot.id, x=robot.x, y=robot.y, z=robot.z,
                 estado=estado, carga_id=cid)


def _ev_movimiento(robot: Robot) -> dict:
    return {"tipo": "movimiento", "robot_id": robot.id,
            "x": robot.x, "y": robot.y, "z": robot.z}


def _ev_bloqueo(robot: Robot) -> dict:
    return {"tipo": "bloqueo", "robot_id": robot.id,
            "x": robot.x, "y": robot.y, "z": robot.z}
