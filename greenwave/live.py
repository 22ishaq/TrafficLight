"""Live terminal view of a simulated junction.

Animates :class:`greenwave.sim.Junction` with plain ANSI escape codes (no
curses, stdlib only): a top-down junction with a UK signal head per approach,
queued vehicles stacked back from each stop line, and a live status panel.
Traffic drives on the left, as in the UK.

Run with::

    python -m greenwave live --controller maxpressure --speed 20
    python -m greenwave live --frames 3 --no-color      # print 3 frames and exit

All drawing goes through the pure :func:`render_frame`, so it can be tested
without a terminal.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import time
from typing import Sequence, TextIO

from .controllers import CONTROLLERS
from .metrics import Metrics
from .sim import APPROACHES, Junction

__all__ = ["WIDTH", "HEIGHT", "render_frame", "strip_ansi", "build_parser", "main"]

#: Visible width of every rendered line, and height of the junction drawing.
WIDTH = 61
HEIGHT = 25
_CX, _CY = WIDTH // 2, HEIGHT // 2  # centre of the junction box

FRAME_INTERVAL = 0.1  # real seconds between frames
MAX_SIM_STEP = 0.5  # largest single Junction.step, in simulated seconds

CAR = "■"
_CAR_SPACING_H = 3  # columns per queued car on the horizontal arms ("■■ ")

# ANSI SGR styles (None = default terminal style)
_RESET = "\x1b[0m"
_STYLES = {
    "red": "\x1b[1;91m",
    "amber": "\x1b[1;93m",
    "green": "\x1b[1;92m",
    "off": "\x1b[2;90m",
    "road": "\x1b[90m",
    "line": "\x1b[37m",
    "stop": "\x1b[1;97m",
    "car_ns": "\x1b[96m",
    "car_ew": "\x1b[95m",
    "label": "\x1b[1;97m",
    "title": "\x1b[1;96m",
    "dim": "\x1b[2m",
}
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

_HIDE_CURSOR, _SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
_CLEAR, _HOME, _CLEAR_BELOW = "\x1b[2J", "\x1b[H", "\x1b[J"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from ``text``."""
    return _ANSI_RE.sub("", text)


class _Canvas:
    """A fixed-size character grid where every cell may carry a style."""

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.chars = [[" "] * width for _ in range(height)]
        self.styles: list[list[str | None]] = [[None] * width for _ in range(height)]

    def put(self, row: int, col: int, text: str, style: str | None = None) -> None:
        for i, ch in enumerate(text):
            c = col + i
            if 0 <= row < self.height and 0 <= c < self.width:
                self.chars[row][c] = ch
                self.styles[row][c] = style

    def lines(self, color: bool) -> list[str]:
        out = []
        for chars, styles in zip(self.chars, self.styles):
            if not color:
                out.append("".join(chars))
                continue
            parts, current = [], None
            for ch, style in zip(chars, styles):
                if style != current:
                    parts.append(_RESET if style is None else _RESET + _STYLES[style])
                    current = style
                parts.append(ch)
            if current is not None:
                parts.append(_RESET)
            out.append("".join(parts))
        return out


def _signal_head(canvas: _Canvas, row: int, col: int, approach: str, aspect: str) -> None:
    """Draw e.g. ``N[R··]`` — lit lamps as letters, unlit as dim dots."""
    lit = {
        "red": aspect in ("red", "red_amber"),
        "amber": aspect in ("amber", "red_amber"),
        "green": aspect == "green",
    }
    canvas.put(row, col, approach, "label")
    canvas.put(row, col + 1, "[", "road")
    for i, (lamp, letter) in enumerate((("red", "R"), ("amber", "A"), ("green", "G"))):
        if lit[lamp]:
            canvas.put(row, col + 2 + i, letter, lamp)
        else:
            canvas.put(row, col + 2 + i, "·", "off")
    canvas.put(row, col + 5, "]", "road")


