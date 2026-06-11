# Keep freellmpool code agent recipes aligned with docs

Labels: `good first issue`, `integration`, `tests`
Estimate: 45-75 minutes

## Context

`freellmpool code <agent>` and `docs/INTEGRATIONS.md` both document supported
coding agents. A small parity test would keep a newly added recipe from being
forgotten in one place.

## Pointers

- [`src/freellmpool/agents.py`](../../src/freellmpool/agents.py)
- [`docs/INTEGRATIONS.md`](../../docs/INTEGRATIONS.md)
- [`tests/test_agents.py`](../../tests/test_agents.py)

## Acceptance

- Add a test that every key in `AGENTS` appears in the supported-agent list and
  the integrations guide.
- Keep the test text-based and network-free.
- Update docs only if the test reveals a real mismatch.
- `ruff check .` and `pytest tests/test_agents.py` pass.
