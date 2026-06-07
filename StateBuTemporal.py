# bus/state_bus.py
# MOCK de desarrollo — reemplazar con implementación real de Martín
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class Robot:
    id: int
    x: int
    y: int
    estado: str        # "inactivo" | "desplazandose" | "excavando" 
                       # | "recuperando" | "bloqueado" | "entregando" | "reponiendo"
    tarea_id: Optional[int] = None

@dataclass
class Caja:
    sku: str
    cantidad: int

@dataclass
class Pedido:
    id: int
    sku: str
    cantidad: int
    estado: str        # "pendiente" | "en_proceso" | "completado"

class StateBus:
    def __init__(self):
        self._lock = threading.Lock()
        self.grilla: Dict[tuple, List[Caja]] = {}   # (x,y) -> [Caja, ...]
        self.robots: List[Robot] = []
        self.pedidos: List[Pedido] = []
        self.modo: str = "diurno"                   # "diurno" | "nocturno"
        self.politica: str = "fifo"                 # "fifo" | "posicion"
        self.tick: int = 0
        self.kpis: Dict[str, float] = {
            "TSP": 0.0, "TPCP": 0.0, "MTRP": 0.0,
            "IOG": 0.0, "TR": 0.0, "TI": 0.0, "TBR": 0.0
        }

    def write(self, delta: dict):
        """Solo M2 llama este método."""
        with self._lock:
            for key, value in delta.items():
                setattr(self, key, value)

    def read(self) -> dict:
        """M1 y M3 llaman este método."""
        return {
            "grilla":   self.grilla,
            "robots":   self.robots,
            "pedidos":  self.pedidos,
            "modo":     self.modo,
            "politica": self.politica,
            "tick":     self.tick,
            "kpis":     self.kpis,
        }

# Instancia global compartida — todos importan esto
bus = StateBus()