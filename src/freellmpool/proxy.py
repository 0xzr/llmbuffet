"""A tiny OpenAI-compatible HTTP proxy backed by the Pool.

Run it, point any OpenAI-SDK app at it, and your existing code transparently
load-balances and fails over across every free provider you have keys for:

    $ freellmpool proxy --port 8080
    $ export OPENAI_BASE_URL=http://localhost:8080/v1
    $ export OPENAI_API_KEY=anything   # ignored by freellmpool

Implemented on the standard library only (``http.server``) so installing
freellmpool pulls in nothing beyond httpx.

Supported routes:
    GET  /v1/models                 list available (provider/model) ids
    POST /v1/chat/completions       route a chat completion (true token streaming)
    POST /v1/embeddings             pooled free embeddings
    POST /v1/responses              Responses API shim (Codex CLI / agents)
    POST /v1/messages               Anthropic Messages shim (Claude Code / agents)
    GET  /healthz                   liveness probe
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .anthropic_shim import estimate_tokens, reply_to_message, reply_to_sse, request_to_chat
from .config import resolve_alias
from .errors import AllProvidersExhausted, BuffetError, NoProvidersConfigured
from .router import Pool

_MAX_BODY = 16 * 1024 * 1024  # 16 MB cap on request bodies


def _model_ids(pool: Pool) -> list[str]:
    ids = ["auto"]
    for provider in pool.providers:
        for m in provider.models:
            if m.enabled:
                ids.append(f"{provider.id}/{m.name}")
    return ids


def make_handler(pool: Pool, api_key: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "freellmpool/0.9"

        # quiet by default; the server prints its own concise log line
        def log_message(self, format, *args):  # noqa: A002
            return

        def _send(self, status: int, payload: dict, headers: dict | None = None) -> None:
            data = json.dumps(payload).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in (headers or {}).items():
                    self.send_header(key, str(value))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):  # client went away
                pass

        def _error(self, status: int, message: str, code: str = "freellmpool_error") -> None:
            self._send(status, {"error": {"message": message, "type": code}})

        def _authorized(self) -> bool:
            """If a proxy key is configured, require a matching Bearer token
            (OpenAI style) or x-api-key (Anthropic style)."""
            if not api_key:
                return True
            if self.headers.get("Authorization", "") == f"Bearer {api_key}":
                return True
            return self.headers.get("x-api-key", "") == api_key

        def do_GET(self) -> None:  # noqa: N802
            try:
                self._do_get()
            except Exception as exc:  # never let a request kill the thread
                self._error(500, f"internal error: {type(exc).__name__}", "internal_error")

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._do_post()
            except Exception as exc:  # never let a request kill the thread
                self._error(500, f"internal error: {type(exc).__name__}", "internal_error")

        def _do_get(self) -> None:
            if self.path.rstrip("/") == "/healthz":
                self._send(200, {"status": "ok"})
                return
            # /dashboard and /v1/models leak inventory/usage, so gate them behind
            # the proxy key when one is configured.
            if not self._authorized():
                self._error(401, "invalid or missing API key", "invalid_api_key")
                return
            if self.path.rstrip("/") in ("/dashboard", "/"):
                html = _dashboard_html(pool).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            if self.path.rstrip("/").endswith("/v1/models") or self.path.rstrip("/") == "/models":
                data = [
                    {"id": mid, "object": "model", "owned_by": "freellmpool"}
                    for mid in _model_ids(pool)
                ]
                self._send(200, {"object": "list", "data": data})
                return
            self._error(404, f"unknown route {self.path}", "not_found")

        def _do_post(self) -> None:
            route = self.path.rstrip("/")
            is_chat = route.endswith("/v1/chat/completions") or route == "/chat/completions"
            is_responses = route.endswith("/v1/responses") or route == "/responses"
            is_embeddings = route.endswith("/v1/embeddings") or route == "/embeddings"
            is_count = route.endswith("/v1/messages/count_tokens")
            is_messages = not is_count and (route.endswith("/v1/messages") or route == "/messages")
            if not (is_chat or is_responses or is_embeddings or is_messages or is_count):
                self._error(404, f"unknown route {self.path}", "not_found")
                return
            if not self._authorized():
                self._error(401, "invalid or missing API key", "invalid_api_key")
                return

            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except (TypeError, ValueError):
                self._error(400, "invalid Content-Length header", "invalid_request_error")
                return
            if length < 0:
                self._error(400, "invalid Content-Length header", "invalid_request_error")
                return
            if length > _MAX_BODY:
                self._error(413, "request body too large", "invalid_request_error")
                return
            try:
                raw = self.rfile.read(length) if length else b"{}"
                req = json.loads(raw or b"{}")
            except (json.JSONDecodeError, ValueError):
                self._error(400, "invalid JSON body", "invalid_request_error")
                return
            if not isinstance(req, dict):
                self._error(400, "request body must be a JSON object", "invalid_request_error")
                return

            if is_embeddings:
                self._handle_embeddings(req)
            elif is_responses:
                self._handle_responses(req)
            elif is_count:
                self._send(200, {"input_tokens": estimate_tokens(req)})
            elif is_messages:
                self._handle_messages(req)
            else:
                self._handle_chat(req)

        def _handle_messages(self, req: dict) -> None:
            """Anthropic Messages API shim — lets Claude Code & friends use free models."""
            chat = request_to_chat(req)
            display_model = req.get("model") or "auto"
            resolved = resolve_alias(str(chat["model"]), pool.env)
            provider_filter, model_filter = _parse_model(resolved, {p.id for p in pool.providers})
            try:
                reply = pool.chat(
                    chat["messages"],
                    model=model_filter,
                    providers=provider_filter,
                    max_tokens=chat["max_tokens"],
                    temperature=chat["temperature"],
                    tools=chat["tools"],
                    tool_choice=chat["tool_choice"],
                )
            except NoProvidersConfigured as exc:
                self._error(503, str(exc), "no_providers")
                return
            except AllProvidersExhausted as exc:
                self._error(502, str(exc), "all_providers_exhausted")
                return
            if req.get("stream"):
                self._send_sse(reply_to_sse(reply, display_model))
            else:
                self._send(200, reply_to_message(reply, display_model))

        def _handle_embeddings(self, req: dict) -> None:
            data = req.get("input")
            if isinstance(data, str):
                inputs = [data]
            elif isinstance(data, list) and all(isinstance(x, str) for x in data):
                inputs = data
            else:
                self._error(
                    400, "'input' must be a string or array of strings", "invalid_request_error"
                )
                return
            if not inputs:
                self._error(400, "'input' is required", "invalid_request_error")
                return
            requested = req.get("model")
            # "auto"/empty/provider-prefixed → let the pool pick any embedder
            if (
                isinstance(requested, str)
                and requested not in ("", "auto")
                and "/" not in requested
            ):
                model = requested
            else:
                model = None
            try:
                reply = pool.embed(inputs, model=model)
            except NoProvidersConfigured as exc:
                self._error(503, str(exc), "no_providers")
                return
            except AllProvidersExhausted as exc:
                self._error(502, str(exc), "all_providers_exhausted")
                return
            self._send(200, _to_embeddings_response(reply))

        def _resolve(self, req: dict, messages: list[dict], *, tools=None, tool_choice=None):
            """Shared: resolve model/params and call the pool. Returns a Reply or
            sends an error response and returns None."""
            requested = req.get("model") or "auto"
            if not isinstance(requested, str):
                self._error(400, "'model' must be a string", "invalid_request_error")
                return None
            requested = resolve_alias(requested, pool.env)  # gpt-4o-mini → free target
            provider_filter, model_filter = _parse_model(requested, {p.id for p in pool.providers})
            try:
                max_tokens = int(req.get("max_tokens") or req.get("max_output_tokens") or 1024)
                temp_raw = req.get("temperature")
                temperature = 0.0 if temp_raw is None else float(temp_raw)
            except (TypeError, ValueError):
                self._error(
                    400, "'max_tokens'/'temperature' must be numbers", "invalid_request_error"
                )
                return None
            try:
                return pool.chat(
                    messages,
                    model=model_filter,
                    providers=provider_filter,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=tools,
                    tool_choice=tool_choice,
                )
            except NoProvidersConfigured as exc:
                self._error(503, str(exc), "no_providers")
            except AllProvidersExhausted as exc:
                self._error(502, str(exc), "all_providers_exhausted")
            except BuffetError as exc:  # pragma: no cover - defensive
                self._error(500, str(exc), "freellmpool_error")
            return None

        def _handle_chat(self, req: dict) -> None:
            messages = req.get("messages")
            if not isinstance(messages, list) or not messages:
                self._error(400, "'messages' must be a non-empty array", "invalid_request_error")
                return
            if not all(isinstance(m, dict) for m in messages):
                self._error(400, "each message must be an object", "invalid_request_error")
                return
            norm = _normalize_messages(messages)
            tools = req.get("tools") if isinstance(req.get("tools"), list) else None
            # True token streaming for plain chat; tools/stream falls back to buffered.
            if req.get("stream") and not tools:
                self._stream_chat(req, norm)
                return
            reply = self._resolve(req, norm, tools=tools, tool_choice=req.get("tool_choice"))
            if reply is None:
                return
            if req.get("stream"):
                self._send_sse(_sse_chunks(reply))
            else:
                self._send(200, _to_openai_response(reply), headers=_obs_headers(reply))

        def _stream_chat(self, req: dict, norm: list[dict]) -> None:
            requested = req.get("model") or "auto"
            if not isinstance(requested, str):
                self._error(400, "'model' must be a string", "invalid_request_error")
                return
            provider_filter, model_filter = _parse_model(
                resolve_alias(requested, pool.env), {p.id for p in pool.providers}
            )
            try:
                max_tokens = int(req.get("max_tokens") or 1024)
                temp_raw = req.get("temperature")
                temperature = 0.0 if temp_raw is None else float(temp_raw)
            except (TypeError, ValueError):
                self._error(
                    400, "'max_tokens'/'temperature' must be numbers", "invalid_request_error"
                )
                return
            try:
                gen = pool.stream_chat(
                    norm,
                    model=model_filter,
                    providers=provider_filter,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                meta = next(gen)  # provider/model chosen, or raises before any bytes
            except NoProvidersConfigured as exc:
                self._error(503, str(exc), "no_providers")
                return
            except (AllProvidersExhausted, StopIteration):
                # nothing streamable succeeded — fall back to a buffered completion
                reply = self._resolve(req, norm)
                if reply is not None:
                    self._send_sse(_sse_chunks(reply))
                return

            provider_id = meta["provider"] if isinstance(meta, dict) else "auto"
            model_name = meta["model"] if isinstance(meta, dict) else "auto"
            cid = f"chatcmpl-freellmpool-{provider_id}"
            model_id = f"{provider_id}/{model_name}"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(_chunk_block(cid, model_id, role="assistant").encode())
                for delta in gen:
                    self.wfile.write(_chunk_block(cid, model_id, content=delta).encode())
                self.wfile.write(_chunk_block(cid, model_id, finish="stop").encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
                pass  # client disconnected
            finally:
                gen.close()  # release the upstream stream even on early disconnect

        def _handle_responses(self, req: dict) -> None:
            """Minimal OpenAI Responses API (/v1/responses) shim for Codex CLI
            and other Responses-based agents."""
            messages = _responses_input_to_messages(req)
            if not messages:
                self._error(400, "'input' is required", "invalid_request_error")
                return
            reply = self._resolve(req, messages)
            if reply is None:
                return
            if req.get("stream"):
                self._send_sse(_responses_sse_events(reply))
            else:
                self._send(200, _to_responses_object(reply))

        def _send_sse(self, sse_blocks) -> None:
            """Emit pre-formatted SSE blocks as a stream.

            This is a *buffered* stream: freellmpool resolves the full completion
            (with failover) first, then frames it as Server-Sent Events so that
            clients which require ``stream: true`` work unchanged. ``sse_blocks``
            is an iterable of already-encoded SSE strings (chat and Responses use
            different framings).
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for block in sse_blocks:
                    self.wfile.write(block.encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
                pass

    return Handler


def _parse_model(requested: str, provider_ids: set[str]):
    """Map an OpenAI 'model' field to (provider_filter, model_filter).

    "auto"                  -> (None, None)        any provider/model
    "groq"                  -> (["groq"], None)    any model on groq
    "groq/llama-3.1-8b"     -> (["groq"], "llama-3.1-8b")
    "openai/gpt-oss-120b"   -> (None, "openai/gpt-oss-120b")  (openai isn't a provider id;
                               it's a catalog model name that happens to contain '/')
    "llama-3.3-70b"         -> (None, "llama-3.3-70b")  model on any provider
    """
    if not requested or requested == "auto":
        return None, None
    if "/" in requested:
        provider, _, model = requested.partition("/")
        # Only treat as provider/model when the prefix is a real provider id —
        # otherwise it's a bare model name that contains a slash.
        if provider in provider_ids:
            return [provider], model
    if requested in provider_ids:
        return [requested], None
    return None, requested


def _content(message: dict) -> str:
    """Flatten OpenAI content (string or array of parts) into plain text."""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def _normalize_messages(messages: list) -> list[dict]:
    """Flatten content to text while preserving tool-calling fields so multi-turn
    tool conversations (assistant tool_calls + tool results) survive the proxy."""
    out: list[dict] = []
    for m in messages:
        nm: dict = {"role": str(m.get("role", "user")), "content": _content(m)}
        for key in ("tool_calls", "tool_call_id", "name"):
            if m.get(key) is not None:
                nm[key] = m[key]
        out.append(nm)
    return out


def _obs_headers(reply) -> dict:
    return {
        "X-Freellmpool-Provider": reply.provider_id,
        "X-Freellmpool-Model": reply.model,
        "X-Freellmpool-Attempts": reply.attempts,
    }


def _to_embeddings_response(reply) -> dict:
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": vec}
            for i, vec in enumerate(reply.vectors)
        ],
        "model": f"{reply.provider_id}/{reply.model}",
        "usage": {
            "prompt_tokens": reply.prompt_tokens or 0,
            "total_tokens": reply.prompt_tokens or 0,
        },
        "x_freellmpool": {"provider": reply.provider_id, "model": reply.model},
    }


