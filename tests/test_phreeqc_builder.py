import pytest

from phreeqpyne.config import default_model_config
from phreeqpyne.phreeqc_builder import build_phreeqc_script, build_stage_blocks


def test_build_phreeqc_script_contains_core_blocks():
    script = build_phreeqc_script(default_model_config())

    assert "CALCULATE_VALUES" in script
    assert "RATES\nHematite_PK" in script
    assert "KINETICS 1-30" in script
    assert script.count("TRANSPORT") == 8
    assert "# --- Stage 08 ---" in script
    assert script.endswith("END")


def test_build_stage_blocks_validates_stage_shift_count():
    config = default_model_config()
    config.stage_shifts = [1]

    with pytest.raises(ValueError, match="stage_shifts"):
        build_stage_blocks(config)
