"""Webster's method for fixed-time signal plans.

F. V. Webster (1958), *Traffic Signal Settings*, Road Research Technical Paper 39,
derived the cycle length that minimises average delay at a fixed-time junction:

    C0 = (1.5 L + 5) / (1 - Y)

where ``L`` is the total lost time per cycle (seconds) and ``Y`` is the sum of the
critical flow ratios ``y = q / s`` (arrival flow over saturation flow) of each
phase. Effective green time is then shared between phases in proportion to ``y``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

#: Default bounds applied to the computed cycle length (seconds).
MIN_CYCLE = 30.0
MAX_CYCLE = 120.0


@dataclass(frozen=True)
class WebsterPlan:
    """A fixed-time plan produced by :func:`webster_plan`.

    Attributes:
        cycle: Cycle length in seconds (after clamping to the allowed range).
        unclamped_cycle: Webster's raw optimum (``inf`` when oversaturated).
        flow_ratios: Critical flow ratio ``y`` of each phase.
        total_flow_ratio: ``Y``, the sum of the critical flow ratios.
        lost_time: Total lost time ``L`` per cycle in seconds.
        greens: Effective green time of each phase in seconds.
        oversaturated: ``True`` when ``Y >= 1`` and no cycle can serve demand.
    """

    cycle: float
    unclamped_cycle: float
    flow_ratios: dict[str, float]
    total_flow_ratio: float
    lost_time: float
    greens: dict[str, float]
    oversaturated: bool


def optimal_cycle(lost_time: float, total_flow_ratio: float) -> float:
    """Return Webster's optimum cycle length ``(1.5 L + 5) / (1 - Y)``.

    Returns ``math.inf`` when the junction is oversaturated (``Y >= 1``).

    >>> round(optimal_cycle(10, 0.55), 2)
    44.44
    """
    if lost_time < 0:
        raise ValueError("lost_time must be non-negative")
    if total_flow_ratio < 0:
        raise ValueError("total_flow_ratio must be non-negative")
    if total_flow_ratio >= 1:
        return float("inf")
    return (1.5 * lost_time + 5.0) / (1.0 - total_flow_ratio)


def webster_plan(
    phase_flows: Mapping[str, Sequence[float]],
    saturation_flow: float,
    lost_time_per_phase: float,
    min_cycle: float = MIN_CYCLE,
    max_cycle: float = MAX_CYCLE,
) -> WebsterPlan:
    """Compute a Webster fixed-time plan.

    Args:
        phase_flows: For each phase, the arrival flows of the approaches it serves
            (any consistent unit, e.g. veh/h). The *critical* (largest) flow sets
            the phase's flow ratio.
        saturation_flow: Saturation flow per approach in the same unit.
        lost_time_per_phase: Lost time per phase in seconds (start-up loss plus
            the part of the inter-green that cannot be used).
        min_cycle: Lower bound for the returned cycle.
        max_cycle: Upper bound for the returned cycle.

    Returns:
        A :class:`WebsterPlan`. When oversaturated the cycle is ``max_cycle``
        and green is split in proportion to the flow ratios anyway.
    """
    if saturation_flow <= 0:
        raise ValueError("saturation_flow must be positive")
    if not phase_flows:
        raise ValueError("at least one phase is required")
    if min_cycle > max_cycle:
        raise ValueError("min_cycle must not exceed max_cycle")

    ratios = {phase: max(flows, default=0.0) / saturation_flow for phase, flows in phase_flows.items()}
    total_y = sum(ratios.values())
    lost = lost_time_per_phase * len(phase_flows)
    raw = optimal_cycle(lost, total_y)
    cycle = min(max(raw, min_cycle, lost + len(phase_flows)), max_cycle)

    effective = cycle - lost
    if total_y > 0:
        greens = {phase: effective * y / total_y for phase, y in ratios.items()}
    else:
        greens = {phase: effective / len(ratios) for phase in ratios}

    return WebsterPlan(
        cycle=cycle,
        unclamped_cycle=raw,
        flow_ratios=ratios,
        total_flow_ratio=total_y,
        lost_time=lost,
        greens=greens,
        oversaturated=total_y >= 1,
    )
