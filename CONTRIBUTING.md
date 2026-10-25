# Contributing to GreenWave

Thanks for helping. Bug reports, new controllers and docs fixes are all welcome.

## Run the tests

```bash
# Python (3.10+)
python -m pip install -e ".[dev]"      # or just: pip install pytest
python -m pytest -q

# Web engine (Node 18+; no npm install needed, there are no dependencies)
cd web && npm test                     # runs: node --test "tests/*.test.mjs"
```

CI runs both suites on every push and pull request (see `.github/workflows/ci.yml`).

To try things by hand:

```bash
python -m greenwave benchmark --duration 600 --seeds 2
python -m greenwave live --controller maxpressure
python -m http.server -d web 8000      # then open http://localhost:8000
```

## Project layout

```
greenwave/            Python package (stdlib only)
  sim.py              mesoscopic junction model (Junction, simulate, benchmark)
  controllers.py      fixed / actuated / maxpressure / webster + CONTROLLERS registry
  webster.py          Webster's optimal cycle and green splits
  metrics.py          Metrics dataclass and averaging
  report.py           demand sweep and SVG chart
  signals.py          UK traffic light state machine
  pelican.py          pelican crossing state machine
  live.py             ANSI terminal live view
  classic.py          turtle GUI for the pelican crossing
  cli.py              `python -m greenwave …`
web/                  browser playground (ES modules, no build step)
  js/sim/             pure simulation: engine.js, controllers.js, benchmark.js, rng.js
  js/                 UI: main.js, render.js, charts.js
  tests/              node --test suites for the engine
tests/                pytest suites
examples/             runnable examples (e.g. a custom controller)
docs/                 HOW_IT_WORKS.md, images
legacy/               the original turtle script
```

## Add a controller

A controller is asked one thing while an axis (`NS` or `EW`) has green: switch now or not? The engines handle amber, all-red and red+amber themselves, so a controller can't make the signals unsafe.

### Python

1. Subclass `greenwave.controllers.Controller`:
   - set a unique `name`;
   - implement `decide(junction) -> bool` (`True` means switch);
   - optionally implement `reset(demand, timing)`, which is called before each run.
2. Use the junction's read-only view: `time`, `phase_time`, `green_axis`, `queue_length(axis_or_approach)` and `time_since_arrival(axis)`.
3. Register it with `CONTROLLERS[MyController.name] = MyController`. It then works with `benchmark`, `sweep`, `live` and `make_controller`.
4. Add tests in `tests/test_controllers.py`.

`examples/custom_controller.py` is a complete worked example.

### Web

1. In `web/js/sim/controllers.js`, write a class with `decide(sim)` that returns `'hold'` or `'switch'`. Useful helpers:
   - `sim.signal.phaseTime`, `sim.signal.axisGreen`;
   - `sim.demandOnAxis(axis)`, `sim.queueOnAxis(axis)`, `sim.pressure(axis)`;
   - `sim.approachingWithin(axis, metres)`.
2. Add it to the `CONTROLLERS` registry in that file (`id`, `name`, `description`, `create`).
3. Make it selectable in the UI:
   - add an `<option>` to `#controllerSel` in `web/index.html`;
   - add its id to `CONTROLLERS` and `CONTROLLER_LABEL` in `web/js/main.js`.
4. Add tests in `web/tests/controllers.test.mjs`.

## Code style

- **Python:** stdlib only at runtime (pytest is the only dev dependency).
  - Type hints with `from __future__ import annotations`, and docstrings on public APIs.
  - Keep simulation logic pure. GUI code imports `turtle` lazily so tests run headless.
- **Web:** plain ES modules with no dependencies, no bundler and no build step.
  - `web/js/sim/` must not touch the DOM, so it runs unchanged in Node.
- **Both:** runs must be deterministic for a given seed. If you add randomness, draw it from the seeded RNG.
- Keep changes focused, add or update tests, and describe behaviour changes in `CHANGELOG.md`.
