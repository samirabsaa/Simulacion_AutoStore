"""motor/run.py — Standalone runner para simulación M2 sin UI ni Omniverse.

Uso:
    python -m motor.run --policy fifo --ticks 100
    python -m motor.run --policy prioridad_posicion --ticks 200 --seed 42
    python -m motor.run --compare  # ejecuta ambas políticas y genera reporte
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bus_persistencia.bus.state_bus import StateBus
from bus_persistencia.models.state import Caja, KPISet, ModoTurno, PoliticaPicking, Robot
from bus_persistencia.persistence.config_loader import load_config
from bus_persistencia.persistence.execution_metadata import (
    MetadataStore,
    create_execution_metadata,
    file_hash,
)
from bus_persistencia.persistence.ola_loader import load_ola
from bus_persistencia.persistence.session_logger import SessionLogger
from motor.simulador import AutoStoreSimulator

# ========== IMPORTS PARA DASHBOARD MEJORADO ==========
try:
    from rich import box
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None

STATE_STYLES = {
    "inactivo": "dim white",
    "desplazandose": "bright_cyan",
    "excavando": "yellow",
    "recuperando": "green",
    "entregando": "magenta",
    "reponiendo": "blue",
    "bloqueado": "bold red",
}

# Constantes ANSI para cuando rich no esté disponible
ANSI_CLEAR = "\x1b[2J\x1b[H"  # Limpia pantalla y mueve cursor arriba
ANSI_BOLD = "\x1b[1m"
ANSI_RESET = "\x1b[0m"
ANSI_CYAN = "\x1b[36m"
ANSI_GREEN = "\x1b[32m"
ANSI_YELLOW = "\x1b[33m"
ANSI_RED = "\x1b[31m"
ANSI_BLUE = "\x1b[34m"
ANSI_MAGENTA = "\x1b[35m"
# ====================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def _asegurar_cajas_para_skus(sim: AutoStoreSimulator) -> None:
    """Garantiza que haya suficientes cajas para satisfacer la demanda de cada SKU.

    Los datos de ola.csv (SKU-A/B/C) no coinciden con los SKUs sintéticos del
    relleno aleatorio (SKU001-010), así que inyectamos cajas para los SKUs
    demandados. Se crea **una caja por pedido** que demande el SKU (descontando
    las que ya existan), de modo que la demanda se pueda satisfacer al 100%.

    Determinismo: se itera en orden ordenado (no sobre un `set`). La
    aleatorización de hash de Python haría que el orden de iteración de un set
    variara entre procesos y rompería la reproducibilidad con semilla fija.
    """
    if not sim.pedidos_cola:
        return

    # Demanda: cuántos pedidos requieren cada SKU
    demanda_por_sku: dict[str, int] = {}
    for p in sim.pedidos_cola:
        demanda_por_sku[p.id_sku] = demanda_por_sku.get(p.id_sku, 0) + 1

    cajas_existentes = list(sim._grilla._celdas.values())
    existentes_por_sku: dict[str, int] = {}
    for c in cajas_existentes:
        existentes_por_sku[c.id_sku] = existentes_por_sku.get(c.id_sku, 0) + 1

    gx = sim._grilla.config.grilla.x
    gy = sim._grilla.config.grilla.y
    gz = sim._grilla.config.grilla.z
    next_id = len(cajas_existentes) + 1

    # Orden ordenado por SKU → colocación reproducible entre corridas
    for sku in sorted(demanda_por_sku):
        faltan = demanda_por_sku[sku] - existentes_por_sku.get(sku, 0)
        for _ in range(max(0, faltan)):
            colocado = False
            for cell_idx in range(gx * gy):
                x = cell_idx % gx
                y = (cell_idx // gx) % gy
                for z in range(gz):
                    if not sim._grilla.ocupada(x, y, z):
                        caja = Caja(
                            id_caja=f"C{next_id:05d}", id_sku=sku,
                            cantidad=1, x=x, y=y, z=z,
                        )
                        sim._grilla.agregar(caja)
                        next_id += 1
                        colocado = True
                        break
                if colocado:
                    break
            if not colocado:
                break

def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


ESTADO_COLOR = {
    "inactivo": ".",
    "desplazandose": ">",
    "excavando": "E",
    "recuperando": "R",
    "bloqueado": "!",
    "entregando": "D",
    "reponiendo": "P",
}


def _vista_matriz_rich(sim: AutoStoreSimulator) -> Group:
    """Renderiza la grilla como matriz 2D usando Rich Tables.

    Retorna un Group: título, grilla, leyenda compacta en una línea.
    """
    g = sim._grilla
    if g is None:
        return Group(Text("(grilla no disponible)"))

    gx, gy, gz = g.config.grilla.x, g.config.grilla.y, g.config.grilla.z
    puertos_set = set(g.puertos)

    robot_en_celda: dict[tuple[int, int], Robot] = {
        (r.x, r.y): r for r in sim.robots.values()
    }

    max_robot_len = max((len(f"R{r.id}") for r in sim.robots.values()), default=2)
    cell_width = max(3, max_robot_len + 1)

    # ── Title panel ──
    title = Panel(
        Text(f"Grid {gx}×{gy}×{gz}  |  {g.total_cajas} cajas  |  {len(sim.robots)} robots", style="bold white"),
        border_style="blue",
    )

    # ── Grid table ──
    grid = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan",
                 padding=(0, 0))
    grid.add_column("x", justify="center", width=cell_width)
    for j in range(gy):
        grid.add_column(f"y{j}", justify="center", width=cell_width)

    for i in range(gx):
        row_cells: list[Text] = [Text(str(i), style="bold white")]
        for j in range(gy):
            rb = robot_en_celda.get((i, j))
            es_puerto = (i, j) in puertos_set
            altura = len(g.columna(i, j))

            if rb is not None:
                style = STATE_STYLES.get(rb.estado.value, "white")
                row_cells.append(Text(f"R{rb.id}", style=style))
            elif es_puerto and altura == 0:
                row_cells.append(Text("P", style="bright_blue"))
            elif altura > 0:
                row_cells.append(Text(str(altura), style="dim white"))
            else:
                row_cells.append(Text("·", style="dim white"))
        grid.add_row(*row_cells)

    # ── Single-line legend ──
    leg = Text("  ")
    leg.append("P", style="bright_blue")
    leg.append("=port  ")
    leg.append("#", style="dim white")
    leg.append("=stack  ")
    leg.append("·", style="dim white")
    leg.append("=empty  |  ", style="dim white")
    for i, (state_val, state_style) in enumerate(STATE_STYLES.items()):
        if i > 0:
            leg.append("  ")
        leg.append(state_val, style=state_style)

    return Group(title, grid, leg)


def _vista_matriz(sim: AutoStoreSimulator) -> str:
    """Renderiza la grilla como matriz 2D (vista superior XY) — versión ANSI/ASCII.

    Usa formato plano sin dependencia de rich. Cada celda (x,y) muestra:
      - R{id} si hay un robot
      - P      si es puerto sin caja
      - {n}    altura de la columna (1-9)
      - ·      celda vacía
    """
    g = sim._grilla
    if g is None:
        return ""

    gx, gy, gz = g.config.grilla.x, g.config.grilla.y, g.config.grilla.z
    puertos_set = set(g.puertos)

    robot_en_celda: dict[tuple[int, int], Robot] = {
        (r.x, r.y): r for r in sim.robots.values()
    }

    lines = []
    lines.append(f"  Grilla {gx}x{gy}x{gz}    Puertos:P   Cajas:#   Robot:R{{id}}  ")
    lines.append("")
    header = "      " + "  ".join(f"y={j:<2}" for j in range(gy))
    lines.append(header)

    for i in range(gx):
        cells = []
        for j in range(gy):
            rb = robot_en_celda.get((i, j))
            es_puerto = (i, j) in puertos_set
            altura = len(g.columna(i, j))

            if rb is not None:
                icono = ESTADO_COLOR.get(rb.estado.value, "?")
                cells.append(f"R{rb.id}{icono}" if rb.id < 10 else f"R{rb.id}")
            elif es_puerto and altura == 0:
                cells.append(" P ")
            elif altura > 0:
                cells.append(f" {min(altura,9)} ")
            else:
                cells.append(" · ")
        row = "  x=" + str(i) + ": " + " ".join(c.ljust(3) for c in cells)
        lines.append(row)

    return "\n".join(lines)


def _crear_dashboard_rich(sim: AutoStoreSimulator, tick: int, max_ticks: int, show_matrix: bool = False) -> str:
    """Crea un dashboard visual con rich. Retorna string para impresión directa."""
    if not RICH_AVAILABLE:
        return ""

    console = Console(file=None, force_terminal=True, width=120)
    renderables: list[object] = []

    k = sim.kpis
    n_comp = sim._acum.pedidos_completados
    n_dem = sim._acum.pedidos_demandados

    # Header
    renderables.append(
        Text(f" ⚙️  AutoStore Simulator  Tick {tick}/{max_ticks} ", style="bold white on blue")
    )

    # KPIs
    kpi_line = (
        f"  Pedidos: {n_comp:>3}/{n_dem:<3}  |  "
        f"TSP: {k.TSP:>6.1f}%  |  "
        f"MTRP: {k.MTRP:>7.1f}  |  "
        f"TBR: {k.TBR:>6.1f}%  |  "
        f"IOG: {k.IOG:>5.1f}%"
    )
    renderables.append(Text(kpi_line))
    renderables.append(Text(""))

    # Robot table
    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("Robot", justify="center", style="bold")
    table.add_column("State")
    table.add_column("Position", justify="center")
    table.add_column("Cargo")

    for robot in sorted(sim.robots.values(), key=lambda r: r.id):
        state_style = STATE_STYLES.get(robot.estado.value, "white")
        state_text = Text(robot.estado.value, style=state_style)
        pos = f"({robot.x:>2},{robot.y:>2},{robot.z})"
        carga = robot.carga_id or "—"
        table.add_row(f"R{robot.id}", state_text, pos, carga)

    renderables.append(table)

    # Matrix view
    if show_matrix:
        renderables.append(Text(""))
        renderables.append(_vista_matriz_rich(sim))

    # Progress bar — always at bottom so it stays visible
    renderables.append(Text(""))
    pct = tick / max_ticks
    ancho = 50
    relleno = int(pct * ancho)
    bar = Text()
    bar.append(f"[{'█' * relleno}{'░' * (ancho - relleno)}] {tick}/{max_ticks}")
    renderables.append(Text("  ") + bar)

    with console.capture() as capture:
        for r in renderables:
            console.print(r)

    return capture.get()


def _crear_dashboard_ansi(sim: AutoStoreSimulator, tick: int, max_ticks: int, show_matrix: bool = False) -> str:
    """Crea un dashboard usando solo ANSI, sin librería rich."""
    k = sim.kpis
    n_comp = sim._acum.pedidos_completados
    n_dem = sim._acum.pedidos_demandados

    output = []

    # Header
    output.append(f"{ANSI_BOLD}{ANSI_CYAN}[AutoStore Simulator] - Tick {tick}/{max_ticks}{ANSI_RESET}")

    # KPIs
    kpi_line = (
        f"  Pedidos: {n_comp:>3}/{n_dem:<3}  |  "
        f"TSP: {k.TSP:>6.1f}%  |  "
        f"MTRP: {k.MTRP:>7.1f}  |  "
        f"TBR: {k.TBR:>6.1f}%  |  "
        f"IOG: {k.IOG:>5.1f}%"
    )
    output.append(f"{ANSI_GREEN}{kpi_line}{ANSI_RESET}")
    output.append("")

    # Tabla de robots (simple)
    output.append(f"{ANSI_BOLD}[Robots]{ANSI_RESET}")
    output.append(f"  {'ID':<8} {'Estado':<15} {'Posición':<15} {'Carga':<15}")
    output.append(f"  {'-'*8} {'-'*15} {'-'*15} {'-'*15}")

    for robot in sorted(sim.robots.values(), key=lambda r: r.id):
        icono = ESTADO_COLOR.get(robot.estado.value, "?")
        carga = robot.carga_id or "—"
        estado = robot.estado.value
        pos = f"({robot.x:>2},{robot.y:>2},{robot.z})"
        output.append(
            f"  [{icono}] R{robot.id:<5} {estado:<15} {pos:<15} {carga:<15}"
        )

    output.append("")

    if show_matrix:
        output.append(_vista_matriz(sim))

    # Progress bar — siempre al final para que quede visible
    ancho = 50
    relleno = int((tick / max_ticks) * ancho)
    barra = f"[{'#' * relleno}{'.' * (ancho - relleno)}] {tick}/{max_ticks}"
    output.append(f"  {barra}")

    return "\n".join(output)


def _mostrar_tick_realtime(
    sim: AutoStoreSimulator,
    tick: int,
    max_ticks: int,
    use_rich: bool = True,
    use_ansi_clear: bool = True,
    show_matrix: bool = False,
) -> None:
    """Muestra el estado actualizado cada tick sin scroll."""
    out = sys.stdout.buffer

    if use_ansi_clear:
        out.write(ANSI_CLEAR.encode("utf-8"))

    if use_rich and RICH_AVAILABLE:
        dashboard = _crear_dashboard_rich(sim, tick, max_ticks, show_matrix=show_matrix)
    else:
        dashboard = _crear_dashboard_ansi(sim, tick, max_ticks, show_matrix=show_matrix)

    out.write((dashboard + "\n").encode("utf-8", errors="replace"))
    out.flush()


def ejecutar_sesion(
    config_path: str | Path,
    ola_path: str | Path,
    politica: PoliticaPicking,
    output_dir: str | Path = OUTPUT_DIR,
    session_name: str | None = None,
    seed: int = 42,
    max_ticks: int = 100,
    verbose: bool = True,
    realtime: bool = False,
    delay_ms: float = 0,
    use_rich: bool = True,
    use_ansi_clear: bool = True,
    show_matrix: bool = False,
) -> dict:
    """Ejecuta una sesión de simulación completa y retorna resultados."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if session_name is None:
        session_name = f"{politica.value}_s{seed}"

    # --- Cargar datos ---
    config_result = load_config(config_path)
    if not config_result.is_valid:
        raise SystemExit(f"Error en config: {config_result.errors}")
    ola_result = load_ola(ola_path)
    if not ola_result.is_valid:
        raise SystemExit(f"Error en ola: {ola_result.errors}")

    # --- Configurar bus ---
    logger = SessionLogger(output_dir=output, session_name=session_name)
    bus = StateBus(session_logger=logger)
    bus.set_config(config_result.data)
    bus.set_pedidos_cola(ola_result.data)
    bus.set_policy(politica)

    # --- Configurar metadata ---
    meta = create_execution_metadata(
        session_name, seed, "diurno", politica.value,
        config_path, ola_path,
    )

    # --- Inicializar simulador ---
    sim = AutoStoreSimulator(bus)
    sim.inicializar_desde_bus(seed=seed)

    # --- Asegurar cajas para los SKUs de pedidos ---
    _asegurar_cajas_para_skus(sim)

    logger.write_metadata_header(meta.to_dict())

    if verbose:
        n_robots = len(sim.robots)
        n_pedidos = len(sim.pedidos_cola)
        print(f"  Grilla: {sim._grilla.config.grilla.x}×{sim._grilla.config.grilla.y}×{sim._grilla.config.grilla.z}")
        print(f"  Cajas iniciales: {sim._grilla.total_cajas}")
        print(f"  Robots: {n_robots}")
        print(f"  Pedidos: {n_pedidos}")
        print(f"  Política: {politica.value}")
        print(f"  Semilla: {seed}")
        print()

    # --- Ciclo de simulación ---
    t_start = time.perf_counter()
    if realtime:
        if RICH_AVAILABLE and use_rich:
            print("  [EN VIVO] Modo Rich (^C para detener)")
        else:
            print("  [EN VIVO] Modo ANSI (^C para detener)")
        if delay_ms > 0:
            print(f"  Delay: {delay_ms:.0f}ms entre ticks")
        print()
        time.sleep(0.5)

    for t in range(1, max_ticks + 1):
        sim.avanzar_tick()

        if realtime:
            _mostrar_tick_realtime(
                sim, t, max_ticks,
                use_rich=use_rich,
                use_ansi_clear=use_ansi_clear,
                show_matrix=show_matrix,
            )
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)
        elif verbose and t % 10 == 0:
            k = sim.kpis
            print(f"  Tick {t:>4} | TSP={k.TSP:6.2f}%  MTRP={k.MTRP:7.2f}  TBR={k.TBR:6.2f}%  IOG={k.IOG:5.1f}%")

        if sim.ha_terminado():
            if verbose:
                print(f"  [+] Sesión completada en {t} ticks")
            break

    elapsed = time.perf_counter() - t_start

    # --- Finalizar ---
    logger.flush_session()

    snap = bus.read_snapshot()
    meta.kpis_finales = snap.kpis.as_dict()
    MetadataStore(output / "metadata").save(meta)

    resultado = {
        "session_name": session_name,
        "tick_final": snap.tick,
        "pedidos_completados": len(snap.pedidos.completados),
        "pedidos_totales": len(snap.pedidos.cola) + len(snap.pedidos.completados),
        "KPIs": snap.kpis.as_dict(),
        "politica": politica.value,
        "seed": seed,
        "tiempo_seg": elapsed,
        "output_dir": str(output),
    }

    if verbose:
        print()
        print("  -------- RESULTADOS --------")
        print(f"  Ticks:        {resultado['tick_final']}")
        print(f"  Pedidos:      {resultado['pedidos_completados']}/{resultado['pedidos_totales']}")
        print(f"  Tiempo:       {elapsed:.2f}s")
        print()
        print(f"  {'KPI':<8} {'Valor':<12}")
        print(f"  {'--------':<8} {'------------':<12}")
        for k, v in snap.kpis.as_dict().items():
            print(f"  {k:<8} {v:<12.2f}")
        print()
        print(f"  Salida: {output / f'sesion_{session_name}.csv'}")

    return resultado


