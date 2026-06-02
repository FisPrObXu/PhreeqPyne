import pytest

from phreeqpyne.interpolation import build_stage_boundary_fluids, interpolate_stage_value, transform_progress


def test_transform_progress_linear_clips_range():
    assert transform_progress(-1.0) == 0.0
    assert transform_progress(2.0) == 1.0
    assert transform_progress(0.25) == 0.25


def test_interpolate_stage_value_exp_hits_endpoints():
    assert interpolate_stage_value(10.0, 20.0, 0.0, mode="exp") == pytest.approx(10.0)
    assert interpolate_stage_value(10.0, 20.0, 1.0, mode="exp") == pytest.approx(20.0)


def test_build_stage_boundary_fluids_interpolates_species():
    fluids = build_stage_boundary_fluids(
        3,
        {"temp": 240, "Na": 1.0},
        {"Cu(1)": {"start": 0.0, "end": 10.0, "mode": "linear"}},
    )

    assert [fluid["Cu(1)"] for fluid in fluids] == pytest.approx([0.0, 5.0, 10.0])
    assert all(fluid["temp"] == 240 for fluid in fluids)


def test_build_stage_boundary_fluids_rejects_empty_stage_count():
    with pytest.raises(ValueError, match="n_stages"):
        build_stage_boundary_fluids(0, {}, {})