def _draw_roads(canvas: _Canvas) -> None:
    cx, cy = _CX, _CY
    for r in range(canvas.height):
        if cy - 2 <= r <= cy + 2:
            continue
        canvas.put(r, cx - 3, "│", "road")
        canvas.put(r, cx + 3, "│", "road")
        if r % 2 == 0:
            canvas.put(r, cx, "┊", "line")
    for c in range(canvas.width):
        if cx - 3 <= c <= cx + 3:
            continue
        canvas.put(cy - 2, c, "─", "road")
        canvas.put(cy + 2, c, "─", "road")
        if c % 2 == 0:
            canvas.put(cy, c, "┄", "line")
    canvas.put(cy - 2, cx - 3, "┘", "road")
    canvas.put(cy - 2, cx + 3, "└", "road")
    canvas.put(cy + 2, cx - 3, "┐", "road")
    canvas.put(cy + 2, cx + 3, "┌", "road")
    # Stop lines (UK: drive on the left).
    canvas.put(cy - 3, cx + 1, "══", "stop")  # N approach, southbound, east lane
    canvas.put(cy + 3, cx - 2, "══", "stop")  # S approach, northbound, west lane
    canvas.put(cy + 1, cx + 4, "║", "stop")  # E approach, westbound, south lane
    canvas.put(cy - 1, cx - 4, "║", "stop")  # W approach, eastbound, north lane


def _draw_queues(canvas: _Canvas, junction: Junction) -> None:
    cx, cy = _CX, _CY
    style = {"N": "car_ns", "S": "car_ns", "E": "car_ew", "W": "car_ew"}
    for approach in APPROACHES:
        n = junction.queue_length(approach)
        if approach in ("N", "S"):
            rows = range(cy - 4, -1, -1) if approach == "N" else range(cy + 4, canvas.height)
            col = cx + 1 if approach == "N" else cx - 2
            capacity = len(rows)
            for row in list(rows)[: min(n, capacity)]:
                canvas.put(row, col, CAR * 2, style[approach])
            if n > capacity:
                label_row = rows[-1]
                label_col = col + 3 if approach == "N" else col - 1 - len(f"+{n - capacity}")
                canvas.put(label_row, label_col, f"+{n - capacity}", "label")
        else:
            if approach == "E":
                starts = list(range(cx + 5, canvas.width - 1, _CAR_SPACING_H))
                row = cy + 1
            else:
                starts = list(range(cx - 6, -1, -_CAR_SPACING_H))
                row = cy - 1
            capacity = len(starts)
            for start in starts[: min(n, capacity)]:
                canvas.put(row, start, CAR * 2, style[approach])
            if n > capacity:
                label = f"+{n - capacity}"
                label_row = cy + 3 if approach == "E" else cy - 3
                label_col = canvas.width - len(label) if approach == "E" else 0
                canvas.put(label_row, label_col, label, "label")


def _fit(text: str, width: int = WIDTH) -> str:
    return text[:width].ljust(width)


def _status_lines(junction: Junction, controller_name: str, color: bool) -> list[str]:
    m = junction.metrics()
    green = junction.green_axis or "—"
    phase = junction.phase.value
    queues = "  ".join(f"{a}:{junction.queue_length(a):>3}" for a in APPROACHES)
    lines = [
        _fit(f" GreenWave Live │ t = {junction.time:7.1f} s │ controller: {controller_name}"),
        _fit(f" Phase: {phase} ({junction.phase_time:4.1f} s) │ green axis: {green} │ switches: {m.switches}"),
        _fit(
            f" Avg delay: {m.avg_delay:5.1f} s │ max: {m.max_delay:5.1f} s │ "
            f"throughput: {m.throughput_per_hour:5.0f} veh/h"
        ),
        _fit(f" Queues  {queues}  │ served {m.served}/{m.spawned}"),
    ]
    if color:
        lines[0] = lines[0].replace("GreenWave Live", _STYLES["title"] + "GreenWave Live" + _RESET, 1)
        aspect = "green" if junction.green_axis else ("red" if phase == "ALL_RED" else "amber")
        lines[1] = lines[1].replace(phase, _STYLES[aspect] + phase + _RESET, 1)
    return lines


