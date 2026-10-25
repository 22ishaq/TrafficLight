"""Tests for the pelican crossing state machine and the classic GUI's pure helpers."""

from __future__ import annotations

import importlib
import sys

import pytest

from greenwave.pelican import PelicanCrossing, PelicanPhase, PelicanTimings

T = PelicanTimings(min_green=10, amber=3, all_red=2, walk=7, flashing=6, flash_period=1.0)


def run(crossing: PelicanCrossing, seconds: float, dt: float = 0.1) -> None:
    for _ in range(round(seconds / dt)):
        crossing.tick(dt)


def test_rests_on_green_indefinitely_without_demand():
    c = PelicanCrossing(T)
    assert c.tick(10_000) == []
    assert c.phase is PelicanPhase.VEHICLE_GREEN
    assert c.vehicle_signal == "green"
    assert c.pedestrian_signal == "dont_walk"
    assert not c.wait_indicator
    assert c.remaining is None


def test_full_sequence_timing_after_min_green():
    c = PelicanCrossing(T)
    c.tick(20)  # green long past min_green
    assert c.press_button() is True
    assert c.wait_indicator
    assert c.tick(0) == [PelicanPhase.VEHICLE_AMBER]  # responds immediately
    assert (c.vehicle_signal, c.pedestrian_signal) == ("amber", "dont_walk")
    c.tick(3)
    assert (c.phase, c.vehicle_signal, c.pedestrian_signal) == (PelicanPhase.ALL_RED, "red", "dont_walk")
    assert c.wait_indicator
    c.tick(2)
    assert (c.phase, c.vehicle_signal, c.pedestrian_signal) == (PelicanPhase.PEDESTRIAN_WALK, "red", "walk")
    assert not c.wait_indicator  # WAIT goes out when the green man shows
    assert c.crossings_served == 1
    c.tick(7)
    assert (c.phase, c.vehicle_signal, c.pedestrian_signal) == (PelicanPhase.FLASHING, "flashing_amber", "flashing")
    c.tick(6)
    assert (c.phase, c.vehicle_signal, c.pedestrian_signal) == (PelicanPhase.VEHICLE_GREEN, "green", "dont_walk")
    # and it rests again
    assert c.tick(1000) == []


def test_min_green_delays_response_to_button():
    c = PelicanCrossing(T)
    c.tick(4)
    c.press_button()
    run(c, 5.9)  # t = 9.9 < 10
    assert c.phase is PelicanPhase.VEHICLE_GREEN
    run(c, 0.2)
    assert c.phase is PelicanPhase.VEHICLE_AMBER
    assert c.phase_time == pytest.approx(0.1, abs=1e-6)


def test_single_large_tick_matches_many_small_ticks():
    a, b = PelicanCrossing(T), PelicanCrossing(T)
    a.press_button()
    b.press_button()
    run(a, 23.5)
    entered = b.tick(23.5)
    assert entered == [
        PelicanPhase.VEHICLE_AMBER,
        PelicanPhase.ALL_RED,
        PelicanPhase.PEDESTRIAN_WALK,
        PelicanPhase.FLASHING,
    ]
    assert a.phase is b.phase is PelicanPhase.FLASHING
    assert a.phase_time == pytest.approx(b.phase_time)


def test_full_cycle_duration_is_min_green_plus_crossing_cycle():
    c = PelicanCrossing(T)
    c.press_button()
    c.tick(T.min_green + T.crossing_cycle - 0.01)
    assert c.phase is PelicanPhase.FLASHING
    c.tick(0.01)
    assert c.phase is PelicanPhase.VEHICLE_GREEN


def test_button_ignored_during_walk():
    c = PelicanCrossing(T)
    c.press_button()
    c.tick(10 + 3 + 2 + 1)
    assert c.phase is PelicanPhase.PEDESTRIAN_WALK
    assert c.press_button() is False
    assert not c.wait_indicator
    c.tick(7 + 6)
    assert c.phase is PelicanPhase.VEHICLE_GREEN
    assert c.tick(1000) == []  # no phantom second cycle


def test_button_during_flashing_is_queued_for_next_cycle():
    c = PelicanCrossing(T)
    c.press_button()
    c.tick(10 + 3 + 2 + 7 + 1)
    assert c.phase is PelicanPhase.FLASHING
    assert c.press_button() is True
    assert c.wait_indicator
    c.tick(5)
    assert c.phase is PelicanPhase.VEHICLE_GREEN
    assert c.wait_indicator
    # min green counts from the start of the new green
    c.tick(T.min_green - 0.5)
    assert c.phase is PelicanPhase.VEHICLE_GREEN
    c.tick(0.5)
    assert c.phase is PelicanPhase.VEHICLE_AMBER
    c.tick(5)
    assert c.crossings_served == 2


