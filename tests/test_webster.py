"""Tests for Webster's method."""

from __future__ import annotations

import math

import pytest

from greenwave.webster import optimal_cycle, webster_plan


def test_textbook_cycle() -> None:
    # Classic worked example: L = 10 s, y1 = 0.30, y2 = 0.25 -> C0 = 20 / 0.45 = 44.4 s.
    assert optimal_cycle(10, 0.55) == pytest.approx(44.444, abs=1e-3)


def test_textbook_plan_splits() -> None:
    # Flows chosen so y = 540/1800 = 0.30 and 450/1800 = 0.25.
    plan = webster_plan({"A": (540, 300), "B": (450, 200)}, saturation_flow=1800, lost_time_per_phase=5)
    assert plan.flow_ratios == pytest.approx({"A": 0.30, "B": 0.25})
    assert plan.total_flow_ratio == pytest.approx(0.55)
    assert plan.lost_time == 10
    assert plan.cycle == pytest.approx(44.444, abs=1e-3)
    assert sum(plan.greens.values()) == pytest.approx(plan.cycle - plan.lost_time)
    assert plan.greens["A"] / plan.greens["B"] == pytest.approx(0.30 / 0.25)
    assert not plan.oversaturated


def test_oversaturated_uses_max_cycle() -> None:
    assert math.isinf(optimal_cycle(10, 1.0))
    plan = webster_plan({"A": (1200,), "B": (900,)}, saturation_flow=1800, lost_time_per_phase=5, max_cycle=120)
    assert plan.oversaturated
    assert plan.cycle == 120


def test_light_demand_uses_min_cycle() -> None:
    plan = webster_plan({"A": (50,), "B": (40,)}, saturation_flow=1800, lost_time_per_phase=4, min_cycle=30)
    assert plan.unclamped_cycle < 30
    assert plan.cycle == 30


def test_zero_demand_splits_evenly() -> None:
    plan = webster_plan({"A": (0,), "B": (0,)}, saturation_flow=1800, lost_time_per_phase=5)
    assert plan.greens["A"] == pytest.approx(plan.greens["B"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"saturation_flow": 0, "lost_time_per_phase": 5},
        {"saturation_flow": 1800, "lost_time_per_phase": 5, "min_cycle": 90, "max_cycle": 60},
    ],
)
def test_invalid_arguments(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        webster_plan({"A": (100,)}, **kwargs)
    with pytest.raises(ValueError):
        optimal_cycle(-1, 0.5)
