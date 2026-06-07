"""Punto de entrada para demo de integración."""

from bus_persistencia.integration.mock_modules import run_integration_demo

if __name__ == "__main__":
    result = run_integration_demo("output", semilla=42, num_ticks=50)
    print(f"Integración completada: {result}")
