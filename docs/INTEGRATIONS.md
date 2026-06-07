# Integrations

`freellmpool` exposes a standard **OpenAI-compatible** API, so any tool that lets
you set a custom base URL can run on pooled free inference. Start the gateway
once, then point your tool at it:

```bash
freellmpool proxy --port 8080
# Base URL:  http://localhost:8080/v1
# API key:   anything   (freellmpool ignores it)
# Model:     auto        (or "groq", or "groq/llama-3.3-70b-versatile")
```

Because freellmpool **aliases common model names** (`gpt-4o-mini`, `gpt-4o`,
`claude-3-5-sonnet`, …) to free models, most tools work with their *default*
model setting untouched — just set the base URL and any API key.

---

## Coding agents & editors

### opencode
`opencode.json` (project or `~/.config/opencode/`):
```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "freellmpool/auto",
  "provider": {
    "freellmpool": {
      "npm": "@ai-sdk/openai-compatible",
      "options": { "baseURL": "http://localhost:8080/v1" },
      "models": { "auto": {}, "fast": {}, "quality": {}, "fair": {} }
    }
  }
}
```
Pick `freellmpool/auto|fast|quality|fair` in the model picker to control routing
(`quality` = capability-matched + latency-aware; `fast` = lowest latency; `fair` =
spread quota). Full guide: <https://0xzr.github.io/freellmpool/run-opencode-on-free-models.html>.

**Embedded dashboard + tools (optional).** Two OpenCode plugins live in the repo:
- [`integrations/opencode-tui`](../integrations/opencode-tui) — a live in-editor TUI
  dashboard (routing mode, $ saved, tokens served free, provider race, latency
  sparkline, last-served model). Install: `opencode plugin -g file:<repo>/integrations/opencode-tui`.
- [`integrations/opencode`](../integrations/opencode) — a server plugin adding
  `freellmpool_status` and `freellmpool_models` tools and a served-model toast.

### aider
```bash
export OPENAI_API_BASE=http://localhost:8080/v1
export OPENAI_API_KEY=anything
aider --model openai/auto
```

### Continue (VS Code / JetBrains)
`~/.continue/config.yaml`:
```yaml
models:
  - name: freellmpool
    provider: openai
    model: auto
    apiBase: http://localhost:8080/v1
    apiKey: anything
```

### Cline / Roo Code
Settings → **API Provider: OpenAI Compatible** → Base URL `http://localhost:8080/v1`,
API key `anything`, Model `auto`.

### Cursor / Windsurf
Settings → Models → enable **Override OpenAI Base URL** → `http://localhost:8080/v1`,
API key `anything`. (Free-tier models are slower than paid frontier models.)

### OpenAI Codex CLI
Codex speaks the Responses API, which freellmpool shims at `/v1/responses` — see
[AGENTS.md](AGENTS.md#openai-codex-cli).

## Chat UIs

### Open WebUI
Admin Panel → Settings → **Connections** → add an OpenAI API connection with URL
`http://localhost:8080/v1` and key `anything`.

### LibreChat
`librechat.yaml`:
```yaml
endpoints:
  custom:
    - name: "freellmpool"
      apiKey: "anything"
      baseURL: "http://localhost:8080/v1"
      models:
        default: ["auto"]
        fetch: true
```

### Lobe Chat
Settings → Language Model → OpenAI → set the **API Proxy Address** to
`http://localhost:8080/v1`, key `anything`.

## Frameworks & SDKs

### LangChain
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(base_url="http://localhost:8080/v1", api_key="anything", model="auto")
```

### LlamaIndex
```python
from llama_index.llms.openai_like import OpenAILike
llm = OpenAILike(api_base="http://localhost:8080/v1", api_key="anything",
                 model="auto", is_chat_model=True)
```

### Vercel AI SDK
```ts
import { createOpenAI } from "@ai-sdk/openai";
const fp = createOpenAI({ baseURL: "http://localhost:8080/v1", apiKey: "anything" });
const { text } = await generateText({ model: fp("auto"), prompt: "..." });
```

### OpenAI SDK (Python / JS)
Set `OPENAI_BASE_URL=http://localhost:8080/v1` — see
[`examples/agent_openai_sdk.py`](../examples/agent_openai_sdk.py).

## CLI tools

### Simon Willison's `llm`
`~/.config/io.datasette.llm/extra-openai-models.yaml`:
```yaml
- model_id: freellmpool
  model_name: auto
  api_base: http://localhost:8080/v1
  api_key_name: freellmpool
```
Then: `llm -m freellmpool "Explain async/await"`.

### shell-gpt (`sgpt`)
`~/.config/shell_gpt/.sgptrc`:
```
API_BASE_URL=http://localhost:8080/v1
DEFAULT_MODEL=auto
OPENAI_API_KEY=anything
```

## Automation

### n8n
In the **OpenAI** node's credential, set the **Base URL** to
`http://localhost:8080/v1` and any API key.

---

> Got a tool working that isn't listed? A PR adding it here is very welcome —
> see [CONTRIBUTING.md](../CONTRIBUTING.md). Config details for third-party tools
> change over time; check the tool's own docs if a field has moved.
