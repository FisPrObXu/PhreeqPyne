"""Typed configuration objects for project-level PhreeqPyne simulations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RuntimeConfig:
    """Paths and output behavior needed by the PHREEQC runtime."""

    dll_path: str = r"D:\USGS\IPhreeqcCOM 3.8.6-17100\bin\IPhreeqcCOM.dll"
    database_path: str = r"D:\USGS\IPhreeqcCOM 3.8.6-17100\database\PHREEQC_ThermoddemV1.10_15Dec2020.dat"
    output_dir: str = "."
    print_full_header: bool = False


@dataclass(slots=True)
class ModelConfig:
    """Serializable scenario configuration extracted from the notebook."""

    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    simulation_kind: str = "transport"
    n_cells: int = 10
    n_stages: int = 8
    stage_shifts: list[int] = field(default_factory=lambda: [2, 3, 4, 10, 15, 16, 19, 20])
    boundary_base: dict[str, Any] = field(default_factory=lambda: {
        "temp": 240,
        "pressure": 27,
        "units": "mol/kgw",
        "pH": 8.0,
        "pe": 0.0,
        "Na": 1.05,
        "Cl": 0.50,
        "K": 1e-3,
        "P(5)": 0.10,
        "water": 0.008,
    })
    boundary_interpolation: dict[str, dict[str, Any]] = field(default_factory=lambda: {
        "Cu(1)": {"start": 6.5e-4, "end": 4.1e-4, "mode": "exp", "shape_k": 3.0},
        "Fe(3)": {"start": 3.0e-4, "end": 5.0e-4, "mode": "exp", "shape_k": 3.0},
        "S(-2)": {"start": 2.4e-2, "end": 2.0e-2, "mode": "exp", "shape_k": 5.0},
        "Au(3)": {"start": 1.0e-4, "end": 1.0e-4, "mode": "linear"},
    })
    initial_pore_solution: dict[str, Any] = field(default_factory=lambda: {
        "temp": 240,
        "pressure": 27,
        "units": "mol/kgw",
        "pH": 8.0,
        "pe": 0.0,
        "Na": 1e-1,
        "Cl": 1e-1,
        "K": 1e-10,
        "P(5)": 0.0,
        "Cu(2)": 5e-5,
        "Fe(3)": 1e-5,
        "S(-2)": 0.0,
        "Au(3)": 0.0,
        "water": 0.008,
    })
    initial_pore_gradient: dict[str, Any] = field(default_factory=lambda: {
        "species": {
            species: {"mode": "log", "shape_k": 5.0, "shell_factor": 1.0, "core_factor": 0.1}
            for species in ["Na", "Cl", "K", "P(5)", "Cu(2)", "Fe(3)", "S(-2)", "Au(3)"]
        },
    })
    equilibrium_phases: list[tuple[Any, ...]] = field(default_factory=lambda: [
        ("Pyrite", 0.8, 0, None),
        ("Chalcopyrite(alpha)", -2.0, 0, None),
        ("Bornite(alpha)", -1.0, 0, None),
        ("Magnetite", 0.6, 0, None),
        ("Chalcocite(alpha)", 1.0, 0, None),
        ("Au(element)", 0, 0, None),
        ("Cu(element)", 0, 0, None),
    ])
    hematite_kinetics: dict[str, Any] = field(default_factory=lambda: {
        "rate_name": "Hematite_PK",
        "formula": "Fe2O3",
        "m": 5e-7,
        "m0": 5e-7,
        "affinity_factor": 0,
        "sp_area": 1.0e3,
        "roughness": 10,
        "lgkH": -9.39,
        "e_H": 66.2,
        "nH": 1,
        "lgkH2O": -14.6,
        "e_H2O": 66.2,
        "lgkOH": -30,
        "e_OH": 0.0,
        "nOH": 0,
        "tol": 1e-8,
        "step_divide": 10,
        "runge_kutta": 3,
        "bad_step_max": 500,
    })
    transport_params: dict[str, Any] = field(default_factory=lambda: {
        "time_step": 1.0e4,
        "flow_direction": "diffusion_only",
        "boundary_conditions": "constant closed",
        "lengths": 1e-3,
        "dispersivities": 1e-6,
        "diffusion_coefficient": 1e-9,
        "correct_disp": None,
        "punch_cells": None,
        "punch_frequency": 1,
    })
    titration_params: dict[str, Any] = field(default_factory=lambda: {
        "mode": "manual_step",
        "solution_source": "reaction_solution",
        "reaction_components": [
            {
                "name": "Hematite",
                "total": 5e-4,
                "start": 1.0,
                "end": 1.0,
                "mode": "linear",
                "shape_k": 3.0,
                "start_step": 1,
                "end_step": None,
                "addition_type": "phase",
            }
        ],
        "reaction_steps": 1000,
        "incremental_reactions": True,
    })
    selected_output: dict[str, Any] = field(default_factory=lambda: {
        "totals": ["Na", "Cl", "K", "P", "Cu", "Fe", "S", "Au", "P(5)", "Cu(1)", "Cu(2)", "Fe(2)", "Fe(3)", "S(-2)", "S(6)", "Au(1)", "Au(3)"],
        "molalities": ["Fe+2", "Fe+3", "FeOH+", "FeOH+2", "FeCl+", "FeCl+2", "FeCl2", "FeCl2+", "Fe(OH)4-"],
        "activities": [
            "SO4-2", "Cu(HS)2-", "Au(HS)2-", "AuHS", "H+", "OH-", "HS-", "H2S",
            "Au(OH)2-", "Au+", "Au+3", "AuCl", "AuCl2-", "AuCl3-2", "AuCl4-", "AuOH",
            "Cu2S(HS)2-2", "CuCl+", "CuCl2", "CuCl2-", "CuCl3-", "CuCl3-2",
            "CuCl4-2", "CuHS", "CuCl", "CuOH", "CuOH+", "H2S", "HS-", "S-2",
        ],
        "equilibrium_phases": ["Magnetite", "Chalcocite(alpha)", "Chalcopyrite(alpha)", "Bornite(alpha)", "Au(element)", "Pyrite", "Cu(element)"],
        "saturation_indices": ["Hematite", "Magnetite", "Chalcocite(alpha)", "Pyrite", "Chalcopyrite(alpha)", "Bornite(alpha)", "Cu(element)", "Au(element)"],
        "kinetic_reactants": ["Hematite_PK"],
    })
    plot: dict[str, Any] = field(default_factory=lambda: {"target_cells": [1, 4, 7, 10]})

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelConfig":
        """Create a config from a dictionary, ignoring absent optional sections."""

        values = dict(data)
        if "runtime" in values and isinstance(values["runtime"], dict):
            values["runtime"] = RuntimeConfig(**values["runtime"])
        return cls(**values)

    @property
    def output_path(self) -> Path:
        """Resolved output directory."""

        return Path(self.runtime.output_dir).resolve()


def default_model_config() -> ModelConfig:
    """Return the default CFAS scenario configuration."""

    return ModelConfig()
