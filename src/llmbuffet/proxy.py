"""A tiny OpenAI-compatible HTTP proxy backed by the Buffet.

Run it, point any OpenAI-SDK app at it, and your existing code transparently
load-balances and fails over across every free provider you have keys for:

    $ llmbuffet proxy --port 8080
    $ export OPENAI_BASE_URL=http://localhost:8080/v1
    $ export OPENAI_API_KEY=anything   # ignored by llmbuffet

Implemented on the standard library only (``http.server``) so installing
llmbuffet pulls in nothing beyond httpx.

Supported routes:
    GET  /v1/models                 list available (provider/model) ids
    POST /v1/chat/completions       route a chat completion
    GET  /healthz                   liveness probe
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .errors import AllProvidersExhausted, BuffetError, NoProvidersConfigured
from .router import Buffet


def _model_ids(buffet: Buffet) -> list[str]:
    ids = ["auto"]
    for provider in buffet.providers:
        for m in provider.models:
            ids.append(f"{provider.id}/{m.name}")
    return ids


def make_handler(buffet: Buffet):
    class Handler(BaseHTTPRequestHandler):
        server_version = "llmbuffet/0.1"

        # quiet by default; the server prints its own concise log line
        def log_message(self, format, *args):  # noqa: A002
            return

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, message: str, code: str = "llmbuffet_error") -> None:
            self._send(status, {"error": {"message": message, "type": code}})

        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") == "/healthz":
                self._send(200, {"status": "ok"})
                return
            if self.path.rstrip("/").endswith("/v1/models") or self.path.rstrip("/") == "/models":
                data = [
                    {"id": mid, "object": "model", "owned_by": "llmbuffet"}
                    for mid in _model_ids(buffet)
                ]
                self._send(200, {"object": "list", "data": data})
                return
            self._error(404, f"unknown route {self.path}", "not_found")

        def do_POST(self) -> None:  # noqa: N802
            route = self.path.rstrip("/")
            if not (route.endswith("/v1/chat/completions") or route == "/chat/completions"):
                self._error(404, f"unknown route {self.path}", "not_found")
                return

            length = int(self.headers.get("Content-Length", 0) or 0)
            try:
                raw = self.rfile.read(length) if length else b"{}"
                req = json.loads(raw or b"{}")
            except (json.JSONDecodeError, ValueError):
                self._error(400, "invalid JSON body", "invalid_request_error")
                return

            messages = req.get("messages")
            if not isinstance(messages, list) or not messages:
                self._error(400, "'messages' must be a non-empty array", "invalid_request_error")
                return

            requested = req.get("model") or "auto"
            provider_filter, model_filter = _parse_model(
                requested, {p.id for p in buffet.providers}
            )
            max_tokens = int(req.get("max_tokens") or 1024)
            temperature = float(
                req.get("temperature") if req.get("temperature") is not None else 0.0
            )

            try:
                reply = buffet.chat(
                    [{"role": m.get("role", "user"), "content": _content(m)} for m in messages],
                    model=model_filter,
                    providers=provider_filter,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except NoProvidersConfigured as exc:
                self._error(503, str(exc), "no_providers")
                return
            except AllProvidersExhausted as exc:
                self._error(502, str(exc), "all_providers_exhausted")
                return
            except BuffetError as exc:  # pragma: no cover - defensive
                self._error(500, str(exc), "llmbuffet_error")
                return

            if req.get("stream"):
                self._send_sse(reply)
            else:
                self._send(200, _to_openai_response(reply))

        def _send_sse(self, reply) -> None:
            """Emit the completion as an OpenAI-style SSE stream.

            This is a *buffered* stream: llmbuffet resolves the full completion
            (with failover) first, then frames it as Server-Sent Events so that
            clients which require ``stream: true`` work unchanged.
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for chunk in _sse_chunks(reply):
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
                pass

    return Handler


def _parse_model(requested: str, provider_ids: set[str]):
    """Map an OpenAI 'model' field to (provider_filter, model_filter).

    "auto"                  -> (None, None)        any provider/model
    "groq"                  -> (["groq"], None)    any model on groq
    "groq/llama-3.1-8b"     -> (["groq"], "llama-3.1-8b")
    "llama-3.3-70b"         -> (None, "llama-3.3-70b")  model on any provider
    """
    if not requested or requested == "auto":
        return None, None
    if "/" in requested:
        provider, _, model = requested.partition("/")
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


def _to_openai_response(reply) -> dict:
    return {
        "id": f"chatcmpl-llmbuffet-{reply.provider_id}",
        "object": "chat.completion",
        "model": f"{reply.provider_id}/{reply.model}",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply.text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": reply.prompt_tokens or 0,
            "completion_tokens": reply.completion_tokens or 0,
            "total_tokens": (reply.prompt_tokens or 0) + (reply.completion_tokens or 0),
        },
        "x_llmbuffet": {"provider": reply.provider_id, "model": reply.model},
    }


def _sse_chunks(reply):
    """Yield OpenAI chat.completion.chunk dicts for a finished reply."""
    cid = f"chatcmpl-llmbuffet-{reply.provider_id}"
    model = f"{reply.provider_id}/{reply.model}"
    base = {"id": cid, "object": "chat.completion.chunk", "model": model}
    # role delta, then the content as one delta, then a stop chunk.
    yield {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    yield {
        **base,
        "choices": [{"index": 0, "delta": {"content": reply.text}, "finish_reason": None}],
    }
    yield {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}


def serve(buffet: Buffet, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    handler = make_handler(buffet)
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd
