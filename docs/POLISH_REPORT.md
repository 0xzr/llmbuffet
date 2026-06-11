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

## P2 — Demo at the top of the README

- Replaced `assets/demo.svg` with an 8.5s looping tokenmax terminal demo that
  shows install, all-model fan-out, per-provider answers, synthesis, and current
  catalog counts.
- Added `assets/tokenmax-results.svg`, a static results image showing "200+
  models, 18 providers, $0" plus keyless-start and failover notes.
- Moved both assets above the README summary and quickstart so the page opens
  with a visual demo.

## P9 — GitHub-native discovery

- Audited live GitHub About/topics metadata read-only and recorded the 20-topic
  replacement plan in `docs/GITHUB_DISCOVERY.md`.
- Prepared a 103-character About description with the zero-keys hook and the
  exact operator-only `gh repo edit` command for after merge.
- Added upload-ready `assets/social-preview.png` at 1280x640, kept the editable
  SVG source, and documented the profile pin plus social-preview upload steps
  without making external writes.
