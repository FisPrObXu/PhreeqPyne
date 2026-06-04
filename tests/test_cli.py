import json

from phreeqpyne.cli import main


def test_cli_init_config_and_build_script(tmp_path):
    config_path = tmp_path / "scenario.json"
    script_path = tmp_path / "scenario.phr"

    assert main(["init-config", "--output", str(config_path)]) == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["n_stages"] == 8

    assert main(["build-script", "--config", str(config_path), "--output", str(script_path)]) == 0
    script = script_path.read_text(encoding="utf-8")
    assert "SOLUTION 0  External boundary fluid at outer shell rim (Stage-1)" in script
    assert "-flow_direction        diffusion_only" in script
    assert "-totals" in script
    assert "TRANSPORT" in script


def test_cli_list_simulations(capsys):
    assert main(["list-simulations"]) == 0
    output = capsys.readouterr().out
    assert "transport" in output
    assert "1D multistage TRANSPORT" in output
