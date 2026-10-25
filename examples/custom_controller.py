"""Write your own signal controller and benchmark it against the built-ins.

A GreenWave controller answers one question, many times a second, while an
axis (``"NS"`` or ``"EW"``) has green: *should the green move to the other
axis now?* Return ``True`` to switch. The junction handles the safe UK
inter-green (amber -> all-red -> red+amber) by itself, so a controller can
never cause a crash -- it can only cause delay.

This example builds a **longest-wait-first** controller: it gives green to
whichever axis has the vehicle that has been waiting longest at its stop line.
That bounds the worst-case wait (good for fairness) while still clearing big
queues, because the head of a big queue has usually been waiting a long time.

Run it::

    python examples/custom_controller.py                  # 30 min x 3 seeds
    python examples/custom_controller.py --duration 600 --seeds 2
"""

from __future__ import annotations

import argparse
from typing import Mapping, Sequence

from greenwave.controllers import CONTROLLERS, Controller
from greenwave.metrics import Metrics
from greenwave.sim import AXES, Timing, benchmark

OTHER_AXIS = {"NS": "EW", "EW": "NS"}


class LongestWaitFirst(Controller):
    """Serve the axis whose oldest queued vehicle has waited longest.

    Rules, checked in order while an axis is green:

    1. Never cut a green shorter than ``min_green`` seconds.
    2. If nobody waits on the red axis, rest on green.
    3. After ``max_green`` seconds, always switch (nobody starves).
    4. If the green axis has emptied *and* no new vehicle has arrived on it
       for ``gap`` seconds, switch -- the green is being wasted ("gap-out").
    5. Otherwise switch when the red axis's oldest vehicle has waited
       ``margin`` seconds longer than the green axis's oldest vehicle. The
       margin is hysteresis: each switch costs ~9 s of lost time, so we only
       pay it for a clear gain. (Try ``margin=0`` and watch the delay
       explode as the signal flaps back and forth.)
    """

    # ``name`` is the key used by ``make_controller`` / ``benchmark`` / the CLI.
    name = "longestwait"
    description = "Serve the axis with the longest-waiting vehicle"

    def __init__(
        self, min_green: float = 8.0, max_green: float = 60.0, margin: float = 30.0, gap: float = 3.0
    ) -> None:
        if not 0 < min_green <= max_green:
            raise ValueError("require 0 < min_green <= max_green")
        self.min_green, self.max_green, self.margin, self.gap = min_green, max_green, margin, gap

    def reset(self, demand: Mapping[str, float], timing: Timing) -> None:
        """Called once before every run. This controller keeps no state, so nothing to do.

        A stateful controller (e.g. one that plans a cycle from ``demand``, like
        the built-in Webster controller) would initialise itself here.
        """

    @staticmethod
    def head_wait(junction, axis: str) -> float:
        """Seconds the oldest queued vehicle on ``axis`` has been waiting (0 if none).

        ``junction.queues[approach]`` is a deque of arrival times, oldest first.
        This reaches past the minimal ``JunctionView`` protocol into the
        :class:`~greenwave.sim.Junction` itself -- fine for your own controllers.
        """
        oldest = [junction.queues[a][0] for a in AXES[axis] if junction.queues[a]]
        return junction.time - min(oldest) if oldest else 0.0

    def decide(self, junction) -> bool:
        axis = junction.green_axis
        if axis is None or junction.phase_time < self.min_green:  # rule 1
            return False
        red = OTHER_AXIS[axis]
        if junction.queue_length(red) == 0:  # rule 2
            return False
        if junction.phase_time >= self.max_green:  # rule 3
            return True
        if junction.queue_length(axis) == 0 and junction.time_since_arrival(axis) >= self.gap:  # rule 4
            return True
        return self.head_wait(junction, red) > self.head_wait(junction, axis) + self.margin  # rule 5


def register() -> None:
    """Add the controller to the registry so every GreenWave tool can find it by name."""
    CONTROLLERS[LongestWaitFirst.name] = LongestWaitFirst


def format_table(results: Sequence[Metrics]) -> str:
    """Render benchmark results as an aligned text table, best average delay marked."""
    best = min(results, key=lambda m: m.avg_delay).controller
    header = f"{'controller':<13}{'avg delay':>11}{'max delay':>11}{'veh/h':>8}{'avg queue':>11}{'switches':>10}"
    rows = [header, "-" * len(header)]
    for m in results:
        mark = "  <- best" if m.controller == best else ""
        rows.append(
            f"{m.controller:<13}{m.avg_delay:>9.1f} s{m.max_delay:>9.1f} s"
            f"{m.throughput_per_hour:>8.0f}{m.avg_queue:>11.1f}{m.switches:>10}{mark}"
        )
    return "\n".join(rows)


def main(argv: Sequence[str] | None = None) -> list[Metrics]:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--duration", type=float, default=1800.0, help="simulated seconds per run (default 1800)")
    parser.add_argument("--seeds", type=int, default=3, help="number of random seeds (default 3)")
    args = parser.parse_args(argv)

    register()
    names = ["fixed", "webster", "actuated", "maxpressure", LongestWaitFirst.name]
    # Heavier-than-default demand, so the controllers actually have to work.
    demand = {"N": 0.16, "S": 0.14, "E": 0.11, "W": 0.09}
    # Every controller sees exactly the same random arrivals (same seeds).
    results = benchmark(names, demand, duration=args.duration, seeds=range(1, args.seeds + 1))

    print(f"Demand (veh/s): {demand}  |  {args.duration:.0f} s x {args.seeds} seeds\n")
    print(format_table(results))
    return results


if __name__ == "__main__":
    main()
