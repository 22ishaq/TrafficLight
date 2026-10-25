"""Tests for the live terminal view."""

from __future__ import annotations

import io

import pytest

from greenwave.live import HEIGHT, WIDTH, main, render_frame, strip_ansi
from greenwave.sim import Junction


def busy_junction(controller: str = "fixed", seconds: float = 120) -> Junction:
    junction = Junction(controller, {"N": 0.3, "E": 0.3, "S": 0.3, "W": 0.3}, seed=7)
    junction.run(seconds)
    return junction


def test_plain_frame_has_no_ansi_and_fixed_width():
    junction = busy_junction()
    frame = render_frame(junction, "fixed", color=False)
    assert "\x1b" not in frame
    lines = frame.split("\n")
    assert len(lines) >= HEIGHT + 4
    assert all(len(line) == WIDTH for line in lines), {len(line) for line in lines}


def test_colour_frame_has_same_visible_layout():
    junction = busy_junction()
    plain = render_frame(junction, "fixed", color=False)
    coloured = render_frame(junction, "fixed", color=True)
    assert "\x1b[" in coloured
    assert strip_ansi(coloured) == plain


def test_frame_shows_phase_controller_and_signal_heads():
    junction = Junction("actuated", seed=1)
    frame = render_frame(junction, "actuated", color=False)
    assert junction.phase.value in frame
    assert "actuated" in frame
    # NS starts green, EW red (UK lamps: R A G)
    assert "N[··G]" in frame and "S[··G]" in frame
    assert "E[R··]" in frame and "W[R··]" in frame


@pytest.mark.parametrize(
    ("aspect", "lamps"),
    [("red", "R··"), ("red_amber", "RA·"), ("green", "··G"), ("amber", "·A·")],
)
def test_signal_head_lamps_follow_uk_aspects(monkeypatch, aspect, lamps):
    junction = Junction("fixed", seed=1)
    monkeypatch.setattr(junction, "light_for", lambda approach: aspect)
    frame = render_frame(junction, "fixed", color=False)
    for approach in "NESW":
        assert f"{approach}[{lamps}]" in frame


def test_queued_cars_are_drawn():
    empty = Junction("fixed", {"N": 0, "E": 0, "S": 0, "W": 0}, seed=1)
    assert "■" not in render_frame(empty, "fixed", color=False)
    busy = busy_junction()
    assert sum(busy.queue_length(a) for a in "NESW") > 0
    assert "■" in render_frame(busy, "fixed", color=False)


def test_overflowing_queue_shows_count():
    junction = Junction("fixed", {"N": 2.0, "E": 0, "S": 0, "W": 0}, seed=3)
    # Hold the N approach on red long enough to build a long queue.
    junction.controller.decide = lambda view: False  # type: ignore[method-assign]
    junction.phase = type(junction.phase)("EW_GREEN")
    junction.axis = "EW"
    junction.run(60)
    n = junction.queue_length("N")
    assert n > 20
    frame = render_frame(junction, "fixed", color=False)
    assert "+" in frame
    assert all(len(line) == WIDTH for line in frame.split("\n"))


def test_main_frames_no_color_exits_zero(capsys):
    assert main(["--frames", "3", "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert out.count("GreenWave Live │") == 3
    assert "avg delay" in out


def test_main_advances_simulation_between_frames():
    buf = io.StringIO()
    assert main(["--frames", "4", "--no-color", "--speed", "50", "--controller", "maxpressure",
                 "--demand", "0.2,0.1,0.2,0.1", "--seed", "5"], out=buf) == 0
    text = buf.getvalue()
    assert "t =     0.0 s" in text
    assert "t =    15.0 s" in text  # 3 advances × 50 sim-s/s × 0.1 s
    assert "maxpressure" in text


def test_main_respects_duration():
    buf = io.StringIO()
    assert main(["--frames", "10", "--no-color", "--speed", "100", "--duration", "25"], out=buf) == 0
    assert "after 25 s" in buf.getvalue()


def test_main_rejects_bad_demand():
    with pytest.raises(SystemExit):
        main(["--frames", "1", "--demand", "1,2,3"])
