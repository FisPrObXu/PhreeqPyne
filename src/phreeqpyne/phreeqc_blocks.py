"""Reusable PHREEQC input blocks shared by simulation workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from phreeqpyne.interpolation import transform_progress


def _format_solution_component(name: str, value: Any) -> str:
    return f"    {name:<12} {value}"


def build_solution_block(number: int | str, cfg: Mapping[str, Any], title: str | None = None) -> str:
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
            if key == "water":
                lines.append(f"    -water      {value}")
            else:
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
    """Build the configured PHREEQC RATES block."""

    custom_rates = str(kin_cfg.get("rates_block", "")).strip()
    if custom_rates:
        return custom_rates

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
    """Build a KINETICS block for the configured kinetic reactant."""

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
    -formula  {kin_cfg.get('formula', 'Fe2O3')}  1
    -m      {kin_cfg['m']}
    -m0     {kin_cfg['m0']}
    -parms  {parms_text}
    -tol    {kin_cfg.get('tol', 1e-8)}
    -step_divide {kin_cfg.get('step_divide', 10)}
    -runge_kutta {kin_cfg.get('runge_kutta', 3)}
    -bad_step_max {kin_cfg.get('bad_step_max', 500)}
""".strip()


def build_initial_cells_block(
    n_cells: int,
    pore_cfg: Mapping[str, Any],
    phases: Sequence[Sequence[Any]],
    kin_cfg: Mapping[str, Any],
    gradient_cfg: Mapping[str, Any] | None = None,
) -> str:
    """Build initial solution, equilibrium phases, and kinetics for all cells."""

    gradient_cfg = gradient_cfg or {}
    species_cfg = gradient_cfg.get("species", {})
    if isinstance(species_cfg, Mapping):
        gradient_species = set(species_cfg)
    else:
        gradient_species = set(species_cfg)
        species_cfg = {
            species: {
                "mode": gradient_cfg.get("mode", "linear"),
                "shape_k": gradient_cfg.get("shape_k", 3.0),
                "shell_factor": gradient_cfg.get("shell_factor", 1.0),
                "core_factor": gradient_cfg.get("core_factor", gradient_cfg.get("shell_factor", 1.0)),
            }
            for species in gradient_species
        }

    def scaled_value(name: str, base_value: Any, progress: float) -> Any:
        if name not in gradient_species:
            return base_value
        spec = species_cfg.get(name, {})
        shell_factor = float(spec.get("shell_factor", 1.0))
        core_factor = float(spec.get("core_factor", shell_factor))
        gradient_mode = str(spec.get("mode", "linear"))
        gradient_shape_k = float(spec.get("shape_k", 3.0))
        mapped = transform_progress(progress=progress, mode=gradient_mode, shape_k=gradient_shape_k)
        return float(base_value) * (shell_factor + (core_factor - shell_factor) * mapped)

    lines: list[str] = []
    for cell in range(1, n_cells + 1):
        progress = 0.0 if n_cells == 1 else (cell - 1) / (n_cells - 1)
        lines.extend(
            [
                f"SOLUTION {cell}  Initial Alkaline Pore Fluid (shell->core gradient)",
                f"    temp      {pore_cfg['temp']}",
                f"    pressure  {pore_cfg['pressure']}",
                f"    units     {pore_cfg['units']}",
                f"    pH        {pore_cfg['pH']}",
                f"    pe        {pore_cfg['pe']}",
                "    redox     pe",
                f"    Na        {scaled_value('Na', pore_cfg['Na'], progress)}",
                f"    Cl        {scaled_value('Cl', pore_cfg['Cl'], progress)} charge",
                f"    P(5)      {scaled_value('P(5)', pore_cfg['P(5)'], progress)}",
                f"    Cu(2)     {scaled_value('Cu(2)', pore_cfg['Cu(2)'], progress)}",
                f"    Fe(3)     {scaled_value('Fe(3)', pore_cfg['Fe(3)'], progress)}",
                f"    S(-2)     {scaled_value('S(-2)', pore_cfg['S(-2)'], progress)}",
                f"    Au(3)     {scaled_value('Au(3)', pore_cfg['Au(3)'], progress)}",
            ]
        )
        if "K" in pore_cfg:
            lines.append(f"    K         {scaled_value('K', pore_cfg['K'], progress)}")
        lines.extend([f"    -water    {pore_cfg['water']}", ""])

    lines.extend([build_equilibrium_phases_block(n_cells, phases), "", build_kinetics_block(n_cells, kin_cfg)])
    return "\n".join(lines).strip()


