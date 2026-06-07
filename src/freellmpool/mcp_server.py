"""A tiny Model Context Protocol (MCP) server, zero extra dependencies.

`freellmpool mcp` speaks MCP over stdio (newline-delimited JSON-RPC 2.0), so an
MCP client — Claude Desktop, Claude Code, Cursor, etc. — can offload subtasks to
free LLMs, get a free *second opinion* from several models at once, see exactly
where a prompt would route, and watch the free tokens add up:

    {
      "mcpServers": {
        "freellmpool": { "command": "freellmpool", "args": ["mcp"] }
      }
    }

Tools exposed:
    free_llm_ask     ask a free model (routing-aware; tells you which model served)
    free_llm_panel   ask N free models in parallel and compare — a free second opinion
    tokenmax         🌈 blast the prompt to a swarm of models; you synthesize them all
    free_llm_route   explain where a prompt WOULD route (difficulty + ranked models), $0
    free_llm_models  list available provider/model ids
    free_llm_quota   today's per-provider usage + daily-limit headroom
    free_llm_stats   lifetime tokens served free + estimated cost avoided

Implemented on the standard library only — no MCP SDK required.
"""

from __future__ import annotations

import concurrent.futures as _cf
import json
import sys
import threading
import time

from .config import resolve_alias
from .router import Pool
from .tokenmax import HARD_CAP, RAINBOW_BANNER, RainbowThrob, fan_out, select_targets

_DEFAULT_PROTOCOL = "2025-06-18"
_ROUTING_MODES = ("fair", "fast", "quality", "legacy", "model", "model-fast")
_MAX_PANEL = 5

# Returned in the `initialize` handshake (MCP's standard `instructions` field) so the
# calling agent learns HOW to invoke these tools — chiefly: call them directly instead
# of shelling out to the CLI, which is what hides the live progress + banner from the user.
_SERVER_INSTRUCTIONS = (
    "freellmpool pools many free-tier LLMs behind these tools. Offload self-contained "
    "subtasks (drafting, summarizing, classifying, quick lookups) to free models instead "
    "of spending your own context/quota.\n\n"
    "INVOKE THESE AS MCP TOOLS DIRECTLY. Do NOT shell out to the `freellmpool` CLI (e.g. "
    "spawning `freellmpool mcp` or `freellmpool tokenmax` as a subprocess) to reach them — "
    "that captures the output in your subprocess and hides the live progress, the rainbow "
    "banner, and the answers from the user.\n\n"
    "`tokenmax` streams live `notifications/progress` as each model in the swarm answers "
    "(e.g. `🌈 TOKENMAXXING ▸ 47/168 models…`); call it directly so the client shows that to "
    "the user in real time, and the result carries a rainbow banner plus every answer for YOU "
    "to synthesize. The flashing rainbow ANSI animation can only render on a real terminal "
    "(not inside an MCP chat), so to let the HUMAN watch it pulse, tell them to run "
    '`freellmpool tokenmax "<prompt>"` in their own terminal.'
)