def _to_openai_response(reply) -> dict:
    message = {"role": "assistant", "content": reply.text or None}
    finish = "stop"
    if reply.message and reply.message.get("tool_calls"):
        message["tool_calls"] = reply.message["tool_calls"]
        finish = "tool_calls"
    return {
        "id": f"chatcmpl-freellmpool-{reply.provider_id}",
        "object": "chat.completion",
        "model": f"{reply.provider_id}/{reply.model}",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": reply.prompt_tokens or 0,
            "completion_tokens": reply.completion_tokens or 0,
            "total_tokens": (reply.prompt_tokens or 0) + (reply.completion_tokens or 0),
        },
        "x_freellmpool": {"provider": reply.provider_id, "model": reply.model},
    }


def _dashboard_html(pool) -> str:
    """A self-contained dashboard page (no JS framework, auto-refreshing)."""
    import html as _html

    from . import __version__
    from .savings import usd_saved

    s = pool.stats
    saved = usd_saved(s.get("prompt_tokens"), s.get("completion_tokens"))
    snap = pool.quota.snapshot()
    by_provider: dict[str, int] = {}
    for key, count in snap.items():
        pid = key.split("::", 1)[0]
        by_provider[pid] = by_provider.get(pid, 0) + count

    configured = {p.id for p in pool.providers}
    rows = []
    for p in pool.providers:
        used = by_provider.get(p.id, 0)
        keyless = " · keyless" if p.keyless else ""
        rows.append(
            f"<tr><td>{_html.escape(p.id)}{keyless}</td>"
            f"<td>{len(p.models)}</td><td class=num>{used}</td></tr>"
        )
    other = sorted(pid for pid in by_provider if pid not in configured)
    for pid in other:
        rows.append(
            f"<tr><td>{_html.escape(pid)}</td><td>-</td><td class=num>{by_provider[pid]}</td></tr>"
        )
    provider_rows = "\n".join(rows) or "<tr><td colspan=3>no providers configured</td></tr>"

    cards = [
        ("requests served", str(s.get("requests", 0))),
        ("cache hits", str(s.get("cache_hits", 0))),
        ("tokens out", f"{s.get('completion_tokens', 0):,}"),
        ("not paid to OpenAI", f"${saved:,.2f}"),
    ]
    card_html = "\n".join(
        f"<div class=card><div class=big>{v}</div><div class=lbl>{k}</div></div>" for k, v in cards
    )
    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta http-equiv=refresh content=5><title>freellmpool</title>
