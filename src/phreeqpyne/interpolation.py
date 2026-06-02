"""Interpolation helpers for staged boundary fluids.

These functions lift the notebook's stage-fluid interpolation logic into a
reusable module so scenario definitions can be tested without starting PHREEQC.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import math


def _clip_unit_interval(value: float) -> float:
    return min(1.0, max(0.0, value))


def _is_close_to_zero(value: float) -> bool:
    return math.isclose(value, 0.0, abs_tol=1e-12)


def transform_progress(progress: float, mode: str = "linear", shape_k: float = 3.0) -> float:
    """Transform a 0..1 stage progress value with a named interpolation curve."""

    p = _clip_unit_interval(float(progress))
    mode_normalized = str(mode).lower()
    k = float(shape_k)

    if mode_normalized == "linear":
        return p
    if mode_normalized == "exp":
        if _is_close_to_zero(k):
            return p
        return float((math.exp(k * p) - 1.0) / (math.exp(k) - 1.0))
    if mode_normalized == "log":
        k_abs = abs(k)
        if _is_close_to_zero(k_abs):
            return p
        return float(math.log1p(k_abs * p) / math.log1p(k_abs))

    raise ValueError(f"Unknown interpolation mode: {mode}")


def interpolate_stage_value(
    start: float,
    end: float,
    progress: float,
    mode: str = "linear",
    shape_k: float = 3.0,
) -> float:
    """Interpolate one scalar composition value for a stage."""

    curve_progress = transform_progress(progress=progress, mode=mode, shape_k=shape_k)
    return float(start + (end - start) * curve_progress)


def build_stage_boundary_fluids(
    n_stages: int,
    boundary_base: Mapping[str, Any],
    boundary_interpolation: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build one boundary fluid dictionary for each simulation stage."""

    if n_stages < 1:
        raise ValueError("n_stages must be at least 1")

    fluids: list[dict[str, Any]] = []
    for stage_index in range(1, n_stages + 1):
        progress = 0.0 if n_stages <= 1 else (stage_index - 1) / (n_stages - 1)
        stage_fluid = dict(boundary_base)
        for species, spec in boundary_interpolation.items():
            stage_fluid[species] = interpolate_stage_value(
                start=float(spec["start"]),
                end=float(spec["end"]),
                progress=progress,
                mode=str(spec.get("mode", "linear")),
                shape_k=float(spec.get("shape_k", 3.0)),
            )
        fluids.append(stage_fluid)

    return fluids
