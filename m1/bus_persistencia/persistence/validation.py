"""Utilidades comunes de validación de archivos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RowError:
    fila: int
    columna: str
    error: str


@dataclass
class ValidationResult(Generic[T]):
    data: T | None
    errors: list[RowError]
    warnings: list[str]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.data is not None
