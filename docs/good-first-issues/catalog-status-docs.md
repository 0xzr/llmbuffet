# Document catalog sync and status commands in the capacity guide

Labels: `good first issue`, `docs`, `provider-catalog`
Estimate: 45-75 minutes

## Context

The capacity commands can use the advisory external provider catalog, and the CLI
also exposes `freellmpool catalog sync` and `freellmpool catalog status`. The
capacity guide should make that path easier to discover without implying the
external catalog changes packaged defaults.

## Pointers

- [`docs/CAPACITY.md`](../../docs/CAPACITY.md)
- [`README.md`](../../README.md)
- [`src/freellmpool/cli.py`](../../src/freellmpool/cli.py)

## Acceptance

- Add a short section to `docs/CAPACITY.md` showing `freellmpool catalog sync`
  and `freellmpool catalog status`.
- Explain that the external catalog is advisory and cached locally.
- Keep the README mention to one sentence at most, if needed.
- `ruff check .` and `pytest tests/test_cli.py` pass.
