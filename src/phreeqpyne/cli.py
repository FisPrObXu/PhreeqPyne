"""Command-line entry point for PhreeqPyne."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ModelConfig, default_model_config
from .phreeqc_builder import build_phreeqc_script
from .runner import run_simulation
from .simulations import list_simulations


def _load_config(path: Path | None) -> ModelConfig:
    if path is None:
        return default_model_config()
    return ModelConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))


def cmd_init_config(args: argparse.Namespace) -> int:
    config = default_model_config()
    output_path = Path(args.output)
    output_path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote default config: {output_path}")
    return 0


def cmd_build_script(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    script = build_phreeqc_script(config)
    if args.output is None:
        print(script)
    else:
        args.output.write_text(script, encoding="utf-8")
        print(f"Wrote PHREEQC input: {args.output}")
    return 0


def cmd_list_simulations(args: argparse.Namespace) -> int:
    for item in list_simulations():
        print(f"{item.kind}	{item.display_name}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui.qt_app import main as gui_main

    return gui_main([])


def cmd_run(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    result = run_simulation(config)
    output_dir = config.output_path
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = output_dir / "phreeqpyne_input.phr"
    csv_path = output_dir / "selected_output.csv"
    script_path.write_text(result.script, encoding="utf-8")
    result.selected_output.to_csv(csv_path, index=False)
    print(f"Wrote PHREEQC input: {script_path}")
    print(f"Wrote selected output: {csv_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PhreeqPyne CFAS multistage simulation tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-config", help="write a default JSON scenario config")
    init_parser.add_argument("--output", default="phreeqpyne.config.json", help="output JSON path")
    init_parser.set_defaults(func=cmd_init_config)

    list_parser = subparsers.add_parser("list-simulations", help="list registered simulation workflows")
    list_parser.set_defaults(func=cmd_list_simulations)

    gui_parser = subparsers.add_parser("gui", help="open the optional Qt scenario editor")
    gui_parser.set_defaults(func=cmd_gui)

    script_parser = subparsers.add_parser("build-script", help="render a PHREEQC input file without running IPhreeqc")
    script_parser.add_argument("--config", type=Path, help="JSON config path")
    script_parser.add_argument("--output", type=Path, help="output PHREEQC input path; prints to stdout when omitted")
    script_parser.set_defaults(func=cmd_build_script)

    run_parser = subparsers.add_parser("run", help="run IPhreeqc and write output artifacts")
    run_parser.add_argument("--config", type=Path, help="JSON config path")
    run_parser.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
