"""motor/dashboard.py — Renderizado de dashboard en tiempo real (Rich y ANSI)."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from motor.simulador import AutoStoreSimulator

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
    Console = None  # type: ignore[assignment,misc]

from bus_persistencia.models.state import Robot

STATE_STYLES = {
    "inactivo": "dim white",
    "desplazandose": "bright_cyan",
    "excavando": "yellow",
    "recuperando": "green",
    "entregando": "magenta",
    "reponiendo": "blue",
    "bloqueado": "bold red",
}

ANSI_CLEAR = "\x1b[2J\x1b[H"
ANSI_BOLD = "\x1b[1m"
ANSI_RESET = "\x1b[0m"
ANSI_CYAN = "\x1b[36m"
ANSI_GREEN = "\x1b[32m"
ANSI_YELLOW = "\x1b[33m"
ANSI_RED = "\x1b[31m"
ANSI_BLUE = "\x1b[34m"
ANSI_MAGENTA = "\x1b[35m"

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
    """Renderiza la grilla como matriz 2D usando Rich Tables."""
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

    title = Panel(
        Text(f"Grid {gx}×{gy}×{gz}  |  {g.total_cajas} cajas  |  {len(sim.robots)} robots", style="bold white"),
        border_style="blue",
    )

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
    """Renderiza la grilla como matriz 2D (vista superior XY) — versión ANSI/ASCII."""
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


def crear_dashboard_rich(sim: AutoStoreSimulator, tick: int, max_ticks: int, show_matrix: bool = False) -> str:
    """Crea un dashboard visual con rich. Retorna string para impresión directa."""
    if not RICH_AVAILABLE:
        return ""

    console = Console(file=None, force_terminal=True, width=120)
    renderables: list[object] = []

    k = sim.kpis
    n_comp = sim._acum.pedidos_completados
    n_dem = sim._acum.pedidos_demandados

    renderables.append(
        Text(f" ⚙️  AutoStore Simulator  Tick {tick}/{max_ticks} ", style="bold white on blue")
    )

    kpi_line = (
        f"  Pedidos: {n_comp:>3}/{n_dem:<3}  |  "
        f"TSP: {k.TSP:>6.1f}%  |  "
        f"MTRP: {k.MTRP:>7.1f}  |  "
        f"TBR: {k.TBR:>6.1f}%  |  "
        f"IOG: {k.IOG:>5.1f}%"
    )
    renderables.append(Text(kpi_line))
    renderables.append(Text(""))

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

    if show_matrix:
        renderables.append(Text(""))
        renderables.append(_vista_matriz_rich(sim))

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


def crear_dashboard_ansi(sim: AutoStoreSimulator, tick: int, max_ticks: int, show_matrix: bool = False) -> str:
    """Crea un dashboard usando solo ANSI, sin librería rich."""
    k = sim.kpis
    n_comp = sim._acum.pedidos_completados
    n_dem = sim._acum.pedidos_demandados

    output = []

    output.append(f"{ANSI_BOLD}{ANSI_CYAN}[AutoStore Simulator] - Tick {tick}/{max_ticks}{ANSI_RESET}")

    kpi_line = (
        f"  Pedidos: {n_comp:>3}/{n_dem:<3}  |  "
        f"TSP: {k.TSP:>6.1f}%  |  "
        f"MTRP: {k.MTRP:>7.1f}  |  "
        f"TBR: {k.TBR:>6.1f}%  |  "
        f"IOG: {k.IOG:>5.1f}%"
    )
    output.append(f"{ANSI_GREEN}{kpi_line}{ANSI_RESET}")
    output.append("")

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

    ancho = 50
    relleno = int((tick / max_ticks) * ancho)
    barra = f"[{'#' * relleno}{'.' * (ancho - relleno)}] {tick}/{max_ticks}"
    output.append(f"  {barra}")

    return "\n".join(output)


def mostrar_tick_realtime(
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
        dashboard = crear_dashboard_rich(sim, tick, max_ticks, show_matrix=show_matrix)
    else:
        dashboard = crear_dashboard_ansi(sim, tick, max_ticks, show_matrix=show_matrix)

    out.write((dashboard + "\n").encode("utf-8", errors="replace"))
    out.flush()
