# Keep .env.example keyless provider notes in sync

Labels: `good first issue`, `docs`, `provider-catalog`
Estimate: 30-45 minutes

## Context

The packaged catalog has several zero-setup providers, but `.env.example` is easy
to let drift because it is handwritten. The keyless section should match the
catalog and mention the optional LLM7 key clearly.

## Pointers

- [`.env.example`](../../.env.example)
- [`src/freellmpool/providers.toml`](../../src/freellmpool/providers.toml)
- [`tests/test_config.py`](../../tests/test_config.py)

## Acceptance

- `.env.example` lists every provider that works without a required key.
- LLM7 remains documented as key-optional, not strictly keyless-only.
- Add or update a small test that fails if the keyless/key-optional catalog rows
  drift away from the `.env.example` note.
- `ruff check .` and `pytest tests/test_config.py` pass.
