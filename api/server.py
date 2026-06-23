"""api/server.py — bridge FastAPI entre el StateBus de M2 y el frontend M1 (T-45).

Contrato acordado con Alonso (M1):
  - FastAPI en :8000, Ionic dev server en :8100 (CORS habilitado para ese origen).
  - WebSocket `ws://localhost:8000/ws/state` empuja `{type: "tick", ...}` por tick.
  - `kpis` con claves en minúscula + `completados`, `capacidad`, `cajasPresentes`.
  - `POST /api/upload/{ola|reposicion}` valida CSV y retorna
    `{valid, errors: [{row, column, value, reason}]}`.

Ejecutar con: `uvicorn api.server:app --reload --port 8000`
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from bus_persistencia.bus.state_bus import StateBus
from bus_persistencia.models.state import Config, GrillaDimensions
from bus_persistencia.persistence.ola_loader import load_ola
from bus_persistencia.persistence.reposicion_loader import load_reposicion
from bus_persistencia.persistence.report_generator import generate_report
from bus_persistencia.persistence.validation import ValidationResult

from api.loop_worker import SimulationLoop
from api.serializers import MODO_FROM_M1, politica_from_m1, snapshot_to_payload

bus = StateBus()
_websockets: set[WebSocket] = set()
_main_loop: asyncio.AbstractEventLoop | None = None
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _broadcast() -> None:
    """Notifica a los websockets conectados. Se llama desde el hilo de simulación."""
    if _main_loop is None or not _websockets:
        return
    payload = snapshot_to_payload(bus.read_snapshot(), loop.status, loop.velocidad)
    for ws in list(_websockets):
        asyncio.run_coroutine_threadsafe(_send_safe(ws, payload), _main_loop)


async def _send_safe(ws: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await ws.send_json(payload)
    except Exception:
        _websockets.discard(ws)


loop = SimulationLoop(bus, on_tick=_broadcast, output_dir=OUTPUT_DIR)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    import logging
    from motor.plugin_loader import load_plugins
    loaded = load_plugins()
    if loaded:
        logging.getLogger(__name__).info("Plugins cargados: %s", loaded)
    yield


app = FastAPI(title="AutoStore Simulator Bridge", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8100"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GridConfigDTO(BaseModel):
    """Espejo de `GridConfigDTO` en `m1/src/app/core/models/grid-config.model.ts`."""

    x: int
    y: int
    z: int
    num_robots: int
    occupancy_pct: float
    mode: str
    policy: str
    session_name: str | None = None
    semilla: int | None = None
    pedidos_demandados: int | None = None
    # Robots 1×2 con orientación fija: conteos por orientación (configurable).
    robots_norte: int | None = None
    robots_este: int | None = None
    robots_oeste: int | None = None


class PolicyDTO(BaseModel):
    policy: str


class VelocidadDTO(BaseModel):
    velocidad: int


def _validation_to_dto(result: ValidationResult[Any]) -> dict[str, Any]:
    return {
        "valid": result.is_valid,
        "errors": [
            {"row": e.fila, "column": e.columna, "value": "", "reason": e.error}
            for e in result.errors
        ],
    }


@app.get("/snapshot")
def get_snapshot() -> dict[str, Any]:
    return snapshot_to_payload(bus.read_snapshot(), loop.status, loop.velocidad)


@app.post("/config")
def post_config(cfg: GridConfigDTO) -> dict[str, Any]:
    config = Config(
        grilla=GrillaDimensions(x=cfg.x, y=cfg.y, z=cfg.z),
        robots=cfg.num_robots,
        ocupacion_inicial=cfg.occupancy_pct,
        robots_norte=cfg.robots_norte or 0,
        robots_este=cfg.robots_este or 0,
        robots_oeste=cfg.robots_oeste or 0,
    )
    modo = MODO_FROM_M1.get(cfg.mode.upper())
    politica = politica_from_m1(cfg.policy)
    loop.configurar(config, seed=cfg.semilla, modo=modo, politica=politica,
                    pedidos_demandados=cfg.pedidos_demandados,
                    session_name=cfg.session_name)
    return {"ok": True}


@app.post("/policy")
def post_policy(body: PolicyDTO) -> dict[str, Any]:
    politica = politica_from_m1(body.policy)
    if politica is None:
        raise HTTPException(status_code=400, detail=f"Política desconocida: {body.policy!r}")
    loop.set_politica(politica)
    return {"ok": True}


@app.get("/policies")
def get_policies() -> dict[str, Any]:
    from motor.politicas import list_politicas
    return {"policies": list_politicas()}


@app.post("/control/play")
def control_play() -> dict[str, Any]:
    try:
        loop.play()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "status": loop.status}


@app.post("/control/pause")
def control_pause() -> dict[str, Any]:
    loop.pause()
    return {"ok": True, "status": loop.status}


@app.post("/control/reset")
def control_reset() -> dict[str, Any]:
    loop.reset()
    return {"ok": True, "status": loop.status}


@app.post("/control/speed")
def control_speed(body: VelocidadDTO) -> dict[str, Any]:
    loop.set_velocidad(body.velocidad)
    return {"ok": True, "velocidad": loop.velocidad}


@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    await websocket.accept()
    _websockets.add(websocket)
    try:
        await websocket.send_json(snapshot_to_payload(bus.read_snapshot(), loop.status, loop.velocidad))
        while True:
            # Mantiene la conexión viva; M1 no necesita enviar nada por este canal.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _websockets.discard(websocket)


PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins" / "politicas"


@app.post("/api/upload/policy")
async def upload_policy(file: UploadFile) -> dict[str, Any]:
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un .py")
    contents = await file.read()
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PLUGINS_DIR / file.filename
    dest.write_bytes(contents)
    from motor.plugin_loader import validate_and_load_file
    name, error = validate_and_load_file(dest)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"ok": True, "policy_name": name}


@app.post("/api/upload/ola")
async def upload_ola(file: UploadFile) -> dict[str, Any]:
    contents = await file.read()
    fd, tmp_str = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    tmp_path = Path(tmp_str)
    tmp_path.write_bytes(contents)
    try:
        result = load_ola(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    if result.is_valid:
        bus.set_pedidos_cola(result.data)
    return _validation_to_dto(result)


@app.post("/api/upload/reposicion")
async def upload_reposicion(file: UploadFile) -> dict[str, Any]:
    contents = await file.read()
    fd, tmp_str = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    tmp_path = Path(tmp_str)
    tmp_path.write_bytes(contents)
    try:
        result = load_reposicion(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    if result.is_valid:
        loop.set_cola_reposicion(result.data)
    return _validation_to_dto(result)


@app.post("/demo/load-ola")
def demo_load_ola(name: str) -> dict[str, Any]:
    """Carga una ola de demostración desde data/ola_{name}.csv al bus."""
    ola_path = DATA_DIR / f"ola_{name}.csv"
    if not ola_path.exists():
        raise HTTPException(status_code=404, detail=f"Demo file not found: ola_{name}.csv")
    result = load_ola(ola_path)
    if result.is_valid:
        bus.set_pedidos_cola(result.data)
    return _validation_to_dto(result)


@app.get("/report/comparativo")
def get_report_comparativo():
    """Genera y descarga reporte_comp.csv comparando las DOS últimas ejecuciones
    terminadas (KPI | Ejecución A | Ejecución B | Δ%)."""
    if len(loop.finished_runs) < 2:
        raise HTTPException(
            409,
            "Se requieren 2 ejecuciones terminadas para el reporte comparativo. "
            f"Hay {len(loop.finished_runs)}. Corre dos simulaciones completas.",
        )
    (nombre_a, kpis_a), (nombre_b, kpis_b) = loop.finished_runs[-2], loop.finished_runs[-1]
    # Desambiguar si ambas corridas tienen el mismo nombre de ejecución.
    if nombre_a == nombre_b:
        nombre_a, nombre_b = f"{nombre_a}_A", f"{nombre_b}_B"
    path = OUTPUT_DIR / "reporte_comp.csv"
    generate_report(nombre_a, nombre_b, path, kpis_a=kpis_a, kpis_b=kpis_b)
    return FileResponse(
        path,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reporte_comp.csv"},
    )


@app.get("/report/sesion")
def get_report_sesion():
    csvs = sorted(OUTPUT_DIR.glob("sesion_*.csv"), reverse=True)
    if not csvs:
        raise HTTPException(404, "No hay sesión guardada aún")
    path = csvs[0]
    return FileResponse(
        path,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={path.name}"},
    )
