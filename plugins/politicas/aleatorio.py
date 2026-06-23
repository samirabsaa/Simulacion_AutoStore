"""Plugin de ejemplo: politica de picking aleatoria (para testing).

Para crear tu propia politica:
1. Copia este archivo a plugins/politicas/
2. Define una funcion con el decorador @picking_policy("nombre")
3. La funcion recibe: (pedidos, grilla, puertos) -> Pedido | None
4. Reinicia el servidor — la politica se carga automaticamente
"""
from __future__ import annotations

import random

from motor.plugin_loader import picking_policy


@picking_policy("aleatorio")
def aleatorio(pedidos, grilla, puertos):
    """Selecciona un pedido aleatorio entre los que tienen caja disponible."""
    disponibles = [p for p in pedidos if grilla.buscar_por_sku(p.id_sku)]
    return random.choice(disponibles) if disponibles else None
