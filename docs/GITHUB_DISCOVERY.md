# GitHub Discovery Checklist

This is the local P9 handoff. It records the read-only audit and the exact
GitHub metadata changes for the operator to apply after this branch is reviewed.
Do not run these write commands during the polish pass.

## Read-only audit

Repository inspected on 2026-06-11 with:

```bash
gh repo view 0xzr/freellmpool --json description,repositoryTopics,url,isPrivate
```

Current About description:

> Pool the free tiers of 18 LLM providers (Groq, Cerebras, NVIDIA NIM, Gemini, OpenRouter, Cloudflare, Hugging Face...) behind one OpenAI-compatible /v1 endpoint. Free, zero-config, automatic failover. Codex/agent ready.

Current topics are already at GitHub's 20-topic limit:

`ai`, `failover`, `free-llm`, `gateway`, `gemini`, `groq`, `llm`,
`llm-api`, `llm-gateway`, `llm-router`, `openai`, `openai-api`,
`openai-proxy`, `openrouter`, `python`, `codex`, `free-llm-api`, `mcp`,
`mcp-server`, `model-context-protocol`.

P9 gap topics missing from the live repo:

`anthropic`, `claude`, `cursor`, `speech-to-text`, `rate-limiting`.

## Recommended metadata

Recommended description (103 chars):

> Free LLM API pool: 18 providers, 200+ models, zero keys to start. OpenAI/Anthropic proxy with failover.

Recommended 20-topic set:

`anthropic`, `claude`, `codex`, `cursor`, `failover`, `free-llm`,
`free-llm-api`, `gemini`, `groq`, `llm-gateway`, `llm-router`, `mcp`,
`mcp-server`, `model-context-protocol`, `openai`, `openai-proxy`,
`openrouter`, `python`, `rate-limiting`, `speech-to-text`.

This removes the lower-signal duplicate topics `ai`, `gateway`, `llm`,
`llm-api`, and `openai-api` to make room for the five P9 discovery gaps.

Operator command after merge:

```bash
gh repo edit 0xzr/freellmpool \
  --description "Free LLM API pool: 18 providers, 200+ models, zero keys to start. OpenAI/Anthropic proxy with failover." \
  --remove-topic ai \
  --remove-topic gateway \
  --remove-topic llm \
  --remove-topic llm-api \
  --remove-topic openai-api \
  --add-topic anthropic \
  --add-topic claude \
  --add-topic cursor \
  --add-topic speech-to-text \
  --add-topic rate-limiting
```

## Social preview

Prepared asset:

- `assets/social-preview.png` at 1280x640 and under 1 MB, ready to upload.
- `assets/social-preview.svg` as the editable source.

GitHub's social preview docs recommend PNG, JPG, or GIF under 1 MB, ideally
1280x640:

https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview

Operator steps after merge:

1. Open `0xzr/freellmpool` on GitHub.
2. Go to Settings, then Social preview.
3. Upload `assets/social-preview.png`.

## Profile pin

Pin `0xzr/freellmpool` on the owner profile through GitHub's profile
customization UI. This cannot be represented as a repository patch or PR.

No external writes were performed while preparing this checklist.