def render_frame(junction: Junction, controller_name: str, color: bool = True) -> str:
    """Render one frame (junction drawing + status panel) as a string.

    Every line has exactly :data:`WIDTH` visible characters. With
    ``color=False`` the result contains no ANSI escape sequences.
    """
    canvas = _Canvas(WIDTH, HEIGHT)
    _draw_roads(canvas)
    _draw_queues(canvas, junction)
    cx, cy = _CX, _CY
    # Signal heads sit on the nearside (left) kerb at each stop line.
    _signal_head(canvas, cy - 3, cx + 4, "N", junction.light_for("N"))
    _signal_head(canvas, cy + 3, cx + 4, "E", junction.light_for("E"))
    _signal_head(canvas, cy + 3, cx - 9, "S", junction.light_for("S"))
    _signal_head(canvas, cy - 3, cx - 9, "W", junction.light_for("W"))
    rule = "─" * WIDTH
    if color:
        rule = _STYLES["road"] + rule + _RESET
    return "\n".join([*canvas.lines(color), rule, *_status_lines(junction, controller_name, color)])


def _parse_demand(text: str) -> dict[str, float]:
    # Same format as ``greenwave benchmark --demand`` (1, 2 or 4 values, N,S,E,W order).
    from .cli import parse_demand

    return parse_demand(text)


def _seconds(positive: bool):
    def convert(text: str) -> float:
        value = float(text)
        if not math.isfinite(value) or value < 0 or (positive and value == 0):
            raise argparse.ArgumentTypeError(
                f"must be a {'positive' if positive else 'non-negative'} finite number, got {text}"
            )
        return value

    return convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greenwave live", description="Animate a simulated junction in the terminal."
    )
    parser.add_argument("--controller", choices=sorted(CONTROLLERS), default="actuated")
    parser.add_argument("--speed", type=_seconds(positive=True), default=10.0,
                        help="simulated seconds per real second (default: 10)")
    parser.add_argument("--duration", type=_seconds(positive=False), default=600.0,
                        help="simulated seconds to run (default: 600)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--demand", type=_parse_demand, default=None, metavar="N,S,E,W",
                        help="arrival rates in veh/s: one value, NS,EW or N,S,E,W (as in benchmark)")
    parser.add_argument("--frames", type=int, default=None, metavar="N",
                        help="print N frames without sleeping or clearing, then exit")
    parser.add_argument("--no-color", dest="color", action="store_false", help="disable ANSI colours")
    return parser


def _advance(junction: Junction, sim_seconds: float, until: float) -> None:
    """Step the junction by ``sim_seconds`` (in chunks), never past ``until``."""
    remaining = min(sim_seconds, until - junction.time)
    if remaining <= 1e-9:
        return
    steps = max(1, math.ceil(remaining / MAX_SIM_STEP))
    for _ in range(steps):
        junction.step(remaining / steps)


def _summary(m: Metrics) -> str:
    return (
        f"GreenWave Live — {m.controller} after {m.duration:.0f} s: "
        f"avg delay {m.avg_delay:.1f} s, max delay {m.max_delay:.1f} s, "
        f"throughput {m.throughput_per_hour:.0f} veh/h, avg queue {m.avg_queue:.1f}, "
        f"served {m.served}/{m.spawned}, {m.switches} switches"
    )


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    """Run the live view. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    out = out or sys.stdout
    junction = Junction(args.controller, args.demand, seed=args.seed)
    name = junction.controller.name
    sim_per_frame = args.speed * FRAME_INTERVAL

    if args.frames is not None:
        for i in range(max(0, args.frames)):
            if i:
                _advance(junction, sim_per_frame, args.duration)
            out.write(render_frame(junction, name, color=args.color) + "\n\n")
        out.write(_summary(junction.metrics()) + "\n")
        out.flush()
        return 0

    out.write(_HIDE_CURSOR + _CLEAR)
    try:
        while True:
            started = time.monotonic()
            out.write(_HOME + render_frame(junction, name, color=args.color) + "\n" + _CLEAR_BELOW)
            out.flush()
            if junction.time >= args.duration - 1e-9:
                break
            _advance(junction, sim_per_frame, args.duration)
            time.sleep(max(0.0, FRAME_INTERVAL - (time.monotonic() - started)))
    except KeyboardInterrupt:
        out.write("\n")
    finally:
        out.write(_SHOW_CURSOR)
        out.flush()
    out.write(_summary(junction.metrics()) + "\n")
    out.flush()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
