"""UK traffic light state machine.

A British traffic signal cycles through four aspects::

    RED -> RED_AMBER -> GREEN -> AMBER -> RED -> ...

:class:`TrafficLight` models that sequence both as a discrete state machine
(:meth:`TrafficLight.advance`) and as a time-driven one (:meth:`TrafficLight.tick`).
It has no GUI dependencies so it can be unit tested and reused by any front end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = ["LightState", "Durations", "TrafficLight", "UK_SEQUENCE"]

#: Tolerance for floating-point drift when many small ticks are summed.
EPSILON = 1e-9


class LightState(Enum):
    """The four aspects of a UK traffic signal."""

    RED = "red"
    RED_AMBER = "red_amber"
    GREEN = "green"
    AMBER = "amber"

    @property
    def lamps(self) -> dict[str, bool]:
        """Which of the three lamps are lit for this aspect."""
        return {
            "red": self in (LightState.RED, LightState.RED_AMBER),
            "amber": self in (LightState.RED_AMBER, LightState.AMBER),
            "green": self is LightState.GREEN,
        }

    @property
    def next(self) -> LightState:
        """The aspect that follows this one in the UK sequence."""
        return _NEXT[self]


UK_SEQUENCE: tuple[LightState, ...] = (
    LightState.RED,
    LightState.RED_AMBER,
    LightState.GREEN,
    LightState.AMBER,
)

_NEXT: dict[LightState, LightState] = {
    state: UK_SEQUENCE[(i + 1) % len(UK_SEQUENCE)] for i, state in enumerate(UK_SEQUENCE)
}


@dataclass(frozen=True)
class Durations:
    """How long (in seconds) each aspect is shown when the light runs on a timer.

    A duration of ``None`` means "hold until told otherwise" (e.g. a crossing
    that rests on green until a pedestrian presses the button).
    """

    red: float | None = 30.0
    red_amber: float | None = 2.0
    green: float | None = 30.0
    amber: float | None = 3.0

    def for_state(self, state: LightState) -> float | None:
        return {
            LightState.RED: self.red,
            LightState.RED_AMBER: self.red_amber,
            LightState.GREEN: self.green,
            LightState.AMBER: self.amber,
        }[state]

    def __post_init__(self) -> None:
        for name in ("red", "red_amber", "green", "amber"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"duration for {name!r} must be positive or None, got {value!r}")

    @property
    def cycle(self) -> float | None:
        """Total cycle length, or ``None`` if any aspect holds indefinitely."""
        parts = (self.red, self.red_amber, self.green, self.amber)
        if any(p is None for p in parts):
            return None
        return float(sum(parts))  # type: ignore[arg-type]


@dataclass
class TrafficLight:
    """A single UK traffic signal head.

    >>> light = TrafficLight()
    >>> light.state
    <LightState.RED: 'red'>
    >>> light.advance().state
    <LightState.RED_AMBER: 'red_amber'>
    >>> light.lamps
    {'red': True, 'amber': True, 'green': False}
    """

    state: LightState = LightState.RED
    durations: Durations = field(default_factory=Durations)
    elapsed: float = 0.0

    def advance(self) -> TrafficLight:
        """Step to the next aspect immediately. Returns ``self`` for chaining."""
        self.state = self.state.next
        self.elapsed = 0.0
        return self

    def set(self, state: LightState) -> TrafficLight:
        """Force an aspect (resets the aspect timer)."""
        self.state = state
        self.elapsed = 0.0
        return self

    @property
    def lamps(self) -> dict[str, bool]:
        """Mapping of lamp name (``'red'``, ``'amber'``, ``'green'``) to lit/unlit."""
        return self.state.lamps

    @property
    def remaining(self) -> float | None:
        """Seconds left in the current aspect, or ``None`` if it holds indefinitely."""
        duration = self.durations.for_state(self.state)
        if duration is None:
            return None
        return max(0.0, duration - self.elapsed)

    def tick(self, dt: float) -> list[LightState]:
        """Advance time by ``dt`` seconds.

        Handles ``dt`` larger than a single aspect by stepping through as many
        aspects as needed. Returns the list of aspects entered during this tick
        (empty if the aspect did not change).
        """
        if dt < 0:
            raise ValueError("dt must be non-negative")
        entered: list[LightState] = []
        self.elapsed += dt
        while True:
            duration = self.durations.for_state(self.state)
            if duration is None or self.elapsed < duration - EPSILON:
                break
            overflow = max(0.0, self.elapsed - duration)
            self.advance()
            self.elapsed = overflow
            entered.append(self.state)
        return entered

    @property
    def can_proceed(self) -> bool:
        """``True`` only when vehicles may enter the junction (green)."""
        return self.state is LightState.GREEN
