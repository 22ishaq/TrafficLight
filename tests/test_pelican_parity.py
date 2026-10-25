"""The golden pelican trace (shared with the JS port's tests) must match the Python model."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "pelican_trace.json"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_pelican_trace", ROOT / "tools" / "gen_pelican_trace.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fixture_matches_python_model():
    gen = _load_generator()
    expected = json.loads(FIXTURE.read_text())
    assert gen.build() == expected, "fixture is stale: run python tools/gen_pelican_trace.py"


def test_fixture_covers_the_edge_cases():
    scenarios = json.loads(FIXTURE.read_text())["scenarios"]
    records = [r for s in scenarios for r in s["trace"]]
    presses = [r for r in records if r["action"] == "press"]
    # a press during the green man is ignored ...
    assert any(not r["accepted"] and r["phase"] == "PEDESTRIAN_WALK" for r in presses)
    # ... and a press during flashing is queued (WAIT lamp back on)
    assert any(r["accepted"] and r["phase"] == "FLASHING" and r["wait"] for r in presses)
    assert {s["timings"] for s in scenarios} == {"default", "fast"}
    assert {r["phase"] for r in records} == {
        "VEHICLE_GREEN", "VEHICLE_AMBER", "ALL_RED", "PEDESTRIAN_WALK", "FLASHING",
    }
