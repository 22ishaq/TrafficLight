"""Performance metrics collected by the junction simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import fmean
from typing import Any, Iterable


@dataclass(frozen=True)
class Metrics:
    """Summary of one simulation run (or an average over several runs).

    Attributes:
        controller: Name of the signal controller that produced the run.
        duration: Simulated time in seconds.
        avg_delay: Mean delay (seconds) of every vehicle that left the junction.
        max_delay: Worst single-vehicle delay in seconds.
        throughput_per_hour: Vehicles served, scaled to vehicles per hour.
        avg_queue: Time-averaged number of vehicles queued over all approaches.
        max_queue: Longest queue seen on any single approach.
        served: Vehicles that crossed the stop line.
        spawned: Vehicles that arrived at the junction.
        remaining: Vehicles still queued when the run ended.
        switches: Number of times the green moved to the other axis.
        delay_by_approach: Mean delay per approach (``N``, ``E``, ``S``, ``W``).
    """

    controller: str
    duration: float
    avg_delay: float
    max_delay: float
    throughput_per_hour: float
    avg_queue: float
    max_queue: int
    served: int
    spawned: int
    remaining: int
    switches: int
    delay_by_approach: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary of the metrics."""
        return asdict(self)


def average(runs: Iterable[Metrics]) -> Metrics:
    """Average several runs of the *same* controller into one :class:`Metrics`.

    Counters are averaged and rounded; ``max_*`` fields keep the worst case.
    """
    runs = list(runs)
    if not runs:
        raise ValueError("cannot average zero runs")
    approaches = runs[0].delay_by_approach.keys()
    return Metrics(
        controller=runs[0].controller,
        duration=runs[0].duration,
        avg_delay=fmean(r.avg_delay for r in runs),
        max_delay=max(r.max_delay for r in runs),
        throughput_per_hour=fmean(r.throughput_per_hour for r in runs),
        avg_queue=fmean(r.avg_queue for r in runs),
        max_queue=max(r.max_queue for r in runs),
        served=round(fmean(r.served for r in runs)),
        spawned=round(fmean(r.spawned for r in runs)),
        remaining=round(fmean(r.remaining for r in runs)),
        switches=round(fmean(r.switches for r in runs)),
        delay_by_approach={a: fmean(r.delay_by_approach[a] for r in runs) for a in approaches},
    )
