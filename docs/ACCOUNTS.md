# Getting your free API keys (step by step)

`freellmpool` is only as good as the free tiers you plug into it. The good news:
**every provider below is free and none require a credit card.** You don't need
all of them — even **one** key gets you going. Start with Groq + Cerebras (the
two fastest, most generous, and quickest to sign up for), then add more later.

> **No keys at all?** freellmpool still works: **OVHcloud** is keyless (anonymous)
> and **LLM7** works without a key. So `freellmpool ask "hi"` runs the moment you
> install. The keys below just add more models, higher limits, and better
> failover.

Each key takes about a minute. Once you have one, either `export` it in your
shell or put it in a `.env` file (copy [`.env.example`](../.env.example)).

> Tip: run `freellmpool providers` at any time to see which keys are detected.

---

## Start here (fastest to sign up for)

### Groq — *~1 min, no card*
1. Go to <https://console.groq.com/keys> and sign in with Google/GitHub.
2. Click **Create API Key**, name it anything, copy the value (`gsk_...`).
3. `export GROQ_API_KEY=gsk_...`

   The same key also powers free **audio transcription** (Whisper) via
   `/v1/audio/transcriptions`.

### Cerebras — *~1 min, no card*
1. Go to <https://cloud.cerebras.ai> and sign in.
2. Open **API Keys** → **Generate key**, copy it (`csk-...`).
3. `export CEREBRAS_API_KEY=csk-...`

That's enough to start. Run `freellmpool ask "hello"`.

---

## Add more free pools (optional)

### OpenRouter — *many `:free` models*
1. <https://openrouter.ai/keys> → sign in → **Create Key**.
2. `export OPENROUTER_API_KEY=sk-or-...`

### Google Gemini (AI Studio) — *generous free tier*
1. <https://aistudio.google.com/apikey> → **Create API key**.
2. `export GEMINI_API_KEY=...`

### GitHub Models — *you probably already have this*
1. Any GitHub Personal Access Token works: <https://github.com/settings/tokens>
   → **Generate new token** (classic). No special scopes are required for
   Models; a token with no scopes is fine.
2. `export GITHUB_TOKEN=ghp_...`

### Mistral — *free tier*
1. <https://console.mistral.ai/api-keys> → **Create new key**.
2. `export MISTRAL_API_KEY=...`

### Cohere — *free trial keys*
1. <https://dashboard.cohere.com/api-keys> → copy your **Trial key**.
2. `export COHERE_API_KEY=...`

### SambaNova — *free tier*
1. <https://cloud.sambanova.ai/apis> → **Generate API key**.
2. `export SAMBANOVA_API_KEY=...`

### NVIDIA NIM — *free credits, huge catalog*
1. <https://build.nvidia.com> → sign in → pick a model → **Get API Key**.
2. `export NVIDIA_API_KEY=nvapi-...`

### Z.ai / Zhipu GLM — *free GLM flash models*
1. <https://z.ai> → sign in → API keys.
2. `export ZHIPU_API_KEY=...`

### Ollama Cloud — *free tier*
1. <https://ollama.com/settings/keys> → **Create key**.
2. `export OLLAMA_API_KEY=...`

### LongCat (Meituan) — *free tier*
1. <https://longcat.chat> → developer/API keys.
2. `export LONGCAT_API_KEY=...`

### OVHcloud & LLM7 — *no signup needed*
Nothing to do — OVHcloud is anonymous and LLM7 works without a key. For higher
LLM7 limits you can optionally grab a token at <https://token.llm7.io> and
`export LLM7_API_KEY=...`.

### Cloudflare Workers AI — *needs two values*
1. Account ID: Cloudflare dashboard → **Workers & Pages** (right sidebar shows
   your Account ID), or **Workers AI** → **Use REST API**.
2. API token: <https://dash.cloudflare.com/profile/api-tokens> → **Create
   Token** → use the **Workers AI** template (read is enough to run models).
3. `export CLOUDFLARE_ACCOUNT_ID=...` and `export CLOUDFLARE_API_TOKEN=...`

---

## Keeping keys around

Rather than re-exporting every shell, drop them in a `.env` file at your project
root (it's gitignored by default in this repo):

```bash
cp .env.example .env
# edit .env, fill in the keys you have
```

`freellmpool` reads from the **environment**, so load the file however you like —
e.g. `set -a; source .env; set +a`, or a tool like
[`direnv`](https://direnv.net/).

## A note on free-tier limits

Free tiers change. The per-day hints in
[`providers.toml`](../src/freellmpool/providers.toml) are conservative guesses
used only to spread load; `freellmpool` reacts to real `429` rate limits at call
time regardless. If a provider changes its limits, a one-line PR to
`providers.toml` keeps everyone current — see [CONTRIBUTING.md](../CONTRIBUTING.md).
