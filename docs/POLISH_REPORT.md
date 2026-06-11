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
