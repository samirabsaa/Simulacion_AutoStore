# motor/simulador.py
# Esqueleto de referencia para Manuel — clase orquestadora del motor (M2).
#
# Rol de esta clase: ser el ÚNICO punto de entrada y de escritura al bus para M2.
# No reimplementa la lógica de simulación — delega en grilla.py / politicas.py /
# despachador.py / kpis.py / modos.py, y arma los TickDelta que el bus necesita
# para que M1 (UI) y M3 (Omniverse) lean snapshots actualizados cada tick.
#
# IMPORTANTE — contrato real (definido por Martín en la rama bus-persistencia,
# ver docs/bus_api.md y docs/integracion_grupo12.md): es DISTINTO al descrito
# originalmente en el CLAUDE.md del proyecto. Este esqueleto ya está alineado
# con la implementación real de bus_persistencia, no con la versión antigua.

from bus_persistencia.bus.state_bus import StateBus, M2_WRITER_ID
from bus_persistencia.models.state import (
    Caja,
    KPISet,
    ModoTurno,
    Pedido,
    PoliticaPicking,
    Robot,
    RobotEstado,
    TickDelta,
)


class AutoStoreSimulator:
    def __init__(self, bus: StateBus):
        """Guarda la referencia al bus (único canal de lectura/escritura para
        M2). NO carga config ni pedidos aquí — eso lo hace M1 vía
        `bus.set_config` / `bus.set_pedidos_cola` ANTES de iniciar la
        simulación (ver flujo en docs/integracion_grupo12.md, sección 4).
        Llamar a `inicializar_desde_bus()` una vez que M1 haya configurado
        el bus y se presione Play."""
        self.bus = bus

        # Estado principal del motor — espejo interno que se traduce a
        # TickDelta cada tick. La grilla se modela igual que en el bus:
        # como máximo una Caja por celda exacta (x, y, z), NO como pila de
        # cajas por columna (ese era el modelo del CLAUDE.md original; el
        # bus real de Martín usa celdas individuales — más fiel al AutoStore
        # real y compatible con cómo Martín arma `grilla_delta`/`grilla_remove`).
        self.grilla: dict[tuple[int, int, int], Caja] = {}
        self.robots: dict[int, Robot] = {}
        self.pedidos_cola: list[Pedido] = []
        self.pedidos_completados: list[Pedido] = []
        self.cola_reposicion: list[Caja] = []
        self.puertos: list[tuple[int, int]] = []

        self.modo: ModoTurno = ModoTurno.DIURNO
        self.tick: int = 0
        self.kpis: KPISet = KPISet()

        # Acumuladores para el cálculo de KPIs (no se exponen al bus tal
        # cual — alimentan motor.kpis para producir el KPISet de cada tick)
        self._acumuladores: dict = {}

        # Cambios pendientes del tick en curso — se vacían en _emitir_delta()
        # al empaquetarlos en el TickDelta. El bus espera deltas reales
        # (solo lo que cambió), no el estado completo — ver TickDelta en
        # bus_persistencia/models/state.py.
        self._grilla_delta: list[Caja] = []
        self._grilla_remove: list[tuple[int, int, int]] = []
        self._robots_delta: list[Robot] = []
        self._pedidos_completados_add: list[Pedido] = []
        self._eventos_pendientes: list[dict] = []
        self._modo_pendiente: ModoTurno | None = None

    # ------------------------------------------------------------------
    # Inicialización — separada de __init__ porque depende de que M1 ya
    # haya configurado el bus (set_config / set_pedidos_cola) antes de Play
    # ------------------------------------------------------------------

    def inicializar_desde_bus(self):
        """Lee el snapshot inicial del bus (config, modo, política, cola de
        pedidos) y construye la grilla 3D y los robots según `config.grilla`
        y `config.robots`. A partir de aquí el motor mantiene su propio
        espejo del estado y reporta cambios vía TickDelta — la política
        (`PoliticaPicking`) la sigue controlando M1 vía `bus.set_policy`,
        el motor solo la lee de `read_snapshot().politica` cada tick.
        Delega la construcción en motor.grilla."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Ciclo de simulación
    # ------------------------------------------------------------------

    def avanzar_tick(self):
        """Ejecuta un paso completo de simulación:
        1. Lee snapshot (política activa, pedidos, modo) — el motor nunca
           asume su copia local de `politica` está al día, siempre relee.
        2. Procesa el turno activo (diurno o nocturno).
        3. Resuelve colisiones (cesión de paso → acumula tiempo para TBR).
        4. Recalcula KPIs.
        5. Empaqueta y emite el TickDelta (único punto de escritura).
        6. Sincroniza `self.tick` con el valor que retorna el bus."""
        snap = self.bus.read_snapshot()
        politica_activa = snap.politica

        if self.modo == ModoTurno.DIURNO:
            self._procesar_turno_diurno(politica_activa)
        else:
            self._procesar_turno_nocturno()

        self._resolver_colisiones()
        self._actualizar_kpis()

        delta = self._construir_delta()
        self.tick = self.bus.write_tick_delta(M2_WRITER_ID, delta)

    def cambiar_modo(self, nuevo_modo: ModoTurno):
        """Marca un cambio de turno para incluir en el próximo TickDelta
        (campo `modo`). A diferencia de la política — que es decisión del
        operador y la fija M1 vía `bus.set_modo` antes de iniciar — el
        cambio diurno/nocturno lo decide el propio motor según la duración
        de cada fase, por eso viaja dentro del delta que M2 escribe."""
        self._modo_pendiente = nuevo_modo
        self.modo = nuevo_modo

    def ha_terminado(self) -> bool:
        """Condición de término de la sesión: cola de pedidos vacía y
        completados, o se alcanzó la duración de sesión configurada."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Procesamiento por turno — delegan en motor.despachador / motor.modos.
    # Reciben la política activa porque M2 NO la decide ni la cambia, solo
    # la aplica (la fija el operador vía M1 → bus.set_policy).
    # ------------------------------------------------------------------

    def _procesar_turno_diurno(self, politica: PoliticaPicking):
        """Turno diurno: el despachador revisa `pedidos_cola` y robots en
        `RobotEstado.INACTIVO`, aplica la política activa (FIFO o
        PRIORIDAD_POSICION/Manhattan) y asigna rutas; cada robot avanza un
        paso de su ruta (desplazarse, excavar, recuperar, entregar).

        Al completar un pedido: moverlo de `pedidos_cola` a
        `pedidos_completados` y acumularlo en `_pedidos_completados_add`
        (recordar que `Pedido` ya no trae campo `estado` — el bus rastrea
        pendientes vs. completados como colecciones separadas, no por
        estado del objeto). Cada cambio de Caja debe registrarse en
        `_grilla_delta` / `_grilla_remove` (el bus mergea por celda
        `(x,y,z)`), y cada evento relevante (`movimiento`, `excavacion`,
        `caja_recuperada`, `pedido_completado`) en `_eventos_pendientes`.

        OJO con `_robots_delta`: a diferencia de `_grilla_delta` (que el bus
        mergea celda por celda), `StateBus._apply_delta` REEMPLAZA la lista
        completa de robots (`self._robots = list(delta.robots_delta)`). Hay
        que volcar ahí el estado de TODOS los robots cada tick — no solo los
        que se movieron — o el snapshot pierde a los que no se incluyan
        (ver punto 5 en docs/guia_integracion_m2_bus.md, a confirmar con
        Martín por si el comportamiento esperado era un merge por `id`).

        Delega en motor.despachador."""
        raise NotImplementedError

    def _procesar_turno_nocturno(self):
        """Turno nocturno: los robots toman cajas desde `puertos` y las
        ubican en celdas libres siguiendo el orden de `cola_reposicion`
        (sin lógica inteligente de reordenamiento — fuera de alcance).
        Igual que en diurno: registrar cambios en `_grilla_delta` /
        `_robots_delta` y eventos en `_eventos_pendientes`.
        Delega en motor.modos."""
        raise NotImplementedError

    def _resolver_colisiones(self):
        """Aplica cesión de paso: un robot espera 1 tick si la celda
        destino está ocupada (su estado pasa a `RobotEstado.BLOQUEADO`).
        Ese tiempo de espera alimenta el cálculo de TBR y debe registrarse
        como evento `bloqueo` en `_eventos_pendientes`."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # KPIs — delega en motor.kpis
    # ------------------------------------------------------------------

    def _actualizar_kpis(self):
        """Recalcula los 7 KPIs (TSP, TPCP, MTRP, IOG, TR, TI, TBR) a
        partir del estado actual y los acumuladores internos, y guarda el
        resultado como `KPISet` en `self.kpis` (no como dict — el contrato
        del bus exige el tipo `KPISet`). Delega las fórmulas en motor.kpis.
        Conviene también encolar un evento `kpi_update` en
        `_eventos_pendientes` (vocabulario de eventos definido por Martín
        en docs/bus_api.md)."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Comunicación con el bus — único punto de escritura
    # ------------------------------------------------------------------

    def _construir_delta(self) -> TickDelta:
        """Empaqueta los cambios acumulados durante el tick en un
        `TickDelta` y vacía los buffers internos. A diferencia de lo que
        planteamos en una primera versión de este esqueleto, el bus de
        Martín espera DELTAS REALES — listas de lo que cambió
        (`grilla_delta`, `grilla_remove`, `robots_delta`,
        `pedidos_completados_add`), no el estado completo en cada tick
        (sus tests miden latencia de escritura P99 < 1ms, así que el
        tamaño del delta importa).

        El campo `modo` solo se incluye si hubo transición de turno este
        tick (`_modo_pendiente`); `politica` NO es parte del TickDelta —
        esa la fija el operador vía M1, M2 nunca la escribe.

        El volcado a `sesion_X.csv` y `metadata_*.json` lo maneja el bus +
        SessionLogger automáticamente a partir de `eventos` — el motor NO
        necesita (ni debe) escribir esos archivos directamente."""
        delta = TickDelta(
            grilla_delta=self._grilla_delta or None,
            grilla_remove=self._grilla_remove or None,
            robots_delta=self._robots_delta or None,
            pedidos_cola=list(self.pedidos_cola),
            pedidos_completados_add=self._pedidos_completados_add or None,
            kpis=self.kpis,
            modo=self._modo_pendiente,
            eventos=list(self._eventos_pendientes),
        )

        self._grilla_delta = []
        self._grilla_remove = []
        self._robots_delta = []
        self._pedidos_completados_add = []
        self._eventos_pendientes = []
        self._modo_pendiente = None

        return delta
