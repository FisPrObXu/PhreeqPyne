"""TRANSPORT workflow builder for the current CFAS multistage model."""

from __future__ import annotations

from phreeqpyne.config import ModelConfig
from phreeqpyne.interpolation import build_stage_boundary_fluids
from phreeqpyne.phreeqc_blocks import (
    build_calculate_values_block,
    build_initial_cells_block,
    build_rates_block,
    build_solution_block,
    make_selected_output_block,
)


class TransportSimulationBuilder:
    """Build the current multistage one-dimensional TRANSPORT simulation."""

    kind = "transport"
    display_name = "1D multistage TRANSPORT"

    def build_script(self, config: ModelConfig) -> str:
        """Build the full PHREEQC script for the configured transport workflow."""

        return "\n\n".join(
            [
                build_calculate_values_block(),
                build_rates_block(config.hematite_kinetics),
                build_initial_cells_block(
                    config.n_cells,
                    config.initial_pore_solution,
                    config.equilibrium_phases,
                    config.hematite_kinetics,
                ),
                *self.build_stage_blocks(config),
                "END",
            ]
        )

    def build_stage_blocks(self, config: ModelConfig) -> list[str]:
        """Build all stage-specific boundary-solution and transport blocks."""

        if len(config.stage_shifts) != config.n_stages:
            raise ValueError("stage_shifts length must match n_stages")

        fluids = build_stage_boundary_fluids(
            config.n_stages,
            config.boundary_base,
            config.boundary_interpolation,
        )
        stage_blocks: list[str] = []
        for stage_index, (fluid, shifts) in enumerate(zip(fluids, config.stage_shifts, strict=True), start=1):
            stage_blocks.append(
                "\n\n".join(
                    [
                        f"# --- Stage {stage_index:02d} ---",
                        build_solution_block(0, fluid, f"Stage {stage_index} boundary fluid"),
                        make_selected_output_block(stage_index),
                        self.make_transport_block(config.n_cells, shifts, config.transport_params),
                    ]
                )
            )
        return stage_blocks

    @staticmethod
    def make_transport_block(n_cells: int, shifts: int, transport_params: dict[str, object]) -> str:
        """Build a TRANSPORT block for one stage."""

        return f"""
TRANSPORT
    -cells {n_cells}
    -shifts {shifts}
    -time_step {transport_params['time_step']}
    -lengths {transport_params['lengths']}
    -flow_direction {transport_params['flow_direction']}
    -boundary_conditions {transport_params['boundary_conditions']}
""".strip()
