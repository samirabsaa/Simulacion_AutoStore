"""T-05 — Carga y validación de reposicion.csv."""

from bus_persistencia.persistence.reposicion_loader import load_reposicion
from bus_persistencia.tests.conftest import DATA_DIR, FIXTURES


def test_load_valid_reposicion():
    result = load_reposicion(DATA_DIR / "reposicion.csv")
    assert result.is_valid
    assert len(result.data) == 4
    assert result.data[0].id_caja == "C001"


def test_invalid_rows_return_errors():
    result = load_reposicion(FIXTURES / "reposicion_invalid.csv")
    assert not result.is_valid
    assert result.data is None
    assert len(result.errors) >= 2
