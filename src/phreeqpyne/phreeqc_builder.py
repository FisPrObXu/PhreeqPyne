"""PHREEQC script entry points.

This module preserves the public API from the initial scaffold while delegating
workflow-specific construction to the simulation registry.  New simulation
families can register their own builder instead of modifying the TRANSPORT
implementation.
"""

from __future__ import annotations

from .config import ModelConfig
from .phreeqc_blocks import (
    build_calculate_values_block,
    build_equilibrium_phases_block,
    build_initial_cells_block,
    build_kinetics_block,
    build_rates_block,
    build_solution_block,
    make_selected_output_block,
)
from .simulations import TransportSimulationBuilder, get_simulation_builder


def make_transport_block(n_cells: int, shifts: int, transport_params: dict[str, object]) -> str:
    """Compatibility wrapper for the registered TRANSPORT workflow."""

    return TransportSimulationBuilder.make_transport_block(n_cells, shifts, transport_params)


def build_stage_blocks(config: ModelConfig) -> list[str]:
    """Compatibility wrapper for current transport stage-block generation."""

    if config.simulation_kind != TransportSimulationBuilder.kind:
        raise ValueError("build_stage_blocks is only available for the transport simulation kind")
    return TransportSimulationBuilder().build_stage_blocks(config)


def build_phreeqc_script(config: ModelConfig | None = None) -> str:
    """Build the full PHREEQC script for the configured simulation workflow."""

    cfg = config or ModelConfig()
    return get_simulation_builder(cfg.simulation_kind).build_script(cfg)


__all__ = [
    "build_calculate_values_block",
    "build_equilibrium_phases_block",
    "build_initial_cells_block",
    "build_kinetics_block",
    "build_phreeqc_script",
    "build_rates_block",
    "build_solution_block",
    "build_stage_blocks",
    "make_selected_output_block",
    "make_transport_block",
]
