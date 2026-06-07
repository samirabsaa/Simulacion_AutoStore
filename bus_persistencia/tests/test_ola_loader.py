"""P02 — Carga y validación de ola.csv."""

from bus_persistencia.persistence.ola_loader import load_ola
from bus_persistencia.tests.conftest import DATA_DIR, FIXTURES


def test_load_valid_ola():
    result = load_ola(DATA_DIR / "ola.csv")
    assert result.is_valid
    assert len(result.data) == 4
    assert result.data[0].id_pedido == "P001"


def test_invalid_rows_return_errors_without_data():
    result = load_ola(FIXTURES / "ola_invalid.csv")
    assert not result.is_valid
    assert result.data is None
    assert len(result.errors) >= 2
    filas = {e.fila for e in result.errors}
    assert 3 in filas
    assert 4 in filas


def test_error_includes_column_and_description():
    result = load_ola(FIXTURES / "ola_invalid.csv")
    cantidad_errors = [e for e in result.errors if e.columna == "cantidad"]
    assert any("mayor que 0" in e.error for e in cantidad_errors)
