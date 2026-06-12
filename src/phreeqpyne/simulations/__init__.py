"""Simulation workflow registry."""

from .base import get_simulation_builder, list_simulations, register_simulation
from .titration import TitrationSimulationBuilder
from .transport import TransportSimulationBuilder

register_simulation(TransportSimulationBuilder)
register_simulation(TitrationSimulationBuilder)

__all__ = [
    "TitrationSimulationBuilder",
    "TransportSimulationBuilder",
    "get_simulation_builder",
    "list_simulations",
    "register_simulation",
]
