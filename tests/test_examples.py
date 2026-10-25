"""Smoke tests for the scripts in examples/."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from greenwave.controllers import CONTROLLERS
from greenwave.sim import Junction

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "custom_controller.py"


@pytest.fixture
def example(monkeypatch):
    """Load the example as a module without running main(); restore the registry afterwards."""
    monkeypatch.setattr(sys, "argv", ["custom_controller.py"])
    saved = dict(CONTROLLERS)
    yield runpy.run_path(str(EXAMPLE), run_name="example")
    CONTROLLERS.clear()
    CONTROLLERS.update(saved)


def test_example_benchmark_completes(example, capsys):
    results = example["main"](["--duration", "300", "--seeds", "1"])
    names = [m.controller for m in results]
    assert names == ["fixed", "webster", "actuated", "maxpressure", "longestwait"]
    assert all(m.served > 0 and m.spawned == m.served + m.remaining for m in results)
    out = capsys.readouterr().out
    assert "longestwait" in out and "<- best" in out


def test_example_registers_controller(example):
    example["register"]()
    assert CONTROLLERS["longestwait"] is example["LongestWaitFirst"]
    junction = Junction("longestwait", seed=3)
    metrics = junction.run(600)
    assert metrics.controller == "longestwait"
    assert metrics.switches > 0


def test_longest_wait_first_rules(example):
    lwf = example["LongestWaitFirst"](min_green=5, max_green=40, margin=10, gap=3)
    junction = Junction(lwf, {"N": 0.0, "E": 0.0, "S": 0.0, "W": 0.0}, seed=1)
    # Nobody waiting anywhere: rests on NS green.
    junction.run(100)
    assert junction.green_axis == "NS" and junction.switches == 0
    junction.phase_time = 10.0  # between min_green and max_green, so rules 4-5 decide
    # One car waits on EW while NS is empty and quiet: gap-out (rule 4).
    junction.queues["E"].append(junction.time)
    assert lwf.decide(junction) is True
    # ...but not while NS traffic is still arriving.
    junction._last_arrival["NS"] = junction.time - 1.0
    assert lwf.decide(junction) is False
    # A red-axis vehicle waiting far longer than anyone on green wins (rule 5).
    junction.queues["N"].append(junction.time - 1.0)
    junction.queues["E"][0] = junction.time - 30.0
    assert lwf.decide(junction) is True
    with pytest.raises(ValueError):
        example["LongestWaitFirst"](min_green=0)
