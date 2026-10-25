"""Command-line interface: ``python -m greenwave`` / ``greenwave``."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Sequence, TextIO

from . import __version__
from .controllers import CONTROLLERS
from .metrics import Metrics
from .sim import APPROACHES, DEFAULT_DEMAND, Timing, benchmark
from .webster import webster_plan

_DEMAND_ORDER = ("N", "S", "E", "W")


# --------------------------------------------------------------------- helpers
def parse_demand(text: str) -> dict[str, float]:
    """Parse ``--demand``: one value (all approaches), two (NS,EW) or four (N,S,E,W)."""
    try:
        values = [float(v) for v in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid demand {text!r}: expected comma-separated numbers") from None
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise argparse.ArgumentTypeError("demand must be finite and non-negative")
    if len(values) == 1:
        return {a: values[0] for a in APPROACHES}
    if len(values) == 2:
        return {"N": values[0], "S": values[0], "E": values[1], "W": values[1]}
    if len(values) == 4:
        return dict(zip(_DEMAND_ORDER, values))
    raise argparse.ArgumentTypeError("demand takes 1 (all), 2 (NS,EW) or 4 (N,S,E,W) values")


def parse_controllers(text: str) -> list[str]:
    names = [n.strip().lower() for n in text.split(",") if n.strip()]
    unknown = [n for n in names if n not in CONTROLLERS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(
            f"unknown controller(s): {', '.join(unknown) or '(none)'}; choose from {', '.join(CONTROLLERS)}"
        )
    return names


def _positive(kind: type[float] | type[int]):
    def convert(text: str) -> float | int:
        value = kind(text)
        if not math.isfinite(value) or value <= 0:
            raise argparse.ArgumentTypeError(f"must be a positive finite number, got {text}")
        return value

    return convert


def parse_flows(text: str) -> list[float]:
    """Parse ``--flows N,S,E,W`` (veh/h): four finite, non-negative numbers."""
    try:
        values = [float(v) for v in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid flows {text!r}: expected four numbers N,S,E,W") from None
    if len(values) != 4 or any(not math.isfinite(v) or v < 0 for v in values):
        raise argparse.ArgumentTypeError("flows need four finite, non-negative numbers: N,S,E,W")
    return values


def _fraction(text: str) -> float:
    value = float(text)
    if not 0 < value < 1:
        raise argparse.ArgumentTypeError(f"must be between 0 and 1, got {text}")
    return value


class _Style:
    """Minimal ANSI styling, disabled for pipes and when NO_COLOR is set."""

    def __init__(self, stream: TextIO) -> None:
        self.enabled = stream.isatty() and "NO_COLOR" not in os.environ

    def __call__(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text


def _format_demand(demand: dict[str, float]) -> str:
    return "  ".join(f"{a} {demand[a]:.3g}" for a in _DEMAND_ORDER) + " veh/s"


def render_table(results: Sequence[Metrics], baseline: str, style: _Style | None = None) -> str:
    """Render benchmark results as an aligned text table."""
    style = style or _Style(sys.stdout)
    base = next(r for r in results if r.controller == baseline)
    best = min(results, key=lambda r: r.avg_delay)
    headers = ("", "Controller", "Avg delay", "Max delay", "Throughput", "Avg queue", f"Delay vs {baseline}")
    rows: list[tuple[str, ...]] = []
    for r in results:
        if r.controller == baseline:
            change = "baseline"
        elif base.avg_delay > 0:
            change = f"{(r.avg_delay - base.avg_delay) / base.avg_delay * 100:+.1f} %"
        else:
            change = "n/a"
        rows.append(
            (
                "★" if r is best else " ",
                r.controller,
                f"{r.avg_delay:.1f} s",
                f"{r.max_delay:.0f} s",
                f"{r.throughput_per_hour:,.0f} veh/h",
                f"{r.avg_queue:.1f} veh",
                change,
            )
        )
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    left = {0, 1}

    def fmt(cells: Sequence[str]) -> str:
        return "  ".join(c.ljust(w) if i in left else c.rjust(w) for i, (c, w) in enumerate(zip(cells, widths)))

    lines = [style(fmt(headers), "1"), "  ".join("─" * w for w in widths)]
    for r, row in zip(results, rows):
        line = fmt(row)
        if r is best:
            line = style(line, "1;32")
        lines.append(line)
    return "\n".join(lines)


# ------------------------------------------------------------------- commands
def _cmd_benchmark(args: argparse.Namespace) -> int:
    seeds = list(range(args.seed, args.seed + args.seeds))
    results = benchmark(args.controllers, args.demand, args.duration, seeds, dt=args.dt)
    baseline = "fixed" if "fixed" in args.controllers else args.controllers[0]
    best = min(results, key=lambda r: r.avg_delay)
    base = next(r for r in results if r.controller == baseline)

    if args.json:
        payload = {
            "version": __version__,
            "config": {"duration": args.duration, "seeds": seeds, "demand": args.demand, "dt": args.dt},
            "baseline": baseline,
            "best": best.controller,
            "results": [
                {
                    **r.to_dict(),
                    "delay_vs_baseline_pct": (
                        (r.avg_delay - base.avg_delay) / base.avg_delay * 100 if base.avg_delay else None
                    ),
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    style = _Style(sys.stdout)
    print(style("GreenWave benchmark", "1"), f"· {args.duration:g} s simulated × {len(seeds)} seed(s)")
    print(f"demand  {_format_demand(args.demand)}")
    print()
    print(render_table(results, baseline, style))
    print()
    if best.controller != baseline and base.avg_delay > 0:
        saved = (base.avg_delay - best.avg_delay) / base.avg_delay * 100
        print(f"★ {style(best.controller, '1;32')} wins: {saved:.0f} % less delay than {baseline}.")
    else:
        print(f"★ {style(best.controller, '1;32')} has the lowest average delay.")
    return 0


def _cmd_webster(args: argparse.Namespace) -> int:
    flows = dict(zip(_DEMAND_ORDER, args.flows))
    plan = webster_plan(
        {"NS": (flows["N"], flows["S"]), "EW": (flows["E"], flows["W"])},
        saturation_flow=args.saturation,
        lost_time_per_phase=args.lost_time,
        min_cycle=args.min_cycle,
        max_cycle=args.max_cycle,
    )
    style = _Style(sys.stdout)
    print(style("Webster fixed-time plan", "1"))
    print(f"  flows (veh/h)      N {flows['N']:g}  S {flows['S']:g}  E {flows['E']:g}  W {flows['W']:g}")
    print(f"  saturation flow    {args.saturation:g} veh/h per approach")
    for axis in ("NS", "EW"):
        print(f"  y[{axis}]              {plan.flow_ratios[axis]:.3f}")
    print(f"  Y = Σy             {plan.total_flow_ratio:.3f}")
    print(f"  lost time L        {plan.lost_time:g} s")
    if plan.oversaturated:
        print(style("  Y ≥ 1: junction is oversaturated -- no cycle can serve this demand.", "1;31"))
    else:
        print(f"  optimum C0         {plan.unclamped_cycle:.1f} s  = (1.5·L + 5) / (1 − Y)")
    print(style(f"  cycle used         {plan.cycle:.1f} s", "1"))
    for axis, g in plan.greens.items():
        print(f"  effective green {axis} {g:.1f} s")
    return 0


def _cmd_controllers(args: argparse.Namespace) -> int:
    width = max(map(len, CONTROLLERS))
    for name, factory in CONTROLLERS.items():
        print(f"{name.ljust(width)}  {getattr(factory, 'description', '')}")
    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    from .report import demand_levels, render_svg, sweep

    levels = demand_levels(args.levels, low=args.low, high=args.high)
    seeds = list(range(args.seed, args.seed + args.seeds))
    data = sweep(args.controllers, levels, args.duration, seeds, split=args.split)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_svg(data), encoding="utf-8")

    width = max(map(len, args.controllers))
    print(f"{'veh/h'.rjust(width)}  " + "  ".join(f"{lv:>7,.0f}" for lv in levels))
    for name in args.controllers:
        print(f"{name.rjust(width)}  " + "  ".join(f"{d:>6.1f}s" for d in data.delays[name]))
    print(f"\nwrote {out} ({len(levels)} demand levels × {len(args.controllers)} controllers)")
    return 0


def _run_module(module: str, argv: Sequence[str]) -> int:
    """Forward ``argv`` to ``greenwave.<module>.main``, importing it lazily."""
    try:
        mod = importlib.import_module(f"{__package__ or 'greenwave'}.{module}")
    except ImportError as exc:  # pragma: no cover - depends on the environment
        print(f"error: greenwave {module} could not be loaded ({exc}).", file=sys.stderr)
        return 1
    try:
        result = mod.main(list(argv))
    except ImportError as exc:  # pragma: no cover - e.g. tkinter missing for classic
        print(f"error: greenwave {module} needs an unavailable module ({exc}).", file=sys.stderr)
        return 1
    return int(result or 0)


#: Sub-commands whose arguments are handed untouched to another module's ``main``.
_PASSTHROUGH: dict[str, tuple[str, str]] = {
    "live": ("live", "animated junction in the terminal (--controller --speed --duration --seed --demand ...)"),
    "classic": ("classic", "open the classic turtle pelican-crossing simulation (needs tkinter)"),
}


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greenwave",
        description="GreenWave -- traffic-signal simulator: compare controllers, plan with Webster, "
        "or play with the classic pelican crossing.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    bench = sub.add_parser("benchmark", help="compare signal controllers on identical random traffic")
    bench.add_argument("--duration", type=_positive(float), default=3600.0, help="simulated seconds (default 3600)")
    bench.add_argument("--seeds", type=_positive(int), default=5, help="number of random seeds (default 5)")
    bench.add_argument("--seed", type=int, default=1, help="first seed (default 1)")
    default_demand = ",".join(f"{DEFAULT_DEMAND[a]:g}" for a in _DEMAND_ORDER)
    bench.add_argument(
        "--demand",
        type=parse_demand,
        default=dict(DEFAULT_DEMAND),
        help=f"veh/s: one value, NS,EW or N,S,E,W (default {default_demand})",
    )
    bench.add_argument(
        "--controllers",
        type=parse_controllers,
        default=list(CONTROLLERS),
        help=f"comma-separated list (default {','.join(CONTROLLERS)})",
    )
    bench.add_argument("--dt", type=_positive(float), default=0.5, help="time step in seconds (default 0.5)")
    bench.add_argument("--json", action="store_true", help="print machine-readable JSON")
    bench.set_defaults(func=_cmd_benchmark)

    web = sub.add_parser("webster", help="compute a Webster-optimal fixed-time plan")
    web.add_argument(
        "--flows",
        type=parse_flows,
        default=[600.0, 540.0, 300.0, 320.0],
        help="arrival flows N,S,E,W in veh/h (default 600,540,300,320)",
    )
    web.add_argument("--saturation", type=_positive(float), default=1800.0, help="saturation flow veh/h (default 1800)")
    web.add_argument(
        "--lost-time",
        type=float,
        default=Timing().lost_time_per_phase,
        help=f"lost time per phase in s (default {Timing().lost_time_per_phase:g})",
    )
    web.add_argument("--min-cycle", type=float, default=30.0)
    web.add_argument("--max-cycle", type=float, default=120.0)
    web.set_defaults(func=_cmd_webster)

    ctl = sub.add_parser("controllers", help="list available controllers")
    ctl.set_defaults(func=_cmd_controllers)

    sw = sub.add_parser("sweep", help="sweep demand from light to near-saturation and draw an SVG chart")
    sw.add_argument("--out", default="docs/sweep.svg", help="output SVG path (default docs/sweep.svg)")
    sw.add_argument("--duration", type=_positive(float), default=1800.0, help="simulated seconds per run (default 1800)")
    sw.add_argument("--seeds", type=_positive(int), default=3, help="number of random seeds (default 3)")
    sw.add_argument("--seed", type=int, default=1, help="first seed (default 1)")
    sw.add_argument("--levels", type=_positive(int), default=8, help="number of demand levels (default 8)")
    sw.add_argument("--split", type=_fraction, default=0.6, help="share of demand on N/S, 0-1 (default 0.6)")
    sw.add_argument("--low", type=_positive(float), default=400.0, help="lightest total demand veh/h (default 400)")
    sw.add_argument("--high", type=_positive(float), default=None, help="heaviest total demand veh/h (default Y=0.8)")
    sw.add_argument(
        "--controllers",
        type=parse_controllers,
        default=list(CONTROLLERS),
        help=f"comma-separated list (default {','.join(CONTROLLERS)})",
    )
    sw.set_defaults(func=_cmd_sweep)

    # Listed for --help only; main() forwards their arguments before parsing.
    for name, (_, help_text) in _PASSTHROUGH.items():
        sub.add_parser(name, help=help_text, add_help=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m greenwave`` and the ``greenwave`` script."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in _PASSTHROUGH:
        return _run_module(_PASSTHROUGH[argv[0]][0], argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except ValueError as exc:  # invalid combinations, e.g. --min-cycle > --max-cycle
        parser.error(str(exc))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
