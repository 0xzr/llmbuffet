"""A tiny Model Context Protocol (MCP) server, zero extra dependencies.

`freellmpool mcp` speaks MCP over stdio (newline-delimited JSON-RPC 2.0), so an
MCP client — Claude Desktop, Claude Code, Cursor, etc. — can offload subtasks to
free LLMs:

    {
      "mcpServers": {
        "freellmpool": { "command": "freellmpool", "args": ["mcp"] }
      }
    }

Tools exposed:
    free_llm_ask     ask a free model a question (prompt + optional system/model/provider)
    free_llm_models  list available provider/model ids

Implemented on the standard library only — no MCP SDK required.
"""

from __future__ import annotations

import json
import sys

from .config import resolve_alias
from .router import Pool

_DEFAULT_PROTOCOL = "2025-06-18"

TOOLS = [
    {
        "name": "free_llm_ask",
        "description": (
            "Ask a free LLM (pooled across 16 free providers, with failover). "
            "Use this to offload a self-contained subtask — drafting, summarizing, "
            "classifying, brainstorming, or a quick lookup — to a free model."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The question or task."},
                "system": {"type": "string", "description": "Optional system instruction."},
                "model": {
                    "type": "string",
                    "description": "Optional model name or provider/model (e.g. groq/llama-3.3-70b-versatile). Default: auto.",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional provider id to restrict to (e.g. groq, cerebras).",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "free_llm_models",
        "description": "List the available free provider/model ids freellmpool can route to.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "free_llm_quota",
        "description": (
            "Show today's free-tier usage (UTC): per-provider request counts and "
            "daily-limit headroom, plus session totals and estimated cost avoided."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _result(mid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _text(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(pool: Pool, params: dict) -> dict:
    name = params.get("name")
    args = params.get("arguments") or {}
    if name == "free_llm_ask":
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return _text("'prompt' is required", is_error=True)
        provider = args.get("provider")
        providers = [provider] if provider else None
        model = args.get("model")
        if isinstance(model, str) and model:
            model = resolve_alias(model, pool.env)
            if model == "auto":
                model = None
            elif "/" in model:
                p, _, m = model.partition("/")
                providers, model = [p], m
        else:
            model = None
        try:
            reply = pool.ask(prompt, system=args.get("system"), model=model, providers=providers)
        except Exception as exc:  # noqa: BLE001 — surface as a tool error
            return _text(f"{type(exc).__name__}: {exc}", is_error=True)
        return _text(reply.text)
    if name == "free_llm_models":
        ids = [f"{p.id}/{m.name}" for p in pool.providers for m in p.models if m.enabled]
        return _text("\n".join(ids) or "no providers configured")
    if name == "free_llm_quota":
        return _text(_quota_summary(pool))
    return _text(f"unknown tool: {name}", is_error=True)


def _quota_summary(pool: Pool) -> str:
    from .savings import usd_saved

    snap = pool.quota.snapshot()  # {provider::model: count} for today (UTC)
    used: dict[str, int] = {}
    for key, count in snap.items():
        pid = key.split("::", 1)[0]
        used[pid] = used.get(pid, 0) + count
    # per-provider daily-limit hint = max rpd across its models (0 = unmetered)
    limit: dict[str, int] = {}
    for p in pool.providers:
        rpds = [m.rpd for m in p.models if m.rpd > 0]
        limit[p.id] = max(rpds) if rpds else 0

    lines = ["Today's free-tier usage (UTC):", ""]
    lines.append(f"{'provider':<13}{'used':>6}  {'daily limit/model':<18}remaining")
    for p in pool.providers:
        u = used.get(p.id, 0)
        lim = limit[p.id]
        if lim:
            lines.append(f"{p.id:<13}{u:>6}  ~{lim:<17}{max(0, lim - u)}")
        else:
            lines.append(f"{p.id:<13}{u:>6}  {'unmetered':<18}-")

    s = pool.stats
    lines += [
        "",
        f"session: {s.get('requests', 0)} requests, {s.get('cache_hits', 0)} cache hits, "
        f"{s.get('completion_tokens', 0)} output tokens",
        f"cost avoided vs gpt-4o: ~${usd_saved(s.get('prompt_tokens'), s.get('completion_tokens')):.4f}",
    ]
    return "\n".join(lines)


def handle_message(pool: Pool, msg: dict, *, version: str = "0.0.0") -> dict | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for
    notifications (which get no reply)."""
    if not isinstance(msg, dict) or "method" not in msg:
        return None
    method = msg["method"]
    if "id" not in msg:  # notification (e.g. notifications/initialized)
        return None
    mid = msg["id"]
    try:
        if method == "initialize":
            params = msg.get("params") or {}
            protocol = params.get("protocolVersion") or _DEFAULT_PROTOCOL
            return _result(
                mid,
                {
                    "protocolVersion": protocol,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "freellmpool", "version": version},
                },
            )
        if method == "ping":
            return _result(mid, {})
        if method == "tools/list":
            return _result(mid, {"tools": TOOLS})
        if method == "tools/call":
            return _result(mid, _call_tool(pool, msg.get("params") or {}))
        return _error(mid, -32601, f"method not found: {method}")
    except Exception as exc:  # noqa: BLE001 — never crash the loop
        return _error(mid, -32603, f"{type(exc).__name__}: {exc}")


def serve_stdio(pool: Pool, version: str = "0.0.0") -> None:
    """Run the MCP server over stdio until stdin closes."""
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        response = handle_message(pool, msg, version=version)
        if response is not None:
            out.write(json.dumps(response) + "\n")
            out.flush()
