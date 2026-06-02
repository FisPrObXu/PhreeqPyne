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
    n_cells: int = 30
    n_stages: int = 8
    stage_shifts: list[int] = field(default_factory=lambda: [20, 20, 20, 20, 20, 20, 20, 20])
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
        "Na": 1.05,
        "Cl": 0.50,
        "K": 1e-3,
        "P(5)": 0.10,
        "Cu(1)": 3.5e-4,
        "Fe(3)": 2.0e-4,
        "S(-2)": 1.5e-2,
        "Au(3)": 1.0e-4,
        "water": 0.008,
    })
    equilibrium_phases: list[tuple[Any, ...]] = field(default_factory=lambda: [
        ("Pyrite", 0, 0),
        ("Chalcopyrite(alpha)", 0, 0),
        ("Bornite(alpha)", 0, 0),
        ("Magnetite", 0, 0),
        ("Chalcocite(alpha)", 0, 0),
        ("Cu(element)", 0, 0),
        ("Au(element)", 0, 0),
    ])
    hematite_kinetics: dict[str, Any] = field(default_factory=lambda: {
        "rate_name": "Hematite_PK",
        "m0": 1.0e-3,
        "m": 1.0e-3,
        "steps": 1,
        "affinity_factor": 1.0,
        "sp_area": 9.8,
        "roughness": 1.0,
        "lgkH": -4.6,
        "e_H": 0.0,
        "nH": 1.0,
        "lgkH2O": -10.3,
        "e_H2O": 0.0,
        "lgkOH": -13.5,
        "e_OH": 0.0,
        "nOH": 1.0,
    })
    transport_params: dict[str, Any] = field(default_factory=lambda: {
        "time_step": 1.0e5,
        "lengths": 0.01,
        "flow_direction": "forward",
        "boundary_conditions": "constant closed",
    })
    plot: dict[str, Any] = field(default_factory=lambda: {"target_cells": [5, 10, 20, 30]})

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
