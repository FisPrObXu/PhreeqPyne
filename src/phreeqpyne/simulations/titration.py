"""Batch titration workflow builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from phreeqpyne.config import ModelConfig
from phreeqpyne.interpolation import transform_progress
from phreeqpyne.phreeqc_blocks import (
    build_calculate_values_block,
    build_equilibrium_phases_block,
    build_solution_block,
)


class TitrationSimulationBuilder:
    """Build a stepwise manual titration simulation."""

    kind = "titration"
    display_name = "Batch mineral titration"

    def build_script(self, config: ModelConfig) -> str:
        """Build a complete PHREEQC script for a batch titration."""

        titration_params = config.titration_params
        solution = self._solution_config(config)
        reaction_components = titration_params.get("reaction_components") or [("Hematite", 5e-7)]
        reaction_steps = int(titration_params.get("reaction_steps", 1000))
        return self._build_phase_solution_step_script(config, solution, reaction_components, reaction_steps)

    def _build_phase_solution_step_script(
        self,
        config: ModelConfig,
        solution: Mapping[str, Any],
        additions: Sequence[object],
        reaction_steps: int,
    ) -> str:
        components = self._normalize_reaction_components(additions)
        phase_components = [component for component in components if self._component_addition_type(component) == "phase"]
        solution_components = [component for component in components if self._component_addition_type(component) == "solution"]
        addition_schedule = self._component_schedule(components, reaction_steps)
        phase_schedule = self._component_schedule(phase_components, reaction_steps) if phase_components else [[] for _ in range(reaction_steps)]
        solution_schedule = self._component_schedule(solution_components, reaction_steps) if solution_components else [[] for _ in range(reaction_steps)]
        phase_targets = self._phase_target_map(config.equilibrium_phases)
        blocks = [
            "TITLE Batch titration with coupled phase and solution additions",
            self.make_selected_output_block(
                config.selected_output,
                step_expression="SIM_NO",
                inventory_components=components,
                inventory_steps=reaction_steps,
                inventory_schedule=addition_schedule,
            ),
            build_calculate_values_block(),
        ]
        for step_index in range(1, reaction_steps + 1):
            step_phase_additions = phase_schedule[step_index - 1]
            step_solution_additions = solution_schedule[step_index - 1]
            step_parts: list[str] = [f"# --- Phase+solution step {step_index:04d} ---"]
            if step_index == 1:
                step_parts.extend(
                    [
                        build_solution_block(1, solution, "Phase+solution titration starting fluid"),
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                        self.make_initial_inventory_phases_block(config.equilibrium_phases, step_phase_additions, phase_targets),
                    ]
                )
            else:
                step_parts.extend(
                    [
                        f"USE equilibrium_phases {step_index - 1}",
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                    ]
                )
            solution_mix_block = self.make_solution_addition_mix_block(
                step_solution_additions,
                step_index,
                1 if step_index == 1 else step_index - 1,
                solution,
            )
            if solution_mix_block:
                step_parts.append(solution_mix_block)
                step_parts.append(f"USE mix {step_index}")
                if step_index == 1:
                    step_parts.append("USE equilibrium_phases 1")
            elif step_index > 1:
                step_parts.append(f"USE solution {step_index - 1}")
            phase_increment_block = ""
            if step_index > 1:
                phase_increment_block = self.make_phase_inventory_addition_block(step_phase_additions, step_index, phase_targets)
            if phase_increment_block:
                step_parts.append(phase_increment_block)
            step_parts.extend(
                [
                    f"SAVE equilibrium_phases {step_index}",
                    f"SAVE solution {step_index}",
                    "END",
                ]
            )
            blocks.append("\n\n".join(step_parts))
        return "\n\n".join(blocks)

    def _build_solution_component_step_script(
        self,
        config: ModelConfig,
        solution: Mapping[str, Any],
        solution_additions: Sequence[object],
        reaction_steps: int,
    ) -> str:
        additions = self._normalize_reaction_components(solution_additions)
        addition_schedule = self._component_schedule(additions, reaction_steps)
        blocks = [
            "TITLE Batch titration with stepwise solution-component additions",
            self.make_selected_output_block(
                config.selected_output,
                step_expression="SIM_NO",
                inventory_components=additions,
                inventory_steps=reaction_steps,
                inventory_schedule=addition_schedule,
            ),
            build_calculate_values_block(),
        ]
        for step_index in range(1, reaction_steps + 1):
            step_additions = addition_schedule[step_index - 1]
            step_parts: list[str] = [f"# --- Solution-component step {step_index:04d} ---"]
            if step_index == 1:
                step_parts.extend(
                    [
                        build_solution_block(1, solution, "Solution-component titration starting fluid"),
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                        build_equilibrium_phases_block(1, config.equilibrium_phases),
                    ]
                )
            else:
                step_parts.extend(
                    [
                        f"USE equilibrium_phases {step_index - 1}",
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                    ]
                )
            solution_mix_block = self.make_solution_addition_mix_block(
                step_additions,
                step_index,
                1 if step_index == 1 else step_index - 1,
                solution,
            )
            if solution_mix_block:
                step_parts.append(solution_mix_block)
                step_parts.append(f"USE mix {step_index}")
                if step_index == 1:
                    step_parts.append("USE equilibrium_phases 1")
            elif step_index > 1:
                step_parts.append(f"USE solution {step_index - 1}")
            step_parts.extend(
                [
                    f"SAVE equilibrium_phases {step_index}",
                    f"SAVE solution {step_index}",
                    "END",
                ]
            )
            blocks.append("\n\n".join(step_parts))
        return "\n\n".join(blocks)

    def _build_inventory_step_script(
        self,
        config: ModelConfig,
        solution: Mapping[str, Any],
        phase_additions: Sequence[object],
        reaction_steps: int,
    ) -> str:
        return self._build_phase_solution_step_script(config, solution, phase_additions, reaction_steps)

    def _build_legacy_inventory_step_script(
        self,
        config: ModelConfig,
        solution: Mapping[str, Any],
        phase_additions: Sequence[object],
        reaction_steps: int,
    ) -> str:
        additions = self._normalize_reaction_components(phase_additions)
        addition_schedule = self._component_schedule(additions, reaction_steps)
        phase_targets = self._phase_target_map(config.equilibrium_phases)
        blocks = [
            "TITLE Batch titration with stepwise phase inventory",
            self.make_selected_output_block(
                config.selected_output,
                step_expression="SIM_NO",
                inventory_components=additions,
                inventory_steps=reaction_steps,
                inventory_schedule=addition_schedule,
            ),
            build_calculate_values_block(),
        ]
        for step_index in range(1, reaction_steps + 1):
            step_additions = addition_schedule[step_index - 1]
            step_parts: list[str] = [f"# --- Inventory step {step_index:04d} ---"]
            if step_index == 1:
                step_parts.extend(
                    [
                        build_solution_block(1, solution, "Inventory-step starting fluid"),
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                        self.make_initial_inventory_phases_block(config.equilibrium_phases, step_additions, phase_targets),
                    ]
                )
            else:
                step_parts.extend(
                    [
                        f"USE solution {step_index - 1}",
                        f"USE equilibrium_phases {step_index - 1}",
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                    ]
                )
            phase_increment_block = ""
            if step_index > 1:
                phase_increment_block = self.make_phase_inventory_addition_block(step_additions, step_index, phase_targets)
            if phase_increment_block:
                step_parts.append(phase_increment_block)
            inventory_reaction_block = self.make_inventory_reaction_block(step_additions, step_index)
            if inventory_reaction_block:
                step_parts.append(inventory_reaction_block)
            step_parts.extend(
                [
                    f"SAVE equilibrium_phases {step_index}",
                    f"SAVE solution {step_index}",
                    "END",
                ]
            )
            blocks.append("\n\n".join(step_parts))
        return "\n\n".join(blocks)

    @staticmethod
    def make_initial_inventory_phases_block(
        equilibrium_phases: Sequence[Sequence[Any]],
        additions: Sequence[Sequence[Any]],
        phase_targets: Mapping[str, Any],
    ) -> str:
        phase_rows = [list(phase) for phase in equilibrium_phases]
        existing_by_name = {str(phase[0]): phase for phase in phase_rows if phase}
        for name, amount in additions:
            if float(amount) == 0.0:
                continue
            existing = existing_by_name.get(str(name))
            if existing is not None:
                while len(existing) < 4:
                    existing.append(None)
                existing[2] = float(existing[2] or 0.0) + float(amount)
            else:
                phase_rows.append([str(name), phase_targets.get(str(name), 0), amount, None])
        return build_equilibrium_phases_block(1, phase_rows)

    @staticmethod
    def make_phase_inventory_addition_block(
        components: Sequence[Sequence[Any]],
        block_id: int,
        phase_targets: Mapping[str, Any],
    ) -> str:
        lines = [f"EQUILIBRIUM_PHASES {block_id}"]
        for name, amount in components:
            if float(amount) == 0.0:
                continue
            lines.append(f"    {str(name):<24} {phase_targets.get(str(name), 0)} {amount}")
        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def make_inventory_reaction_block(components: Sequence[Sequence[Any]], block_id: int) -> str:
        return ""

    @staticmethod
    def make_solution_addition_mix_block(
        components: Sequence[Sequence[Any]],
        block_id: int,
        base_solution_id: int,
        solution: Mapping[str, Any],
    ) -> str:
        nonzero_components = [(str(name), float(amount)) for name, amount in components if float(amount) != 0.0]
        if not nonzero_components:
            return ""
        blocks: list[str] = []
        mix_lines = [f"MIX {block_id}", f"    {base_solution_id} 1"]
        for component_index, (name, amount) in enumerate(nonzero_components, start=1):
            addition_solution_id = 100000 + block_id * 100 + component_index
            addition_solution = {
                "temp": solution.get("temp", 25),
                "pressure": solution.get("pressure", 1),
                "units": "mol/kgw",
                "pH": solution.get("pH", 7),
                "pe": solution.get("pe", 4),
                "water": 1.0,
                name: 1.0,
            }
            blocks.append(build_solution_block(addition_solution_id, addition_solution, f"Addition {name} step {block_id}"))
            mix_lines.append(f"    {addition_solution_id} {amount}")
        blocks.append("\n".join(mix_lines))
        return "\n\n".join(blocks)

    @staticmethod
    def _phase_target_map(equilibrium_phases: Sequence[Sequence[Any]]) -> dict[str, Any]:
        targets: dict[str, Any] = {}
        for phase in equilibrium_phases:
            if len(phase) >= 2:
                targets[str(phase[0])] = phase[1]
        return targets

    def _build_variable_reaction_script(
        self,
        config: ModelConfig,
        solution: Mapping[str, Any],
        reaction_components: Sequence[object],
        reaction_steps: int,
    ) -> str:
        return self._build_phase_solution_step_script(config, solution, reaction_components, reaction_steps)

    def _build_legacy_variable_reaction_script(
        self,
        config: ModelConfig,
        solution: Mapping[str, Any],
        reaction_components: Sequence[object],
        reaction_steps: int,
    ) -> str:
        components = self._normalize_reaction_components(reaction_components)
        reaction_schedule = self._component_schedule(components, reaction_steps)
        blocks = [
            "TITLE Batch mineral titration with variable reaction schedule",
            self.make_selected_output_block(config.selected_output, step_expression="SIM_NO"),
            build_calculate_values_block(),
        ]
        for step_index in range(1, reaction_steps + 1):
            step_parts: list[str] = [f"# --- Reaction step {step_index:04d} ---"]
            if step_index == 1:
                step_parts.extend(
                    [
                        build_solution_block(1, solution, "Titration starting fluid"),
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                        build_equilibrium_phases_block(1, config.equilibrium_phases),
                    ]
                )
            else:
                step_parts.extend(
                    [
                        f"USE solution {step_index - 1}",
                        f"USE equilibrium_phases {step_index - 1}",
                        self.make_reaction_temperature_block([solution["temp"]], step_index),
                        self.make_reaction_pressure_block([solution["pressure"]], step_index),
                    ]
                )
            step_parts.extend(
                [
                    self.make_reaction_block(
                        reaction_schedule[step_index - 1],
                        1,
                        1,
                        step_index,
                    ),
                    f"SAVE equilibrium_phases {step_index}",
                    f"SAVE solution {step_index}",
                    "END",
                ]
            )
            blocks.append("\n\n".join(step_parts))
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
        return ""

    @staticmethod
    def _has_variable_components(components: Sequence[object]) -> bool:
        return any(
            normalized.get("end") is not None
            or normalized.get("total") is not None
            or str(normalized.get("mode", "linear")).lower() != "linear"
            for normalized in (
                TitrationSimulationBuilder._normalize_reaction_component(component)
                for component in components
            )
        )

    @staticmethod
    def _normalize_reaction_components(components: Sequence[object]) -> list[dict[str, Any]]:
        return [TitrationSimulationBuilder._normalize_reaction_component(component) for component in components]

    @staticmethod
    def _normalize_reaction_component(component: object) -> dict[str, Any]:
        if isinstance(component, Mapping):
            normalized = {
                "name": str(component["name"]),
                "start": float(component.get("amount", component.get("start", 0.0))),
                "end": None if component.get("end") is None else float(component["end"]),
                "mode": str(component.get("mode", "linear")).lower(),
                "shape_k": float(component.get("shape_k", 3.0)),
                "start_step": int(component.get("start_step", 1) or 1),
                "end_step": None if component.get("end_step") is None else int(component["end_step"]),
                "addition_type": str(component.get("addition_type", component.get("type", "phase"))).lower(),
            }
            if component.get("total") is not None:
                normalized["total"] = float(component["total"])
                normalized["start"] = float(component.get("start", 1.0))
                normalized["end"] = float(component.get("end", normalized["start"]))
            return normalized
        if isinstance(component, Sequence) and not isinstance(component, (str, bytes)):
            if len(component) == 2:
                name, amount = component
                return {
                    "name": str(name),
                    "start": float(amount),
                    "end": None,
                    "mode": "linear",
                    "shape_k": 3.0,
                    "start_step": 1,
                    "end_step": None,
                    "addition_type": "phase",
                }
            if len(component) == 3:
                name, start, end = component
                return {
                    "name": str(name),
                    "start": float(start),
                    "end": float(end),
                    "mode": "linear",
                    "shape_k": 3.0,
                    "start_step": 1,
                    "end_step": None,
                    "addition_type": "phase",
                }
        raise ValueError(f"Invalid titration reaction component: {component}")

    @staticmethod
    def _component_addition_type(component: Mapping[str, Any]) -> str:
        addition_type = str(component.get("addition_type", component.get("type", "phase"))).lower()
        if addition_type in {"solution", "solution_component", "component"}:
            return "solution"
        return "phase"

    @staticmethod
    def _component_schedule(
        components: Sequence[Mapping[str, Any]],
        reaction_steps: int,
    ) -> list[list[tuple[str, float]]]:
        total_steps = max(1, int(reaction_steps))
        per_component_values = [
            (
                str(component["name"]),
                TitrationSimulationBuilder._component_step_values(component, total_steps),
            )
            for component in components
        ]
        schedule: list[list[tuple[str, float]]] = []
        for step_index in range(total_steps):
            step_components = [
                (name, values[step_index])
                for name, values in per_component_values
                if values[step_index] != 0
            ]
            schedule.append(step_components or [("H+", 0.0)])
        return schedule

    @staticmethod
    def _component_step_values(component: Mapping[str, Any], reaction_steps: int) -> list[float]:
        total_steps = max(1, int(reaction_steps))
        active_start, active_end = TitrationSimulationBuilder._component_active_bounds(component, total_steps)
        active_count = active_end - active_start + 1
        start = float(component["start"])
        end = start if component.get("end") is None else float(component["end"])
        mode = str(component.get("mode", "linear")).lower()
        shape_k = float(component.get("shape_k", 3.0))
        weights = [
            start
            + (end - start)
            * transform_progress(
                progress=0.0 if active_count <= 1 else active_index / (active_count - 1),
                mode=mode,
                shape_k=shape_k,
            )
            for active_index in range(active_count)
        ]
        if component.get("total") is None:
            values = [0.0 for _ in range(total_steps)]
            for offset, weight in enumerate(weights):
                values[active_start - 1 + offset] = weight
            return values
        total = float(component["total"])
        weight_sum = sum(weights)
        values = [0.0 for _ in range(total_steps)]
        if weight_sum == 0:
            return values
        for offset, weight in enumerate(weights):
            values[active_start - 1 + offset] = total * weight / weight_sum
        return values

    @staticmethod
    def _component_active_bounds(component: Mapping[str, Any], total_steps: int) -> tuple[int, int]:
        raw_start = component.get("start_step", 1)
        raw_end = component.get("end_step", total_steps)
        start = max(1, min(total_steps, int(raw_start or 1)))
        end = max(1, min(total_steps, int(raw_end or total_steps)))
        if end < start:
            start, end = end, start
        return start, end

    @staticmethod
    def _reaction_components_for_step(
        components: Sequence[Mapping[str, Any]],
        step_index: int,
        reaction_steps: int,
    ) -> list[tuple[str, float]]:
        return TitrationSimulationBuilder._component_schedule(components, reaction_steps)[step_index - 1]

    @staticmethod
    def make_selected_output_block(
        selected_output: Mapping[str, Sequence[str]] | None = None,
        user_number: int = 1,
        step_expression: str = "STEP_NO",
        inventory_components: Sequence[Mapping[str, Any]] | None = None,
        inventory_steps: int = 1,
        inventory_schedule: Sequence[Sequence[Sequence[Any]]] | None = None,
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
        inventory_components = inventory_components or []
        inventory_headings = [f"add_{str(component['name']).replace(' ', '_')}" for component in inventory_components]
        inventory_punches = [
            TitrationSimulationBuilder._inventory_step_expression(component, step_expression, inventory_steps)
            for component in inventory_components
        ]
        assignment_lines: list[str] = []
        if inventory_schedule:
            inventory_punches = [f"add_{index}" for index, _ in enumerate(inventory_components, start=1)]
            line_number = 20
            for index, _component in enumerate(inventory_components, start=1):
                assignment_lines.append(f"{line_number} add_{index} = 0")
                line_number += 1
            for step_index, step_components in enumerate(inventory_schedule, start=1):
                amounts_by_name = {str(name): float(amount) for name, amount in step_components}
                for index, component in enumerate(inventory_components, start=1):
                    amount = amounts_by_name.get(str(component["name"]), 0.0)
                    assignment_lines.append(f"{line_number} IF ({step_expression} = {step_index}) THEN add_{index} = {amount}")
                    line_number += 1
        headings_text = " ".join(["rxn_step", "pH_user", "logaHS-", "logaH2S", "SR_Hematite", *inventory_headings])
        punch_values = ", ".join([step_expression, '-LA("H+")', 'LA("HS-")', 'LA("H2S")', 'SR("Hematite")', *inventory_punches])
        assignment_text = "\n".join(assignment_lines)
        if assignment_text:
            assignment_text = "\n" + assignment_text
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
    -headings {headings_text}
    -start
10 IF ({step_expression} <= 0) THEN GOTO 20000
{assignment_text}
10000 PUNCH {punch_values}
20000 END
    -end
""".strip()

    @staticmethod
    def _inventory_step_expression(component: Mapping[str, Any], step_expression: str, inventory_steps: int) -> str:
        start = float(component["start"])
        end = start if component.get("end") is None else float(component["end"])
        if end == start:
            return str(start)
        denominator = max(1, int(inventory_steps) - 1)
        mode = str(component.get("mode", "linear")).lower()
        if mode != "linear" or component.get("total") is not None:
            return "0"
        return f"({start}) + (({end}) - ({start})) * ({step_expression} - 1) / {denominator}"

    @staticmethod
    def _selected_output_line(keyword: str, values: Sequence[str]) -> str:
        return f"    {keyword:<22} {'  '.join(values)}" if values else ""

    @staticmethod
    def _solution_config(config: ModelConfig) -> dict[str, Any]:
        source = str(config.titration_params.get("solution_source", "reaction_solution")).lower()
        if source in {"reaction_solution", "boundary"}:
            return dict(config.boundary_base)
        raise ValueError("titration solution_source must be reaction_solution")
