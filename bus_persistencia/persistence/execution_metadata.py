"""Registro de semilla y parámetros para reproducibilidad (T-08)."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ExecutionMetadata:
    nombre_ejecucion: str
    semilla: int
    modo: str
    politica: str
    config_path: str
    data_path: str
    config_hash: str
    data_hash: str
    timestamp_inicio: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    kpis_finales: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def file_hash(path: str | Path) -> str:
    content = Path(path).read_bytes()
    return hashlib.sha256(content).hexdigest()


def create_execution_metadata(
    nombre_ejecucion: str,
    semilla: int,
    modo: str,
    politica: str,
    config_path: str | Path,
    data_path: str | Path,
) -> ExecutionMetadata:
    return ExecutionMetadata(
        nombre_ejecucion=nombre_ejecucion,
        semilla=semilla,
        modo=modo,
        politica=politica,
        config_path=str(config_path),
        data_path=str(data_path),
        config_hash=file_hash(config_path),
        data_hash=file_hash(data_path),
    )


def apply_seed(semilla: int) -> None:
    random.seed(semilla)


class MetadataStore:
    """Almacena y recupera metadata de ejecuciones."""

    def __init__(self, output_dir: str | Path) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def save(self, metadata: ExecutionMetadata) -> Path:
        path = self._output_dir / f"metadata_{metadata.nombre_ejecucion}.json"
        path.write_text(
            json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def load(self, nombre_ejecucion: str) -> ExecutionMetadata:
        path = self._output_dir / f"metadata_{nombre_ejecucion}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExecutionMetadata(**data)

    def list_executions(self) -> list[str]:
        return [
            p.stem.replace("metadata_", "")
            for p in self._output_dir.glob("metadata_*.json")
        ]
