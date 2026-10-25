# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-10-25

The original turtle traffic light becomes **GreenWave**, a traffic-signal
simulator and playground.

### Added

- **Web playground** (`web/`): a zero-dependency, no-build browser app.
  - A top-down four-way junction drawn on canvas, with traffic driving on the left.
  - Car-following using the Intelligent Driver Model, with a UK signal sequence (red, red + amber, green, amber).
  - Controllers: fixed time, vehicle actuated, max pressure and manual.
  - Pedestrian push button that starts an all-red scramble phase.
  - Emergency vehicles that pre-empt the signals.
  - Sliders to change demand.
  - Live queue and wait charts, signal timeline and event log.
  - Benchmark button that compares controllers.
  - Dark and light themes, keyboard shortcuts, and URL parameters (`theme`, `warmup`, `speed`, `seed`).
- **Browser pelican crossing** (`web/classic.html`): the classic button-operated crossing, playable in the browser.
- **Python engine** (`greenwave/`): a stdlib-only, fast mesoscopic queue model of a junction.
  - Poisson arrivals, saturation-flow discharge, and the UK inter-green.
  - Four controllers: `fixed`, `actuated` (gap-out/max-out), `maxpressure` (with hysteresis) and `webster` (Webster-optimal fixed time).
- **Command-line tools** (`python -m greenwave …` or `greenwave …`):
  - `benchmark`: compares controllers on identical random traffic, with table or `--json` output.
  - `sweep`: runs demand from light to near-saturation and draws an SVG delay chart (`docs/sweep.svg`).
  - `webster`: computes the optimal cycle length and green splits for given flows.
  - `controllers`: lists the available controllers.
  - `live`: animates a simulated junction in the terminal using ANSI escapes.
  - `classic`: the turtle-graphics UK pelican crossing.
- **Signal state machines**: `greenwave.signals.TrafficLight` (UK sequence) and `greenwave.pelican.PelicanCrossing`, both pure and unit-tested.
- **Docs**:
  - README with an animated demo GIF and screenshots.
  - `docs/HOW_IT_WORKS.md`, explaining the models, controllers and metrics with references.
  - `CONTRIBUTING.md`.
  - `examples/custom_controller.py`, a longest-wait-first controller benchmarked against the built-in ones.
- **Tooling**:
  - pytest and `node --test` suites.
  - GitHub Actions CI for Python 3.10–3.13 and Node 22.
  - A GitHub Pages workflow for the web playground.
  - Issue templates.

### Fixed (compared with the original script)

- The click handler that was cut off mid-line (`screen.onc…`) and so never bound.
- The "infinite" green, which was a 1 000 000 000 ms timer; the crossing now rests on green properly.
- The push button's hit-box, which was off-centre.

## [0.1] — original

- `trafficlight`: a Python turtle-graphics traffic light (green → amber → red → amber → green) started by clicking a button. It is kept as `legacy/trafficlight.py`.

[1.0.0]: https://github.com/22ishaq/TrafficLight/releases/tag/v1.0.0
