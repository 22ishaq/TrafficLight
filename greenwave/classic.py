"""GreenWave Classic — a turtle-graphics UK pelican crossing.

The polished descendant of the original ``trafficlight`` script in this repo:
a traffic light head, a red/green man pedestrian signal and a yellow push-button
unit with a WAIT lamp. Click the button (or press Space) to cross.

All timing comes from :class:`greenwave.pelican.PelicanCrossing`; this module
only draws its state. ``turtle`` (and therefore ``tkinter``) is imported lazily
inside :func:`main`, so importing this module never needs a display.

Run with::

    python -m greenwave classic          # or: python -m greenwave.classic
    python -m greenwave classic --fast   # shortened timings for demos
"""

from __future__ import annotations

import argparse
import dataclasses
import time
from typing import Any, Sequence

from greenwave.pelican import PelicanCrossing, PelicanPhase, PelicanTimings

__all__ = ["main", "build_parser", "LAMP_COLOURS", "BUTTON_CENTRE", "BUTTON_RADIUS", "hit_button"]

WINDOW_TITLE = "GreenWave Classic — Pelican Crossing"
TICK_MS = 100  # ~10 Hz

# (lit, unlit) colour pairs
LAMP_COLOURS: dict[str, tuple[str, str]] = {
    "red": ("#ff2b2b", "#3b0f0f"),
    "amber": ("#ffb000", "#3d2b06"),
    "green": ("#1fdc5a", "#0c3018"),
    "red_man": ("#ff3b30", "#3a1210"),
    "green_man": ("#33ff77", "#0e3319"),
    "wait": ("#ff7a1a", "#3a2614"),
}

BACKGROUND = "#1b2330"
HOUSING = "#111111"
POLE = "#5c6672"
BUTTON_BOX = "#f2c200"

# Layout (turtle coordinates, origin at the window centre)
HEAD_X, HEAD_TOP = -150, 210
LAMP_SPACING = 70
PED_X, PED_TOP = 60, 190
BUTTON_BOX_X, BUTTON_BOX_Y, BUTTON_BOX_W, BUTTON_BOX_H = 200, -10, 120, 170
BUTTON_CENTRE = (BUTTON_BOX_X + BUTTON_BOX_W / 2, BUTTON_BOX_Y - 115)
BUTTON_RADIUS = 26

PHASE_LABELS = {
    PelicanPhase.VEHICLE_GREEN: "Traffic: GREEN",
    PelicanPhase.VEHICLE_AMBER: "Traffic: AMBER — stopping",
    PelicanPhase.ALL_RED: "Traffic: RED — clearing",
    PelicanPhase.PEDESTRIAN_WALK: "Green man — CROSS NOW",
    PelicanPhase.FLASHING: "Flashing — do not start to cross",
}


def hit_button(x: float, y: float) -> bool:
    """Whether a click at (x, y) lands on the push-button unit.

    The whole yellow box counts, plus the round button itself (which sits on
    the box) — fixing the original script's lopsided rectangular hitbox.
    """
    bx, by = BUTTON_CENTRE
    on_button = (x - bx) ** 2 + (y - by) ** 2 <= BUTTON_RADIUS**2
    on_box = (
        BUTTON_BOX_X <= x <= BUTTON_BOX_X + BUTTON_BOX_W
        and BUTTON_BOX_Y - BUTTON_BOX_H <= y <= BUTTON_BOX_Y
    )
    return on_button or on_box


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greenwave classic", description="Turtle-graphics UK pelican crossing (GreenWave Classic)."
    )
    parser.add_argument("--fast", action="store_true", help="use shortened demo timings")
    parser.add_argument(
        "--min-green", type=float, default=None, metavar="SECONDS",
        help="minimum traffic green before a button press is honoured",
    )
    return parser


# --------------------------------------------------------------------------- drawing helpers
def _rect(pen: Any, x: float, y: float, w: float, h: float, fill: str, outline: str | None = None) -> None:
    """Filled rectangle with top-left corner at (x, y)."""
    pen.penup()
    pen.goto(x, y)
    pen.setheading(0)
    pen.color(outline or fill, fill)
    pen.pendown()
    pen.begin_fill()
    for side in (w, h, w, h):
        pen.forward(side)
        pen.right(90)
    pen.end_fill()
    pen.penup()


