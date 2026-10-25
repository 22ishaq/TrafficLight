"""Tests for the mesoscopic junction simulation."""

from __future__ import annotations

import pytest

from greenwave.sim import APPROACHES, AXIS_OF, Junction, Phase, Timing, benchmark, simulate

ASYMMETRIC = {"N": 0.2, "S": 0.18, "E": 0.05, "W": 0.06}


def test_same_seed_is_deterministic() -> None:
    a = simulate("actuated", ASYMMETRIC, duration=900, seed=7)
    b = simulate("actuated", ASYMMETRIC, duration=900, seed=7)
    assert a == b


def test_different_seeds_differ() -> None:
    a = simulate("fixed", duration=900, seed=1)
    b = simulate("fixed", duration=900, seed=2)
    assert a.spawned != b.spawned or a.avg_delay != b.avg_delay


@pytest.mark.parametrize("controller", ["fixed", "actuated", "maxpressure", "webster"])
def test_vehicles_are_conserved(controller: str) -> None:
    junction = Junction(controller, ASYMMETRIC, seed=3)
    for _ in range(2000):
        junction.step(0.5)
        queued = sum(len(q) for q in junction.queues.values())
        assert junction.spawned == junction.served + queued
    metrics = junction.metrics()
    assert metrics.spawned == metrics.served + metrics.remaining
    assert sum(junction.served_by_approach.values()) == junction.served


def test_no_discharge_unless_green() -> None:
    junction = Junction("actuated", ASYMMETRIC, seed=11)
    for _ in range(4000):
        lights = {a: junction.light_for(a) for a in APPROACHES}
        before = dict(junction.served_by_approach)
        junction.step(0.5)
        for a in APPROACHES:
            if junction.served_by_approach[a] > before[a]:
                assert lights[a] == "green", f"{a} discharged on {lights[a]}"


def test_uk_phase_sequence() -> None:
    junction = Junction("fixed", seed=1)
    seen = [junction.phase]
    for _ in range(400):
        junction.step(0.5)
        if junction.phase != seen[-1]:
            seen.append(junction.phase)
    expected = [Phase.NS_GREEN, Phase.NS_AMBER, Phase.ALL_RED, Phase.EW_RED_AMBER, Phase.EW_GREEN, Phase.EW_AMBER]
    assert seen[: len(expected)] == expected


def test_intergreen_durations() -> None:
    timing = Timing(amber=3, all_red=2, red_amber=2)
    junction = Junction("fixed", seed=1, timing=timing)
    durations: dict[Phase, float] = {}
    phase, start = junction.phase, 0.0
    for _ in range(600):
        junction.step(0.25)
        if junction.phase != phase:
            durations.setdefault(phase, junction.time - start)
            phase, start = junction.phase, junction.time
    assert durations[Phase.NS_AMBER] == pytest.approx(3.0)
    assert durations[Phase.ALL_RED] == pytest.approx(2.0)
    assert durations[Phase.EW_RED_AMBER] == pytest.approx(2.0)
    assert durations[Phase.NS_GREEN] == pytest.approx(30.0)


def test_lights_are_never_green_on_both_axes() -> None:
    junction = Junction("maxpressure", ASYMMETRIC, seed=5)
    for _ in range(3000):
        junction.step(0.5)
        greens = {AXIS_OF[a] for a in APPROACHES if junction.light_for(a) in ("green", "amber")}
        assert len(greens) <= 1


def test_saturation_flow_caps_discharge() -> None:
    # Swamp one approach: discharge cannot exceed one vehicle per headway.
    timing = Timing()
    junction = Junction("fixed", {"N": 2.0}, seed=1, timing=timing)
    junction.run(600)
    green_share = 30 / (60 + 2 * timing.intergreen)
    upper = 600 * green_share / timing.saturation_headway + 5
    assert junction.served_by_approach["N"] <= upper
    assert junction.metrics().remaining > 0


def test_zero_demand_is_quiet() -> None:
    metrics = simulate("actuated", {"N": 0, "E": 0, "S": 0, "W": 0}, duration=300)
    assert metrics.spawned == metrics.served == 0
    assert metrics.avg_delay == 0
    assert metrics.switches == 0  # actuated rests on green with no conflicting demand


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        Junction(demand={"X": 0.1})
    with pytest.raises(ValueError):
        Junction(demand={"N": -1})
    with pytest.raises(ValueError):
        Junction(initial_axis="NE")
    with pytest.raises(ValueError):
        Junction().step(0)


def test_benchmark_returns_one_result_per_controller() -> None:
    results = benchmark(["fixed", "webster"], duration=600, seeds=(1, 2))
    assert [r.controller for r in results] == ["fixed", "webster"]
    assert all(r.duration == pytest.approx(600) for r in results)
