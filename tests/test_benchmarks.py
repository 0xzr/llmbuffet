"""Local benchmark comparison helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "compare_benchmarks.py"
_SPEC = importlib.util.spec_from_file_location("compare_benchmarks", _SCRIPT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
compare = _MODULE.compare


def test_compare_benchmarks_reports_large_regressions():
    previous = {"rank": {"mean_ms": 10.0, "p95_ms": 20.0}}
    current = {"rank": {"mean_ms": 12.0, "p95_ms": 31.0}}
    warnings = compare(previous, current, warn_percent=30.0)
    assert warnings == ["rank.p95_ms: 20.0000 -> 31.0000 ms (+55.0%)"]


def test_compare_benchmarks_ignores_small_changes():
    previous = {"rank": {"mean_ms": 10.0, "p95_ms": 20.0}}
    current = {"rank": {"mean_ms": 12.0, "p95_ms": 25.0}}
    assert compare(previous, current, warn_percent=30.0) == []
