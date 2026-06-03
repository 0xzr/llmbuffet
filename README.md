# 🍽️ llmbuffet — one free LLM API gateway for every free tier

**A free, OpenAI-compatible LLM gateway that pools 15 free-tier providers (Groq, Cerebras, NVIDIA NIM, Gemini, OpenRouter, GitHub Models, Cloudflare & more) behind one endpoint — with automatic failover and quota tracking. Works out of the box with zero API keys.**

[![CI](https://github.com/0xzr/llmbuffet/actions/workflows/ci.yml/badge.svg)](https://github.com/0xzr/llmbuffet/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)

> Stop juggling a dozen free LLM SDKs and rate limits. Point your OpenAI client at `llmbuffet` and never pay for a hobby project's inference again.

Groq, Cerebras, Google Gemini, OpenRouter, GitHub Models, Cloudflare Workers AI, Mistral, Cohere, SambaNova — each hands out a generous **free tier**, but each has its own SDK, its own rate limits, and its own daily cap. `llmbuffet` puts all of them into one pool:

- 🔌 **One OpenAI-compatible endpoint.** Point any existing OpenAI SDK / tool at `llmbuffet` and it just works — no code changes.
- 🔁 **Automatic failover.** Hit a rate limit or a 5xx on one provider? `llmbuffet` transparently moves to the next.
- 📊 **Quota-aware routing.** Spreads load least-used-first and respects each provider's free daily limit, so you squeeze the most out of every tier.
- 🧩 **One catalog, your keys.** Drop in the keys you have; `llmbuffet` skips the rest. No key is ever stored in the repo.
- 🪶 **Tiny.** Pure-Python, one dependency (`httpx`). The proxy runs on the standard library.

> Why it exists: stitching together a dozen free LLM tiers by hand is fiddly and breaks constantly. `llmbuffet` makes "never pay for a hobby project's LLM calls again" a one-command setup.

---

## Install

```bash
pip install llmbuffet      # or: pipx install llmbuffet
```

## Zero-config: it works with no keys at all

Two providers in the catalog need **no signup** (OVHcloud is keyless; LLM7's key is optional), so this works the moment you install:

```bash
pip install llmbuffet
llmbuffet ask "Explain the CAP theorem in one sentence."
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
   llmbuffet ask "Explain the CAP theorem in one sentence."
   ```

   or pipe context in:

   ```bash
   cat error.log | llmbuffet ask "What's the root cause here?"
   ```

Check what's wired up:

```bash
llmbuffet providers
```

```
llmbuffet catalog: 15 providers, 53 models

  ✓ ovh          OVHcloud AI Endpoints (keyless)  5 models   [configured]
  ✓ llm7         LLM7 (key optional)           1 models   [configured]
  · groq         Groq                          6 models   [set GROQ_API_KEY]
  · cerebras     Cerebras                      4 models   [set CEREBRAS_API_KEY]
  · nvidia       NVIDIA NIM                    5 models   [set NVIDIA_API_KEY]
  ...
```

## Choosing a model or provider

By default llmbuffet auto-picks the least-used provider you have. To pin a choice:

```bash
llmbuffet models                       # list every provider/model id
llmbuffet ask -m groq/llama-3.3-70b-versatile "hi"   # exact provider + model
llmbuffet ask -m llama-3.3-70b-versatile "hi"        # that model on any provider
llmbuffet ask -p cerebras,groq "hi"                  # restrict to these providers
```

Same idea through the proxy via the OpenAI `model` field: `"auto"`, `"groq"`, or `"groq/llama-3.3-70b-versatile"`.

### Providers in the box

| Provider | Key env | Notes |
|---|---|---|
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
llmbuffet proxy --port 8080
```

Now point **any** OpenAI-compatible app or SDK at it — no other changes:

```bash
export OPENAI_BASE_URL=http://localhost:8080/v1
export OPENAI_API_KEY=anything        # llmbuffet ignores it
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

Coding agents and agent frameworks (aider, Continue, Cline, the OpenAI Agents SDK, LangChain, ...) almost all speak the OpenAI API — so they can run on pooled free inference through `llmbuffet`, with **failover when one provider rate-limits you mid-run** (exactly when long agent loops tend to die):

```bash
llmbuffet proxy --port 8080
export OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=anything
aider --model openai/auto          # or point any OpenAI-compatible tool here
```

The proxy supports `stream: true` (Server-Sent Events), so streaming chat UIs and agent loops work too. Full integration snippets (aider, LangChain, Continue/Cline, OpenAI Agents SDK) are in **[docs/AGENTS.md](docs/AGENTS.md)**.

## Use it as a library

```python
from llmbuffet import Buffet

buffet = Buffet.from_default_config()
reply = buffet.ask("Summarize the plot of Hamlet in 20 words.")
print(reply.text)
print(f"served by {reply.provider_id}/{reply.model}")
```

## How routing works

For each request `llmbuffet` builds the list of `(provider, model)` candidates you have keys for, orders them **least-used-today first** (providers already over their free daily hint sink to the bottom), then tries them in order until one returns a non-empty completion. Every success is recorded to a small per-day counter at `~/.config/llmbuffet/quota.json` (reset at UTC midnight). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full picture.

## Adding or overriding providers

The built-in catalog lives in [`src/llmbuffet/providers.toml`](src/llmbuffet/providers.toml). To add a provider or override a model list without forking, drop a `providers.toml` at `~/.config/llmbuffet/providers.toml` (or point `LLMBUFFET_CONFIG` at one). Same-`id` entries override the built-ins; new ids are appended. See [CONTRIBUTING.md](CONTRIBUTING.md) for the (small) anatomy of a provider.

## Comparison

| | llmbuffet | Calling each SDK by hand | A paid gateway |
|---|---|---|---|
| Free tiers pooled | ✅ 15 providers | ⚠️ you wire each one | ❌ |
| Automatic failover | ✅ | ❌ | ✅ |
| Quota tracking | ✅ per-day | ❌ | varies |
| Drop-in OpenAI proxy | ✅ | ❌ | ✅ |
| Cost | $0 | $0 | 💸 |
| Dependencies | 1 (`httpx`) | many | a service |

## Status

`llmbuffet` is `0.1` and moving fast. Provider endpoints and free-tier limits drift — if something breaks, please [open an issue](https://github.com/0xzr/llmbuffet/issues) or send a one-line PR to `providers.toml`. Contributions of new free providers are especially welcome.

## Found this useful?

⭐ **Star the repo** — it's the single biggest thing that helps others discover llmbuffet, and it keeps the free-provider catalog maintained. New free providers and one-line limit fixes are always welcome ([CONTRIBUTING.md](CONTRIBUTING.md)).

## License

MIT — see [LICENSE](LICENSE).

