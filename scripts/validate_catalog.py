#!/usr/bin/env python3
"""Validate bundled provider catalog structure without making network calls."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from freellmpool.catalog_validation import validate_catalog  # noqa: E402


def main() -> int:
    errors = validate_catalog(Path("src/freellmpool/providers.toml"))
    if errors:
        print("Catalog validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Catalog validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
