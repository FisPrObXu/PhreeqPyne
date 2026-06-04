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
    selected_output = pd.DataFrame(output[1:], columns=header)
    selected_output = add_cell_columns(selected_output)
    selected_output = add_phase_percent_columns(selected_output, config)
    return SimulationResult(script=script, selected_output=selected_output)


def add_cell_columns(selected_output: object) -> object:
    """Add notebook-compatible cell coordinate columns to selected output."""

    import pandas as pd

    if not isinstance(selected_output, pd.DataFrame) or selected_output.empty:
        return selected_output
    if "cell" in selected_output.columns and "cell_plot" in selected_output.columns:
        return selected_output

    source_column = None
    for candidate in ["soln", "solution"]:
        if candidate in selected_output.columns:
            source_column = candidate
            break
    if source_column is None:
        return selected_output

    result = selected_output.copy()
    cell_values = pd.to_numeric(result[source_column], errors="coerce")
    if "cell" not in result.columns:
        insert_at = result.columns.get_loc(source_column) + 1
        result.insert(insert_at, "cell", cell_values)
    if "cell_plot" not in result.columns:
        insert_at = result.columns.get_loc("cell") + 1
        result.insert(insert_at, "cell_plot", cell_values)
    return result


def add_phase_percent_columns(selected_output: object, config: ModelConfig | None = None) -> object:
    """Add row-wise 100% mineral phase columns for stack-area plotting."""

    import pandas as pd

    if not isinstance(selected_output, pd.DataFrame) or selected_output.empty:
        return selected_output

    result = selected_output.copy()
    phase_columns = _phase_amount_columns(result, config)
    if not phase_columns:
        return result

    amounts = result[phase_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    amounts = amounts.clip(lower=0.0)
    row_sum = amounts.sum(axis=1)
    valid = row_sum > 0
    for column in phase_columns:
        percent_column = f"{column}_pct"
        values = pd.Series(0.0, index=result.index)
        values.loc[valid] = amounts.loc[valid, column] / row_sum.loc[valid] * 100.0
        result[percent_column] = values
    return result


def _phase_amount_columns(selected_output: object, config: ModelConfig | None = None) -> list[str]:
    configured_phases: list[str] = []
    if config is not None:
        configured_phases.extend(str(phase[0]) for phase in config.equilibrium_phases)
        configured_phases.extend(str(name) for name in config.selected_output.get("kinetic_reactants", []))
    candidates = [
        "HematitePK_m",
        *configured_phases,
        "Magnetite",
        "Chalcocite(alpha)",
        "Chalcopyrite(alpha)",
        "Bornite(alpha)",
        "Au(element)",
        "Pyrite",
        "Cu(element)",
    ]
    columns: list[str] = []
    for candidate in candidates:
        if candidate in selected_output.columns and candidate not in columns:
            columns.append(candidate)
    return columns
