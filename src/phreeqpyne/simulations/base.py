"""Extensible simulation workflow interfaces.

The project can host more than one PHREEQC workflow.  A workflow builder is
responsible for translating a high-level model config into executable PHREEQC
input blocks; runners and UIs can then stay agnostic to whether the simulation
uses TRANSPORT, ADVECTION, batch EQUILIBRIUM calculations, or another pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from phreeqpyne.config import ModelConfig


class SimulationBuilder(Protocol):
    """Protocol implemented by PHREEQC workflow builders."""

    kind: str
    display_name: str

    def build_script(self, config: ModelConfig) -> str:
        """Build a complete PHREEQC input script for the workflow."""


@dataclass(frozen=True, slots=True)
class RegisteredSimulation:
    """Metadata stored for a simulation workflow."""

    kind: str
    display_name: str
    factory: Callable[[], SimulationBuilder]


_REGISTRY: dict[str, RegisteredSimulation] = {}


def register_simulation(factory: Callable[[], SimulationBuilder]) -> None:
    """Register a workflow builder factory by its stable kind."""

    builder = factory()
    _REGISTRY[builder.kind] = RegisteredSimulation(
        kind=builder.kind,
        display_name=builder.display_name,
        factory=factory,
    )


def get_simulation_builder(kind: str) -> SimulationBuilder:
    """Return a new workflow builder for ``kind``."""

    if kind not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise ValueError(f"Unknown simulation kind: {kind}. Available kinds: {available}")
    return _REGISTRY[kind].factory()


def list_simulations() -> list[RegisteredSimulation]:
    """List registered simulation workflow metadata."""

    return sorted(_REGISTRY.values(), key=lambda item: item.kind)
