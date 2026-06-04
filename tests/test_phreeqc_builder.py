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
