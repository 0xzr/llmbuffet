#!/usr/bin/env python3
"""Compare two ``bench_hotpaths.py`` JSON files and report timing regressions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(previous: dict, current: dict, *, warn_percent: float) -> list[str]:
    warnings: list[str] = []
    factor = 1.0 + warn_percent / 100.0
    for name, cur in sorted(current.items()):
        prev = previous.get(name)
        if not isinstance(prev, dict) or not isinstance(cur, dict):
            continue
        for field in ("mean_ms", "p95_ms"):
            old = prev.get(field)
            new = cur.get(field)
            if not isinstance(old, int | float) or not isinstance(new, int | float):
                continue
            if old > 0 and new > old * factor:
                pct = (new / old - 1.0) * 100.0
                warnings.append(f"{name}.{field}: {old:.4f} -> {new:.4f} ms (+{pct:.1f}%)")
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--warn-percent", type=float, default=30.0)
    parser.add_argument("--fail", action="store_true", help="exit 1 when regressions are found")
    args = parser.parse_args(argv)

    warnings = compare(_load(args.previous), _load(args.current), warn_percent=args.warn_percent)
    if not warnings:
        print("Benchmark comparison: no regressions above threshold.")
        return 0
    print("Benchmark comparison warnings:", file=sys.stderr)
    for warning in warnings:
        print(f"  - {warning}", file=sys.stderr)
    return 1 if args.fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
