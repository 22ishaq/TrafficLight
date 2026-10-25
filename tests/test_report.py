"""Tests for demand sweeps, the SVG chart and the sweep/live CLI commands."""

from __future__ import annotations

import importlib.util
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from greenwave.cli import main
from greenwave.report import SweepData, demand_for, demand_levels, nice_ticks, render_svg, sweep

SVG = "{http://www.w3.org/2000/svg}"
CONTROLLERS = ["fixed", "actuated", "maxpressure", "webster"]


@pytest.fixture(scope="module")
def data() -> SweepData:
    return sweep(CONTROLLERS, demand_levels(4, low=400, high=2400), duration=600, seeds=(1, 2))


def test_sweep_shape(data: SweepData) -> None:
    assert data.levels == [400, 1067, 1733, 2400]
    assert set(data.delays) == set(CONTROLLERS)
    assert all(len(series) == 4 for series in data.delays.values())
    assert all(d >= 0 for series in data.delays.values() for d in series)


def test_demand_helpers() -> None:
    demand = demand_for(3600, 0.6)
    assert sum(demand.values()) == pytest.approx(1.0)
    assert demand["N"] == demand["S"] == pytest.approx(0.3)
    assert demand_levels(3, low=100, high=300) == [100, 200, 300]
    with pytest.raises(ValueError):
        demand_for(100, 1.5)
    with pytest.raises(ValueError):
        demand_levels(1)


def test_nice_ticks_cover_range() -> None:
    ticks = nice_ticks(0, 187)
    assert ticks[0] == 0 and ticks[-1] >= 187
    steps = {round(b - a, 6) for a, b in zip(ticks, ticks[1:])}
    assert len(steps) == 1


def test_svg_is_valid_xml_with_one_path_per_controller(data: SweepData) -> None:
    root = ET.fromstring(render_svg(data))
    assert root.tag == f"{SVG}svg"
    paths = root.findall(f".//{SVG}path")
    assert sorted(p.get("data-controller") for p in paths) == sorted(CONTROLLERS)
    texts = " ".join(t.text or "" for t in root.iter(f"{SVG}text"))
    assert "Average delay (s)" in texts and "Total demand (veh/h)" in texts
    for name in CONTROLLERS:
        assert name in texts  # legend entry
    for element in root.iter():
        if element.tag in {f"{SVG}rect", f"{SVG}text", f"{SVG}path", f"{SVG}circle", f"{SVG}line"}:
            assert element.get("fill"), f"{element.tag} lacks an explicit fill"


def test_render_rejects_empty() -> None:
    with pytest.raises(ValueError):
        render_svg(SweepData(levels=[], delays={}))


def test_cli_sweep_writes_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "nested" / "sweep.svg"
    code = main(["sweep", "--out", str(out), "--duration", "300", "--seeds", "1", "--levels", "3", "--split", "0.7"])
    assert code == 0
    assert out.exists()
    root = ET.parse(out).getroot()
    assert len(root.findall(f".//{SVG}path")) == len(CONTROLLERS)
    assert "wrote" in capsys.readouterr().out


def test_cli_sweep_rejects_bad_split() -> None:
    with pytest.raises(SystemExit):
        main(["sweep", "--split", "1.5"])


def test_live_forwards_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    fake = types.ModuleType("greenwave.live")
    fake.main = lambda argv=None: seen.append(argv) or 0  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "greenwave.live", fake)
    assert main(["live", "--controller", "fixed", "--frames", "3"]) == 0
    assert seen == [["--controller", "fixed", "--frames", "3"]]


@pytest.mark.skipif(importlib.util.find_spec("greenwave.live") is None, reason="greenwave/live.py not present")
def test_live_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["live", "--frames", "2", "--no-color", "--speed", "1000", "--duration", "10"])
    assert code == 0
    assert capsys.readouterr().out
