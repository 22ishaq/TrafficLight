"""Tests for signal controllers."""

from __future__ import annotations

import pytest

from greenwave.controllers import CONTROLLERS, Actuated, FixedTime, MaxPressure, Webster, make_controller
from greenwave.sim import Timing, benchmark

ASYMMETRIC = {"N": 0.2, "S": 0.18, "E": 0.05, "W": 0.06}


class FakeJunction:
    def __init__(self, axis: str | None, phase_time: float, queues: dict[str, int], gap: float = 10.0) -> None:
        self.green_axis = axis
        self.phase_time = phase_time
        self.time = 100.0
        self._queues = queues
        self._gap = gap

    def queue_length(self, axis: str) -> int:
        return self._queues.get(axis, 0)

    def time_since_arrival(self, axis: str) -> float:
        return self._gap


def test_registry_and_factory() -> None:
    assert set(CONTROLLERS) == {"fixed", "actuated", "maxpressure", "webster"}
    assert isinstance(make_controller("Fixed"), FixedTime)
    assert make_controller("fixed", green=20).green == 20
    with pytest.raises(ValueError, match="unknown controller"):
        make_controller("chaos")


def test_fixed_time_switches_on_schedule() -> None:
    ctl = FixedTime(green=30)
    assert not ctl.decide(FakeJunction("NS", 29.5, {}))
    assert ctl.decide(FakeJunction("NS", 30.0, {}))


def test_actuated_rules() -> None:
    ctl = Actuated(min_green=8, max_green=45, gap=3)
    assert not ctl.decide(FakeJunction("NS", 5, {"EW": 4}))  # min green
    assert ctl.decide(FakeJunction("NS", 10, {"NS": 0, "EW": 4}, gap=3.5))  # gap-out
    assert not ctl.decide(FakeJunction("NS", 10, {"NS": 0, "EW": 4}, gap=1.0))  # still arriving
    assert not ctl.decide(FakeJunction("NS", 10, {"NS": 3, "EW": 4}))  # queue still discharging
    assert ctl.decide(FakeJunction("NS", 45, {"NS": 3, "EW": 4}))  # max-out
    assert not ctl.decide(FakeJunction("NS", 90, {"NS": 3, "EW": 0}))  # rest on green


def test_max_pressure_rules() -> None:
    ctl = MaxPressure(min_green=8, max_green=40, threshold=2)
    assert not ctl.decide(FakeJunction("EW", 5, {"NS": 10}))
    assert ctl.decide(FakeJunction("EW", 9, {"NS": 10, "EW": 1}))
    assert not ctl.decide(FakeJunction("EW", 9, {"NS": 3, "EW": 1}))
    assert ctl.decide(FakeJunction("EW", 40, {"NS": 1, "EW": 9}))
    with pytest.raises(ValueError):
        MaxPressure(min_green=10, max_green=5)


def test_webster_splits_follow_demand() -> None:
    ctl = Webster()
    ctl.reset(ASYMMETRIC, Timing())
    assert ctl.greens["NS"] > ctl.greens["EW"]
    assert not ctl.decide(FakeJunction("NS", ctl.greens["NS"] - 0.5, {}))
    assert ctl.decide(FakeJunction("NS", ctl.greens["NS"], {}))


@pytest.mark.parametrize("smart", ["actuated", "maxpressure", "webster"])
def test_adaptive_controllers_beat_fixed_under_asymmetric_demand(smart: str) -> None:
    fixed, other = benchmark(["fixed", smart], ASYMMETRIC, duration=1800, seeds=(1, 2, 3))
    assert other.avg_delay < fixed.avg_delay * 0.6
    assert other.throughput_per_hour >= fixed.throughput_per_hour


@pytest.mark.parametrize(
    "ctl, seconds",
    [(FixedTime(green=0.3), 0.3), (Actuated(min_green=0.3, max_green=0.7), 0.7), (MaxPressure(0.3, 0.7), 0.7)],
)
def test_boundaries_tolerate_float_accumulation(ctl, seconds: float) -> None:
    # 0.1 + 0.1 + 0.1 == 0.30000000000000004 but 7 x 0.1 == 0.7000000000000001; sums can
    # also land just *below* the boundary, which used to cost an extra step.
    below = sum([0.1] * round(seconds * 10)) - 1e-12
    assert ctl.decide(FakeJunction("NS", below, {"NS": 5, "EW": 5}, gap=0))
