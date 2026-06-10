# tests/test_api_bridge.py
#
# Tests del bridge FastAPI (T-45) que conecta el StateBus de M2 con M1.
# Ejecutar con: pytest tests/test_api_bridge.py -v
# (ruta explícita — pytest.ini fija testpaths = bus_persistencia/tests)

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from api.server import app, bus, loop

OLA_VALIDA = b"id_pedido,id_sku,cantidad,destino\nP001,SKU-A,2,Tienda_01\n"
OLA_INVALIDA = b"id_pedido,id_sku,cantidad\nP001,SKU-A,2\n"

CONFIG_BODY = {
    "x": 3,
    "y": 3,
    "z": 2,
    "num_robots": 1,
    "occupancy_pct": 30,
    "mode": "DIURNO",
    "policy": "FIFO",
    "semilla": 42,
}


def test_snapshot_inicial_sin_config():
    with TestClient(app) as client:
        loop.reset()
        resp = client.get("/snapshot")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "tick"
        assert body["tick"] == 0
        assert body["grid"] is None
        assert set(body["kpis"]) >= {"tsp", "tpcp", "mtrp", "iog", "tr", "ti", "tbr"}


def test_config_play_pause_avanza_ticks():
    with TestClient(app) as client:
        # Cargar pedidos antes de /config para que inicializar_desde_bus() los lea
        upload = client.post(
            "/api/upload/ola", files={"file": ("ola.csv", io.BytesIO(OLA_VALIDA), "text/csv")}
        )
        assert upload.json()["valid"] is True

        cfg = client.post("/config", json=CONFIG_BODY)
        assert cfg.status_code == 200

        snap = client.get("/snapshot").json()
        assert snap["grid"] == {"x": 3, "y": 3, "z": 2}
        assert snap["status"] == "IDLE"

        client.post("/control/speed", json={"velocidad": 5})
        play = client.post("/control/play")
        assert play.json()["status"] == "RUNNING"

        import time

        time.sleep(0.6)

        client.post("/control/pause")
        snap2 = client.get("/snapshot").json()
        assert snap2["tick"] > 0


def test_policy_endpoint():
    with TestClient(app) as client:
        resp = client.post("/policy", json={"policy": "PRIORIDAD_POSICION"})
        assert resp.status_code == 200

        snap = client.get("/snapshot").json()
        assert snap["policy"] == "PRIORIDAD_POSICION"

        bad = client.post("/policy", json={"policy": "no_existe"})
        assert bad.status_code == 400


def test_websocket_recibe_tick():
    with TestClient(app) as client:
        upload = client.post(
            "/api/upload/ola", files={"file": ("ola.csv", io.BytesIO(OLA_VALIDA), "text/csv")}
        )
        assert upload.json()["valid"] is True

        client.post("/config", json=CONFIG_BODY)
        client.post("/control/speed", json={"velocidad": 5})
        client.post("/control/play")

        with client.websocket_connect("/ws/state") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "tick"
            assert "tsp" in msg["kpis"]
            assert "completados" in msg["kpis"]

            msg2 = ws.receive_json()
            assert msg2["type"] == "tick"

        client.post("/control/pause")


def test_upload_ola_invalida_retorna_errores():
    with TestClient(app) as client:
        resp = client.post(
            "/api/upload/ola", files={"file": ("ola.csv", io.BytesIO(OLA_INVALIDA), "text/csv")}
        )
        body = resp.json()
        assert body["valid"] is False
        assert len(body["errors"]) > 0
        err = body["errors"][0]
        assert set(err) == {"row", "column", "value", "reason"}


def test_control_reset_vuelve_al_tick_inicial():
    with TestClient(app) as client:
        client.post(
            "/api/upload/ola", files={"file": ("ola.csv", io.BytesIO(OLA_VALIDA), "text/csv")}
        )
        client.post("/config", json=CONFIG_BODY)
        tick_inicial = bus.read_snapshot().tick

        client.post("/control/speed", json={"velocidad": 5})
        client.post("/control/play")

        import time

        time.sleep(0.4)
        client.post("/control/pause")
        assert bus.read_snapshot().tick > tick_inicial

        reset = client.post("/control/reset")
        assert reset.json()["status"] == "IDLE"
        assert bus.read_snapshot().tick == tick_inicial
