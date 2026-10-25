"""Tests for the UK traffic light state machine."""

from __future__ import annotations

import pytest

from greenwave.signals import UK_SEQUENCE, Durations, LightState, TrafficLight


def test_uk_sequence_order():
    assert UK_SEQUENCE == (LightState.RED, LightState.RED_AMBER, LightState.GREEN, LightState.AMBER)


def test_advance_cycles_through_uk_sequence_and_wraps():
    light = TrafficLight()
    seen = [light.state]
    for _ in range(4):
        seen.append(light.advance().state)
    assert seen == [
        LightState.RED,
        LightState.RED_AMBER,
        LightState.GREEN,
        LightState.AMBER,
        LightState.RED,
    ]


@pytest.mark.parametrize(
    ("state", "lamps"),
    [
        (LightState.RED, {"red": True, "amber": False, "green": False}),
        (LightState.RED_AMBER, {"red": True, "amber": True, "green": False}),
        (LightState.GREEN, {"red": False, "amber": False, "green": True}),
        (LightState.AMBER, {"red": False, "amber": True, "green": False}),
    ],
)
def test_lamps_for_each_aspect(state, lamps):
    assert TrafficLight(state=state).lamps == lamps


def test_only_green_allows_proceeding():
    assert [TrafficLight(state=s).can_proceed for s in UK_SEQUENCE] == [False, False, True, False]


def test_tick_follows_durations():
    light = TrafficLight(durations=Durations(red=5, red_amber=2, green=10, amber=3))
    assert light.tick(4.9) == []
    assert light.state is LightState.RED
    assert light.tick(0.1) == [LightState.RED_AMBER]
    assert light.remaining == pytest.approx(2.0)
    light.tick(2)
    assert light.state is LightState.GREEN
    light.tick(10)
    assert light.state is LightState.AMBER
    light.tick(3)
    assert light.state is LightState.RED


def test_large_tick_carries_overflow_through_multiple_aspects():
    light = TrafficLight(durations=Durations(red=5, red_amber=2, green=10, amber=3))
    entered = light.tick(5 + 2 + 10 + 1.5)
    assert entered == [LightState.RED_AMBER, LightState.GREEN, LightState.AMBER]
    assert light.elapsed == pytest.approx(1.5)
    assert light.remaining == pytest.approx(1.5)


def test_small_and_large_ticks_agree():
    a = TrafficLight(durations=Durations(red=3, red_amber=1, green=4, amber=2))
    b = TrafficLight(durations=Durations(red=3, red_amber=1, green=4, amber=2))
    for _ in range(137):
        a.tick(0.1)
    b.tick(13.7)
    assert a.state is b.state
    assert a.elapsed == pytest.approx(b.elapsed)


def test_none_duration_holds_forever():
    light = TrafficLight(state=LightState.GREEN, durations=Durations(green=None))
    assert light.tick(1e9) == []
    assert light.state is LightState.GREEN
    assert light.remaining is None
    assert light.durations.cycle is None


def test_cycle_length():
    assert Durations(red=30, red_amber=2, green=30, amber=3).cycle == 65


def test_set_forces_state_and_resets_timer():
    light = TrafficLight()
    light.tick(10)
    light.set(LightState.GREEN)
    assert light.state is LightState.GREEN
    assert light.elapsed == 0


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        Durations(amber=0)
    with pytest.raises(ValueError):
        TrafficLight().tick(-1)
