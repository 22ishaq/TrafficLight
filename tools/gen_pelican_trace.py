"""Generate the golden pelican-crossing trace shared by the Python and JS tests.

The fixture (``tests/fixtures/pelican_trace.json``) holds scripted scenarios
(button presses and ticks) together with the state of
:class:`greenwave.pelican.PelicanCrossing` after every step. The Python test
regenerates it in memory; ``web/tests/pelican.test.mjs`` replays the same
scripts against the browser port in ``web/js/classic.js``.

Usage::

    python tools/gen_pelican_trace.py          # rewrite the fixture
    python tools/gen_pelican_trace.py --check  # exit 1 if the fixture is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "pelican_trace.json"
sys.path.insert(0, str(ROOT))

from greenwave.pelican import PelicanCrossing, PelicanTimings  # noqa: E402

DECIMALS = 9


def _steps_fine_cycle() -> list[list[Any]]:
    """Fast timings in 0.1 s ticks: press during walk (ignored) and during flashing (queued)."""
    steps: list[list[Any]] = [["tick", 1.0], ["press"]]
    steps += [["tick", 0.1]] * 60  # through min green, amber, all-red, into walk
    steps += [["press"]]  # green man showing -> ignored
    steps += [["tick", 0.1]] * 25  # into flashing
    steps += [["press"]]  # flashing -> queued, WAIT lights again
    steps += [["tick", 0.1]] * 80  # back to green, min green again, next cycle
    return steps


SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "default: press before min green, repeat press, full cycle",
        "timings": "default",
        "steps": [["tick", 4.0], ["press"], ["tick", 1.0], ["press"]]
        + [["tick", 1.0]] * 25,
    },
    {
        "name": "default: rests on green, late press switches at once",
        "timings": "default",
        "steps": [["tick", 30.0], ["tick", 0.0], ["press"], ["tick", 0.0], ["tick", 3.0], ["tick", 2.0]],
    },
    {
        "name": "default: press during walk ignored, press during flashing queued",
        "timings": "default",
        "steps": [["tick", 12.0], ["press"], ["tick", 3.0], ["tick", 2.0], ["tick", 1.0], ["press"],
                  ["tick", 6.5], ["press"], ["press"], ["tick", 0.5], ["tick", 5.0], ["tick", 4.9],
                  ["tick", 0.1], ["tick", 3.0], ["tick", 2.0], ["tick", 7.0], ["tick", 6.0], ["tick", 20.0]],
    },
    {
        "name": "fast: large ticks carry over several phases",
        "timings": "fast",
        "steps": [["press"], ["tick", 20.0], ["press"], ["tick", 7.25], ["press"], ["tick", 1.75],
                  ["tick", 0.25], ["tick", 100.0]],
    },
    {
        "name": "fast: 0.1 s ticks with ignored and queued presses",
        "timings": "fast",
        "steps": _steps_fine_cycle(),
    },
]


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, DECIMALS)


def _snapshot(c: PelicanCrossing) -> dict[str, Any]:
    return {
        "time": _r(c.time),
        "phase": c.phase.name,
        "phase_time": _r(c.phase_time),
        "remaining": _r(c.remaining),
        "vehicle": c.vehicle_signal,
        "pedestrian": c.pedestrian_signal,
        "wait": c.wait_indicator,
        "served": c.crossings_served,
        "vehicle_lamps": c.vehicle_lamps,
        "pedestrian_lamps": c.pedestrian_lamps,
    }


def run_scenario(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    timings = PelicanTimings.fast() if scenario["timings"] == "fast" else PelicanTimings()
    crossing = PelicanCrossing(timings)
    trace = [{"action": "start", **_snapshot(crossing)}]
    for step in scenario["steps"]:
        if step[0] == "press":
            record: dict[str, Any] = {"action": "press", "accepted": crossing.press_button()}
        else:
            entered = crossing.tick(step[1])
            record = {"action": "tick", "dt": step[1], "entered": [p.name for p in entered]}
        trace.append({**record, **_snapshot(crossing)})
    return trace


def build() -> dict[str, Any]:
    return {
        "description": "Golden trace of greenwave.pelican.PelicanCrossing; regenerate with tools/gen_pelican_trace.py",
        "decimals": DECIMALS,
        "scenarios": [{**s, "trace": run_scenario(s)} for s in SCENARIOS],
    }


def render() -> str:
    return json.dumps(build(), indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the fixture is out of date")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        ok = FIXTURE.exists() and FIXTURE.read_text() == text
        print("fixture up to date" if ok else f"fixture stale: run python {Path(__file__).name}")
        return 0 if ok else 1
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text)
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