def generar_reporte_comparativo(
    resultado_a: dict,
    resultado_b: dict,
    output_dir: str | Path = OUTPUT_DIR,
) -> Path:
    """Genera reporte_comp.csv comparando dos ejecuciones."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "reporte_comp.csv"

    kpis_a = resultado_a["KPIs"]
    kpis_b = resultado_b["KPIs"]
    nombre_a = f"{resultado_a['politica']}_s{resultado_a['seed']}"
    nombre_b = f"{resultado_b['politica']}_s{resultado_b['seed']}"

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["KPI", "FIFO_75", "Prioridad_90", "Delta_%"])
        for kpi_name in ("TSP", "TPCP", "MTRP", "IOG", "TR", "TI", "TBR"):
            va = kpis_a.get(kpi_name, 0.0)
            vb = kpis_b.get(kpi_name, 0.0)
            delta = ((vb - va) / va * 100) if va != 0 else 0.0
            sign = "+" if delta >= 0 else ""
            w.writerow([kpi_name, f"{va:.2f}", f"{vb:.2f}", f"{sign}{delta:.2f}%"])

    print(f"  Reporte: {path}")
    return path


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AutoStore Simulator — Motor M2 (standalone, sin UI ni Omniverse)",
    )
    p.add_argument("--config", default=str(DATA_DIR / "config.json"),
                    help="Ruta a config.json")
    p.add_argument("--ola", default=str(DATA_DIR / "ola.csv"),
                    help="Ruta a ola.csv")
    p.add_argument("--output", default=str(OUTPUT_DIR),
                    help="Directorio de salida")
    p.add_argument("--ticks", type=int, default=100,
                    help="Máximo de ticks a simular")
    p.add_argument("--seed", type=int, default=42,
                    help="Semilla para reproducibilidad")
    p.add_argument("--policy", default="fifo",
                    choices=["fifo", "prioridad_posicion"],
                    help="Política de picking")
    p.add_argument("--compare", action="store_true",
                    help="Ejecuta ambas políticas y genera reporte comparativo")
    p.add_argument("--quiet", action="store_true",
                    help="Modo silencioso (solo muestra resultado final)")
    p.add_argument("--realtime", "-r", action="store_true",
                    help="Modo en vivo: muestra cada tick con estado de robots")
    p.add_argument("--delay", type=float, default=0,
                    help="Milisegundos de espera entre ticks en modo realtime (default: 0)")
    p.add_argument("--no-rich", action="store_true",
                    help="Usa ANSI puro en lugar de rich (más ligero)")
    p.add_argument("--no-clear", action="store_true",
                    help="No limpia la pantalla entre ticks (DEBUG)")
    p.add_argument("--matrix", action="store_true",
                    help="Incluye vista de matriz 2D de la grilla en tiempo real")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # realtime implica verbose, ignorar --quiet
    if args.realtime:
        args.quiet = False

    use_rich = not args.no_rich and RICH_AVAILABLE
    use_ansi_clear = not args.no_clear
    show_matrix = args.matrix

    if args.compare:
        print("=== Ejecutando Demo FIFO (75%) ===")
        print()
        res_a = ejecutar_sesion(
            args.config, args.ola,
            PoliticaPicking.FIFO,
            output_dir=args.output,
            session_name="fifo_s75",
            seed=args.seed,
            max_ticks=args.ticks,
            verbose=not args.quiet,
            realtime=args.realtime,
            delay_ms=args.delay,
            use_rich=use_rich,
            use_ansi_clear=use_ansi_clear,
            show_matrix=show_matrix,
        )
        print()
        print("=== Ejecutando Demo Prioridad (90%) ===")
        print()
        res_b = ejecutar_sesion(
            args.config, args.ola,
            PoliticaPicking.PRIORIDAD_POSICION,
            output_dir=args.output,
            session_name="prioridad_s90",
            seed=args.seed,
            max_ticks=args.ticks,
            verbose=not args.quiet,
            realtime=args.realtime,
            delay_ms=args.delay,
            use_rich=use_rich,
            use_ansi_clear=use_ansi_clear,
            show_matrix=show_matrix,
        )
        print()
        print("=== Generando reporte comparativo ===")
        generar_reporte_comparativo(res_a, res_b, args.output)
        print()
        print("  Demo completada. Revisar output/ para resultados.")
    else:
        politica = PoliticaPicking.FIFO if args.policy == "fifo" else PoliticaPicking.PRIORIDAD_POSICION
        ejecutar_sesion(
            args.config, args.ola,
            politica,
            output_dir=args.output,
            session_name=f"{args.policy}_s{args.seed}",
            seed=args.seed,
            max_ticks=args.ticks,
            verbose=not args.quiet,
            realtime=args.realtime,
            delay_ms=args.delay,
            use_rich=use_rich,
            use_ansi_clear=use_ansi_clear,
            show_matrix=show_matrix,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
