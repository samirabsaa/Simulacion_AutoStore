"""Escritura diferida de sesion_X.csv con buffer en memoria (T-06)."""

from __future__ import annotations

import csv
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionLogger:
    """Acumula eventos en memoria y escribe a disco al final de cada tick."""

    FIELDNAMES = ("timestamp", "tick", "tipo_evento", "payload_json")

    def __init__(
        self,
        output_path: str | Path | None = None,
        defer_io: bool = True,
        output_dir: str | Path | None = None,
        session_name: str = "default",
    ) -> None:
        if output_path is not None:
            self._output_path = Path(output_path)
        elif output_dir is not None:
            self._output_path = Path(output_dir) / f"sesion_{session_name}.csv"
        else:
            self._output_path = Path("output") / f"sesion_{session_name}.csv"

        self._defer_io = defer_io
        self._buffer: list[dict[str, Any]] = []
        self._pending_flush: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._header_written = False
        self._flush_thread: threading.Thread | None = None

    @property
    def output_path(self) -> Path:
        return self._output_path

    def configure(self, output_dir: str | Path, session_name: str) -> None:
        self._output_path = Path(output_dir) / f"sesion_{session_name}.csv"
        self._header_written = False

    def write_metadata_header(self, metadata: dict[str, Any]) -> None:
        meta_path = self._output_path.with_suffix(".meta.json")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def buffer_event(self, tick: int, evento: dict[str, Any]) -> None:
        record = self._make_record(tick, evento)
        with self._lock:
            self._buffer.append(record)

    def log_event_in_tick(
        self,
        tick: int,
        tipo_evento: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.buffer_event(tick, {"tipo": tipo_evento, **(payload or {})})

    def flush_tick_async(self, tick: int) -> None:
        self._schedule_flush(tick)

    def flush_tick(self, tick: int) -> None:
        self._schedule_flush(tick)

    def _schedule_flush(self, tick: int) -> None:
        with self._lock:
            if not self._buffer:
                return
            self._pending_flush.extend(self._buffer)
            self._buffer.clear()

        if self._defer_io:
            thread = threading.Thread(
                target=self._flush_to_disk,
                args=(tick,),
                daemon=True,
            )
            thread.start()
            self._flush_thread = thread
        else:
            self._flush_to_disk(tick)

    def flush_all(self) -> None:
        self.flush_session()

    def flush_session(self) -> None:
        with self._lock:
            self._pending_flush.extend(self._buffer)
            self._buffer.clear()
        self._flush_to_disk(0)
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5)

    def reset(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._pending_flush.clear()
        self._header_written = False

    def _make_record(self, tick: int, evento: dict[str, Any]) -> dict[str, Any]:
        return {
            "timestamp": evento.get(
                "timestamp",
                datetime.now(timezone.utc).isoformat(),
            ),
            "tick": tick,
            "tipo_evento": evento.get("tipo", "desconocido"),
            "payload_json": json.dumps(
                {k: v for k, v in evento.items() if k not in ("tipo", "timestamp")},
                ensure_ascii=False,
            ),
        }

    def _flush_to_disk(self, tick: int) -> None:
        with self._io_lock:
            with self._lock:
                records = list(self._pending_flush)
                self._pending_flush.clear()

            if not records:
                return

            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            write_header = not self._header_written and not self._output_path.exists()

            with self._output_path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.FIELDNAMES)
                if write_header:
                    writer.writeheader()
                    self._header_written = True
                writer.writerows(records)

    def get_buffered_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._buffer) + list(self._pending_flush)

    def read_all_events(self) -> list[dict[str, Any]]:
        if not self._output_path.exists():
            return []
        with self._output_path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
