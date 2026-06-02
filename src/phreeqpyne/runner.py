"""Runtime integration with IPhreeqc.

The import of :mod:`phreeqpy` is intentionally local to ``run_simulation`` so
configuration and PHREEQC input generation remain testable on machines that do
not have the IPhreeqc DLL/SO installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import ModelConfig
from .phreeqc_builder import build_phreeqc_script


@dataclass(slots=True)
class SimulationResult:
    """In-memory result returned by a PHREEQC execution."""

    script: str
    selected_output: object


def run_simulation(config: ModelConfig) -> SimulationResult:
    """Run IPhreeqc with the configured database and return selected output."""

    import pandas as pd
    import phreeqpy.iphreeqc.phreeqc_dll as phreeqc_mod

    script = build_phreeqc_script(config)
    phreeqc = phreeqc_mod.IPhreeqc(config.runtime.dll_path)
    phreeqc.load_database(config.runtime.database_path)
    phreeqc.run_string(script)

    output = phreeqc.get_selected_output_array()
    if not output:
        return SimulationResult(script=script, selected_output=pd.DataFrame())

    header = [str(column).strip() for column in output[0]]
    return SimulationResult(script=script, selected_output=pd.DataFrame(output[1:], columns=header))