def test_repeated_presses_do_not_restart_the_wait():
    c = PelicanCrossing(T)
    c.tick(2)
    c.press_button()
    c.tick(5)
    c.press_button()  # mashing the button doesn't delay or speed up anything
    c.tick(2.9)
    assert c.phase is PelicanPhase.VEHICLE_GREEN
    c.tick(0.1)
    assert c.phase is PelicanPhase.VEHICLE_AMBER


def test_press_during_amber_or_all_red_keeps_single_demand():
    c = PelicanCrossing(T)
    c.press_button()
    c.tick(11)
    assert c.phase is PelicanPhase.VEHICLE_AMBER
    assert c.press_button() is True
    c.tick(2.5)
    assert c.phase is PelicanPhase.ALL_RED
    c.tick(1.5)
    assert c.phase is PelicanPhase.PEDESTRIAN_WALK
    assert not c.wait_indicator
    c.tick(13)
    assert c.tick(1000) == []


def test_flashing_lamps_blink():
    c = PelicanCrossing(T)
    c.press_button()
    c.tick(10 + 3 + 2 + 7)
    assert c.phase is PelicanPhase.FLASHING
    pattern = []
    for _ in range(4):
        pattern.append((c.vehicle_lamps["amber"], c.pedestrian_lamps["green_man"]))
        c.tick(0.5)
    assert pattern == [(True, True), (False, False), (True, True), (False, False)]
    assert not c.vehicle_lamps["red"] and not c.vehicle_lamps["green"]
    assert not c.pedestrian_lamps["red_man"]


def test_lamps_in_steady_phases():
    c = PelicanCrossing(T)
    assert c.vehicle_lamps == {"red": False, "amber": False, "green": True}
    assert c.pedestrian_lamps == {"red_man": True, "green_man": False}
    c.press_button()
    c.tick(10 + 3 + 2)
    assert c.vehicle_lamps == {"red": True, "amber": False, "green": False}
    assert c.pedestrian_lamps == {"red_man": False, "green_man": True}


def test_vehicles_may_proceed():
    c = PelicanCrossing(T)
    assert c.vehicles_may_proceed
    c.press_button()
    c.tick(10)
    assert not c.vehicles_may_proceed  # amber
    c.tick(3 + 2 + 7)
    assert c.vehicles_may_proceed  # flashing amber: give way


def test_remaining_counts_down():
    c = PelicanCrossing(T)
    c.press_button()
    c.tick(10)
    assert c.remaining == pytest.approx(3)
    c.tick(1)
    assert c.remaining == pytest.approx(2)


def test_reset():
    c = PelicanCrossing(T)
    c.press_button()
    c.tick(17)
    c.reset()
    assert c.phase is PelicanPhase.VEHICLE_GREEN
    assert c.time == 0 and c.crossings_served == 0 and not c.wait_indicator


def test_fast_timings_and_validation():
    fast = PelicanTimings.fast()
    assert fast.crossing_cycle < PelicanTimings().crossing_cycle
    assert fast.min_green < PelicanTimings().min_green
    with pytest.raises(ValueError):
        PelicanTimings(walk=0)
    with pytest.raises(ValueError):
        PelicanTimings(min_green=-1)
    with pytest.raises(ValueError):
        PelicanCrossing().tick(-0.1)


def test_zero_min_green_responds_instantly():
    c = PelicanCrossing(PelicanTimings(min_green=0))
    c.press_button()
    assert c.tick(0) == [PelicanPhase.VEHICLE_AMBER]


# ---------------------------------------------------------------- classic GUI (no display needed)
def test_classic_imports_without_turtle():
    sys.modules.pop("greenwave.classic", None)
    classic = importlib.import_module("greenwave.classic")
    assert "turtle" not in vars(classic)
    assert callable(classic.main)


def test_classic_button_hitbox():
    from greenwave.classic import BUTTON_CENTRE, BUTTON_RADIUS, hit_button

    bx, by = BUTTON_CENTRE
    assert hit_button(bx, by)
    assert hit_button(bx + BUTTON_RADIUS * 0.9, by)
    assert not hit_button(0, 0)
    assert not hit_button(-300, -250)


def test_classic_parser():
    from greenwave.classic import build_parser

    args = build_parser().parse_args(["--fast", "--min-green", "2"])
    assert args.fast and args.min_green == 2
    assert build_parser().parse_args([]).fast is False
