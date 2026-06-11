# Add JSON output to freellmpool models

Labels: `good first issue`, `cli`, `tests`
Estimate: 60-90 minutes

## Context

`freellmpool models` is useful for humans, but editor integrations and scripts
would be easier to write if the command had a stable JSON mode.

## Pointers

- [`src/freellmpool/cli.py`](../../src/freellmpool/cli.py)
- [`tests/test_cli.py`](../../tests/test_cli.py)
- [`src/freellmpool/config.py`](../../src/freellmpool/config.py)

## Acceptance

- Add `freellmpool models --json`.
- Output a JSON list of model rows with at least `provider`, `model`, `enabled`,
  and `configured` fields.
- Keep the existing text output unchanged when `--json` is not passed.
- Add a fake/local test in `tests/test_cli.py`.
- `ruff check .` and `pytest tests/test_cli.py` pass.
