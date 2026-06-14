import pytest
import pandas as pd

from phreeqpyne.config import default_model_config
from phreeqpyne.phreeqc_builder import build_phreeqc_script
from phreeqpyne.runner import add_cell_columns, add_phase_percent_columns, prepare_selected_output
from phreeqpyne.simulations import get_simulation_builder, list_simulations


def test_transport_workflow_is_registered():
    simulations = {item.kind: item.display_name for item in list_simulations()}

    assert simulations["transport"] == "1D multistage TRANSPORT"
    assert simulations["titration"] == "Batch mineral titration"
    assert get_simulation_builder("transport").kind == "transport"
    assert get_simulation_builder("titration").kind == "titration"


def test_build_phreeqc_script_dispatches_by_simulation_kind():
    config = default_model_config()
    config.simulation_kind = "transport"

    assert "TRANSPORT" in build_phreeqc_script(config)

    config.simulation_kind = "titration"

    titration_script = build_phreeqc_script(config)
    assert "Phase+solution step" in titration_script
    assert not any(line.startswith("REACTION ") for line in titration_script.splitlines())


def test_unknown_simulation_kind_fails_with_available_kinds():
    config = default_model_config()
    config.simulation_kind = "equilibrium-batch"

    with pytest.raises(ValueError, match="Available kinds: titration, transport"):
        build_phreeqc_script(config)


def test_selected_output_gets_cell_columns_from_solution_number():
    output = pd.DataFrame({"soln": [0, 1, 2], "pH": [8.0, 7.9, 7.8]})

    augmented = add_cell_columns(output)

    assert list(augmented.columns) == ["soln", "cell", "cell_plot", "pH"]
    assert augmented["cell"].tolist() == [0, 1, 2]
    assert augmented["cell_plot"].tolist() == [0, 1, 2]


def test_selected_output_cell_columns_are_transport_only():
    output = pd.DataFrame({"soln": [1, 1, 1], "rxn_step": [1, 2, 3], "pH": [8.0, 7.9, 7.8]})

    transport_config = default_model_config()
    transport_config.simulation_kind = "transport"
    transport_output = prepare_selected_output(output, transport_config)

    titration_config = default_model_config()
    titration_config.simulation_kind = "titration"
    titration_output = prepare_selected_output(output, titration_config)

    assert "cell" in transport_output.columns
    assert "cell_plot" in transport_output.columns
    assert "cell" not in titration_output.columns
    assert "cell_plot" not in titration_output.columns
    assert titration_output["rxn_step"].tolist() == [1, 2, 3]


def test_selected_output_gets_phase_percent_columns():
    output = pd.DataFrame({
        "Magnetite": [2.0, 0.0],
        "Pyrite": [1.0, 0.0],
        "HematitePK_m": [1.0, 0.0],
    })

    augmented = add_phase_percent_columns(output)

    percent_columns = ["Magnetite_pct", "Pyrite_pct", "HematitePK_m_pct"]
    assert augmented.loc[0, percent_columns].sum() == pytest.approx(100.0)
    assert augmented.loc[1, percent_columns].sum() == pytest.approx(0.0)
