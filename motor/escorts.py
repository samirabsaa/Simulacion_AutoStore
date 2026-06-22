"""motor/escorts.py — Coordinación de celdas libres en excavación (EscortPlanner).

Anexo técnico al soporte de la "Mente Colmena" (`motor/colmena.py`). Resuelve el
**livelock** observado a alta ocupación (≈95%): cuando casi no quedan celdas
libres, varios robots compiten greedy por las mismas pocas celdas durante la
excavación y, como último recurso, descargan cajas en columnas que son objetivo
de otra tarea → se re-entierran cajas, ninguna columna baja y `total_desplazamientos`
(MTRP) sube sin que `pedidos_completados` (TSP) progrese.

Fundamento (literatura *Puzzle-Based Storage*, Gue & Kim 2007): las celdas libres
se tratan como **escorts** — un recurso que se *planifica con destino y dueño*, no
espacio que cualquier robot toma por cercanía. La asignación es **conjunta** entre
todas las excavaciones activas y se recalcula por **horizonte rodante**
(cada `HORIZONTE_REPLANIFICACION` ticks, o antes si el `StagnationDetector`
detecta estancamiento). Si hay más excavaciones que regiones abiertas
disponibles, algunas tareas quedan **sin escort y esperan** (serialización):
esto rompe la competencia degenerativa — un subconjunto de excavaciones termina,
libera celdas, y las que esperaban retoman.

Mapeo con el spec (clases propuestas → implementación real):
  TareaExcavacion → se fusiona en `motor.despachador.Tarea` (campos
                    `profundidad_inicial`, `ultimo_progreso_medido`,
                    `ticks_sin_progreso`, `escort_asignado`); no se duplica.
  Escort, EscortPlanner, StagnationDetector → este módulo.

Determinismo: toda iteración es por orden estable (ids / row-major) para preservar
la reproducibilidad que exigen las pruebas y la animación de M3.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from motor.colmena import distancia_manhattan

if TYPE_CHECKING:
    from bus_persistencia.models.state import Caja
    from motor.despachador import Tarea
    from motor.grilla import Grilla

# Constantes configurables (calibrables contra datos reales de Forus — no
# hardcodear en la lógica). Calibradas contra el escenario de 95% de ocupación.
HORIZONTE_REPLANIFICACION = 10  # K: ticks entre replanificaciones completas
UMBRAL_ESTANCAMIENTO = 4        # T: ticks sin progreso neto que disparan replan


def _es_excavacion(tarea: "Tarea") -> bool:
    """True si la tarea está excavando o acaba de llegar a su columna objetivo."""
    return tarea.fase == "excavar" or (
        tarea.fase == "mover_a_objetivo" and not tarea.ruta_entrada
    )


def _camino_l(origen: tuple[int, int], destino: tuple[int, int]) -> list[tuple[int, int]]:
    """Columnas intermedias de la ruta L-shaped (X primero, luego Y), sin incluir
    origen ni destino. Sirve para detectar si una trayectoria de descarga cruzaría
    una columna protegida."""
    x, y = origen
    dx, dy = destino
    pasos: list[tuple[int, int]] = []
    while x != dx:
        x += 1 if dx > x else -1
        pasos.append((x, y))
    while y != dy:
        y += 1 if dy > y else -1
        pasos.append((x, y))
    return pasos[:-1] if pasos else pasos  # excluir el destino


@dataclass
class Escort:
    """Celda/columna libre gestionada como recurso planificable.

    `columna` es la columna de descanso (x,y) asignada a una tarea; el nivel z
    concreto se resuelve al colocar la caja (la columna se va llenando)."""

    columna: tuple[int, int]
    propietario: int | None = None        # robot_id de la tarea dueña
    reservado_hasta_tick: int | None = None


class EscortPlanner:
    """Asignación conjunta de columnas-escort a las excavaciones activas."""

    def __init__(self, horizonte: int = HORIZONTE_REPLANIFICACION) -> None:
        self.horizonte = horizonte

    # ------------------------------------------------------------------
    # Planificación conjunta (rolling horizon)
    # ------------------------------------------------------------------

    def planificar(self, tareas: dict[int, "Tarea"], grilla: "Grilla", tick: int) -> None:
        """Asigna `escort_asignado` a cada excavación activa que lo necesite.

        Conserva las asignaciones aún válidas (estabilidad dentro de la ventana) y
        reparte columnas-escort libres a las tareas sin escort, en orden
        determinista (excavaciones más cortas primero → liberan celdas antes)."""
        excav = [(rid, t) for rid, t in tareas.items() if _es_excavacion(t)]
        protegidas = {(t.caja_objetivo.x, t.caja_objetivo.y) for _, t in excav}
        reservadas: set[tuple[int, int]] = set()

        # 1) Conservar asignaciones previas que sigan siendo válidas.
        for _rid, t in excav:
            e = t.escort_asignado
            if e is not None and self._columna_valida(e.columna, grilla, protegidas):
                reservadas.add(e.columna)
            else:
                t.escort_asignado = None

        # 2) Asignar a las que no tienen escort, en orden determinista.
        faltantes = sorted(
            (rt for rt in excav if rt[1].escort_asignado is None),
            key=lambda rt: (rt[1].profundidad_inicial, rt[0]),
        )
        for rid, t in faltantes:
            destino = self._mejor_columna(t, grilla, protegidas, reservadas)
            if destino is not None:
                reservadas.add(destino)
                t.escort_asignado = Escort(
                    columna=destino,
                    propietario=rid,
                    reservado_hasta_tick=tick + self.horizonte,
                )
            # Si no hay columna segura disponible, la tarea queda sin escort y
            # esperará (serialización) hasta la próxima replanificación.

    def _columna_valida(
        self, col: tuple[int, int], grilla: "Grilla", protegidas: set[tuple[int, int]]
    ) -> bool:
        return (
            col not in protegidas
            and not grilla.es_transito(*col)
            and bool(grilla.celdas_libres_en_columna(*col))
        )

    def _mejor_columna(
        self,
        tarea: "Tarea",
        grilla: "Grilla",
        protegidas: set[tuple[int, int]],
        reservadas: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        """Columna-escort más cercana al objetivo cuya trayectoria de descarga no
        cruce una columna protegida. Degrada a la no protegida más cercana si no
        hay opción 'segura'; None si no queda ninguna columna libre no protegida."""
        objetivo = (tarea.caja_objetivo.x, tarea.caja_objetivo.y)
        gx, gy = grilla.config.grilla.x, grilla.config.grilla.y

        candidatas: list[tuple[int, int]] = []
        for x in range(gx):
            for y in range(gy):
                col = (x, y)
                if col == objetivo or col in protegidas or col in reservadas:
                    continue
                if grilla.es_transito(x, y):
                    continue
                if grilla.celdas_libres_en_columna(x, y):
                    candidatas.append(col)
        if not candidatas:
            return None

        seguras = [
            c for c in candidatas
            if not any(p in protegidas for p in _camino_l(objetivo, c))
        ]
        pool = seguras if seguras else candidatas
        return min(pool, key=lambda c: (distancia_manhattan(objetivo, c), c))

    # ------------------------------------------------------------------
    # Movimiento físico del escort (un salto por tick)
    # ------------------------------------------------------------------

    def mover_escort_un_paso(
        self,
        caja_mover: "Caja",
        tarea: "Tarea",
        grilla: "Grilla",
        protegidas: set[tuple[int, int]],
        reservadas: set[tuple[int, int]],
    ) -> tuple[int, int, int] | None:
        """Celda (x,y,z) donde depositar la caja excavada este tick.

        Patrón de 3 pasos (directo): salto a la columna adyacente —no protegida y
        no reservada por otra tarea— que más acerca la caja a su columna-escort.
        Patrón de 5 pasos (rodeo): si ninguna adyacente sirve, se coloca
        directamente en la columna-escort reservada de la tarea (la caja queda
        'escoltada' a su región de descanso). None si tampoco hay espacio allí
        (la tarea esperará y se replanificará)."""
        escort = tarea.escort_asignado
        if escort is None:
            return None
        destino = escort.columna
        bx, by = caja_mover.x, caja_mover.y

        adyacentes = grilla.columnas_adyacentes(bx, by)
        candidatas = [
            c for c in adyacentes
            if c not in protegidas
            and (c == destino or c not in reservadas)
            and grilla.celdas_libres_en_columna(*c)
        ]
        if candidatas:
            mejor = min(candidatas, key=lambda c: (distancia_manhattan(c, destino), c))
            z = grilla.celdas_libres_en_columna(*mejor)[0]
            return (mejor[0], mejor[1], z)

        # Rodeo: depositar en la columna-escort reservada (si conserva espacio).
        if destino not in protegidas:
            libres = grilla.celdas_libres_en_columna(*destino)
            if libres:
                return (destino[0], destino[1], libres[0])
        return None


class StagnationDetector:
    """Detecta el ciclo degenerativo midiendo **progreso neto** sobre la columna
    objetivo (no movimientos totales): si la cantidad de cajas sobre el objetivo no
    baja durante `umbral` ticks, hay estancamiento → replanificación anticipada."""

    def __init__(self, umbral: int = UMBRAL_ESTANCAMIENTO) -> None:
        self.umbral = umbral

    @staticmethod
    def cajas_encima(tarea: "Tarea", grilla: "Grilla") -> int:
        col = grilla.columna(tarea.caja_objetivo.x, tarea.caja_objetivo.y)
        return sum(1 for c in col if c.z > tarea.caja_objetivo.z)

    def actualizar(self, tareas: list["Tarea"], grilla: "Grilla") -> None:
        for tarea in tareas:
            encima = self.cajas_encima(tarea, grilla)
            if tarea.profundidad_inicial < 0:
                # Primer tick de excavación: fijar la profundidad de referencia.
                tarea.profundidad_inicial = encima
                tarea.ultimo_progreso_medido = 0
                tarea.ticks_sin_progreso = 0
                continue
            progreso = tarea.profundidad_inicial - encima
            if progreso <= tarea.ultimo_progreso_medido:
                tarea.ticks_sin_progreso += 1
            else:
                tarea.ticks_sin_progreso = 0
            tarea.ultimo_progreso_medido = progreso

    def hay_estancamiento(self, tareas: list["Tarea"]) -> bool:
        return any(t.ticks_sin_progreso >= self.umbral for t in tareas)
