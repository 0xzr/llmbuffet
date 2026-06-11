# Polish Report

## P1 — 30-second quickstart

- Added `scripts/quickstart-test.sh` to create a fresh virtual environment,
  install `freellmpool`, isolate config/cache/quota paths, clear API-key
  environment state, and require a keyless `freellmpool ask` reply within 30s.
- Added a dedicated CI quickstart job that runs the same script against the
  checkout with `FREELLMPOOL_QUICKSTART_PACKAGE=.`.
- Updated the README above the fold with the cold-env quickstart command path.
- Measured locally on 2026-06-11 with a fresh Python 3.12 venv and no API keys:
  19s from venv creation to first reply in CI mode
  (`FREELLMPOOL_QUICKSTART_PACKAGE=.`); a direct manual probe measured the model
  call itself at 3.29s.

## P3 — FAQ.md

- Added `FAQ.md` with a provider-by-provider prompt destination table for all 18
  built-in chat providers, conservative jurisdiction notes, ToS posture, failover
  behavior, reliability caveats, comparison positioning, and ban-risk guidance.
- Linked the FAQ prominently from the top of the README.
- Grounded behavior claims in `providers.toml`, `models.py`, `config.py`,
  `router.py`, and `client.py`; provider privacy links are listed separately.

## P4 — Gracious comparison table

- Replaced the README comparison table with the required columns: keyless start,
  provider coverage, failover, MCP server, CLI, transcription, local/self-hosted,
  and license.
- Added rows for freellmpool, OpenRouter free models, LiteLLM, and FreeLLMAPI.
- Noted that FreeLLMAPI predates this project and that the overlap is independent
  convergence.

## P5 — Single-source the counts

- Added `scripts/catalog_counts.py` so public provider/model counts are derived
  from `src/freellmpool/providers.toml`.
- Added executable `scripts/check-counts`, wired it into CI, and reused the shared
  count helper from `scripts/check_release_ready.py`.
- Updated `docs/free-llm-api-providers-list.html` model counts to match enabled
  chat, embedding, and transcription routes in the catalog.
- Removed the hardcoded provider count from the MCP tool description.
