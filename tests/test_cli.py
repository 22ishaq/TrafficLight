"""Tests for the command-line interface."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import pytest

from greenwave import __version__
from greenwave.cli import main, parse_demand


def test_benchmark_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["benchmark", "--duration", "600", "--seeds", "2", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["baseline"] == "fixed"
    names = [r["controller"] for r in payload["results"]]
    assert names == ["fixed", "actuated", "maxpressure", "webster"]
    assert payload["best"] in names
    assert payload["config"]["seeds"] == [1, 2]
    fixed = payload["results"][0]
    assert fixed["delay_vs_baseline_pct"] == 0
    assert fixed["spawned"] == fixed["served"] + fixed["remaining"]


def test_benchmark_table(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["benchmark", "--duration", "600", "--seeds", "1", "--controllers", "fixed,actuated"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Controller" in out and "baseline" in out and "★" in out
    assert "\033[" not in out  # no colour codes when not a TTY


def test_webster_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["webster", "--flows", "540,300,450,200", "--lost-time", "5"]) == 0
    out = capsys.readouterr().out
    assert "44.4 s" in out


def test_controllers_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["controllers"]) == 0
    assert "maxpressure" in capsys.readouterr().out


def test_parse_demand_shapes() -> None:
    assert parse_demand("0.1") == {"N": 0.1, "E": 0.1, "S": 0.1, "W": 0.1}
    assert parse_demand("0.2,0.05") == {"N": 0.2, "S": 0.2, "E": 0.05, "W": 0.05}
    assert parse_demand("1,2,3,4") == {"N": 1, "S": 2, "E": 3, "W": 4}
    for bad in ("1,2,3", "x", "-1"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_demand(bad)


def test_bad_controller_exits() -> None:
    with pytest.raises(SystemExit):
        main(["benchmark", "--controllers", "nope"])


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "greenwave", "--version"], capture_output=True, text=True, check=True
    )
    assert __version__ in result.stdout
