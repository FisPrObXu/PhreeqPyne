"""Reusable PHREEQC input blocks shared by simulation workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _format_solution_component(name: str, value: Any) -> str:
    return f"    {name:<12} {value}"


def build_solution_block(number: int, cfg: Mapping[str, Any], title: str | None = None) -> str:
    """Build a PHREEQC SOLUTION block from a solution dictionary."""

    lines = [f"SOLUTION {number}" if title is None else f"SOLUTION {number} {title}"]
    preferred_order = ["temp", "pressure", "units", "pH", "pe"]
    emitted = set()
    for key in preferred_order:
        if key in cfg:
            lines.append(_format_solution_component(key, cfg[key]))
            emitted.add(key)
    for key, value in cfg.items():
        if key not in emitted:
            lines.append(_format_solution_component(key, value))
    return "\n".join(lines)


def build_calculate_values_block() -> str:
    """Build the notebook's hematite saturation calculation block."""

    return """
CALCULATE_VALUES
SR_m_Hematite
-start
10 m = MOL("H+")
20 IF (m <= 0) THEN m = 1e-30
30 SR = SI("Hematite")
40 m_Hematite = 10^((2*LA("Fe+3") + 3*LA("H2O") - 6*LA("H+")) - LK_PHASE("Hematite"))
50 SAVE m_Hematite
-end
""".strip()


def build_rates_block(kin_cfg: Mapping[str, Any]) -> str:
    """Build the notebook's kinetic hematite dissolution RATES block."""

    return f"""
RATES
{kin_cfg['rate_name']}
-start
10 if (M <= 0) then goto 200
20 si_h = SI("Hematite")
30 if (si_h >= 0) then goto 200
40 aH = ACT("H+")
50 if (aH <= 1e-30) then aH = 1e-30
60 area = PARM(2) * PARM(3) * (M/M0)^PARM(4)
70 kH = 10^(PARM(5) - PARM(6)/TK) * (aH^PARM(7))
80 kH2O = 10^(PARM(8) - PARM(9)/TK)
90 kOH = 10^(PARM(10) - PARM(11)/TK) * (aH^(-PARM(12)))
100 rate = area * (kH + kH2O + kOH) * (1 - 10^(si_h))
110 if (rate < 0) then rate = 0
120 moles = rate * TIME
130 if (moles > M) then moles = M
200 SAVE moles
-end
""".strip()


def build_equilibrium_phases_block(n_cells: int, phases: Sequence[Sequence[Any]]) -> str:
    """Build an EQUILIBRIUM_PHASES range block."""

    lines = [f"EQUILIBRIUM_PHASES 1-{n_cells}"]
    for phase in phases:
        if len(phase) == 4:
            name, si, amount, option = phase
            suffix = "" if option is None or str(option).strip() == "" else f" {option}"
            lines.append(f"    {name:<24} {si} {amount}{suffix}")
        elif len(phase) == 3:
            name, si, amount = phase
            lines.append(f"    {name:<24} {si} {amount}")
        else:
            raise ValueError(f"Invalid equilibrium phase tuple: {phase}")
    return "\n".join(lines)


def build_kinetics_block(n_cells: int, kin_cfg: Mapping[str, Any]) -> str:
    """Build the KINETICS block for the hematite kinetic reactant."""

    parms = [
        kin_cfg["affinity_factor"],
        kin_cfg["sp_area"],
        kin_cfg["roughness"],
        0.67,
        kin_cfg["lgkH"],
        kin_cfg["e_H"],
        kin_cfg["nH"],
        kin_cfg["lgkH2O"],
        kin_cfg["e_H2O"],
        kin_cfg["lgkOH"],
        kin_cfg["e_OH"],
        kin_cfg["nOH"],
    ]
    parms_text = " ".join(str(value) for value in parms)
    return f"""
KINETICS 1-{n_cells}
{kin_cfg['rate_name']}
    -formula Hematite 1
    -m0 {kin_cfg['m0']}
    -m  {kin_cfg['m']}
    -parms {parms_text}
    -steps {kin_cfg['steps']}
""".strip()


def build_initial_cells_block(
    n_cells: int,
    pore_cfg: Mapping[str, Any],
    phases: Sequence[Sequence[Any]],
    kin_cfg: Mapping[str, Any],
) -> str:
    """Build initial solution, equilibrium phases, and kinetics for all cells."""

    return "\n\n".join(
        [
            build_solution_block(1, pore_cfg, "Initial pore fluid"),
            f"COPY solution 1 {n_cells}",
            build_equilibrium_phases_block(n_cells, phases),
            build_kinetics_block(n_cells, kin_cfg),
        ]
    )


def make_selected_output_block(stage_index: int, user_number: int = 1) -> str:
    """Build a compact SELECTED_OUTPUT block with stage identification."""

    return f"""
SELECTED_OUTPUT {user_number}
    -reset false
    -simulation true
    -state true
    -solution true
    -distance true
    -time true
    -step true
    -pH true
    -pe true
    -temperature true
USER_PUNCH {user_number}
    -headings stage
    -start
    10 PUNCH {stage_index}
    -end
""".strip()
