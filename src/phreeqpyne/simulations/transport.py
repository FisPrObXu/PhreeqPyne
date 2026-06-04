"""TRANSPORT workflow builder for the current CFAS multistage model."""

from __future__ import annotations

from phreeqpyne.config import ModelConfig
from phreeqpyne.interpolation import build_stage_boundary_fluids
from phreeqpyne.phreeqc_blocks import (
    build_boundary_solution0_block,
    build_calculate_values_block,
    build_initial_cells_block,
    build_rates_block,
    make_selected_output_block,
)


class TransportSimulationBuilder:
    """Build the current multistage one-dimensional TRANSPORT simulation."""

    kind = "transport"
    display_name = "1D multistage TRANSPORT"

    def build_script(self, config: ModelConfig) -> str:
        """Build the full PHREEQC script for the configured transport workflow."""

        return "\n\n".join(self.build_stage_blocks(config))

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
            fluid["stage_index"] = stage_index
            fluid["stage_label"] = f"Stage-{stage_index}"
            stage_parts = [
                f"# --- Stage {stage_index:02d} ---",
                make_selected_output_block(
                    stage_index,
                    selected_output=config.selected_output,
                    rate_name=str(config.hematite_kinetics.get("rate_name", "Hematite_PK")),
                ),
                build_boundary_solution0_block(fluid, config.initial_pore_solution),
            ]
            if stage_index == 1:
                stage_parts.extend(
                    [
                        build_calculate_values_block(),
                        build_rates_block(config.hematite_kinetics),
                        build_initial_cells_block(
                            config.n_cells,
                            config.initial_pore_solution,
                            config.equilibrium_phases,
                            config.hematite_kinetics,
                            config.initial_pore_gradient,
                        ),
                    ]
                )
            stage_parts.extend(
                [
                    self.make_transport_block(config.n_cells, shifts, config.transport_params),
                    "END",
                ]
            )
            stage_blocks.append("\n\n".join(stage_parts))
        return stage_blocks

    @staticmethod
    def make_transport_block(n_cells: int, shifts: int, transport_params: dict[str, object]) -> str:
        """Build a TRANSPORT block for one stage."""

        punch_cells = transport_params.get("punch_cells") or f"1-{n_cells}"
        lines = [
            "TRANSPORT",
            f"    -cells                 {n_cells}",
            f"    -shifts                {shifts}",
        ]
        if transport_params.get("time_step") is not None:
            lines.append(f"    -time_step             {transport_params['time_step']}")
        lines.extend(
            [
                f"    -flow_direction        {transport_params['flow_direction']}",
                f"    -boundary_conditions   {transport_params['boundary_conditions']}",
                f"    -lengths               {transport_params['lengths']}",
                f"    -dispersivities        {transport_params['dispersivities']}",
                f"    -diffusion_coefficient {transport_params['diffusion_coefficient']}",
                f"    -punch_cells           {punch_cells}",
                f"    -punch_frequency       {transport_params['punch_frequency']}",
            ]
        )
        correct_disp = transport_params.get("correct_disp")
        if correct_disp is True:
            lines.append("    -correct_disp          true")
        elif correct_disp is False:
            lines.append("    -correct_disp          false")
        return "\n".join(lines).strip()
