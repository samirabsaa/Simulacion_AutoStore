"""Carga y validación de ola.csv (T-04)."""

from __future__ import annotations

import csv
from pathlib import Path

from bus_persistencia.models.state import Pedido
from bus_persistencia.persistence.validation import RowError, ValidationResult

REQUIRED_COLUMNS = ("id_pedido", "id_sku", "cantidad", "destino")


def load_ola(path: str | Path) -> ValidationResult[list[Pedido]]:
    file_path = Path(path)
    errors: list[RowError] = []
    pedidos: list[Pedido] = []

    try:
        with file_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return ValidationResult(
                    data=None,
                    errors=[RowError(0, "header", "Archivo CSV vacío o sin encabezado")],
                    warnings=[],
                )

            normalized_fields = [f.strip().lower() for f in reader.fieldnames]
            for col in REQUIRED_COLUMNS:
                if col not in normalized_fields:
                    return ValidationResult(
                        data=None,
                        errors=[
                            RowError(0, col, f"Columna obligatoria ausente: {col}")
                        ],
                        warnings=[],
                    )

            for row_num, row in enumerate(reader, start=2):
                row_norm = {k.strip().lower(): (v or "").strip() for k, v in row.items()}

                id_pedido = row_norm.get("id_pedido", "")
                id_sku = row_norm.get("id_sku", "")
                destino = row_norm.get("destino", "")
                cantidad_raw = row_norm.get("cantidad", "")

                row_has_error = False

                if not id_pedido:
                    errors.append(
                        RowError(row_num, "id_pedido", "Campo obligatorio vacío")
                    )
                    row_has_error = True
                if not id_sku:
                    errors.append(RowError(row_num, "id_sku", "Campo obligatorio vacío"))
                    row_has_error = True
                if not destino:
                    errors.append(RowError(row_num, "destino", "Campo obligatorio vacío"))
                    row_has_error = True

                cantidad: int | None = None
                if not cantidad_raw:
                    errors.append(
                        RowError(row_num, "cantidad", "Campo obligatorio vacío")
                    )
                    row_has_error = True
                else:
                    try:
                        cantidad = int(cantidad_raw)
                        if cantidad <= 0:
                            errors.append(
                                RowError(row_num, "cantidad", "Debe ser mayor que 0")
                            )
                            row_has_error = True
                    except ValueError:
                        errors.append(
                            RowError(row_num, "cantidad", "Debe ser un entero válido")
                        )
                        row_has_error = True

                if not row_has_error and cantidad is not None:
                    pedidos.append(
                        Pedido(
                            id_pedido=id_pedido,
                            id_sku=id_sku,
                            cantidad=cantidad,
                            destino=destino,
                        )
                    )

    except OSError as exc:
        return ValidationResult(
            data=None,
            errors=[RowError(0, "archivo", f"No se pudo leer {file_path}: {exc}")],
            warnings=[],
        )

    if errors:
        return ValidationResult(data=None, errors=errors, warnings=[])

    if not pedidos:
        return ValidationResult(
            data=None,
            errors=[RowError(0, "archivo", "El archivo no contiene pedidos válidos")],
            warnings=[],
        )

    return ValidationResult(data=pedidos, errors=[], warnings=[])
