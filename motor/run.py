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
from bus_persistencia.models.state import Caja, KPISet, ModoTurno, PoliticaPicking
from bus_persistencia.persistence.config_loader import load_config
from bus_persistencia.persistence.execution_metadata import (
    MetadataStore,
    create_execution_metadata,
    file_hash,
)
from bus_persistencia.persistence.ola_loader import load_ola
from bus_persistencia.persistence.session_logger import SessionLogger
from motor.simulador import AutoStoreSimulator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def _asegurar_cajas_para_skus(sim: AutoStoreSimulator) -> None:
    """Verifica que todos los SKUs de los pedidos tengan al menos una caja
    en la grilla. Si falta alguno, agrega una caja sintética."""
    skus_en_cola = {p.id_sku for p in sim.pedidos_cola}
    if not skus_en_cola:
        return

    cajas_existentes = list(sim._grilla._celdas.values())
    skus_en_grilla = {c.id_sku for c in cajas_existentes}
    skus_faltantes = skus_en_cola - skus_en_grilla

    if not skus_faltantes:
        return

    gx = sim._grilla.config.grilla.x
    gy = sim._grilla.config.grilla.y
    next_id = len(cajas_existentes) + 1
    idx = 0

    for sku in skus_faltantes:
        x = idx % gx
        y = (idx // gx) % gy
        z = 0
        while sim._grilla.ocupada(x, y, z):
            z += 1
            if z >= sim._grilla.config.grilla.z:
                idx += 1
                x = idx % gx
                y = (idx // gx) % gy
                z = 0
        caja = Caja(id_caja=f"C{next_id:05d}", id_sku=sku, cantidad=1, x=x, y=y, z=z)
        sim._grilla.agregar(caja)
        next_id += 1
        idx += 1


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


def _mostrar_tick_realtime(sim: AutoStoreSimulator, tick: int, max_ticks: int) -> None:
    """Muestra el estado de todos los robots en una linea por tick."""
    k = sim.kpis
    n_comp = sim._acum.pedidos_completados
    n_dem = sim._acum.pedidos_demandados
    print(f"Tick {tick:>4}/{max_ticks}  Pedidos: {n_comp}/{n_dem}  "
          f"TSP={k.TSP:5.1f}%  MTRP={k.MTRP:6.1f}  TBR={k.TBR:5.1f}%  "
          f"IOG={k.IOG:4.1f}%")
    for robot in sorted(sim.robots.values(), key=lambda r: r.id):
        icono = ESTADO_COLOR.get(robot.estado.value, "?")
        carga = robot.carga_id or "-"
        estado = robot.estado.value[:8]
        print(f"  [{icono}] R{robot.id}  ({robot.x:>2},{robot.y:>2},z={robot.z})  "
              f"{estado:<10}  carga={carga}")


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
        print(f"  Modo REAL-TIME (delay={delay_ms:.0f}ms, ^C para detener)")
        print(f"  Iconos: [>] mov  [E] excav  [R] recup  [D] entre  [!] bloq  [.] inac  [P] repon")
        print()

    for t in range(1, max_ticks + 1):
        sim.avanzar_tick()

        if realtime:
            _mostrar_tick_realtime(sim, t, max_ticks)
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
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # realtime implica verbose, ignorar --quiet
    if args.realtime:
        args.quiet = False

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
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