def _rounded_rect(pen: Any, x: float, y: float, w: float, h: float, r: float, fill: str) -> None:
    """Filled rectangle with rounded corners, top-left at (x, y)."""
    pen.penup()
    pen.goto(x + r, y)
    pen.setheading(0)
    pen.color(fill, fill)
    pen.pendown()
    pen.begin_fill()
    for side in (w, h, w, h):
        pen.forward(side - 2 * r)
        pen.circle(-r, 90)
    pen.end_fill()
    pen.penup()


def _line(pen: Any, x1: float, y1: float, x2: float, y2: float) -> None:
    pen.penup()
    pen.goto(x1, y1)
    pen.pendown()
    pen.goto(x2, y2)
    pen.penup()


def _dot(pen: Any, x: float, y: float, size: float, colour: str) -> None:
    pen.penup()
    pen.goto(x, y)
    pen.dot(size, colour)


def _draw_man(pen: Any, cx: float, cy: float, colour: str, walking: bool) -> None:
    """A stick-figure pedestrian (standing red man or walking green man)."""
    pen.pensize(7)
    pen.color(colour)
    _dot(pen, cx, cy + 34, 18, colour)  # head
    _line(pen, cx, cy + 24, cx, cy - 6)  # body
    if walking:
        _line(pen, cx, cy + 18, cx + 14, cy + 4)   # front arm
        _line(pen, cx, cy + 18, cx - 13, cy + 6)   # back arm
        _line(pen, cx, cy - 6, cx + 15, cy - 30)   # front leg
        _line(pen, cx, cy - 6, cx - 14, cy - 30)   # back leg
    else:
        _line(pen, cx, cy + 18, cx - 9, cy - 4)
        _line(pen, cx, cy + 18, cx + 9, cy - 4)
        _line(pen, cx - 3, cy - 6, cx - 6, cy - 32)
        _line(pen, cx + 3, cy - 6, cx + 6, cy - 32)
    pen.pensize(1)


def _draw_static(pen: Any) -> None:
    """Background, pole, housings and labels — drawn once."""
    # road + zebra-free pelican stud markings
    _rect(pen, -400, -170, 800, 120, "#2b2f36")
    for i in range(-380, 400, 60):
        _rect(pen, i, -108, 30, 4, "#d8d8d8")
    for i in range(-380, 400, 22):
        _rect(pen, i, -170, 10, 6, "#bfbfbf")
    # traffic light pole + head
    _rect(pen, HEAD_X + 32, HEAD_TOP - 200, 16, 240, POLE)
    _rounded_rect(pen, HEAD_X, HEAD_TOP, 80, 210, 14, HOUSING)
    for i in range(3):  # visors
        _rect(pen, HEAD_X - 6, HEAD_TOP - 14 - i * LAMP_SPACING, 92, 6, "#000000")
    # pedestrian signal housing
    _rect(pen, PED_X + 34, PED_TOP - 200, 12, 120, POLE)
    _rounded_rect(pen, PED_X, PED_TOP, 80, 200, 10, HOUSING)
    # push-button unit
    _rect(pen, BUTTON_BOX_X + BUTTON_BOX_W / 2 - 7, BUTTON_BOX_Y - BUTTON_BOX_H, 14, 70, POLE)
    _rounded_rect(pen, BUTTON_BOX_X, BUTTON_BOX_Y, BUTTON_BOX_W, BUTTON_BOX_H, 12, BUTTON_BOX)
    _rect(pen, BUTTON_BOX_X + 14, BUTTON_BOX_Y - 14, BUTTON_BOX_W - 28, 40, "#111111")
    pen.goto(BUTTON_BOX_X + BUTTON_BOX_W / 2, BUTTON_BOX_Y - 78)
    pen.color("#222222")
    pen.write("PUSH BUTTON", align="center", font=("Arial", 9, "bold"))
    pen.goto(BUTTON_BOX_X + BUTTON_BOX_W / 2, BUTTON_BOX_Y - 92)
    pen.write("& WAIT", align="center", font=("Arial", 9, "bold"))
    # title
    pen.goto(0, 255)
    pen.color("#e8eef5")
    pen.write("GreenWave Classic", align="center", font=("Arial", 20, "bold"))
    pen.goto(0, -230)
    pen.color("#9fb0c2")
    pen.write("Click the yellow button (or press Space) to cross  ·  Q to quit",
              align="center", font=("Arial", 11, "normal"))