TOOLS = [
    {
        "name": "free_llm_ask",
        "description": (
            "Ask a free LLM (pooled across 16 free providers, with automatic failover). "
            "Offload a self-contained subtask — drafting, summarizing, classifying, "
            "brainstorming, a quick lookup — to a free model. The reply tells you which "
            "provider/model actually served it."
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
                "routing": {
                    "type": "string",
                    "enum": ["auto", "fast", "quality", "fair"],
                    "description": "How to pick the model: quality (best capable model for the prompt), fast (lowest latency), fair (spread quota), or auto (server default).",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Max output tokens (default 1024).",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "free_llm_panel",
        "description": (
            "Ask the SAME prompt to several different free models at once and get every "
            "answer back side by side — a free 'second opinion' / ensemble. Great for "
            "cross-checking a fact, comparing approaches, or reducing single-model bias. "
            "Optionally have a strong model synthesize the best combined answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The question or task to ask every model.",
                },
                "system": {"type": "string", "description": "Optional system instruction."},
                "n": {
                    "type": "integer",
                    "description": f"How many distinct models to ask (2-{_MAX_PANEL}, default 3).",
                },
                "synthesize": {
                    "type": "boolean",
                    "description": "If true, a quality-routed model synthesizes the panel into one best answer.",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Max output tokens per model (default 512).",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "tokenmax",
        "description": (
            "🌈 TOKENMAX 🌈 — gloriously excessive: fan the SAME prompt out to EVERY available "
            "model across EVERY configured provider at once (a deliberate maximum-effort stress "
            "test), then YOU (the calling model) synthesize the single best answer from all of "
            "them. Maximum free tokens, maximum cross-checking. Tongue-in-cheek, but genuinely "
            "useful for the hardest questions where you want every model's take. "
            "Call this tool DIRECTLY (your client receives live `🌈 TOKENMAXXING ▸ N/total` "
            "progress as each model answers) — do NOT shell out to the CLI, which hides that "
            "from the user. To let the human watch the flashing rainbow, suggest they run "
            '`freellmpool tokenmax "<prompt>"` in their own terminal.'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt to blast to every model."},
                "system": {"type": "string", "description": "Optional system instruction."},
                "max_models": {
                    "type": "integer",
                    "description": f"Optional cap on how many models to hit (default: ALL of them; hard max {HARD_CAP}).",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Max output tokens per model (default 400).",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "free_llm_route",
        "description": (
            "Explain where a prompt WOULD be routed without spending a single token: the "
            "estimated difficulty and the ranked list of candidate models (with capability "
            "scores) for the chosen routing mode. Use it to understand or debug routing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt to analyze."},
                "routing": {
                    "type": "string",
                    "enum": ["auto", "fast", "quality", "fair"],
                    "description": "Routing mode to explain (default: the server's mode).",
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
    {
        "name": "free_llm_stats",
        "description": (
            "Show freellmpool's LIFETIME totals (persisted across restarts): tokens served "
            "free, requests, and estimated cost avoided vs Claude Opus 4.8 — the number that keeps growing."
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


def _routing_arg(value) -> str | None:
    """Map the tool's routing arg to a pool routing override (auto/unknown -> None)."""
    return value if isinstance(value, str) and value in _ROUTING_MODES else None


def _messages(system, prompt: str) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    if isinstance(system, str) and system.strip():
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _max_tokens(value, default: int) -> int:
    return _clamp_int(value, default, 1, 8192)


def _resolve_model(model, env) -> tuple[list[str] | None, str | None]:
    """Resolve a model arg to (providers, model) filters, honoring aliases."""
    if not (isinstance(model, str) and model):
        return None, None
    model = resolve_alias(model, env)
    if model == "auto":
        return None, None
    if "/" in model:
        p, _, m = model.partition("/")
        return [p], m
    return None, model


def _call_tool(pool: Pool, params: dict, notify=None) -> dict:
    name = params.get("name")
    args = params.get("arguments") or {}
    if name == "free_llm_ask":
        return _tool_ask(pool, args)
    if name == "free_llm_panel":
        return _tool_panel(pool, args)
    if name == "tokenmax":
        return _tool_tokenmax(pool, args, notify=notify)
    if name == "free_llm_route":
        return _tool_route(pool, args)
    if name == "free_llm_models":
        ids = [f"{p.id}/{m.name}" for p in pool.providers for m in p.models if m.enabled]
        return _text("\n".join(ids) or "no providers configured")
    if name == "free_llm_quota":
        return _text(_quota_summary(pool))
    if name == "free_llm_stats":
        return _text(_lifetime_summary(pool))
    return _text(f"unknown tool: {name}", is_error=True)


def _tool_ask(pool: Pool, args: dict) -> dict:
    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return _text("'prompt' is required", is_error=True)
    provider = args.get("provider")
    providers = [provider] if provider else None
    p_filter, model = _resolve_model(args.get("model"), pool.env)
    if p_filter is not None:
        providers = p_filter
    routing = _routing_arg(args.get("routing"))
    started = time.monotonic()
    try:
        reply = pool.chat(
            _messages(args.get("system"), prompt),
            model=model,
            providers=providers,
            routing=routing,
            max_tokens=_max_tokens(args.get("max_tokens"), 1024),
        )
    except Exception as exc:  # noqa: BLE001 — surface as a tool error
        return _text(f"{type(exc).__name__}: {exc}", is_error=True)
    ms = round((time.monotonic() - started) * 1000)
    tag = "cache" if reply.cached else f"{ms}ms"
    return _text(f"{reply.text}\n\n— via {reply.provider_id}/{reply.model} ({tag})")


def _tool_panel(pool: Pool, args: dict) -> dict:
    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return _text("'prompt' is required", is_error=True)
    n = _clamp_int(args.get("n"), 3, 2, _MAX_PANEL)
    max_tokens = _max_tokens(args.get("max_tokens"), 512)
    msgs = _messages(args.get("system"), prompt)
    # Pick the top N candidates across DISTINCT providers for diverse opinions.
    picks, seen = [], set()
    for t in pool.rank_targets(msgs, routing="quality"):
        if t.provider.id in seen:
            continue
        seen.add(t.provider.id)
        picks.append(t)
        if len(picks) >= n:
            break
    if not picks:
        return _text("no providers configured", is_error=True)

    def ask_one(t):
        started = time.monotonic()
        try:
            r = pool.chat(msgs, model=t.model, providers=[t.provider.id], max_tokens=max_tokens)
            return (
                f"{r.provider_id}/{r.model}",
                r.text,
                round((time.monotonic() - started) * 1000),
                None,
            )
        except Exception as exc:  # noqa: BLE001
            return (f"{t.provider.id}/{t.model}", None, 0, f"{type(exc).__name__}: {exc}")

    with _cf.ThreadPoolExecutor(max_workers=len(picks)) as ex:
        results = list(ex.map(ask_one, picks))

    out = [f'freellmpool panel — {len(results)} free models on: "{prompt[:70]}"', ""]
    answers = []
    for label, text, ms, err in results:
        if err:
            out.append(f"### {label}  (failed)\n{err}\n")
        else:
            answers.append((label, text))
            out.append(f"### {label}  ({ms}ms)\n{text}\n")

    if args.get("synthesize") and answers:
        blob = "\n\n".join(f"[{lbl}]\n{txt}" for lbl, txt in answers)
        syn_prompt = (
            "Below are several models' answers to the same question. Synthesize the single "
            f"best, correct, concise answer, resolving any disagreements.\n\nQuestion: {prompt}\n\n{blob}"
        )
        try:
            syn = pool.chat(
                _messages(None, syn_prompt), routing="quality", max_tokens=max(max_tokens, 1024)
            )
            out.append(f"### synthesis — via {syn.provider_id}/{syn.model}\n{syn.text}")
        except Exception as exc:  # noqa: BLE001
            out.append(f"### synthesis (failed)\n{type(exc).__name__}: {exc}")
    return _text("\n".join(out))


def _tool_tokenmax(pool: Pool, args: dict, notify=None) -> dict:
    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return _text("'prompt' is required", is_error=True)
    max_tokens = _max_tokens(args.get("max_tokens"), 350)
    msgs = _messages(args.get("system"), prompt)
    picks, n_providers = select_targets(pool, msgs, args.get("max_models"))
    if not picks:
        return _text("no providers configured", is_error=True)

    # Live progress for hosts that support it (Claude Code shows the message ticking
    # up). Raw ANSI can't animate inside an MCP chat, so this is the "it's alive" signal.
    def progress(done: int, total: int, _label: str) -> None:
        if notify is not None:
            notify(done, total, f"🌈 TOKENMAXXING ▸ {done}/{total} models")

    with RainbowThrob(f"TOKENMAXXING {len(picks)} models across {n_providers} providers"):
        answered, failed = fan_out(pool, msgs, picks, max_tokens=max_tokens, progress=progress)

    head = [
        f"{RAINBOW_BANNER} TOKENMAX — blasted your prompt to {len(picks)} models across "
        f"{n_providers} providers; {len(answered)} answered, {len(failed)} unavailable. "
        f"{RAINBOW_BANNER}",
        "Synthesize the single best, correct answer from every response below "
        "(weigh agreement, discard outliers):",
        "",
    ]
    body = [f"### {lbl}\n{txt}\n" for lbl, txt in answered]
    if failed:
        shown = ", ".join(failed[:30]) + ("…" if len(failed) > 30 else "")
        body.append(f"_{len(failed)} unavailable (rate-limited / errored): {shown}_")
    return _text("\n".join(head + body))


def _tool_route(pool: Pool, args: dict) -> dict:
    from .capability import capability_table, model_capability, prompt_difficulty

    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return _text("'prompt' is required", is_error=True)
    routing = _routing_arg(args.get("routing")) or pool.routing
    msgs = _messages(None, prompt)
    difficulty = prompt_difficulty(msgs)
    targets = pool.rank_targets(msgs, routing=routing)
    table = capability_table()
    lines = [
        f"routing mode: {routing}",
        f"estimated prompt difficulty: {difficulty:.2f}  (0 = trivial, 1 = hardest)",
        "",
        f"top candidates (in failover order){' — strongest-fit first' if routing == 'quality' else ''}:",
    ]
    for i, t in enumerate(targets[:8], 1):
        cap = model_capability(t.model, table)
        lines.append(f"  {i:>2}. {t.provider.id}/{t.model}  (capability {cap:.2f})")
    if not targets:
        lines.append("  (no configured candidates)")
    return _text("\n".join(lines))


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

    s = pool.stats_snapshot()
    lines += [
        "",
        f"session: {s.get('requests', 0)} requests, {s.get('cache_hits', 0)} cache hits, "
        f"{s.get('completion_tokens', 0)} output tokens",
        f"cost avoided vs Claude Opus 4.8: ~${usd_saved(s.get('prompt_tokens'), s.get('completion_tokens')):.4f}",
    ]
    return "\n".join(lines)


def _lifetime_summary(pool: Pool) -> str:
    from .savings import usd_saved

    life = pool.lifetime_stats()
    tokens = int(life.get("prompt_tokens", 0)) + int(life.get("completion_tokens", 0))
    saved = usd_saved(life.get("prompt_tokens"), life.get("completion_tokens"))
    lines = [
        "freellmpool — served free (lifetime):",
        f"  requests:   {life.get('requests', 0):,}",
        f"  tokens:     {tokens:,}",
        f"  cache hits: {life.get('cache_hits', 0):,}",
        f"  cost avoided vs Claude Opus 4.8: ~${saved:,.2f}"
        if saved >= 1
        else f"  cost avoided vs Claude Opus 4.8: ~${saved:.4f}",
    ]
    if life.get("first_seen"):
        lines.append(f"  since: {life['first_seen']}")
    return "\n".join(lines)


def _make_notify(params: dict, send_notification):
    """Build a progress callback that emits MCP `notifications/progress`, but only
    when the client supplied a progressToken (per the MCP spec) and we have a
    channel to send on. Otherwise return None so the tool runs silently."""
    if send_notification is None:
        return None
    token = (params.get("_meta") or {}).get("progressToken")
    if token is None:
        return None

    def notify(progress: int, total: int, message: str) -> None:
        send_notification(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": token,
                    "progress": progress,
                    "total": total,
                    "message": message,
                },
            }
        )

    return notify


def handle_message(
    pool: Pool, msg: dict, *, version: str = "0.0.0", send_notification=None
) -> dict | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for
    notifications (which get no reply). `send_notification`, if given, is a
    callback the server can use to emit out-of-band notifications (e.g. progress)
    while a tool is still running."""
    if not isinstance(msg, dict):
        return _error(None, -32600, "invalid request: not a JSON-RPC object")
    if "method" not in msg or not isinstance(msg["method"], str):
        # A request (has id) without a valid method is an invalid request; a
        # notification (no id) we simply drop.
        return _error(msg["id"], -32600, "invalid request: missing method") if "id" in msg else None
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
                    "instructions": _SERVER_INSTRUCTIONS,
                },
            )
        if method == "ping":
            return _result(mid, {})
        if method == "tools/list":
            return _result(mid, {"tools": TOOLS})
        if method == "tools/call":
            params = msg.get("params") or {}
            notify = _make_notify(params, send_notification)
            return _result(mid, _call_tool(pool, params, notify=notify))
        return _error(mid, -32601, f"method not found: {method}")
    except Exception as exc:  # noqa: BLE001 — never crash the loop
        return _error(mid, -32603, f"{type(exc).__name__}: {exc}")


def serve_stdio(pool: Pool, version: str = "0.0.0") -> None:
    """Run the MCP server over stdio until stdin closes."""
    out = sys.stdout
    # A lock guards every write so progress notifications emitted from tokenmax's
    # worker threads can't interleave mid-line with the final response.
    #
    # Deadlock-safety invariant: the lock is only ever held for the duration of a
    # single write_obj() call. handle_message() (which runs the tool's fan-out and
    # all of its worker-thread progress notifications) is fully evaluated BEFORE
    # emit()/write_obj() acquires the lock — so the main thread never holds the lock
    # while workers are trying to acquire it. Do not move write_obj() to wrap a
    # handle_message() call, or the workers' notifications would deadlock.
    write_lock = threading.Lock()

    def write_obj(obj) -> None:
        with write_lock:
            out.write(json.dumps(obj) + "\n")
            out.flush()

    def emit(resp) -> None:
        if resp is not None:
            write_obj(resp)

    def send_notification(obj) -> None:
        try:  # best-effort; a failed progress ping must never abort the tool
            write_obj(obj)
        except Exception:  # noqa: BLE001
            pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            emit(_error(None, -32700, "parse error: invalid JSON"))
            continue
        if isinstance(msg, list):  # JSON-RPC batch
            if not msg:
                emit(_error(None, -32600, "invalid request: empty batch"))
                continue
            responses = [
                r
                for r in (
                    handle_message(pool, m, version=version, send_notification=send_notification)
                    for m in msg
                )
                if r
            ]
            # JSON-RPC 2.0: a batch gets a single response that is an array of the
            # individual responses (omitting notifications). All-notifications → no reply.
            if responses:
                write_obj(responses)
            continue
        emit(handle_message(pool, msg, version=version, send_notification=send_notification))
