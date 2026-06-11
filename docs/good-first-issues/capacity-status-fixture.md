# Add a capacity-status fixture for quota edge cases

Labels: `good first issue`, `tests`, `cli`
Estimate: 60-90 minutes

## Context

`freellmpool capacity status` reports healthy, low-quota, exhausted, invalid-key,
and missing providers. The core capacity tests cover the model, but one more CLI
fixture would make the human output harder to regress.

## Pointers

- [`src/freellmpool/capacity.py`](../../src/freellmpool/capacity.py)
- [`src/freellmpool/cli.py`](../../src/freellmpool/cli.py)
- [`tests/test_capacity.py`](../../tests/test_capacity.py)
- [`tests/test_cli.py`](../../tests/test_cli.py)

## Acceptance

- Add a no-network CLI test for `freellmpool capacity status --all --no-catalog-sync`.
- The fixture should include at least one healthy provider, one low-quota or
  exhausted provider, and one missing provider.
- Keep the test deterministic by using fake quota/env/catalog data.
- `ruff check .` and `pytest tests/test_capacity.py tests/test_cli.py` pass.
