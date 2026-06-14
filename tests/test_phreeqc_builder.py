import pytest

from phreeqpyne.config import default_model_config
from phreeqpyne.phreeqc_builder import build_phreeqc_script, build_stage_blocks


def test_build_phreeqc_script_contains_core_blocks():
    script = build_phreeqc_script(default_model_config())

    assert "CALCULATE_VALUES" in script
    assert "RATES\nHematite_PK" in script
    assert "SOLUTION 1  Initial Alkaline Pore Fluid (shell->core gradient)" in script
    assert "SOLUTION 10  Initial Alkaline Pore Fluid (shell->core gradient)" in script
    assert "COPY solution" not in script
    assert "KINETICS 1-10" in script
    assert "-diffusion_coefficient 1e-09" in script
    assert "-punch_frequency       1" in script
    assert "-totals" in script
    assert "-kinetic_reactants" in script
    assert script.count("TRANSPORT") == 8
    assert script.count("\nEND") == 8
    assert script.count("SAVE solution 0") == 8
    assert script.count("Initial Alkaline Pore Fluid (shell->core gradient)") == 10
    assert "# --- Stage 08 ---" in script
    assert script.endswith("END")


def test_build_stage_blocks_validates_stage_shift_count():
    config = default_model_config()
    config.stage_shifts = [1]

    with pytest.raises(ValueError, match="stage_shifts"):
        build_stage_blocks(config)


def test_build_titration_script_contains_manual_step_blocks_without_reaction():
    config = default_model_config()
    config.simulation_kind = "titration"

    script = build_phreeqc_script(config)

    assert "TITLE Batch titration with coupled phase and solution additions" in script
    assert "SOLUTION 1 Phase+solution titration starting fluid" in script
    assert "REACTION_TEMPERATURE 1" in script
    assert "REACTION_PRESSURE 1" in script
    assert not any(line.startswith("REACTION ") for line in script.splitlines())
    assert "EQUILIBRIUM_PHASES 1-1" in script
    assert "Hematite" in script
    assert "# --- Phase+solution step 1000 ---" in script
    assert "SELECTED_OUTPUT 1" in script
    assert "RATES" not in script
    assert "KIN(\"Hematite_PK\")" not in script
    assert "-kinetic_reactants" not in script
    assert "TRANSPORT" not in script


def test_build_titration_script_supports_variable_manual_phase_schedule():
    config = default_model_config()
    config.simulation_kind = "titration"
    config.titration_params["reaction_steps"] = 3
    config.titration_params["reaction_components"] = [
        ("Hematite", 5e-7, 1e-7),
        ("Chalcopyrite(alpha)", 0.0, 4e-7),
    ]

    script = build_phreeqc_script(config)

    assert "TITLE Batch titration with coupled phase and solution additions" in script
    assert not any(line.startswith("REACTION ") for line in script.splitlines())
    assert "# --- Phase+solution step 0003 ---" in script
    assert "USE solution 1" in script
    assert "USE equilibrium_phases 1" in script
    assert "Hematite                 0 5e-07" in script
    assert "Hematite                 0 1e-07" in script
    assert "Chalcopyrite(alpha)" in script
    assert "4e-07" in script
    assert "PUNCH SIM_NO" in script


def test_build_titration_script_includes_equilibrium_phase_controls():
    config = default_model_config()
    config.simulation_kind = "titration"
    config.equilibrium_phases = [
        ("O2(g)", -35.0, 10.0, None),
        ("Hematite", 0.0, 0.0, None),
    ]

    script = build_phreeqc_script(config)

    assert "EQUILIBRIUM_PHASES 1-1" in script
    assert "O2(g)" in script
    assert "-35.0 10.0" in script
    assert "Hematite" in script


def test_build_titration_inventory_step_uses_phase_inventory_blocks():
    config = default_model_config()
    config.simulation_kind = "titration"
    config.titration_params["mode"] = "inventory_step"
    config.titration_params["reaction_steps"] = 3
    config.titration_params["reaction_components"] = [
        ("Hematite", 5e-7, 1e-7),
        ("Chalcopyrite(alpha)", 0.0, 4e-7),
    ]

    script = build_phreeqc_script(config)

    assert "TITLE Batch titration with coupled phase and solution additions" in script
    assert not any(line.startswith("REACTION ") for line in script.splitlines())
    assert "# --- Phase+solution step 0003 ---" in script
    assert "USE solution 1" in script
    assert "USE equilibrium_phases 1" in script
    assert "EQUILIBRIUM_PHASES 3" in script
    assert "Hematite" in script
    assert "Chalcopyrite(alpha)" in script
    assert "add_Hematite" in script
    assert "add_Chalcopyrite(alpha)" in script
    assert "PUNCH SIM_NO" in script


