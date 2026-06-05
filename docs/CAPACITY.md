# Capacity management

freellmpool can pool several legitimate LLM providers behind one local endpoint. The capacity tools help you see what is usable right now, what is close to quota, and what needs manual setup.

This feature is intentionally read-only. It does not create accounts, does not manage email inboxes, and does not try to bypass provider limits.

## Main commands

```bash
freellmpool capacity status --target 5
freellmpool keys status --target 5
freellmpool keys checklist --target 5
freellmpool providers health
```

## Provider capacity

`capacity status` summarizes the local catalog, configured environment variables, daily quota counters and optional key inventory.

Statuses:

- `healthy`: configured and usable according to local state.
- `low_quota`: usage is above 80 percent of the daily request hint.
- `exhausted`: usage reached the daily request hint.
- `invalid_key`: local inventory says the key has expired.
- `missing`: the provider exists in the catalog but is not configured.

Example:

```text
LLM capacity: 3/5 healthy providers
Action recommended: add 2 provider(s).
```

## Key inventory

The key inventory is optional. It tracks metadata about keys you created manually. By default it is read from:

```text
~/.config/freellmpool/keys.toml
```

You can override it with:

```bash
export FREELLMPOOL_KEYS_PATH=/path/to/keys.toml
```

Example:

```toml
[[keys]]
provider = "groq"
env_var = "GROQ_API_KEY"
label = "personal-main"
created_at = "2026-06-05"
expires_at = "2026-12-31"
commercial_allowed = true
notes = "created manually"
```

The inventory should not contain raw API key values. Keep real secrets in environment variables, `config.toml`, your shell profile, or a secret manager.

## Manual checklist

`keys checklist --target 5` tells you which providers to configure manually to reach the desired number of healthy providers.

Example:

```text
Manual key checklist to reach 5 healthy providers:
  - cerebras: create a key manually, then set CEREBRAS_API_KEY
  - cloudflare: create a key manually, then set CLOUDFLARE_API_TOKEN
```

## Provider health

`providers health` sends one tiny request to each configured provider and reports latency or failure.

```bash
freellmpool providers health
freellmpool providers health --timeout 10
freellmpool providers health -p groq,cerebras
freellmpool providers health -m llama-3.3-70b-versatile
```

This is different from `capacity status`: health checks touch the network, while capacity status only reads local state.

## Dashboard

When the proxy is running, open:

```text
http://127.0.0.1:8080/dashboard
```

The dashboard shows request counters, cache hits, estimated savings, provider usage, capacity status, and measured latency if the process has already made calls or health checks.

## Recommended workflow

1. Run `freellmpool capacity status --target 5`.
2. Run `freellmpool keys checklist --target 5`.
3. Add provider keys manually.
4. Run `freellmpool providers health`.
5. Start the proxy and watch `/dashboard`.

## Limits

The daily quota hints are local estimates. Providers can change limits or return 429 earlier. The router still reacts to real provider failures at request time.