# --------------------------------------------------------------------------- app
def main(argv: Sequence[str] | None = None) -> int:
    """Open the turtle window and run the crossing until closed."""
    args = build_parser().parse_args(argv)
    timings = PelicanTimings.fast() if args.fast else PelicanTimings()
    if args.min_green is not None:
        timings = dataclasses.replace(timings, min_green=max(0.0, args.min_green))
    crossing = PelicanCrossing(timings)

    try:
        import tkinter  # turtle's backend; imported for TclError
        import turtle
    except ImportError as exc:  # pragma: no cover - depends on the host Python build
        print(f"GreenWave Classic needs tkinter/turtle, which is unavailable: {exc}")
        print("Install your platform's Tk package (e.g. `sudo apt install python3-tk`).")
        return 1

    screen = turtle.Screen()
    screen.setup(820, 600)
    screen.title(WINDOW_TITLE)
    screen.bgcolor(BACKGROUND)
    screen.tracer(0)

    static = turtle.Turtle(visible=False)
    static.speed(0)
    _draw_static(static)

    lamps: dict[str, Any] = {}
    for i, name in enumerate(("red", "amber", "green")):
        lamp = turtle.Turtle(shape="circle")
        lamp.penup()
        lamp.shapesize(2.6)
        lamp.goto(HEAD_X + 40, HEAD_TOP - 38 - i * LAMP_SPACING)
        lamps[name] = lamp

    button = turtle.Turtle(shape="circle")
    button.penup()
    button.shapesize(BUTTON_RADIUS / 10)
    button.color("#333333", "#c9c9c9")
    button.goto(*BUTTON_CENTRE)

    dynamic = turtle.Turtle(visible=False)  # redrawn when lamps change
    status = turtle.Turtle(visible=False)
    status.penup()

    last_frame: dict[str, Any] = {"key": None}
    clock = {"t": time.monotonic()}

    def render() -> None:
        v = crossing.vehicle_lamps
        p = crossing.pedestrian_lamps
        wait = crossing.wait_indicator
        key = (tuple(v.values()), tuple(p.values()), wait)
        if key != last_frame["key"]:
            last_frame["key"] = key
            for name, lamp in lamps.items():
                lamp.color(LAMP_COLOURS[name][0 if v[name] else 1])
            dynamic.clear()
            _draw_man(dynamic, PED_X + 40, PED_TOP - 60,
                      LAMP_COLOURS["red_man"][0 if p["red_man"] else 1], walking=False)
            _draw_man(dynamic, PED_X + 40, PED_TOP - 150,
                      LAMP_COLOURS["green_man"][0 if p["green_man"] else 1], walking=True)
            dynamic.goto(BUTTON_BOX_X + BUTTON_BOX_W / 2, BUTTON_BOX_Y - 46)
            dynamic.color(LAMP_COLOURS["wait"][0 if wait else 1])
            dynamic.write("WAIT", align="center", font=("Arial", 18, "bold"))
        status.clear()
        status.goto(0, -205)
        status.color("#e8eef5")
        remaining = crossing.remaining
        countdown = "" if remaining is None else f"  ({remaining:4.1f}s)"
        status.write(
            f"{PHASE_LABELS[crossing.phase]}{countdown}   ·   crossings: {crossing.crossings_served}",
            align="center", font=("Arial", 13, "bold"),
        )
        screen.update()

    def press(x: float | None = None, y: float | None = None) -> None:
        if x is not None and y is not None and not hit_button(x, y):
            return
        if crossing.press_button():
            button.color("#333333", "#8a8a8a")
            screen.ontimer(lambda: button.color("#333333", "#c9c9c9"), 180)
        render()

    def loop() -> None:
        now = time.monotonic()
        dt, clock["t"] = now - clock["t"], now
        crossing.tick(min(dt, 1.0))  # clamp: window drags / sleeps shouldn't skip phases
        try:
            render()
            screen.ontimer(loop, TICK_MS)
        except (turtle.Terminator, tkinter.TclError):  # window closed mid-frame
            pass

    def quit_app() -> None:
        try:
            screen.bye()
        except turtle.Terminator:
            pass

    screen.onclick(press)
    screen.onkey(press, "space")
    screen.onkey(quit_app, "q")
    screen.onkey(quit_app, "Escape")
    screen.listen()

    render()
    screen.ontimer(loop, TICK_MS)
    try:
        turtle.mainloop()
    except turtle.Terminator:
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
