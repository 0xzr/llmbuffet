# Architecture

freellmpool is deliberately small. The whole thing is a catalog, a router, a
client with three adapters, a quota counter, and a proxy that wraps the router.

```
                       ┌──────────────────────────────┐
   CLI  (cli.py) ─────▶│            Pool             │
   Proxy (proxy.py) ──▶│           (router.py)         │
   Library import ────▶│                               │
                       │  1. build (provider, model)   │
                       │     candidates you have keys  │
                       │     for                       │
                       │  2. order least-used-first    │◀── QuotaStore (quota.py)
                       │  3. call each until one wins  │        ~/.config/freellmpool/
                       └───────────────┬───────────────┘        quota.json (per UTC day)
                                       │
                                       ▼
                              client.call(...)  (client.py)
                                       │
                  ┌────────────────────┼────────────────────┐
                  ▼                    ▼                    ▼
            openai adapter      cloudflare adapter     gemini adapter
        (Groq, Cerebras,      (substitutes account   (Generative Language
         OpenRouter, GitHub    id, then openai shape)  API; different body)
         Models, Mistral,
         Cohere, SambaNova)
```

## Modules

| File | Responsibility |
|---|---|
| `models.py` | `Provider`, `Model`, `Reply` dataclasses. |
| `config.py` | Load `providers.toml` (packaged + user override); filter to providers whose API key is in the environment. |
| `quota.py` | Tiny JSON counter keyed by `(UTC-day, provider, model)`. Injectable clock + path for tests. |
| `client.py` | One `call()` entrypoint + three adapters. All network I/O behind an injectable `post` callable. |
| `router.py` | `Pool`: candidate building, ordering, and the failover loop. |
| `cli.py` | `ask` / `providers` / `quota` / `proxy` subcommands. |
| `proxy.py` | Stdlib `http.server` exposing an OpenAI-compatible API over a `Pool`. |

## Design choices

- **One dependency (`httpx`).** The proxy uses only the standard library so
  installing freellmpool stays light. `httpx` is loaded lazily inside
  `default_post`, so even importing the library doesn't require it until a real
  network call is made — which is why the test suite needs no network and no
  httpx mocking.
- **Injectable transport.** `Pool`, `client.call`, and the proxy all accept a
  `post` callable. Tests pass a fake one (`tests/helpers.py`) and assert on
  routing decisions deterministically.
- **Adapters, not provider classes.** Nearly every provider is OpenAI-compatible,
  so the default path is shared. Only genuinely different shapes (Gemini) get
  their own ~30-line function.
- **Quota is advisory.** The per-day `rpd` hints spread load and de-prioritize
  exhausted pools, but freellmpool always reacts to real `429`s at call time, so a
  wrong hint degrades gracefully instead of failing.
- **Failover, not retry-storms.** Each candidate is tried once; on failure the
  router advances to the next. There's no per-provider retry loop to avoid
  hammering a struggling endpoint.

## Request lifecycle

1. `Pool.chat(messages, ...)` builds candidate `(provider, model)` targets,
   filtered by any `model`/`providers` constraints.
2. Providers are sorted least-used-today first, then targets inside each provider
   are sorted least-used-first. Pools over their daily hint sink to the back but
   remain reachable as a last resort. `FREELLMPOOL_ROUTING=legacy` restores the
   old per-target ordering; `=fast` orders by measured latency; `=quality` orders
   by benchmark-scored capability matched to the prompt's estimated difficulty
   (see `capability.py` — strong models for hard prompts, light ones for easy
   prompts, so scarce strong-model quota is rationed across the day).
3. For each target: call the provider; on a non-empty success, record one unit
   of quota and return the normalized `Reply`.
4. If every target fails, raise `AllProvidersExhausted` with the per-target
   reasons (handy for debugging which pools were rate-limited).
