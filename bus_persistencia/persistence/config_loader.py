"""Carga y validación de config.json (T-03)."""

from __future__ import annotations

import json
from pathlib import Path

from bus_persistencia.models.state import (
    Config,
    Estacion,
    GrillaDimensions,
    Orientacion,
    TipoEstacion,
)
from bus_persistencia.persistence.validation import ValidationResult


class ConfigParseError(Exception):
    """Error al parsear o validar config.json."""


def _parse_estaciones(raw: object, errors: list[str]) -> tuple[Estacion, ...]:
    """Parsea la lista opcional `estaciones` de config.json.

    Cada entrada: {id, x, y, tipo: "cinta"|"carrusel", orientacion: "N"|"E"|"O"}.
    Entradas inválidas se registran en `errors` y se omiten. Lista ausente → ()."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errors.append("Campo 'estaciones' debe ser una lista")
        return ()

    estaciones: list[Estacion] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"estaciones[{i}] debe ser un objeto")
            continue
        try:
            tipo = TipoEstacion(str(item.get("tipo", "cinta")).lower())
        except ValueError:
            errors.append(f"estaciones[{i}].tipo inválido: {item.get('tipo')!r}")
            continue
        try:
            orient = Orientacion(str(item.get("orientacion", "N")).upper())
        except ValueError:
            errors.append(f"estaciones[{i}].orientacion inválida: {item.get('orientacion')!r}")
            continue
        x, y = item.get("x"), item.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            errors.append(f"estaciones[{i}].x/y deben ser enteros")
            continue
        estaciones.append(Estacion(
            id=str(item.get("id", f"E{i:02d}")),
            x=x, y=y, tipo=tipo, orientacion_requerida=orient,
        ))
    return tuple(estaciones)


PERFORMANCE_GRID_LIMIT = (20, 20, 5)
PERFORMANCE_ROBOT_LIMIT = 10


def _validate_grilla(raw: object, errors: list[str]) -> GrillaDimensions | None:
    if not isinstance(raw, dict):
        errors.append("Campo 'grilla' debe ser un objeto con x, y, z")
        return None

    dims: dict[str, int] = {}
    for axis in ("x", "y", "z"):
        value = raw.get(axis)
        if value is None:
            errors.append(f"Campo 'grilla.{axis}' es obligatorio")
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"Campo 'grilla.{axis}' debe ser un entero")
            continue
        if value <= 0:
            errors.append(f"Campo 'grilla.{axis}' debe ser mayor que 0")
            continue
        dims[axis] = value

    if len(dims) == 3:
        return GrillaDimensions(x=dims["x"], y=dims["y"], z=dims["z"])
    return None


def validate_config_data(data: dict) -> ValidationResult[Config]:
    errors: list[str] = []
    warnings: list[str] = []

    grilla = _validate_grilla(data.get("grilla"), errors)

    robots = data.get("robots")
    if robots is None:
        errors.append("Campo 'robots' es obligatorio")
    elif not isinstance(robots, int) or isinstance(robots, bool):
        errors.append("Campo 'robots' debe ser un entero")
    elif robots < 1:
        errors.append("Campo 'robots' debe ser al menos 1")

    ocupacion = data.get("ocupacion_inicial")
    if ocupacion is None:
        errors.append("Campo 'ocupacion_inicial' es obligatorio")
    elif not isinstance(ocupacion, (int, float)) or isinstance(ocupacion, bool):
        errors.append("Campo 'ocupacion_inicial' debe ser numérico")
    elif not (0 <= float(ocupacion) <= 100):
        errors.append("Campo 'ocupacion_inicial' debe estar entre 0 y 100")

    if grilla and robots is not None and isinstance(robots, int):
        if (
            grilla.x > PERFORMANCE_GRID_LIMIT[0]
            or grilla.y > PERFORMANCE_GRID_LIMIT[1]
            or grilla.z > PERFORMANCE_GRID_LIMIT[2]
        ):
            warnings.append(
                f"Grilla {grilla.x}x{grilla.y}x{grilla.z} supera el umbral "
                f"{PERFORMANCE_GRID_LIMIT[0]}x{PERFORMANCE_GRID_LIMIT[1]}x"
                f"{PERFORMANCE_GRID_LIMIT[2]} (T-23)"
            )
        if robots > PERFORMANCE_ROBOT_LIMIT:
            warnings.append(
                f"Número de robots ({robots}) supera el umbral "
                f"{PERFORMANCE_ROBOT_LIMIT} (T-23)"
            )

    # Campos opcionales de extensión M3 (no invalidan config si faltan)
    anillo = bool(data.get("anillo_transito", False))
    estaciones = _parse_estaciones(data.get("estaciones"), errors)

    if errors or grilla is None:
        return ValidationResult(data=None, errors=[], warnings=warnings)

    config = Config(
        grilla=grilla,
        robots=int(robots),
        ocupacion_inicial=float(ocupacion),
        anillo_transito=anillo,
        estaciones=estaciones,
    )
    return ValidationResult(data=config, errors=[], warnings=warnings)


def load_config(path: str | Path) -> ValidationResult[Config]:
    """Carga config.json. Lanza ConfigParseError si el JSON es inválido."""
    file_path = Path(path)
    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigParseError(f"No se pudo leer {file_path}: {exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigParseError(
            f"config.json malformado en {file_path}: línea {exc.lineno}, "
            f"columna {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigParseError("config.json debe ser un objeto JSON")

    result = validate_config_data(data)
    if not result.is_valid:
        messages = []
        if not data.get("grilla"):
            messages.append("Campo 'grilla' es obligatorio")
        if data.get("robots") is None:
            messages.append("Campo 'robots' es obligatorio")
        if data.get("ocupacion_inicial") is None:
            messages.append("Campo 'ocupacion_inicial' es obligatorio")

        grilla_errors: list[str] = []
        _validate_grilla(data.get("grilla"), grilla_errors)
        messages.extend(grilla_errors)

        if data.get("robots") is not None:
            if not isinstance(data["robots"], int) or isinstance(data["robots"], bool):
                messages.append("Campo 'robots' debe ser un entero")
            elif data["robots"] < 1:
                messages.append("Campo 'robots' debe ser al menos 1")

        ocup = data.get("ocupacion_inicial")
        if ocup is not None:
            if not isinstance(ocup, (int, float)) or isinstance(ocup, bool):
                messages.append("Campo 'ocupacion_inicial' debe ser numérico")
            elif not (0 <= float(ocup) <= 100):
                messages.append("Campo 'ocupacion_inicial' debe estar entre 0 y 100")

        raise ConfigParseError(
            "config.json inválido: " + "; ".join(dict.fromkeys(messages))
        )

    return result