def build_boundary_solution0_block(cfg: Mapping[str, Any], fallback_cfg: Mapping[str, Any]) -> str:
    """Build and save the external boundary solution used by staged TRANSPORT."""

    stage_label = cfg.get("stage_label", f"Stage-{cfg.get('stage_index', '')}".strip("-"))
    lines = [
        f"SOLUTION 0  External boundary fluid at outer shell rim ({stage_label})",
        f"    temp      {cfg['temp']}",
        f"    pressure  {cfg['pressure']}",
        f"    pH        {cfg.get('pH', fallback_cfg['pH'])}",
        f"    pe        {cfg.get('pe', fallback_cfg['pe'])}",
        "    redox     pe",
        f"    units     {cfg['units']}",
        f"    Na        {cfg['Na']}",
        f"    Cl        {cfg['Cl']} charge",
        f"    P(5)      {cfg['P(5)']}",
        f"    Cu(1)     {cfg.get('Cu(1)', cfg.get('cu_value'))}",
        f"    Fe(3)     {cfg.get('Fe(3)', cfg.get('fe_value'))}",
        f"    S(-2)     {cfg.get('S(-2)', cfg.get('s_value'))}",
        f"    Au(3)     {cfg.get('Au(3)', cfg.get('au_value'))}",
    ]
    if "K" in cfg:
        lines.append(f"    K         {cfg['K']}")
    lines.extend([f"    -water    {cfg['water']}", "SAVE solution 0"])
    return "\n".join(lines).strip()


def _selected_output_line(keyword: str, values: Sequence[str]) -> str:
    return f"    {keyword:<22} {'  '.join(values)}" if values else ""


def make_selected_output_block(
    stage_index: int,
    selected_output: Mapping[str, Sequence[str]] | None = None,
    rate_name: str = "Hematite_PK",
    user_number: int = 1,
) -> str:
    """Build the notebook's extended SELECTED_OUTPUT block with stage identification."""

    selected_output = selected_output or {}
    optional_lines = [
        _selected_output_line("-totals", selected_output.get("totals", [])),
        _selected_output_line("-molalities", selected_output.get("molalities", [])),
        _selected_output_line("-activities", selected_output.get("activities", [])),
        _selected_output_line("-equilibrium_phases", selected_output.get("equilibrium_phases", [])),
        _selected_output_line("-saturation_indices", selected_output.get("saturation_indices", [])),
        _selected_output_line("-kinetic_reactants", selected_output.get("kinetic_reactants", [rate_name])),
    ]
    optional_text = "\n".join(line for line in optional_lines if line)

    return f"""
TITLE Shell-to-core diffusion replacement: Sequential Stage {stage_index}
SELECTED_OUTPUT {user_number}
    -reset false
    -step true
    -soln true
    -dist true
    -time true
    -temperature true
    -pH true
    -pe true
    -charge_balance true
    -percent_error true
{optional_text}
USER_PUNCH {user_number}
    -headings stage u_step time_days pH_user logaHS- logaH2S SR_Hematite HematitePK_m
    -start
10 PUNCH {stage_index}, STEP_NO, TOTAL_TIME/3600/24, -LA("H+"), LA("HS-"), LA("H2S"), SR("Hematite"), KIN("{rate_name}")
    -end
""".strip()
