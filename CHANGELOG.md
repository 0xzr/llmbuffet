# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-06-03

### Added
- **Six more providers** (15 total / 53 models): NVIDIA NIM, OVHcloud AI
  Endpoints, LLM7, Ollama Cloud, Z.ai/Zhipu GLM, LongCat; expanded model lists
  for Groq, Cerebras, OpenRouter, GitHub Models, SambaNova, Mistral, Gemini.
- **Keyless / zero-setup providers.** OVHcloud works with no API key
  (anonymous); LLM7's key is optional. `pip install llmbuffet && llmbuffet ask`
  now works with no signup at all. Catalog gains `auth` and `key_optional`.
- **Model selection.** New `llmbuffet models` lists every `provider/model` id;
  `ask -m provider/model` pins an exact model on an exact provider.
- **Streaming proxy.** The proxy honors `stream: true` with a buffered
  OpenAI-style SSE stream, so stream-only clients (chat UIs, agents) work.
- **429 cooldown.** A rate-limited provider is deprioritized for a cooldown
  window instead of being retried immediately.
- **Reasoning-model handling.** Thinking models get a `max_tokens` floor and
  `<think>…</think>` blocks are stripped from output.
- `llmbuffet ask --json` requests JSON and strips code fences.

## [0.1.0] — 2026-06-02

Initial release.

### Added
- Provider catalog (`providers.toml`) covering 9 free-tier providers and 24
  models: Groq, Cerebras, OpenRouter, Google Gemini, GitHub Models, Cloudflare
  Workers AI, Mistral, Cohere, SambaNova.
- Quota-aware, least-used-first router with automatic failover across providers.
- Persistent per-provider/day quota tracking (`~/.config/llmbuffet/quota.json`,
  resets at UTC midnight).
- OpenAI-compatible proxy server (`llmbuffet proxy`) exposing
  `/v1/chat/completions` and `/v1/models` — a drop-in `OPENAI_BASE_URL`.
- CLI: `ask`, `providers`, `quota`, `proxy`.
- Python API: `from llmbuffet import Buffet`.
- Three request/response adapters (openai, gemini, cloudflare) and per-user
  catalog overrides via `~/.config/llmbuffet/providers.toml`.
- Full unit-test suite with a faked transport (no network) and CI on Python
  3.11–3.13.
