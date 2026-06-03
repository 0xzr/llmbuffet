---
name: Add a free provider
about: Propose adding a new free-tier LLM provider to the catalog
title: "Add provider: <name>"
labels: ["good first issue", "provider"]
---

**Provider:** <name + homepage>

**Free tier?** (link to the free-tier docs — must be usable without a credit card)

**OpenAI-compatible?** (does it expose `/v1/chat/completions`? If yes, this is a
one-block PR to `src/llmbuffet/providers.toml`. If no, it needs a small adapter.)

**Base URL:**

**Models to include** (name + free daily request limit if known):
-

**Env var for the API key:** `<PROVIDER>_API_KEY`

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the (small) steps. New providers
are the most valuable contribution to llmbuffet — thank you!
