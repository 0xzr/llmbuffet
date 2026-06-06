"""HTTP client and per-adapter request/response shaping.

Three adapters cover every provider in the catalog:

* ``openai``     — standard ``/chat/completions`` (Groq, Cerebras, OpenRouter,
                   GitHub Models, Mistral, Cohere, SambaNova, ...).
* ``cloudflare`` — Cloudflare Workers AI, which exposes an OpenAI-compatible
                   route once ``{account_id}`` is substituted into the URL.
* ``gemini``     — Google Generative Language API (different body shape).

All network access goes through a single injectable ``post`` callable so the
router and adapters can be unit-tested without touching the network.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .errors import ProviderHTTPError
from .models import EmbedReply, Provider, Reply

Message = dict[str, str]

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
# Reasoning models burn output budget on hidden reasoning; give them headroom
# if the caller left max_tokens at a small default.
_THINKING_HINTS = (
    "glm-4.7",
    "-r1",
    "reasoning",
    "thinking",
    "magistral",
    "deepseek-r1",
    "nemotron",
    "gpt-oss",  # emits reasoning; needs token headroom or content comes back empty
)
_THINKING_FLOOR = 4096  # room for reasoning, but under caps like Groq's gpt-oss limit


def _is_thinking(model: str) -> bool:
    m = model.lower()
    return any(h in m for h in _THINKING_HINTS)


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


@dataclass
class HTTPResult:
    status: int
    body: dict
    text: str


PostFn = Callable[[str, dict, dict, float], HTTPResult]
# A streaming transport returns (status, iterable-of-SSE-lines). The iterable
# keeps the connection open until exhausted/closed.
from collections.abc import Iterable, Iterator  # noqa: E402

StreamPostFn = Callable[[str, dict, dict, float], "tuple[int, Iterable[str]]"]

_USER_AGENT = "freellmpool/0.11 (+https://github.com/0xzr/freellmpool)"

_CONNECT_TIMEOUT = 10.0  # fail fast on dead/unreachable providers so failover is quick
_shared = None  # one pooled, keep-alive httpx.Client shared across calls/threads
_shared_lock = threading.Lock()


def _client():
    """A process-wide pooled httpx.Client. Reusing connections (keep-alive) avoids
    a TCP+TLS handshake on every request — a big win for repeated calls to the
    same provider (agent loops). httpx.Client is thread-safe."""
    global _shared
    if _shared is None:  # fast path: avoid the lock once initialized
        with _shared_lock:
            if _shared is None:  # double-checked under the threaded proxy
                import atexit

                import httpx

                _shared = httpx.Client(
                    headers={"User-Agent": _USER_AGENT},
                    limits=httpx.Limits(
                        max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0
                    ),
                    follow_redirects=True,
                )
                atexit.register(_shared.close)
    return _shared


def _timeout(timeout: float):
    import httpx

    return httpx.Timeout(timeout, connect=min(_CONNECT_TIMEOUT, timeout))


def default_post(url: str, headers: dict, json_body: dict, timeout: float) -> HTTPResult:
    """Real network POST via the pooled httpx client."""
    resp = _client().post(url, headers=headers, json=json_body, timeout=_timeout(timeout))
    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError):
        body = {}
    return HTTPResult(status=resp.status_code, body=body, text=resp.text)


class _StreamLines:
    """An explicitly-closeable line iterator over a streaming response, so the
    connection is released back to the pool on exhaustion, early close, OR non-200
    (where the caller closes it before ever iterating). Does NOT close the shared
    client — only the response/stream."""

    def __init__(self, cm, resp):
        self._cm, self._resp = cm, resp
        self._closed = False

    def __iter__(self) -> Iterator[str]:
        try:
            yield from self._resp.iter_lines()
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._cm.__exit__(None, None, None)  # releases the connection to the pool
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass


def default_stream_post(url: str, headers: dict, json_body: dict, timeout: float):
    """Open a streaming POST on the pooled client and return (status, line iter)."""
    cm = _client().stream("POST", url, headers=headers, json=json_body, timeout=_timeout(timeout))
    resp = cm.__enter__()
    return resp.status_code, _StreamLines(cm, resp)


def stream_call(
    provider: Provider,
    model: str,
    messages: list[Message],
    *,
    api_key: str | None,
    env: dict[str, str],
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout: float = 90.0,
    stream_post: StreamPostFn = default_stream_post,
) -> Iterator[str]:
    """Stream content deltas from an OpenAI-shape provider.

    Raises :class:`ProviderHTTPError` on the first iteration if the provider did
    not return 200 — so the router can still fail over *before* any bytes are
    sent to the client. Once tokens start flowing there is no mid-stream failover.
    """
    base_url = provider.base_url
    if provider.adapter == "cloudflare":
        base_url = base_url.replace("{account_id}", env.get("CLOUDFLARE_ACCOUNT_ID", ""))
    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    status, line_iter = stream_post(url, headers, body, timeout)
    close = getattr(line_iter, "close", lambda: None)
    if status != 200:
        close()
        raise ProviderHTTPError(status, f"HTTP {status}", retryable=_retryable(status))
    try:
        for line in line_iter:
            if not line:
                continue
            if line.startswith("data:"):
                line = line[len("data:") :]
            line = line.strip()
            if not line or line == "[DONE]":
                if line == "[DONE]":
                    break
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            choices = obj.get("choices") or [{}]
            delta = (choices[0].get("delta") or {}).get("content")
            if delta:
                yield delta
    finally:
        close()


def _retryable(status: int) -> bool:
    # 429 (rate limit) and 5xx are worth trying another provider for.
    # 408 request timeout too. 4xx config errors are not retryable per-call but
    # the router still advances to a different provider regardless.
    return status == 429 or status == 408 or 500 <= status < 600


def _err_message(result: HTTPResult) -> str:
    err = result.body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)
    if isinstance(err, str):
        return err
    return (result.text or "").strip()[:200] or "no body"


def _to_gemini_contents(messages: list[Message]) -> tuple[dict | None, list[dict]]:
    """Split OpenAI-style messages into (systemInstruction, contents)."""
    system: str | None = None
    contents: list[dict] = []
    for msg in messages:
        role = msg.get("role", "user")
        text = msg.get("content", "")
        if role == "system":
            system = f"{system}\n{text}" if system else text
            continue
        gem_role = "model" if role == "assistant" else "user"
        contents.append({"role": gem_role, "parts": [{"text": text}]})
    system_instruction = {"parts": [{"text": system}]} if system else None
    return system_instruction, contents


def _adapter_openai(
    provider,
    model,
    messages,
    *,
    api_key,
    env,
    max_tokens,
    temperature,
    timeout,
    tools,
    tool_choice,
    post,
) -> Reply:
    return _call_openai(
        provider,
        model,
        messages,
        api_key=api_key,
        env=env,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        tools=tools,
        tool_choice=tool_choice,
        post=post,
    )


def _adapter_gemini(
    provider,
    model,
    messages,
    *,
    api_key,
    env,
    max_tokens,
    temperature,
    timeout,
    tools,
    tool_choice,
    post,
) -> Reply:
    # Gemini uses a different tool schema; skip tools for now (the router will
    # fail over to an openai-shape provider that supports them).
    if tools:
        raise ProviderHTTPError(400, "gemini adapter does not support tools", retryable=True)
    return _call_gemini(
        provider,
        model,
        messages,
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        post=post,
    )


# Built-in request/response shapes. Plugins can register more via
# freellmpool.plugins.register_adapter; an unknown adapter name falls back to openai.
_BUILTIN_ADAPTERS = {
    "openai": _adapter_openai,
    "cloudflare": _adapter_openai,  # OpenAI-compatible once {account_id} is filled
    "gemini": _adapter_gemini,
}


def _resolve_adapter(name: str):
    from .plugins import registered_adapters  # lazy: avoids import cycle

    custom = registered_adapters()
    if name in custom:
        return custom[name]
    return _BUILTIN_ADAPTERS.get(name, _adapter_openai)


def call(
    provider: Provider,
    model: str,
    messages: list[Message],
    *,
    api_key: str | None,
    env: dict[str, str],
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout: float = 90.0,
    tools: list | None = None,
    tool_choice=None,
    post: PostFn = default_post,
) -> Reply:
    """Dispatch one completion to ``provider`` and normalize the response.

    Routes through the adapter named by ``provider.adapter`` (built-in or
    plugin-registered). Raises :class:`ProviderHTTPError` on a non-200 status.
    """
    if _is_thinking(model) and max_tokens < _THINKING_FLOOR:
        # Give reasoning models room so hidden reasoning doesn't eat the whole
        # budget and return empty content.
        max_tokens = _THINKING_FLOOR
    adapter = _resolve_adapter(provider.adapter)
    return adapter(
        provider,
        model,
        messages,
        api_key=api_key,
        env=env,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        tools=tools,
        tool_choice=tool_choice,
        post=post,
    )


def _call_openai(
    provider: Provider,
    model: str,
    messages: list[Message],
    *,
    api_key: str | None,
    env: dict[str, str],
    max_tokens: int,
    temperature: float,
    timeout: float,
    tools: list | None = None,
    tool_choice=None,
    post: PostFn,
) -> Reply:
    base_url = provider.base_url
    if provider.adapter == "cloudflare":
        account_id = env.get("CLOUDFLARE_ACCOUNT_ID", "")
        base_url = base_url.replace("{account_id}", account_id)

    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:  # keyless providers (e.g. OVH anonymous) send no auth header
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if tools:  # function/tool calling — passed through to providers that support it
        body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
    result = post(url, headers, body, timeout)
    if result.status != 200:
        raise ProviderHTTPError(
            result.status, _err_message(result), retryable=_retryable(result.status)
        )

    choices = result.body.get("choices") or []
    if not choices:
        raise ProviderHTTPError(502, "no choices in response", retryable=True)
    message = choices[0].get("message") or {}
    text = _strip_think(message.get("content") or "")
    usage = result.body.get("usage") or {}
    return Reply(
        text=text,
        provider_id=provider.id,
        model=model,
        raw=result.body,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        message=message if isinstance(message, dict) else None,
    )


def embed(
    provider: Provider,
    model: str,
    inputs: list[str],
    *,
    api_key: str | None,
    env: dict[str, str],
    timeout: float = 90.0,
    post: PostFn = default_post,
) -> EmbedReply:
    """Dispatch an embeddings request (OpenAI ``/embeddings`` shape)."""
    base_url = provider.base_url
    if provider.adapter == "cloudflare" or "{account_id}" in base_url:
        base_url = base_url.replace("{account_id}", env.get("CLOUDFLARE_ACCOUNT_ID", ""))
    url = f"{base_url}/embeddings"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {"model": model, "input": inputs, "encoding_format": "float"}
    result = post(url, headers, body, timeout)
    if result.status != 200:
        raise ProviderHTTPError(
            result.status, _err_message(result), retryable=_retryable(result.status)
        )
    data = result.body.get("data") or []
    if not data:
        raise ProviderHTTPError(502, "no embeddings in response", retryable=True)
    vectors = [row.get("embedding") or [] for row in data]
    if not all(vectors):
        raise ProviderHTTPError(502, "empty embedding vector", retryable=True)
    usage = result.body.get("usage") or {}
    return EmbedReply(
        vectors=vectors,
        provider_id=provider.id,
        model=model,
        prompt_tokens=usage.get("prompt_tokens"),
    )


def _call_gemini(
    provider: Provider,
    model: str,
    messages: list[Message],
    *,
    api_key: str | None,
    max_tokens: int,
    temperature: float,
    timeout: float,
    post: PostFn,
) -> Reply:
    system_instruction, contents = _to_gemini_contents(messages)
    url = f"{provider.base_url}/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    body: dict = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system_instruction:
        body["systemInstruction"] = system_instruction

    result = post(url, headers, body, timeout)
    if result.status != 200:
        raise ProviderHTTPError(
            result.status, _err_message(result), retryable=_retryable(result.status)
        )

    candidates = result.body.get("candidates") or []
    if not candidates:
        raise ProviderHTTPError(502, "no candidates in response", retryable=True)
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = _strip_think("".join(p.get("text", "") for p in parts))
    usage = result.body.get("usageMetadata") or {}
    return Reply(
        text=text,
        provider_id=provider.id,
        model=model,
        raw=result.body,
        prompt_tokens=usage.get("promptTokenCount"),
        completion_tokens=usage.get("candidatesTokenCount"),
    )
