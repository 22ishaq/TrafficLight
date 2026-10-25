"""UK pelican crossing state machine.

A *pelican* (PEdestrian LIght CONtrolled) crossing rests on green for traffic
until a pedestrian presses the push-button. The sequence is then::

    vehicles GREEN  (button pressed, WAIT lamp lit; held for at least min_green)
      -> vehicles AMBER                            pedestrians: red man
      -> vehicles RED  (all-red clearance)         pedestrians: red man
      -> vehicles RED                              pedestrians: GREEN MAN (walk)
      -> vehicles FLASHING AMBER                   pedestrians: flashing green man
      -> vehicles GREEN                            pedestrians: red man

This is the bug-fixed, fully testable evolution of the original ``trafficlight``
turtle script in this repository: the original was a button-triggered crossing
that rested on green "infinitely" (via a 1e9 ms timer) and never handled a
second press. All timing lives here; :mod:`greenwave.classic` only draws it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = ["PelicanPhase", "PelicanTimings", "PelicanCrossing"]

#: Tolerance for floating-point drift when many small ticks are summed.
EPSILON = 1e-9


class PelicanPhase(Enum):
    """Phases of a pelican crossing cycle."""

    VEHICLE_GREEN = "vehicle_green"
    VEHICLE_AMBER = "vehicle_amber"
    ALL_RED = "all_red"
    PEDESTRIAN_WALK = "pedestrian_walk"
    FLASHING = "flashing"


@dataclass(frozen=True)
class PelicanTimings:
    """Phase durations in seconds (UK-style defaults, shortened for a demo).

    ``min_green`` is the minimum time traffic keeps green before a button
    press is honoured. ``flash_period`` is one full on+off blink cycle.
    """

    min_green: float = 10.0
    amber: float = 3.0
    all_red: float = 2.0
    walk: float = 7.0
    flashing: float = 6.0
    flash_period: float = 1.0

    def __post_init__(self) -> None:
        for name in ("amber", "all_red", "walk", "flashing", "flash_period"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.min_green < 0:
            raise ValueError("min_green must be non-negative")

    @classmethod
    def fast(cls) -> PelicanTimings:
        """Shortened timings, handy for demos and the ``--fast`` flag."""
        return cls(min_green=3.0, amber=1.5, all_red=1.0, walk=3.0, flashing=3.0, flash_period=0.5)

    @property
    def crossing_cycle(self) -> float:
        """Time from the start of amber until traffic is green again."""
        return self.amber + self.all_red + self.walk + self.flashing


@dataclass
class PelicanCrossing:
    """Time-driven pelican crossing controller.

    Drive it by calling :meth:`tick` with elapsed seconds and
    :meth:`press_button` when a pedestrian pushes the button.

    >>> crossing = PelicanCrossing(PelicanTimings(min_green=0))
    >>> crossing.vehicle_signal, crossing.pedestrian_signal
    ('green', 'dont_walk')
    >>> crossing.press_button()
    True
    >>> crossing.wait_indicator
    True
    >>> _ = crossing.tick(0.0)
    >>> crossing.vehicle_signal
    'amber'
    """

    timings: PelicanTimings = field(default_factory=PelicanTimings)
    phase: PelicanPhase = PelicanPhase.VEHICLE_GREEN
    phase_time: float = 0.0
    time: float = 0.0
    crossings_served: int = 0
    _demand: bool = field(default=False, repr=False)
    _demand_at: float = field(default=0.0, repr=False)

    # ------------------------------------------------------------------ input
    def press_button(self) -> bool:
        """Register a pedestrian request.

        Returns ``True`` if the press registered a (new or existing) demand.
        Presses while the green man is already showing are ignored, because
        the pedestrian is already being served. Presses during the flashing
        phase are queued for the next cycle (the WAIT lamp lights again).
        """
        if self.phase is PelicanPhase.PEDESTRIAN_WALK:
            return False
        if not self._demand:
            self._demand = True
            # Only meaningful in VEHICLE_GREEN; a queued press restarts the clock at green.
            self._demand_at = self.phase_time if self.phase is PelicanPhase.VEHICLE_GREEN else 0.0
        return True

    # ------------------------------------------------------------------- time
    def tick(self, dt: float) -> list[PelicanPhase]:
        """Advance time by ``dt`` seconds; returns the phases entered (in order).

        Large ``dt`` values are handled exactly: surplus time carries into the
        following phase(s), so ticking 10 × 0.1 s equals ticking 1 × 1.0 s.
        """
        if dt < 0:
            raise ValueError("dt must be non-negative")
        self.time += dt
        self.phase_time += dt
        entered: list[PelicanPhase] = []
        while True:
            ends_at = self._phase_end()
            if ends_at is None or self.phase_time < ends_at - EPSILON:
                break
            overflow = max(0.0, self.phase_time - ends_at)
            self._enter(self._next_phase())
            self.phase_time = overflow
            entered.append(self.phase)
        return entered

    def _phase_end(self) -> float | None:
        t = self.timings
        if self.phase is PelicanPhase.VEHICLE_GREEN:
            if not self._demand:
                return None  # rest on green indefinitely
            return max(t.min_green, self._demand_at)
        return {
            PelicanPhase.VEHICLE_AMBER: t.amber,
            PelicanPhase.ALL_RED: t.all_red,
            PelicanPhase.PEDESTRIAN_WALK: t.walk,
            PelicanPhase.FLASHING: t.flashing,
        }[self.phase]

    def _next_phase(self) -> PelicanPhase:
        order = {
            PelicanPhase.VEHICLE_GREEN: PelicanPhase.VEHICLE_AMBER,
            PelicanPhase.VEHICLE_AMBER: PelicanPhase.ALL_RED,
            PelicanPhase.ALL_RED: PelicanPhase.PEDESTRIAN_WALK,
            PelicanPhase.PEDESTRIAN_WALK: PelicanPhase.FLASHING,
            PelicanPhase.FLASHING: PelicanPhase.VEHICLE_GREEN,
        }
        return order[self.phase]

    def _enter(self, phase: PelicanPhase) -> None:
        self.phase = phase
        if phase is PelicanPhase.PEDESTRIAN_WALK:
            # Green man showing: the current demand is being served.
            self._demand = False
            self.crossings_served += 1
        elif phase is PelicanPhase.VEHICLE_GREEN and self._demand:
            # A press queued during the flashing phase; min green counts from now.
            self._demand_at = 0.0

    def reset(self) -> None:
        """Return to resting green with no demand."""
        self.phase = PelicanPhase.VEHICLE_GREEN
        self.phase_time = 0.0
        self.time = 0.0
        self.crossings_served = 0
        self._demand = False
        self._demand_at = 0.0

    # ----------------------------------------------------------------- output
    @property
    def remaining(self) -> float | None:
        """Seconds left in the current phase (``None`` while resting on green)."""
        end = self._phase_end()
        return None if end is None else max(0.0, end - self.phase_time)

    @property
    def flash_on(self) -> bool:
        """Blink state for flashing aspects: on for the first half of each period."""
        period = self.timings.flash_period
        return (self.phase_time % period) < period / 2

    @property
    def vehicle_signal(self) -> str:
        """``'green'``, ``'amber'``, ``'red'`` or ``'flashing_amber'``."""
        return {
            PelicanPhase.VEHICLE_GREEN: "green",
            PelicanPhase.VEHICLE_AMBER: "amber",
            PelicanPhase.ALL_RED: "red",
            PelicanPhase.PEDESTRIAN_WALK: "red",
            PelicanPhase.FLASHING: "flashing_amber",
        }[self.phase]

    @property
    def pedestrian_signal(self) -> str:
        """``'dont_walk'`` (red man), ``'walk'`` (green man) or ``'flashing'``."""
        if self.phase is PelicanPhase.PEDESTRIAN_WALK:
            return "walk"
        if self.phase is PelicanPhase.FLASHING:
            return "flashing"
        return "dont_walk"

    @property
    def wait_indicator(self) -> bool:
        """Whether the push-button's WAIT lamp is lit."""
        return self._demand

    @property
    def vehicle_lamps(self) -> dict[str, bool]:
        """Lit state of the vehicle head's red/amber/green lamps, blinking included."""
        signal = self.vehicle_signal
        return {
            "red": signal == "red",
            "amber": signal == "amber" or (signal == "flashing_amber" and self.flash_on),
            "green": signal == "green",
        }

    @property
    def pedestrian_lamps(self) -> dict[str, bool]:
        """Lit state of the red-man / green-man lamps, blinking included."""
        signal = self.pedestrian_signal
        return {
            "red_man": signal == "dont_walk",
            "green_man": signal == "walk" or (signal == "flashing" and self.flash_on),
        }

    @property
    def vehicles_may_proceed(self) -> bool:
        """Green, or flashing amber (give way to pedestrians still crossing)."""
        return self.phase in (PelicanPhase.VEHICLE_GREEN, PelicanPhase.FLASHING)
