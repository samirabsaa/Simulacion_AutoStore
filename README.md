# Simulación AutoStore — Forus S.A. (Grupo 12)

Repositorio del simulador AutoStore. Remoto: `https://github.com/samirabsaa/Simulacion_AutoStore.git`

## Estructura del proyecto

```
Simulacion_AutoStore/
├── bus_persistencia/     # Módulo Bus + Persistencia (Martín / Guadalupe) — T-01 a T-08
├── data/                 # Archivos de ejemplo: config.json, ola.csv, reposicion.csv
├── docs/                 # Contrato API e integración con M1/M2/M3
├── StateBuTemporal.py    # Mock temporal usado por M1 durante desarrollo (deprecar)
└── ...
```

## Módulo Bus + Persistencia

Capa transversal: **StateBus** (estado compartido) + loaders/validadores + sesión CSV + reportes.

```bash
pip install -r requirements.txt
pytest
python -m bus_persistencia.integration
```

Documentación:
- [docs/bus_api.md](docs/bus_api.md) — contrato para M1, M2, M3
- [docs/integracion_grupo12.md](docs/integracion_grupo12.md) — diagrama de integración

### Migración desde `StateBuTemporal.py`

M1 usó un mock en la raíz (`StateBuTemporal.py` con `bus = StateBus()` global). La implementación real está en `bus_persistencia/`:

```python
# Antes (mock)
from StateBuTemporal import bus

# Después (producción)
from bus_persistencia import StateBus
from bus_persistencia.persistence import load_config, load_ola

bus = StateBus()
```

Ver `docs/integracion_grupo12.md` para el flujo completo con M1/M2/M3.
