# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.9.2] — 2026-06-03

### Changed (performance)
- **Connection pooling.** Requests now reuse a process-wide keep-alive httpx
  client instead of opening a fresh TCP+TLS connection per call. Big latency win
  for repeated calls to the same provider (agent loops, the proxy): ~0.15s/call
  warm vs a full handshake each time.
- **Fast-fail connect timeout (10s)** so a dead/unreachable provider fails over
  quickly instead of waiting the full read timeout.
- `_order` snapshots quota once per request instead of a locked read per
  candidate — matters now that the catalog has 300+ models.

## [0.9.1] — 2026-06-03

### Changed
- **Every model live-validated; broken ones off by default.** All 324 catalog
  models were reachability-tested; 94 that failed (404/403/402, persistent
  errors, timeouts) are now `enabled = false` — skipped by auto-routing so users
  don't hit dead models, but still callable when pinned explicitly (`-m`).
  `Model.enabled` added; `freellmpool providers` shows `N models (+M off)` and
  `freellmpool models --all` lists the disabled ones.

### Fixed
- Reasoning-model token floor lowered from 8192 to 4096 — 8192 exceeded some
  providers' caps (e.g. Groq's gpt-oss), which made those models error/return
  empty. Groq's `gpt-oss-120b`/`-20b` work again.

## [0.9.0] — 2026-06-03

### Added
- **Catalog expanded from 56 to 300+ chat models.** Model lists are now
  discovered from each provider's `/models` endpoint and filtered to chat models
  (embeddings/rerank/audio/safety models excluded). The embedder catalog grew to
  23. Not every advertised model is callable on every free tier — freellmpool
  fails over.
- **`free_llm_quota` MCP tool** — shows today's per-provider usage, daily-limit
  headroom, session totals, and estimated cost avoided.

## [0.8.1] — 2026-06-03

### Fixed
- Streaming connection lifecycle: the httpx stream/client is now always closed —
  on non-200 failover, on early client disconnect, and on exhaustion (was leaking
  sockets/fds on exactly the failover paths streaming exercises).
- Proxy rejects negative `Content-Length` and caps request bodies at 16 MB.
- Model names that contain `/` but aren't provider-prefixed now route correctly
  (e.g. a client sending `openai/gpt-oss-120b` as the model).
- Response cache key now includes `tool_choice`.
- 429 cooldown is stamped with a fresh timestamp instead of the request-start time.
- The Anthropic `/v1/messages` shim no longer 500s on malformed input (bad
  `max_tokens`/`temperature`, null text blocks).
- `/dashboard` and `/v1/models` are gated behind the proxy key when one is set.
- Responses tolerate broken pipes; reasoning models (incl. `gpt-oss`) get token
  headroom so they don't return empty content.

### Changed
- Rewrote the README and docs in a plainer style (less emoji, less marketing).

## [0.8.0] — 2026-06-03

### Added
- **Anthropic Messages shim (`/v1/messages`)** — run **Claude Code** (and any
  Anthropic-API tool) on free models via `ANTHROPIC_BASE_URL`. Translates text +
  tools (tool_use/tool_result) and emits Claude's exact streaming event sequence;
  `claude-*` model names auto-route to free models. `freellmpool code claude`
  prints the setup. Experimental (no vision yet). Live-verified end to end.
- **Response caching (sqlite, opt-in).** Set `FREELLMPOOL_CACHE_TTL` (or
  `[settings] cache_ttl`) to cache identical requests — saves quota on dev/test
  loops and answers instantly. Off by default.
- **Web dashboard** at **`/dashboard`** — a self-contained page showing
  configured providers, today's per-provider usage, requests served, cache hits,
  and "$ not paid to OpenAI". Auto-refreshes.

## [0.7.0] — 2026-06-03

### Added
- **True token streaming.** The proxy now streams tokens from the provider in
  real time (`stream: true`) instead of buffering — with failover *before* the
  first byte. `Pool.stream_chat()` exposed for library use. Live-verified (15
  incremental chunks on Groq). Tool-calling requests still use the buffered path.
- **`freellmpool code <agent>`** — prints one-command setup to wire a coding
  agent (codex, aider, cline, continue, cursor, opencode) to the free proxy.

## [0.6.0] — 2026-06-03

### Added
- **MCP server** — `freellmpool mcp` runs a Model Context Protocol server over
  stdio (zero extra deps), so **Claude Desktop / Claude Code / Cursor** can
  offload subtasks to free models. Tools: `free_llm_ask`, `free_llm_models`.
  Works with no API keys. See [docs/MCP.md](docs/MCP.md). Live-verified end to end.

## [0.5.0] — 2026-06-03

### Added
- **Pooled free embeddings** — `pool.embed(...)` and a proxy `/v1/embeddings`
  route over Cohere / GitHub Models / Cloudflare / Mistral / NVIDIA free tiers,
  with failover. (Free RAG, not just chat.) Live-verified.
- **`llm-freellmpool` plugin** for Simon Willison's [`llm`](https://llm.datasette.io)
  CLI — `llm install llm-freellmpool` → `llm -m freellmpool "..."` (zero keys).
- **`config.toml`** support: `[keys]` (filled under env), `[aliases]`, `[settings]`
  (`cooldown_seconds`, `proxy_key`). See `config.toml.example`.
- **Docker**: image + GHCR build/push workflow + `docker-compose.yml` (freellmpool
  + Open WebUI). Built and run-tested locally.
- **"$ saved vs OpenAI" metric** — `freellmpool ask -v` and the proxy shutdown
  line show avoided GPT-4o cost.
- README repositioned around the developer wedge (CLI + library + proxy + `llm`
  plugin, keyless) with a "correct by design" section; terminal demo at the top.

## [0.4.0] — 2026-06-03

### Added
- **Model aliasing.** Common OpenAI/Anthropic names (`gpt-4o-mini`, `gpt-4o`,
  `claude-3-5-sonnet`, …) auto-resolve to free models, so existing code runs
  against freellmpool unchanged. Override with `FREELLMPOOL_ALIAS_<name>=...`.
- **Tool / function-calling passthrough.** `tools` / `tool_choice` are forwarded
  to providers that support them and `tool_calls` are returned — unlocking
  aider, Continue, and other agentic tools. Live-verified on Groq.
- **Observability headers** on proxy responses: `X-Freellmpool-Provider`,
  `X-Freellmpool-Model`, `X-Freellmpool-Attempts`.
- **[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)** — copy-paste setup for opencode,
  aider, Continue, Cline, Cursor, Open WebUI, LibreChat, LangChain, LlamaIndex,
  Vercel AI SDK, `llm` CLI, shell-gpt, n8n, and more.

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
