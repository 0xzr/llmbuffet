# freellmpool

Pool the free tiers of 16 LLM providers (300+ models) behind one
OpenAI-compatible endpoint — as a CLI, a Python library, or a local proxy.
Works with no API keys.

[![PyPI](https://img.shields.io/pypi/v/freellmpool.svg)](https://pypi.org/project/freellmpool/)
[![CI](https://github.com/0xzr/freellmpool/actions/workflows/ci.yml/badge.svg)](https://github.com/0xzr/freellmpool/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

![demo](assets/demo.svg)

Groq, Cerebras, NVIDIA NIM, Google Gemini, OpenRouter, GitHub Models, Cloudflare,
Mistral, Cohere and others each give away a free tier — but each has its own SDK,
rate limits, and daily cap. freellmpool puts them in one pool: it sends each
request to a provider you have access to, fails over to the next when one is rate
limited or down, and tracks per-day usage so you get the most out of every tier.

Two providers (Pollinations and OVHcloud) need no API key, so a fresh install
answers immediately:

```console
$ pip install freellmpool
$ freellmpool ask "Explain the CAP theorem in one sentence."
A distributed system can guarantee at most two of consistency, availability, and
partition tolerance at the same time.
```

Add keys for the other providers to unlock more models and higher limits.

## Install

```bash
pip install freellmpool      # or: pipx install freellmpool
```

Only dependency is `httpx`. Python 3.11+.

## Command line

```bash
freellmpool ask "Write a haiku about sqlite"
git diff | freellmpool ask "Write a commit message for this"
freellmpool providers        # which providers are configured
freellmpool models           # every provider/model id
```

Pin a provider or model; common OpenAI/Anthropic model names are mapped to a free
equivalent so existing scripts keep working:

```bash
freellmpool ask -m groq/llama-3.3-70b-versatile "hi"
freellmpool ask -p cerebras,groq "hi"
freellmpool ask -m gpt-4o-mini "hi"      # routed to a free model
```

## As a proxy

Run a local server that speaks the OpenAI API, then point any OpenAI-compatible
tool at it:

```bash
freellmpool proxy
export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=unused
```

```python
from openai import OpenAI
client = OpenAI()
print(client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "hi"}],
).choices[0].message.content)
```

The proxy also implements the OpenAI Responses API (for the Codex CLI) and the
Anthropic Messages API (for Claude Code), so coding agents can run on free models
too. `freellmpool code <agent>` prints the exact setup:

```bash
freellmpool code aider       # also: claude, codex, cline, continue, cursor, opencode
```

Endpoints: `/v1/chat/completions` (token streaming, tool calling), `/v1/embeddings`,
`/v1/responses`, `/v1/messages`, `/v1/models`, and a `/dashboard` page showing usage.
Setup snippets for specific tools are in [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)
and [docs/AGENTS.md](docs/AGENTS.md).

## As a library

```python
from freellmpool import Pool

pool = Pool.from_default_config()
reply = pool.ask("Summarize the plot of Hamlet in 20 words.")
print(reply.text, "—", reply.provider_id)

vectors = pool.embed(["first document", "second document"]).vectors
```

## As an MCP server

`freellmpool mcp` runs a Model Context Protocol server over stdio, so Claude
Desktop, Claude Code, or Cursor can hand subtasks to free models. See
[docs/MCP.md](docs/MCP.md).

## Provider keys

freellmpool reads keys from the environment and uses whatever is set. None are
required. Step-by-step signup links for each (all free, no card) are in
[docs/ACCOUNTS.md](docs/ACCOUNTS.md).

| Provider | Env var | Notes |
|---|---|---|
| Pollinations | — | no key needed |
| OVHcloud | — | no key needed (anonymous tier) |
| LLM7 | `LLM7_API_KEY` | optional |
| Groq | `GROQ_API_KEY` | fast |
| Cerebras | `CEREBRAS_API_KEY` | fast, large daily cap |
| NVIDIA NIM | `NVIDIA_API_KEY` | |
| OpenRouter | `OPENROUTER_API_KEY` | free models |
| Google Gemini | `GEMINI_API_KEY` | |
| GitHub Models | `GITHUB_TOKEN` | any PAT |
| Cloudflare | `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` | |
| Mistral, Cohere, SambaNova, Z.ai, Ollama Cloud, LongCat | see `.env.example` | |

A `config.toml` (see [config.toml.example](config.toml.example)) can hold keys,
model aliases, and settings instead of env vars.

## How routing works

For each request, freellmpool builds the list of `(provider, model)` pairs you
have access to, orders them least-used-first (so load spreads across tiers), and
tries them in order until one returns a non-empty result. A provider that returns
a 429 is set aside for a cooldown window. Daily counts are kept in
`~/.config/freellmpool/quota.json` and reset at UTC midnight.

Architecture notes: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Limitations

- Free-tier models are smaller than frontier models. They're good for drafting,
  summarizing, classification, triage, and everyday coding — not a replacement
  for GPT-class reasoning on hard problems.
- Quality and capacity vary through the day as high-cap tiers exhaust; limits
  reset at UTC midnight.
- Free tiers change without notice. When a model id or limit goes stale, a
  one-line PR to `providers.toml` fixes it for everyone.
- The proxy is meant for local/single-user use. It binds to `127.0.0.1` by
  default; if you expose it, set a key (`--api-key`).
- The Claude Code / Anthropic path is experimental (text and tool use; no vision).
- These are free tiers shared by everyone — don't abuse them.

## Contributing

New providers and fixes to stale limits are the most useful contributions, and
both are usually a small change to `providers.toml`. See
[CONTRIBUTING.md](CONTRIBUTING.md). Tests run with no network access:

```bash
pip install -e ".[dev]" && pytest && ruff check src tests
```

## License

MIT
