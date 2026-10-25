"""Signal control strategies.

A controller is consulted on every simulation step while an axis shows green
and answers one question: *should the green move to the other axis now?*
The junction takes care of the safe UK inter-green (amber, all-red,
red+amber) on its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Mapping, Protocol

from .webster import webster_plan

if TYPE_CHECKING:  # pragma: no cover - imported for type hints only
    from .sim import Timing


class JunctionView(Protocol):
    """The read-only part of :class:`greenwave.sim.Junction` controllers use."""

    time: float
    phase_time: float

    @property
    def green_axis(self) -> str | None: ...

    def queue_length(self, axis_or_approach: str) -> int: ...

    def time_since_arrival(self, axis: str) -> float: ...


_OTHER = {"NS": "EW", "EW": "NS"}


class Controller:
    """Base class for signal controllers."""

    name = "base"
    description = ""

    def reset(self, demand: Mapping[str, float], timing: Timing) -> None:
        """Called once before a run with the junction's demand and timings."""

    def decide(self, junction: JunctionView) -> bool:
        """Return ``True`` to end the current green and switch axis."""
        raise NotImplementedError

    def __repr__(self) -> str:
        params = ", ".join(f"{k}={v!r}" for k, v in vars(self).items() if not k.startswith("_"))
        return f"{type(self).__name__}({params})"


class FixedTime(Controller):
    """Classic fixed-time plan: every axis gets the same green, demand or not."""

    name = "fixed"
    description = "Fixed 30 s green per axis, ignores traffic"

    def __init__(self, green: float = 30.0) -> None:
        if green <= 0:
            raise ValueError("green must be positive")
        self.green = green

    def decide(self, junction: JunctionView) -> bool:
        return junction.phase_time >= self.green


class Actuated(Controller):
    """Vehicle-actuated control with minimum green, gap-out and max-out.

    The green is extended while vehicles keep arriving; it ends when the
    green axis has been empty for ``gap`` seconds (gap-out) or after
    ``max_green`` (max-out) -- but only if someone is waiting on the other
    axis. With no conflicting demand the signal rests on green.
    """

    name = "actuated"
    description = "Gap-out / max-out vehicle actuation (8-45 s green)"

    def __init__(self, min_green: float = 8.0, max_green: float = 45.0, gap: float = 3.0) -> None:
        if not 0 < min_green <= max_green:
            raise ValueError("require 0 < min_green <= max_green")
        self.min_green, self.max_green, self.gap = min_green, max_green, gap

    def decide(self, junction: JunctionView) -> bool:
        axis = junction.green_axis
        if axis is None or junction.phase_time < self.min_green:
            return False
        if junction.queue_length(_OTHER[axis]) == 0:
            return False
        if junction.phase_time >= self.max_green:
            return True
        return junction.queue_length(axis) == 0 and junction.time_since_arrival(axis) >= self.gap


class MaxPressure(Controller):
    """Max-pressure (back-pressure) control.

    Switch when the waiting queue on the red axis exceeds the queue on the
    green axis by more than ``threshold`` vehicles, subject to a minimum
    green and a maximum green that guarantees service. The threshold acts as
    hysteresis: every switch costs ~9 s of lost time, so flapping is expensive.
    """

    name = "maxpressure"
    description = "Serve the axis with the most queued vehicles"

    def __init__(self, min_green: float = 12.0, max_green: float = 40.0, threshold: int = 6) -> None:
        if not 0 < min_green <= max_green:
            raise ValueError("require 0 < min_green <= max_green")
        self.min_green, self.max_green, self.threshold = min_green, max_green, threshold

    def decide(self, junction: JunctionView) -> bool:
        axis = junction.green_axis
        if axis is None or junction.phase_time < self.min_green:
            return False
        waiting = junction.queue_length(_OTHER[axis])
        if waiting == 0:
            return False
        if junction.phase_time >= self.max_green:
            return True
        return waiting - junction.queue_length(axis) > self.threshold


class Webster(Controller):
    """Fixed-time plan with Webster-optimal cycle length and green splits.

    The plan is computed from the expected demand when the run starts, so it
    adapts to the *average* traffic but not to moment-to-moment fluctuations.
    """

    name = "webster"
    description = "Fixed-time, Webster-optimal cycle & splits"

    def __init__(self, min_cycle: float = 30.0, max_cycle: float = 120.0) -> None:
        self.min_cycle, self.max_cycle = min_cycle, max_cycle
        self._green: dict[str, float] = {"NS": 30.0, "EW": 30.0}

    def reset(self, demand: Mapping[str, float], timing: Timing) -> None:
        plan = webster_plan(
            {"NS": (demand.get("N", 0.0), demand.get("S", 0.0)), "EW": (demand.get("E", 0.0), demand.get("W", 0.0))},
            saturation_flow=timing.saturation_flow,
            lost_time_per_phase=timing.lost_time_per_phase,
            min_cycle=self.min_cycle,
            max_cycle=self.max_cycle,
        )
        # Effective green excludes start-up lost time, which the junction applies.
        self._green = {axis: g + timing.startup_lost for axis, g in plan.greens.items()}

    @property
    def greens(self) -> dict[str, float]:
        """Actual green time (seconds) per axis from the current plan."""
        return dict(self._green)

    def decide(self, junction: JunctionView) -> bool:
        axis = junction.green_axis
        return axis is not None and junction.phase_time >= self._green[axis]


#: Registry of available controllers by name.
CONTROLLERS: dict[str, Callable[..., Controller]] = {
    cls.name: cls for cls in (FixedTime, Actuated, MaxPressure, Webster)
}


def make_controller(name: str, **kwargs: float) -> Controller:
    """Instantiate a controller from :data:`CONTROLLERS` by name."""
    try:
        factory = CONTROLLERS[name.lower()]
    except KeyError:
        raise ValueError(f"unknown controller {name!r}; choose from {', '.join(CONTROLLERS)}") from None
    return factory(**kwargs)