def test_build_titration_inventory_step_supports_total_mode_schedule():
    config = default_model_config()
    config.simulation_kind = "titration"
    config.titration_params["mode"] = "inventory_step"
    config.titration_params["reaction_steps"] = 3
    config.titration_params["reaction_components"] = [
        {"name": "Hematite", "total": 6e-6, "start": 1.0, "end": 1.0, "mode": "linear"},
        {"name": "Chalcopyrite(alpha)", "total": 6e-6, "start": 1.0, "end": 4.0, "mode": "exp"},
    ]

    script = build_phreeqc_script(config)

    assert "add_Hematite" in script
    assert "IF (SIM_NO = 1) THEN add_1 = 2e-06" in script
    assert "IF (SIM_NO = 3) THEN add_1 = 2e-06" in script
    assert "IF (SIM_NO = 3) THEN add_2 =" in script
    assert "10000 PUNCH SIM_NO" in script


def test_build_titration_component_can_be_limited_to_step_window():
    config = default_model_config()
    config.simulation_kind = "titration"
    config.titration_params["mode"] = "inventory_step"
    config.titration_params["reaction_steps"] = 5
    config.titration_params["reaction_components"] = [
        {
            "name": "Hematite",
            "total": 9e-6,
            "start": 1.0,
            "end": 1.0,
            "mode": "linear",
            "shape_k": 3.0,
            "start_step": 2,
            "end_step": 4,
        }
    ]

    script = build_phreeqc_script(config)

    assert "IF (SIM_NO = 1) THEN add_1 = 0.0" in script
    assert "IF (SIM_NO = 2) THEN add_1 = 3e-06" in script
    assert "IF (SIM_NO = 4) THEN add_1 = 3e-06" in script
    assert "IF (SIM_NO = 5) THEN add_1 = 0.0" in script


def test_build_titration_solution_component_step_adds_redox_components_without_phase_inventory():
    config = default_model_config()
    config.simulation_kind = "titration"
    config.titration_params["mode"] = "solution_component_step"
    config.titration_params["reaction_steps"] = 2
    config.titration_params["reaction_components"] = [
        {
            "name": "Cu(1)",
            "addition_type": "solution",
            "total": 2e-6,
            "start": 1.0,
            "end": 1.0,
            "mode": "linear",
            "shape_k": 3.0,
            "start_step": 1,
            "end_step": 2,
        },
        {
            "name": "Au(3)",
            "addition_type": "solution",
            "total": 4e-6,
            "start": 1.0,
            "end": 1.0,
            "mode": "linear",
            "shape_k": 3.0,
            "start_step": 2,
            "end_step": 2,
        },
    ]

    script = build_phreeqc_script(config)

    assert "TITLE Batch titration with coupled phase and solution additions" in script
    assert "# --- Phase+solution step 0002 ---" in script
    assert not any(line.startswith("REACTION ") for line in script.splitlines())
    assert "add_Cu(1)" in script
    assert "add_Au(3)" in script
    assert "MIX 1" in script
    assert "USE mix 1" in script
    assert "Cu(1)" in script
    assert "1e-06" in script
    assert "Au(3)" in script
    assert "4e-06" in script
    assert "EQUILIBRIUM_PHASES 2\n    Cu(1)" not in script


def test_build_titration_phase_solution_step_combines_phase_inventory_and_solution_mixing():
    config = default_model_config()
    config.simulation_kind = "titration"
    config.titration_params["mode"] = "phase_solution_step"
    config.titration_params["reaction_steps"] = 2
    config.titration_params["reaction_components"] = [
        {
            "name": "Hematite",
            "addition_type": "phase",
            "total": 2e-6,
            "start": 1.0,
            "end": 1.0,
            "mode": "linear",
            "start_step": 1,
            "end_step": 2,
        },
        {
            "name": "Cu(1)",
            "addition_type": "solution",
            "total": 4e-6,
            "start": 1.0,
            "end": 1.0,
            "mode": "linear",
            "start_step": 1,
            "end_step": 2,
        },
    ]

    script = build_phreeqc_script(config)

    assert "TITLE Batch titration with coupled phase and solution additions" in script
    assert "# --- Phase+solution step 0002 ---" in script
    assert "EQUILIBRIUM_PHASES 2\n    Hematite" in script
    assert "EQUILIBRIUM_PHASES 2\n    Cu(1)" not in script
    assert not any(line.startswith("REACTION ") for line in script.splitlines())
    assert "MIX 2" in script
    assert "USE mix 2" in script
    assert "Hematite" in script
    assert "Cu(1)" in script
    assert "add_Hematite" in script
    assert "add_Cu(1)" in script
