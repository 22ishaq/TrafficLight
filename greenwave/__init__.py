"""GreenWave -- a traffic-signal simulator and playground.

Quick start::

    >>> from greenwave import simulate
    >>> metrics = simulate("actuated", duration=600, seed=1)
    >>> metrics.spawned == metrics.served + metrics.remaining
    True

Run ``python -m greenwave --help`` for the command-line interface.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .controllers import CONTROLLERS, Actuated, Controller, FixedTime, MaxPressure, Webster, make_controller
from .metrics import Metrics
from .sim import APPROACHES, DEFAULT_DEMAND, Junction, Phase, Timing, benchmark, simulate
from .webster import WebsterPlan, optimal_cycle, webster_plan

__version__ = "1.0.0"

# Signal state machines are loaded on first use so that ``import greenwave``
# stays cheap and never depends on optional GUI modules.
_LAZY = {
    "LightState": "signals",
    "TrafficLight": "signals",
    "PelicanCrossing": "pelican",
}

__all__ = [
    "APPROACHES",
    "CONTROLLERS",
    "DEFAULT_DEMAND",
    "Actuated",
    "Controller",
    "FixedTime",
    "Junction",
    "MaxPressure",
    "Metrics",
    "Phase",
    "Timing",
    "Webster",
    "WebsterPlan",
    "__version__",
    "benchmark",
    "make_controller",
    "optimal_cycle",
    "simulate",
    "webster_plan",
    *_LAZY,
]


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        return getattr(import_module(f".{_LAZY[name]}", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
