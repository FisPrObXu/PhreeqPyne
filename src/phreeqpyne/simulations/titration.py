"""Batch titration workflow builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from phreeqpyne.config import ModelConfig
from phreeqpyne.phreeqc_blocks import (
    build_calculate_values_block,
    build_equilibrium_phases_block,
    build_solution_block,
)


class TitrationSimulationBuilder:
    """Build a single batch REACTION titration simulation."""

    kind = "titration"
    display_name = "Batch mineral titration"

    def build_script(self, config: ModelConfig) -> str:
        """Build a complete PHREEQC script for a batch titration."""

        titration_params = config.titration_params
        solution = self._solution_config(config)
        reaction_components = titration_params.get("reaction_components") or [("Hematite", 5e-7)]
        blocks = [
            "TITLE Batch mineral titration",
            build_solution_block(1, solution, "Titration starting fluid"),
            self.make_reaction_temperature_block([solution["temp"]]),
            self.make_reaction_pressure_block([solution["pressure"]]),
            build_equilibrium_phases_block(1, config.equilibrium_phases),
            self.make_reaction_block(
                reaction_components,
                titration_params.get("reaction_total_moles", 1.0),
                titration_params.get("reaction_steps", 1000),
            ),
            f"INCREMENTAL_REACTIONS {'true' if bool(titration_params.get('incremental_reactions', True)) else 'false'}",
            build_calculate_values_block(),
            self.make_selected_output_block(config.selected_output),
            "SAVE equilibrium_phases 2",
            "SAVE solution 2",
            "END",
        ]
        return "\n\n".join(blocks)

    @staticmethod
    def make_reaction_temperature_block(values: Sequence[Any], block_id: int = 1) -> str:
        """Build a REACTION_TEMPERATURE block."""

        return "\n".join([f"REACTION_TEMPERATURE {block_id}", *(f"    {value}" for value in values)])

    @staticmethod
    def make_reaction_pressure_block(values: Sequence[Any], block_id: int = 1) -> str:
        """Build a REACTION_PRESSURE block."""

        return "\n".join([f"REACTION_PRESSURE {block_id}", *(f"    {value}" for value in values)])

    @staticmethod
    def make_reaction_block(
        components: Sequence[Sequence[Any]],
        total_moles: Any,
        steps: Any,
        block_id: int = 1,
    ) -> str:
        """Build a PHREEQC REACTION block for titration components."""

        lines = [f"REACTION {block_id}"]
        for component in components:
            if len(component) != 2:
                raise ValueError(f"Invalid titration reaction component: {component}")
            name, amount = component
            lines.append(f"    {str(name):<22} {amount}")
        lines.append(f"    {total_moles} moles in {int(steps)} steps")
        return "\n".join(lines)

    @staticmethod
    def make_selected_output_block(
        selected_output: Mapping[str, Sequence[str]] | None = None,
        user_number: int = 1,
    ) -> str:
        """Build SELECTED_OUTPUT/USER_PUNCH for titration output."""

        selected_output = selected_output or {}
        optional_lines = [
            TitrationSimulationBuilder._selected_output_line("-totals", selected_output.get("totals", [])),
            TitrationSimulationBuilder._selected_output_line("-molalities", selected_output.get("molalities", [])),
            TitrationSimulationBuilder._selected_output_line("-activities", selected_output.get("activities", [])),
            TitrationSimulationBuilder._selected_output_line("-equilibrium_phases", selected_output.get("equilibrium_phases", [])),
            TitrationSimulationBuilder._selected_output_line("-saturation_indices", selected_output.get("saturation_indices", [])),
        ]
        optional_text = "\n".join(line for line in optional_lines if line)
        return f"""
SELECTED_OUTPUT {user_number}
    -reset false
    -high_precision true
    -simulation true
    -state true
    -solution true
    -step true
    -reaction false
    -temperature true
    -pH true
    -pe true
    -charge_balance true
    -percent_error true
{optional_text}
USER_PUNCH {user_number}
    -headings rxn_step pH_user logaHS- logaH2S SR_Hematite
    -start
10 IF (STEP_NO <= 0) THEN GOTO 100
20 PUNCH STEP_NO, -LA("H+"), LA("HS-"), LA("H2S"), SR("Hematite")
100 END
    -end
""".strip()

    @staticmethod
    def _selected_output_line(keyword: str, values: Sequence[str]) -> str:
        return f"    {keyword:<22} {'  '.join(values)}" if values else ""

    @staticmethod
    def _solution_config(config: ModelConfig) -> dict[str, Any]:
        source = str(config.titration_params.get("solution_source", "reaction_solution")).lower()
        if source in {"reaction_solution", "boundary"}:
            return dict(config.boundary_base)
        raise ValueError("titration solution_source must be reaction_solution")
