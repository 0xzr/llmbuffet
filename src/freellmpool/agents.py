"""Setup recipes for `freellmpool code <agent>` — wire a coding agent to the
free proxy in one glance. Covers OpenAI-compatible agents plus Claude Code
(via the experimental Anthropic /v1/messages shim)."""

from __future__ import annotations

_PROXY = "http://localhost:8080/v1"

AGENTS: dict[str, dict] = {
    "claude": {
        "label": "Claude Code",
        "steps": [
            "freellmpool proxy --port 8080",
            "export ANTHROPIC_BASE_URL=http://localhost:8080",
            "export ANTHROPIC_AUTH_TOKEN=dummy ANTHROPIC_API_KEY=dummy",
            "export ANTHROPIC_MODEL=auto ANTHROPIC_SMALL_FAST_MODEL=auto",
            "export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1",
            "claude   # now running on freellmpool via the /v1/messages bridge",
        ],
        "note": "Pin a model with ANTHROPIC_MODEL=provider/model, e.g. alibaba_cloud_model_studio/qwen3-plus.",
    },
    "codex": {
        "label": "OpenAI Codex CLI",
        "steps": [
            "freellmpool proxy --port 8080",
            "export OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=anything",
            "codex   # uses the /v1/responses shim",
        ],
        "note": "Codex speaks the Responses API, which freellmpool shims at /v1/responses.",
    },
    "aider": {
        "label": "aider",
        "steps": [
            "freellmpool proxy --port 8080",
            "export OPENAI_API_BASE=http://localhost:8080/v1 OPENAI_API_KEY=anything",
            "aider --model openai/auto",
        ],
    },
    "cline": {
        "label": "Cline / Roo Code (VS Code)",
        "steps": [
            "freellmpool proxy --port 8080",
            "Settings → API Provider: 'OpenAI Compatible'",
            f"  Base URL: {_PROXY}   API Key: anything   Model: auto",
        ],
    },
    "continue": {
        "label": "Continue (VS Code / JetBrains)",
        "steps": [
            "freellmpool proxy --port 8080",
            "Add to ~/.continue/config.yaml:",
            "  models:",
            "    - name: freellmpool",
            "      provider: openai",
            "      model: auto",
            f"      apiBase: {_PROXY}",
            "      apiKey: anything",
        ],
    },
    "cursor": {
        "label": "Cursor / Windsurf",
        "steps": [
            "freellmpool proxy --port 8080",
            "Settings → Models → enable 'Override OpenAI Base URL':",
            f"  {_PROXY}   API key: anything   (free models are slower than paid)",
        ],
    },
    "opencode": {
        "label": "opencode",
        "steps": [
            "freellmpool proxy --port 8080",
            "Add to opencode.json:",
            '  "provider": {',
            '    "freellmpool": {',
            '      "npm": "@ai-sdk/openai-compatible",',
            f'      "options": {{ "baseURL": "{_PROXY}" }},',
            '      "models": { "auto": { "name": "freellmpool (auto)" } }',
            "    }",
            "  }",
        ],
    },
}


def render(agent: str) -> str | None:
    rec = AGENTS.get(agent)
    if rec is None:
        return None
    lines = [f"Wire {rec['label']} to free models via freellmpool:\n"]
    for i, step in enumerate(rec["steps"], 1):
        prefix = f"  {i}. " if not step.startswith("  ") else "     "
        lines.append(f"{prefix}{step}")
    if rec.get("note"):
        lines.append(f"\n  ℹ {rec['note']}")
    lines.append("\n  More tools + details: docs/INTEGRATIONS.md")
    return "\n".join(lines)


def list_agents() -> str:
    rows = [f"  {name:<10} {rec['label']}" for name, rec in AGENTS.items()]
    return "Usage: freellmpool code <agent>\n\nSupported coding agents:\n" + "\n".join(rows)
