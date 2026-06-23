"""motor/plugin_loader.py — Carga dinamica de politicas de picking externas.

Permite a investigadores agregar politicas sin modificar el codigo base:
basta con colocar un .py en plugins/politicas/ con una funcion decorada
con @picking_policy("nombre").
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Callable

from motor.politicas import Selector, register_politica

logger = logging.getLogger(__name__)

EXPECTED_PARAMS = 3


def picking_policy(name: str) -> Callable:
    """Decorador que marca una funcion como politica de picking."""
    def wrapper(fn: Callable) -> Callable:
        fn._policy_name = name  # type: ignore[attr-defined]
        return fn
    return wrapper


def _validate_signature(fn: Callable, name: str) -> bool:
    sig = inspect.signature(fn)
    required = [
        p for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                       inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(required) != EXPECTED_PARAMS:
        logger.warning(
            "Plugin '%s': firma invalida — se esperan %d params, tiene %d",
            name, EXPECTED_PARAMS, len(required),
        )
        return False
    return True


def validate_and_load_file(path: Path) -> tuple[str, str | None]:
    """Importa un .py, busca funciones decoradas y las registra.

    Retorna (policy_name, None) en exito, o ("", error_message) en fallo.
    """
    try:
        spec = importlib.util.spec_from_file_location(
            f"plugins.politicas.{path.stem}", path,
        )
        if spec is None or spec.loader is None:
            return ("", f"No se pudo cargar el modulo {path.name}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:
        return ("", f"Error al importar {path.name}: {exc}")

    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if callable(obj) and hasattr(obj, "_policy_name"):
            policy_name: str = obj._policy_name
            if not _validate_signature(obj, policy_name):
                return ("", f"Firma invalida en '{policy_name}': se requieren 3 parametros (pedidos, grilla, puertos)")
            try:
                register_politica(policy_name, obj)
            except ValueError as exc:
                return ("", str(exc))
            logger.info("Plugin cargado: %s (desde %s)", policy_name, path.name)
            return (policy_name, None)

    return ("", f"No se encontro ninguna funcion decorada con @picking_policy en {path.name}")


def load_plugins(plugin_dir: str | Path | None = None) -> list[str]:
    """Carga todos los plugins .py del directorio. Retorna nombres registrados."""
    if plugin_dir is None:
        plugin_dir = Path(__file__).resolve().parents[1] / "plugins" / "politicas"
    plugin_dir = Path(plugin_dir)
    if not plugin_dir.is_dir():
        return []

    loaded: list[str] = []
    for py_file in sorted(plugin_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        name, error = validate_and_load_file(py_file)
        if error:
            logger.warning("Plugin %s: %s", py_file.name, error)
        else:
            loaded.append(name)
    return loaded
