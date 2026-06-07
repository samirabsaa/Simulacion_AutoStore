"""P01 — Carga y validación de config.json."""

import pytest

from bus_persistencia.persistence.config_loader import ConfigParseError, load_config
from bus_persistencia.tests.conftest import DATA_DIR, FIXTURES


def test_load_valid_config():
    result = load_config(DATA_DIR / "config.json")
    assert result.is_valid
    assert result.data.grilla.x == 10
    assert result.data.grilla.y == 10
    assert result.data.grilla.z == 5
    assert result.data.robots == 4
    assert result.data.ocupacion_inicial == 70


def test_malformed_json_raises_descriptive_error():
    with pytest.raises(ConfigParseError) as exc_info:
        load_config(FIXTURES / "config_malformed.json")
    assert "malformado" in str(exc_info.value).lower()


def test_invalid_values_raise_descriptive_error():
    with pytest.raises(ConfigParseError) as exc_info:
        load_config(FIXTURES / "config_invalid.json")
    assert "grilla.x" in str(exc_info.value)


def test_performance_warning_large_grid(tmp_path):
    large_config = tmp_path / "large.json"
    large_config.write_text(
        '{"grilla": {"x": 25, "y": 25, "z": 6}, "robots": 12, "ocupacion_inicial": 80}',
        encoding="utf-8",
    )
    result = load_config(large_config)
    assert result.is_valid
    assert any("T-23" in w for w in result.warnings)
