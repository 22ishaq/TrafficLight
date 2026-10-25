"""Fast mesoscopic simulation of a signalised four-way junction.

Each approach (``N``, ``E``, ``S``, ``W`` -- the direction traffic comes *from*)
is modelled as a single queue at its stop line:

* vehicles arrive as an independent Poisson process per approach;
* while an approach shows green, its queue discharges at the saturation flow
  (one vehicle every ``saturation_headway`` seconds) after a start-up lost time;
* nothing discharges on amber, red or red+amber -- the UK inter-green
  ``amber -> all-red -> red+amber`` is pure lost time.

The model is intentionally simple so that hours of traffic simulate in
milliseconds, which makes it a good bench for comparing signal controllers.
Runs are fully deterministic for a given seed.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .controllers import Controller, make_controller
from .metrics import Metrics, average

APPROACHES: tuple[str, ...] = ("N", "E", "S", "W")
AXES: dict[str, tuple[str, str]] = {"NS": ("N", "S"), "EW": ("E", "W")}
AXIS_OF: dict[str, str] = {"N": "NS", "S": "NS", "E": "EW", "W": "EW"}
OTHER_AXIS: dict[str, str] = {"NS": "EW", "EW": "NS"}

#: Default demand in vehicles per second for each approach.
DEFAULT_DEMAND: dict[str, float] = {"N": 0.12, "S": 0.12, "E": 0.08, "W": 0.08}

_EPS = 1e-9


class Phase(str, Enum):
    """Signal phases. The axis prefix names the axis the phase belongs to."""

    NS_GREEN = "NS_GREEN"
    NS_AMBER = "NS_AMBER"
    NS_RED_AMBER = "NS_RED_AMBER"
    EW_GREEN = "EW_GREEN"
    EW_AMBER = "EW_AMBER"
    EW_RED_AMBER = "EW_RED_AMBER"
    ALL_RED = "ALL_RED"


@dataclass(frozen=True)
class Timing:
    """Signal timings and discharge characteristics (seconds).

    The defaults follow UK practice: 3 s amber, 2 s red+amber and a short
    all-red clearance, with a saturation flow of 1800 veh/h per lane.
    """

    amber: float = 3.0
    all_red: float = 2.0
    red_amber: float = 2.0
    saturation_headway: float = 2.0
    startup_lost: float = 2.0

    @property
    def intergreen(self) -> float:
        """Time between one axis losing green and the other gaining it."""
        return self.amber + self.all_red + self.red_amber

    @property
    def saturation_flow(self) -> float:
        """Saturation flow per approach in vehicles per second."""
        return 1.0 / self.saturation_headway

    @property
    def lost_time_per_phase(self) -> float:
        """Seconds per phase in which no vehicle can discharge."""
        return self.intergreen + self.startup_lost


class Junction:
    """A four-way signalised junction driven by a :class:`Controller`.

    The junction exposes a small read-only view for controllers:
    :attr:`time`, :attr:`phase`, :attr:`phase_time`, :attr:`green_axis`,
    :meth:`queue_length` and :meth:`time_since_arrival`.
    """

    def __init__(
        self,
        controller: Controller | str = "actuated",
        demand: Mapping[str, float] | None = None,
        seed: int = 42,
        timing: Timing | None = None,
        initial_axis: str = "NS",
    ) -> None:
        if initial_axis not in AXES:
            raise ValueError(f"initial_axis must be one of {sorted(AXES)}")
        self.controller = make_controller(controller) if isinstance(controller, str) else controller
        self.demand = _normalise_demand(DEFAULT_DEMAND if demand is None else demand)
        self.timing = timing or Timing()
        self.seed = seed
        self._rng = random.Random(seed)

        self.time = 0.0
        self.phase = Phase(f"{initial_axis}_GREEN")
        self.phase_time = 0.0
        self.axis = initial_axis  # axis owning the current phase (next axis during ALL_RED)

        self.queues: dict[str, deque[float]] = {a: deque() for a in APPROACHES}
        self._credit = {a: 0.0 for a in APPROACHES}
        self._last_arrival = {axis: float("-inf") for axis in AXES}
        self._next_arrival = {a: self._draw_gap(a) for a in APPROACHES}

        self.spawned = 0
        self.served = 0
        self.switches = 0
        self.served_by_approach = {a: 0 for a in APPROACHES}
        self._delay_by_approach = {a: 0.0 for a in APPROACHES}
        self._total_delay = 0.0
        self._max_delay = 0.0
        self._queue_integral = 0.0
        self._max_queue = 0

        self.controller.reset(self.demand, self.timing)

    # ------------------------------------------------------------------ view
    @property
    def green_axis(self) -> str | None:
        """Axis currently showing green, or ``None`` during an inter-green."""
        return self.axis if self.phase.name.endswith("_GREEN") else None

    def queue_length(self, axis_or_approach: str) -> int:
        """Vehicles queued on an approach (``"N"``) or a whole axis (``"NS"``)."""
        if axis_or_approach in AXES:
            return sum(len(self.queues[a]) for a in AXES[axis_or_approach])
        return len(self.queues[axis_or_approach])

    def time_since_arrival(self, axis: str) -> float:
        """Seconds since the last vehicle arrived on ``axis``."""
        return self.time - self._last_arrival[axis]

    def light_for(self, approach: str) -> str:
        """UK signal aspect shown to ``approach``: red, red_amber, green or amber."""
        axis = AXIS_OF[approach]
        if self.phase.name.startswith(axis):
            return {"GREEN": "green", "AMBER": "amber", "RED_AMBER": "red_amber"}[self.phase.name[3:]]
        return "red"

    # ------------------------------------------------------------ simulation
    def step(self, dt: float) -> None:
        """Advance the junction by ``dt`` seconds."""
        if dt <= 0:
            raise ValueError("dt must be positive")
        t0, t1 = self.time, self.time + dt
        self._arrivals(t1)
        self._discharge(t0, dt)

        self.time = t1
        self.phase_time += dt
        self._advance_signal()

        queued = [len(q) for q in self.queues.values()]
        self._queue_integral += sum(queued) * dt
        self._max_queue = max(self._max_queue, *queued)

    def run(self, duration: float, dt: float = 0.5) -> Metrics:
        """Simulate ``duration`` seconds and return the resulting metrics."""
        steps = round(duration / dt)
        for _ in range(steps):
            self.step(dt)
        return self.metrics()

    def metrics(self) -> Metrics:
        """Metrics so far. Vehicles still queued count with their delay so far."""
        waiting = [(a, self.time - arrival) for a, q in self.queues.items() for arrival in q]
        total = self._total_delay + sum(d for _, d in waiting)
        count = self.served + len(waiting)
        by_approach: dict[str, float] = {}
        for a in APPROACHES:
            pending = [d for ap, d in waiting if ap == a]
            n = self.served_by_approach[a] + len(pending)
            by_approach[a] = (self._delay_by_approach[a] + sum(pending)) / n if n else 0.0
        duration = self.time or 1.0
        return Metrics(
            controller=self.controller.name,
            duration=self.time,
            avg_delay=total / count if count else 0.0,
            max_delay=max([self._max_delay, *(d for _, d in waiting)]),
            throughput_per_hour=self.served / duration * 3600.0,
            avg_queue=self._queue_integral / duration,
            max_queue=self._max_queue,
            served=self.served,
            spawned=self.spawned,
            remaining=len(waiting),
            switches=self.switches,
            delay_by_approach=by_approach,
        )

    # -------------------------------------------------------------- internals
    def _draw_gap(self, approach: str) -> float:
        rate = self.demand[approach]
        return self._rng.expovariate(rate) if rate > 0 else float("inf")

    def _arrivals(self, until: float) -> None:
        for a in APPROACHES:
            while self._next_arrival[a] < until:
                arrival = self._next_arrival[a]
                self.queues[a].append(arrival)
                self.spawned += 1
                self._last_arrival[AXIS_OF[a]] = arrival
                self._next_arrival[a] = arrival + self._draw_gap(a)

    def _discharge(self, t0: float, dt: float) -> None:
        if self.green_axis is None:
            return
        # Portion of this step that lies beyond the start-up lost time.
        usable = min(dt, self.phase_time + dt - self.timing.startup_lost)
        if usable <= 0:
            return
        for a in AXES[self.axis]:
            queue = self.queues[a]
            credit = self._credit[a] + usable / self.timing.saturation_headway
            n = min(int(credit + _EPS), len(queue))
            for _ in range(n):
                delay = max(0.0, t0 - queue.popleft())
                self._total_delay += delay
                self._delay_by_approach[a] += delay
                self._max_delay = max(self._max_delay, delay)
            credit -= n
            # An empty queue cannot bank capacity beyond one waiting slot.
            self._credit[a] = min(credit, 1.0) if not queue else credit
            self.served += n
            self.served_by_approach[a] += n

    def _enter(self, phase: Phase, axis: str) -> None:
        self.phase, self.axis, self.phase_time = phase, axis, 0.0

    def _advance_signal(self) -> None:
        t = self.timing
        name = self.phase.name
        if name.endswith("_GREEN"):
            if self.controller.decide(self):
                self.switches += 1
                self._enter(Phase(f"{self.axis}_AMBER"), self.axis)
        elif name.endswith("_RED_AMBER"):
            if self.phase_time >= t.red_amber - _EPS:
                self._enter(Phase(f"{self.axis}_GREEN"), self.axis)
                self._credit = {a: 0.0 for a in APPROACHES}
        elif name.endswith("_AMBER"):
            if self.phase_time >= t.amber - _EPS:
                self._enter(Phase.ALL_RED, OTHER_AXIS[self.axis])
        elif self.phase is Phase.ALL_RED:
            if self.phase_time >= t.all_red - _EPS:
                self._enter(Phase(f"{self.axis}_RED_AMBER"), self.axis)


def _normalise_demand(demand: Mapping[str, float]) -> dict[str, float]:
    unknown = set(demand) - set(APPROACHES)
    if unknown:
        raise ValueError(f"unknown approaches in demand: {sorted(unknown)}")
    result = {a: float(demand.get(a, 0.0)) for a in APPROACHES}
    if any(rate < 0 for rate in result.values()):
        raise ValueError("demand rates must be non-negative")
    return result


def simulate(
    controller: Controller | str = "actuated",
    demand: Mapping[str, float] | None = None,
    duration: float = 3600.0,
    seed: int = 42,
    dt: float = 0.5,
    timing: Timing | None = None,
) -> Metrics:
    """Run one simulation and return its :class:`Metrics`.

    >>> m = simulate("fixed", duration=600, seed=1)
    >>> m.spawned == m.served + m.remaining
    True
    """
    return Junction(controller, demand, seed=seed, timing=timing).run(duration, dt)


def benchmark(
    controllers: Iterable[str],
    demand: Mapping[str, float] | None = None,
    duration: float = 3600.0,
    seeds: Sequence[int] = (1, 2, 3, 4, 5),
    dt: float = 0.5,
    timing: Timing | None = None,
) -> list[Metrics]:
    """Run every controller on the *same* seeds and average the results."""
    return [
        average(simulate(name, demand, duration, seed, dt, timing) for seed in seeds)
        for name in controllers
    ]
