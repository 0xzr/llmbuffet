# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-06-03

### Changed
- **Renamed `llmbuffet` → `freellmpool`** (clearer, keyword-rich, no name
  collision). Python API is now `from freellmpool import Pool`; CLI is
  `freellmpool` (with `ffp` as a short alias); config lives under
  `~/.config/freellmpool/`; env vars are `FREELLMPOOL_*`.

### Added
- **Codex / Responses API shim** — the proxy now serves `POST /v1/responses`
  (non-streaming + typed SSE events), so OpenAI Codex CLI and other
  Responses-based agents can run on pooled free inference.
- **Pollinations** — a second keyless provider (16 providers / 56 models total),
  strengthening the zero-config path.
- Agent docs for Codex CLI in `docs/AGENTS.md`; honest **Limitations** section
  in the README.

## [0.2.0] — 2026-06-03

### Added
- **Six more providers** (15 total / 53 models): NVIDIA NIM, OVHcloud AI
  Endpoints, LLM7, Ollama Cloud, Z.ai/Zhipu GLM, LongCat; expanded model lists
  for Groq, Cerebras, OpenRouter, GitHub Models, SambaNova, Mistral, Gemini.
- **Keyless / zero-setup providers.** OVHcloud works with no API key
  (anonymous); LLM7's key is optional. `pip install freellmpool && freellmpool ask`
  now works with no signup at all. Catalog gains `auth` and `key_optional`.
- **Model selection.** New `freellmpool models` lists every `provider/model` id;
  `ask -m provider/model` pins an exact model on an exact provider.
- **Streaming proxy.** The proxy honors `stream: true` with a buffered
  OpenAI-style SSE stream, so stream-only clients (chat UIs, agents) work.
- **429 cooldown.** A rate-limited provider is deprioritized for a cooldown
  window instead of being retried immediately.
- **Reasoning-model handling.** Thinking models get a `max_tokens` floor and
  `<think>…</think>` blocks are stripped from output.
- `freellmpool ask --json` requests JSON and strips code fences.

### Hardening (post-review)
- Proxy now validates all request fields and returns OpenAI-style `400`s for
  malformed input; a catch-all ensures no request can kill a server thread.
- Optional proxy auth: `--api-key` / `FREELLMPOOL_PROXY_KEY` requires a Bearer
  token; a warning fires when binding to a non-loopback host without one.
- Quota store is now thread-safe (lock + unique temp file) and best-effort, so
  a persistence hiccup can't abort a successful completion.
- A provider that returns `429` has its remaining models skipped for that
  request; cooldowns update under a lock with `max()`.
- Verified live against 11 providers + the OpenAI SDK (non-streaming & SSE).
  Fixed the LongCat model id (`LongCat-2.0-Preview`); LLM7 leads the keyless
  pool (most reliable zero-key provider).

## [0.1.0] — 2026-06-02

Initial release.

### Added
- Provider catalog (`providers.toml`) covering 9 free-tier providers and 24
  models: Groq, Cerebras, OpenRouter, Google Gemini, GitHub Models, Cloudflare
  Workers AI, Mistral, Cohere, SambaNova.
- Quota-aware, least-used-first router with automatic failover across providers.
- Persistent per-provider/day quota tracking (`~/.config/freellmpool/quota.json`,
  resets at UTC midnight).
- OpenAI-compatible proxy server (`freellmpool proxy`) exposing
  `/v1/chat/completions` and `/v1/models` — a drop-in `OPENAI_BASE_URL`.
- CLI: `ask`, `providers`, `quota`, `proxy`.
- Python API: `from freellmpool import Pool`.
- Three request/response adapters (openai, gemini, cloudflare) and per-user
  catalog overrides via `~/.config/freellmpool/providers.toml`.
- Full unit-test suite with a faked transport (no network) and CI on Python
  3.11–3.13.
