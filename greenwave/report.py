"""Demand sweeps and a hand-written SVG chart of the results.

``sweep`` runs every controller across a range of total demand levels (on the
same random seeds) and ``render_svg`` draws average delay against demand as a
self-contained SVG card that reads well on both light and dark backgrounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence
from xml.sax.saxutils import escape

from .sim import Timing, benchmark

#: Line colours per controller (chosen to contrast on the dark card).
COLORS: dict[str, str] = {
    "fixed": "#94a3b8",
    "actuated": "#4ade80",
    "maxpressure": "#fbbf24",
    "webster": "#38bdf8",
}
_FALLBACK_COLORS = ("#f472b6", "#a78bfa", "#fb923c", "#2dd4bf")

# Card palette: a solid dark card is legible on GitHub's light *and* dark themes.
_CARD, _BORDER, _GRID, _AXIS = "#0f172a", "#1e293b", "#1e293b", "#475569"
_TEXT, _MUTED = "#f1f5f9", "#94a3b8"
_FONT = "font-family=\"ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif\""


@dataclass(frozen=True)
class SweepData:
    """Results of :func:`sweep`.

    Attributes:
        levels: Total junction demand of each point in vehicles per hour.
        delays: Average delay (s) per controller, aligned with ``levels``.
        throughput: Served vehicles per hour per controller, aligned with ``levels``.
        split: Share of the total demand on the N/S axis.
        duration: Simulated seconds per run.
        seeds: Random seeds averaged at every point.
    """

    levels: list[float]
    delays: dict[str, list[float]]
    throughput: dict[str, list[float]] = field(default_factory=dict)
    split: float = 0.6
    duration: float = 1800.0
    seeds: tuple[int, ...] = (1, 2, 3)


def demand_levels(count: int = 8, low: float = 400.0, high: float | None = None, timing: Timing | None = None) -> list[float]:
    """Evenly spaced total demand levels (veh/h) from light traffic to near saturation.

    By default ``high`` is 80 % of the junction's theoretical capacity
    (two approaches per axis at the saturation flow), i.e. ``Y = 0.8``.
    """
    if count < 2:
        raise ValueError("count must be at least 2")
    timing = timing or Timing()
    if high is None:
        high = 0.8 * 2 * timing.saturation_flow * 3600.0
    step = (high - low) / (count - 1)
    return [round(low + i * step) for i in range(count)]


def demand_for(total_per_hour: float, split: float) -> dict[str, float]:
    """Per-approach demand (veh/s) for a total junction demand and N/S share."""
    if not 0 <= split <= 1:
        raise ValueError("split must be between 0 and 1")
    total = total_per_hour / 3600.0
    ns, ew = total * split / 2, total * (1 - split) / 2
    return {"N": ns, "S": ns, "E": ew, "W": ew}


def sweep(
    controllers: Sequence[str],
    levels: Sequence[float],
    duration: float = 1800.0,
    seeds: Sequence[int] = (1, 2, 3),
    split: float = 0.6,
) -> SweepData:
    """Benchmark ``controllers`` at each total demand level (veh/h)."""
    delays: dict[str, list[float]] = {c: [] for c in controllers}
    throughput: dict[str, list[float]] = {c: [] for c in controllers}
    for level in levels:
        for result in benchmark(controllers, demand_for(level, split), duration, seeds):
            delays[result.controller].append(result.avg_delay)
            throughput[result.controller].append(result.throughput_per_hour)
    return SweepData(list(levels), delays, throughput, split, duration, tuple(seeds))


def nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    """Round tick values covering ``[lo, hi]`` (1-2-5 steps)."""
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / target
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(lo / step) * step
    ticks, value = [], start
    while value < hi + step * 0.5:
        ticks.append(round(value, 10))
        value += step
    return ticks


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 10 or value == int(value) else f"{value:.1f}"


def render_svg(data: SweepData, width: int = 800, height: int = 460, title: str | None = None) -> str:
    """Draw average delay vs total demand, one line per controller, as SVG."""
    if not data.levels or not data.delays:
        raise ValueError("nothing to plot")
    title = title or "Average delay vs demand"
    left, right, top, bottom = 76, 190, 84, 64
    plot_w, plot_h = width - left - right, height - top - bottom

    x_ticks = nice_ticks(min(data.levels), max(data.levels), 6)
    y_max = max(max(series) for series in data.delays.values())
    y_ticks = nice_ticks(0, y_max * 1.05, 5)
    x0, x1, y1 = x_ticks[0], x_ticks[-1], y_ticks[-1]

    def sx(v: float) -> float:
        return left + (v - x0) / (x1 - x0) * plot_w

    def sy(v: float) -> float:
        return top + plot_h - v / y1 * plot_h

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc" {_FONT}>',
        f'<title id="title">{escape(title)}</title>',
        f'<desc id="desc">GreenWave demand sweep: average vehicle delay in seconds for each signal controller '
        f'as total junction demand rises from {_fmt(data.levels[0])} to {_fmt(data.levels[-1])} vehicles per hour.</desc>',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" ry="14" '
        f'fill="{_CARD}" stroke="{_BORDER}" stroke-width="1"/>',
        f'<text x="{left}" y="38" fill="{_TEXT}" font-size="20" font-weight="700">{escape(title)}</text>',
        f'<text x="{left}" y="60" fill="{_MUTED}" font-size="13">'
        f'{data.split:.0%} of traffic on N/S · {data.duration:g} s × {len(data.seeds)} seeds per point · lower is better</text>',
    ]

    # Grid, ticks and tick labels.
    for v in y_ticks:
        y = sy(v)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{_GRID}" stroke-width="1" fill="none"/>')
        out.append(f'<text x="{left - 10}" y="{y + 4:.1f}" fill="{_MUTED}" font-size="12" text-anchor="end">{_fmt(v)}</text>')
    for v in x_ticks:
        x = sx(v)
        out.append(f'<line x1="{x:.1f}" y1="{top + plot_h}" x2="{x:.1f}" y2="{top + plot_h + 5}" stroke="{_AXIS}" stroke-width="1" fill="none"/>')
        out.append(f'<text x="{x:.1f}" y="{top + plot_h + 21}" fill="{_MUTED}" font-size="12" text-anchor="middle">{_fmt(v)}</text>')
    out.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="{_AXIS}" stroke-width="1.5" fill="none"/>'
    )
    out.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="{_AXIS}" stroke-width="1.5" fill="none"/>')
    out.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 18}" fill="{_TEXT}" font-size="13" text-anchor="middle">'
        f"Total demand (veh/h)</text>"
    )
    cy = top + plot_h / 2
    out.append(
        f'<text x="22" y="{cy:.1f}" fill="{_TEXT}" font-size="13" text-anchor="middle" '
        f'transform="rotate(-90 22 {cy:.1f})">Average delay (s)</text>'
    )

    # One line per controller, best (lowest mean delay) drawn last so it sits on top.
    order = sorted(data.delays, key=lambda c: -sum(data.delays[c]))
    colors = {c: COLORS.get(c, _FALLBACK_COLORS[i % len(_FALLBACK_COLORS)]) for i, c in enumerate(data.delays)}
    for name in order:
        series, color = data.delays[name], colors[name]
        points = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(zip(data.levels, series)))
        dash = ' stroke-dasharray="6 5"' if name == "fixed" else ""
        out.append(
            f'<path d="{points}" fill="none" stroke="{color}" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round"{dash} data-controller="{escape(name)}"/>'
        )
        for x, y in zip(data.levels, series):
            out.append(
                f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3.5" fill="{color}" stroke="{_CARD}" stroke-width="1.5">'
                f"<title>{escape(name)}: {y:.1f} s at {_fmt(x)} veh/h</title></circle>"
            )

    # Legend with the delay at the heaviest demand level.
    lx, ly = left + plot_w + 28, top + 6
    out.append(f'<text x="{lx}" y="{ly}" fill="{_MUTED}" font-size="12">at {_fmt(data.levels[-1])} veh/h</text>')
    ranking = sorted(data.delays, key=lambda c: data.delays[c][-1])
    for i, name in enumerate(ranking):
        y = ly + 30 + i * 38
        color = colors[name]
        dash = ' stroke-dasharray="6 5"' if name == "fixed" else ""
        out.append(f'<line x1="{lx}" y1="{y - 4}" x2="{lx + 22}" y2="{y - 4}" stroke="{color}" stroke-width="3" fill="none"{dash}/>')
        out.append(f'<text x="{lx + 30}" y="{y}" fill="{_TEXT}" font-size="13" font-weight="600">{escape(name)}</text>')
        out.append(f'<text x="{lx + 30}" y="{y + 15}" fill="{_MUTED}" font-size="12">{data.delays[name][-1]:.1f} s</text>')
    out.append(
        f'<text x="{width - 16}" y="{height - 18}" fill="{_AXIS}" font-size="11" text-anchor="end">greenwave sweep</text>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"
