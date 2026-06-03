# freellmpool — pool every free LLM API into one endpoint

**A free, OpenAI-compatible LLM gateway that pools the free tiers of 16 providers (Groq, Cerebras, NVIDIA NIM, Gemini, OpenRouter, GitHub Models, Cloudflare & more) behind one `/v1` endpoint — with automatic failover and quota tracking. Works out of the box with zero API keys.**

[![PyPI](https://img.shields.io/pypi/v/freellmpool.svg)](https://pypi.org/project/freellmpool/)
[![CI](https://github.com/0xzr/freellmpool/actions/workflows/ci.yml/badge.svg)](https://github.com/0xzr/freellmpool/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)

![freellmpool demo](assets/demo.svg)

> One free tier is a toy. **Sixteen, stacked, are tens of thousands of free requests a day.** And unlike a self-hosted gateway, freellmpool is just `pip install` — a CLI, a Python library, *and* a proxy — that works with **no keys, no Docker, no setup**.

```bash
pip install freellmpool
freellmpool ask "Explain the CAP theorem in one sentence."   # ← real answer, zero keys
```

Groq, Cerebras, NVIDIA NIM, Google Gemini, OpenRouter, GitHub Models, Cloudflare Workers AI, Mistral, Cohere, and more each hand out a generous **free tier** — but each has its own SDK, rate limits, and daily cap. `freellmpool` puts all of them into one pool:

- 🔌 **True drop-in.** Point any OpenAI SDK / tool at `freellmpool` and it just works — `/v1/chat/completions`, `/v1/models`, **tool/function-calling**, and a `/v1/responses` shim for **Codex CLI & agents**. Common model names (`gpt-4o-mini`, `claude-3-5-sonnet`, …) are **auto-aliased to free models**, so existing code runs unchanged.
- 🟢 **Zero config.** Works with **no API keys at all** — keyless providers are built in. `pip install` → `ask` → done.
- 🔁 **Automatic failover.** Rate-limited or 5xx on one provider? `freellmpool` transparently rolls to the next, with a cooldown so it stops hammering a throttled pool.
- 📊 **Quota-aware routing.** Spreads load least-used-first and respects each free daily limit, so you squeeze the most out of every tier.
- 🤖 **Built for agents.** Streaming (SSE), a Codex/Responses shim, and mid-run failover — exactly where long agent loops usually die.
- 🧠 **Chat + embeddings.** Pooled free `/v1/embeddings` too (`pool.embed(...)`) — free RAG, not just chat.
- 🪶 **Tiny.** Pure-Python, one dependency (`httpx`). The proxy runs on the standard library. No keys are ever stored in the repo.

## Use it four ways

| | |
|---|---|
| **CLI** | `freellmpool ask "..."` — pipe stdin in, `--json` out |
| **Library** | `from freellmpool import Pool` — `pool.ask(...)`, `pool.embed(...)` |
| **Proxy** | `freellmpool proxy` — a drop-in `OPENAI_BASE_URL` for any tool |
| **`llm` plugin** | `llm install llm-freellmpool` → `llm -m freellmpool "..."` |

It's not a server you have to host with keys you have to manage — it's a client that just works.

---

## Install

```bash
pip install freellmpool      # or: pipx install freellmpool
```

## Zero-config: it works with no keys at all

Three providers in the catalog need **no signup** (Pollinations and OVHcloud are keyless; LLM7's key is optional), so this works the moment you install:

```bash
pip install freellmpool
freellmpool ask "Explain the CAP theorem in one sentence."
```

Add provider keys (below) to unlock more models, higher limits, and better failover.

## 60-second quickstart (with keys)

1. Grab one or more free API keys — **all free, no credit card**. You only need
   **one** to start (Groq and Cerebras are the fastest to sign up for).
   👉 **[docs/ACCOUNTS.md](docs/ACCOUNTS.md) has 1-minute, click-by-click steps for every provider.**

   | Provider | Get a key |
   |---|---|
   | Groq | <https://console.groq.com/keys> |
   | Cerebras | <https://cloud.cerebras.ai> |
   | OpenRouter | <https://openrouter.ai/keys> |
   | Google Gemini | <https://aistudio.google.com/apikey> |
   | GitHub Models | any GitHub PAT |

2. Export the ones you have (see [`.env.example`](.env.example) for all of them):

   ```bash
   export GROQ_API_KEY=gsk_...
   export CEREBRAS_API_KEY=csk-...
   ```

3. Ask something:

   ```bash
   freellmpool ask "Explain the CAP theorem in one sentence."
   ```

   or pipe context in:

   ```bash
   cat error.log | freellmpool ask "What's the root cause here?"
   ```

Check what's wired up:

```bash
freellmpool providers
```

```
freellmpool catalog: 16 providers, 56 models

  ✓ ovh          OVHcloud AI Endpoints (keyless)  5 models   [configured]
  ✓ llm7         LLM7 (key optional)           1 models   [configured]
  · groq         Groq                          6 models   [set GROQ_API_KEY]
  · cerebras     Cerebras                      4 models   [set CEREBRAS_API_KEY]
  · nvidia       NVIDIA NIM                    5 models   [set NVIDIA_API_KEY]
  ...
```

## Choosing a model or provider

By default freellmpool auto-picks the least-used provider you have. To pin a choice:

```bash
freellmpool models                       # list every provider/model id
freellmpool ask -m groq/llama-3.3-70b-versatile "hi"   # exact provider + model
freellmpool ask -m llama-3.3-70b-versatile "hi"        # that model on any provider
freellmpool ask -p cerebras,groq "hi"                  # restrict to these providers
```

Same idea through the proxy via the OpenAI `model` field: `"auto"`, `"groq"`, or `"groq/llama-3.3-70b-versatile"`.

### Providers in the box

| Provider | Key env | Notes |
|---|---|---|
| Pollinations | — | **keyless**, works out of the box |
| OVHcloud AI Endpoints | — | **keyless**, works out of the box |
| LLM7 | `LLM7_API_KEY` | key optional |
| Groq | `GROQ_API_KEY` | very fast |
| Cerebras | `CEREBRAS_API_KEY` | very fast, large daily cap |
| NVIDIA NIM | `NVIDIA_API_KEY` | big model catalog (build.nvidia.com) |
| OpenRouter | `OPENROUTER_API_KEY` | many `:free` models |
| Google Gemini | `GEMINI_API_KEY` | generous free tier |
| GitHub Models | `GITHUB_TOKEN` | any PAT works |
| Cloudflare Workers AI | `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` | |
| Mistral | `MISTRAL_API_KEY` | |
| Cohere | `COHERE_API_KEY` | |
| SambaNova | `SAMBANOVA_API_KEY` | |
| Z.ai / Zhipu GLM | `ZHIPU_API_KEY` | |
| Ollama Cloud | `OLLAMA_API_KEY` | |
| LongCat (Meituan) | `LONGCAT_API_KEY` | |

Full signup steps for each: **[docs/ACCOUNTS.md](docs/ACCOUNTS.md)**.

## The killer feature: a drop-in OpenAI proxy

Run the gateway:

```bash
freellmpool proxy --port 8080
```

Now point **any** OpenAI-compatible app or SDK at it — no other changes:

```bash
export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=anything        # freellmpool ignores it
```

```python
from openai import OpenAI

client = OpenAI()  # picks up OPENAI_BASE_URL
resp = client.chat.completions.create(
    model="auto",                      # or "groq", or "groq/llama-3.3-70b-versatile"
    messages=[{"role": "user", "content": "Say hi in French."}],
)
print(resp.choices[0].message.content)
```

The `model` field controls routing:

| `model` value | Routes to |
|---|---|
| `auto` (or omitted) | any configured provider, least-used first |
| `groq` | any model on Groq |
| `groq/llama-3.3-70b-versatile` | that exact model |
| `llama-3.3-70b-versatile` | that model on any provider that has it |

## Use it as the free LLM backend for your AI agent

Coding agents and agent frameworks (aider, Continue, Cline, the OpenAI Agents SDK, LangChain, ...) almost all speak the OpenAI API — so they can run on pooled free inference through `freellmpool`, with **failover when one provider rate-limits you mid-run** (exactly when long agent loops tend to die):

```bash
freellmpool proxy --port 8080
export OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=anything
aider --model openai/auto          # or point any OpenAI-compatible tool here
```

The proxy supports `stream: true` (SSE) and tool/function-calling, so streaming chat UIs and tool-using agent loops work too.

## Works with your tools

Anything that accepts a custom OpenAI base URL drops straight in — copy-paste configs in **[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)**:

**[opencode](docs/INTEGRATIONS.md#opencode)** · **[aider](docs/INTEGRATIONS.md#aider)** · **[Continue](docs/INTEGRATIONS.md#continue-vs-code--jetbrains)** · **[Cline / Roo](docs/INTEGRATIONS.md#cline--roo-code)** · **[Cursor / Windsurf](docs/INTEGRATIONS.md#cursor--windsurf)** · **[Codex CLI](docs/AGENTS.md#openai-codex-cli)** · **[Open WebUI](docs/INTEGRATIONS.md#open-webui)** · **[LibreChat](docs/INTEGRATIONS.md#librechat)** · **[LangChain](docs/INTEGRATIONS.md#langchain)** · **[LlamaIndex](docs/INTEGRATIONS.md#llamaindex)** · **[Vercel AI SDK](docs/INTEGRATIONS.md#vercel-ai-sdk)** · **[llm CLI](docs/INTEGRATIONS.md#simon-willisons-llm)** · **[shell-gpt](docs/INTEGRATIONS.md#shell-gpt-sgpt)** · **[n8n](docs/INTEGRATIONS.md#n8n)**

## Use it as a library

```python
from freellmpool import Pool

pool = Pool.from_default_config()
reply = pool.ask("Summarize the plot of Hamlet in 20 words.")
print(reply.text)
print(f"served by {reply.provider_id}/{reply.model}")

# Pooled free embeddings too — free RAG in a couple lines:
vecs = pool.embed(["first document", "second document"]).vectors
```

## Correct by design

freellmpool aims to be a *faithful* OpenAI drop-in, so agents and SDKs don't trip over edge cases:

- **Fails over on errors** (incl. provider tool-call errors) instead of returning a hard `400`.
- **Accepts assistant messages with empty/null content** + `tool_calls` (doesn't reject them).
- **Respects each provider's own per-day free limit** in its quota tracking, not a single global guess.
- **Skips a rate-limited provider's other models** for that request, with a cooldown so it stops hammering a throttled pool.

## How routing works

For each request `freellmpool` builds the list of `(provider, model)` candidates you have keys for, orders them **least-used-today first** (providers already over their free daily hint sink to the bottom), then tries them in order until one returns a non-empty completion. Every success is recorded to a small per-day counter at `~/.config/freellmpool/quota.json` (reset at UTC midnight). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full picture.

## Adding or overriding providers

The built-in catalog lives in [`src/freellmpool/providers.toml`](src/freellmpool/providers.toml). To add a provider or override a model list without forking, drop a `providers.toml` at `~/.config/freellmpool/providers.toml` (or point `FREELLMPOOL_CONFIG` at one). Same-`id` entries override the built-ins; new ids are appended. See [CONTRIBUTING.md](CONTRIBUTING.md) for the (small) anatomy of a provider.

## Comparison

| | freellmpool | Calling each SDK by hand | A paid gateway |
|---|---|---|---|
| Free tiers pooled | ✅ 16 providers | ⚠️ you wire each one | ❌ |
| Automatic failover | ✅ | ❌ | ✅ |
| Quota tracking | ✅ per-day | ❌ | varies |
| Drop-in OpenAI proxy | ✅ | ❌ | ✅ |
| Cost | $0 | $0 | 💸 |
| Dependencies | 1 (`httpx`) | many | a service |

## Limitations (read this)

`freellmpool` is honest about what it is — a way to pool **free tiers**, not a frontier-model service:

- **No GPT-5 / Claude-Opus-class reasoning.** Free tiers are smaller/faster models — great for triage, drafting, classification, tool-routing, and everyday coding; reach for a frontier model for the hardest reasoning.
- **Quality and capacity vary through the day** as high-cap pools exhaust; daily limits reset at UTC midnight.
- **Free tiers change without notice.** Endpoints, model ids, and limits drift — that's what the one-line `providers.toml` PRs are for.
- **Local-first, single-user.** The proxy defaults to `127.0.0.1`; if you bind it to a network interface, set a proxy key (`--api-key`). Not meant as a multi-tenant production gateway.
- **Respect the providers.** This pools *free* tiers for personal projects and experimentation — don't abuse them, or we all lose them.

## Status

`freellmpool` is `0.3` and moving fast. Provider endpoints and free-tier limits drift — if something breaks, please [open an issue](https://github.com/0xzr/freellmpool/issues) or send a one-line PR to `providers.toml`. Contributions of new free providers are especially welcome.

## Found this useful?

⭐ **Star the repo** — it's the single biggest thing that helps others discover freellmpool, and it keeps the free-provider catalog maintained. New free providers and one-line limit fixes are always welcome ([CONTRIBUTING.md](CONTRIBUTING.md)).

## License

MIT — see [LICENSE](LICENSE).

