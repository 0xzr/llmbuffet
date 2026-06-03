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
from collections.abc import Callable
from dataclasses import dataclass

from .errors import ProviderHTTPError
from .models import Provider, Reply

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
)
_THINKING_FLOOR = 8192


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

_USER_AGENT = "freellmpool/0.3 (+https://github.com/0xzr/freellmpool)"


def default_post(url: str, headers: dict, json_body: dict, timeout: float) -> HTTPResult:
    """Real network POST via httpx. Imported lazily so tests need no httpx."""
    import httpx

    headers = {"User-Agent": _USER_AGENT, **headers}
    resp = httpx.post(url, headers=headers, json=json_body, timeout=timeout)
    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError):
        body = {}
    return HTTPResult(status=resp.status_code, body=body, text=resp.text)


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
    post: PostFn = default_post,
) -> Reply:
    """Dispatch one completion to ``provider`` and normalize the response.

    Raises :class:`ProviderHTTPError` on a non-200 status.
    """
    if _is_thinking(model) and max_tokens < _THINKING_FLOOR:
        # Give reasoning models room so hidden reasoning doesn't eat the whole
        # budget and return empty content.
        max_tokens = _THINKING_FLOOR
    if provider.adapter == "gemini":
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
    # openai + cloudflare share the chat/completions shape.
    return _call_openai(
        provider,
        model,
        messages,
        api_key=api_key,
        env=env,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
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
