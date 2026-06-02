import pytest

from phreeqpyne.config import default_model_config
from phreeqpyne.phreeqc_builder import build_phreeqc_script
from phreeqpyne.simulations import get_simulation_builder, list_simulations


def test_transport_workflow_is_registered():
    simulations = {item.kind: item.display_name for item in list_simulations()}

    assert simulations["transport"] == "1D multistage TRANSPORT"
    assert get_simulation_builder("transport").kind == "transport"


def test_build_phreeqc_script_dispatches_by_simulation_kind():
    config = default_model_config()
    config.simulation_kind = "transport"

    assert "TRANSPORT" in build_phreeqc_script(config)


def test_unknown_simulation_kind_fails_with_available_kinds():
    config = default_model_config()
    config.simulation_kind = "equilibrium-batch"

    with pytest.raises(ValueError, match="Available kinds: transport"):
        build_phreeqc_script(config)