<style>
 body{{font-family:ui-sans-serif,system-ui,sans-serif;margin:0;background:#0b0e14;color:#e6e6e6}}
 .wrap{{max-width:760px;margin:0 auto;padding:32px 20px}}
 h1{{font-size:22px;margin:0 0 2px}} .sub{{color:#8a93a2;font-size:13px;margin-bottom:24px}}
 .cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:28px}}
 .card{{background:#141925;border:1px solid #232a39;border-radius:10px;padding:16px;text-align:center}}
 .big{{font-size:26px;font-weight:700}} .lbl{{color:#8a93a2;font-size:11px;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;background:#141925;border:1px solid #232a39;border-radius:10px;overflow:hidden}}
 th,td{{padding:9px 14px;text-align:left;border-bottom:1px solid #232a39;font-size:14px}}
 th{{color:#8a93a2;font-weight:600;font-size:12px}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
 a{{color:#6ea8ff}}
</style></head><body><div class=wrap>
<h1>freellmpool <span style="color:#8a93a2;font-weight:400;font-size:14px">v{__version__}</span></h1>
<div class=sub>{len(pool.providers)} providers configured · today's usage (UTC) · auto-refreshes every 5s</div>
<div class=cards>{card_html}</div>
<table><tr><th>provider</th><th>models</th><th class=num>requests today</th></tr>
{provider_rows}</table>
<p class=sub style="margin-top:20px">OpenAI endpoint: <code>/v1</code> · <a href="https://github.com/0xzr/freellmpool">github.com/0xzr/freellmpool</a></p>
</div></body></html>"""


def _chunk_block(cid: str, model_id: str, *, role=None, content=None, finish=None) -> str:
    delta: dict = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    chunk = {
        "id": cid,
        "object": "chat.completion.chunk",
        "model": model_id,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _sse_chunks(reply):
    """Yield OpenAI chat.completion.chunk SSE blocks for a finished reply."""
    cid = f"chatcmpl-freellmpool-{reply.provider_id}"
    model = f"{reply.provider_id}/{reply.model}"
    base = {"id": cid, "object": "chat.completion.chunk", "model": model}

    def block(chunk):
        return f"data: {json.dumps(chunk)}\n\n"

    yield block(
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    )
    yield block(
        {**base, "choices": [{"index": 0, "delta": {"content": reply.text}, "finish_reason": None}]}
    )
    yield block({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    yield "data: [DONE]\n\n"


# ---- OpenAI Responses API (/v1/responses) shim — for Codex CLI & agents ------


def _responses_input_to_messages(req: dict) -> list[dict]:
    """Convert a Responses request (`instructions` + `input`) to chat messages.

    `input` may be a plain string or a list of items, each with a `role` and
    `content` that is a string or a list of typed parts ({type, text}).
    """
    messages: list[dict] = []
    instructions = req.get("instructions")
    if isinstance(instructions, str) and instructions:
        messages.append({"role": "system", "content": instructions})

    data = req.get("input")
    if isinstance(data, str):
        messages.append({"role": "user", "content": data})
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "user"))
            content = item.get("content", "")
            if isinstance(content, list):
                text = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            else:
                text = str(content)
            messages.append({"role": role, "content": text})
    return messages


def _to_responses_object(reply) -> dict:
    rid = f"resp-freellmpool-{reply.provider_id}"
    return {
        "id": rid,
        "object": "response",
        "status": "completed",
        "model": f"{reply.provider_id}/{reply.model}",
        "output": [
            {
                "type": "message",
                "id": f"msg-{reply.provider_id}",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": reply.text, "annotations": []}],
            }
        ],
        "output_text": reply.text,  # convenience field the OpenAI SDK exposes
        "usage": {
            "input_tokens": reply.prompt_tokens or 0,
            "output_tokens": reply.completion_tokens or 0,
            "total_tokens": (reply.prompt_tokens or 0) + (reply.completion_tokens or 0),
        },
        "x_freellmpool": {"provider": reply.provider_id, "model": reply.model},
    }


def _responses_sse_events(reply):
    """Yield Responses-API SSE blocks (typed events) for a finished reply."""
    obj = _to_responses_object(reply)

    def event(name, payload):
        return f"event: {name}\ndata: {json.dumps(payload)}\n\n"

    yield event(
        "response.created",
        {"type": "response.created", "response": {"id": obj["id"], "status": "in_progress"}},
    )
    yield event(
        "response.output_text.delta", {"type": "response.output_text.delta", "delta": reply.text}
    )
    yield event("response.completed", {"type": "response.completed", "response": obj})


def serve(
    pool: Pool,
    host: str = "127.0.0.1",
    port: int = 8080,
    api_key: str | None = None,
) -> ThreadingHTTPServer:
    """Build the proxy server. If ``api_key`` is set (or ``FREELLMPOOL_PROXY_KEY``
    is in the environment), POSTs must present ``Authorization: Bearer <key>``."""
    if api_key is None:
        api_key = os.environ.get("FREELLMPOOL_PROXY_KEY") or None
    handler = make_handler(pool, api_key)
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd
