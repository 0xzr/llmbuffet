"""Adapter behavior: thinking-model handling, header shaping, stream lifecycle."""

from __future__ import annotations

import json

import pytest
from helpers import make_post, openai_body

from freellmpool import client as C
from freellmpool.errors import ProviderHTTPError
from freellmpool.models import Model, Provider

P = Provider(
    id="x",
    label="X",
    adapter="openai",
    base_url="https://x.test/v1",
    key_env="X_KEY",
    models=(Model("zai-glm-4.7"),),
)


def test_thinking_model_bumps_max_tokens():
    seen = {}

    def post(url, headers, body, timeout):
        seen.update(body)
        return C.HTTPResult(200, openai_body("ok"), "ok")

    C.call(
        P,
        "zai-glm-4.7",
        [{"role": "user", "content": "hi"}],
        api_key="k",
        env={},
        max_tokens=512,
        post=post,
    )
    assert seen["max_tokens"] >= 4096  # reasoning model got headroom


def test_non_thinking_model_keeps_max_tokens():
    seen = {}

    def post(url, headers, body, timeout):
        seen.update(body)
        return C.HTTPResult(200, openai_body("ok"), "ok")

    C.call(
        P,
        "llama-3.1-8b",
        [{"role": "user", "content": "hi"}],
        api_key="k",
        env={},
        max_tokens=512,
        post=post,
    )
    assert seen["max_tokens"] == 512


def test_tools_forwarded_and_tool_calls_preserved():
    tc = [{"id": "call_1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    seen = {}

    def post(url, headers, body, timeout):
        seen.update(body)
        return C.HTTPResult(
            200,
            {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": tc}}]},
            "",
        )

    reply = C.call(
        P,
        "some-model",
        [{"role": "user", "content": "hi"}],
        api_key="k",
        env={},
        tools=[{"type": "function", "function": {"name": "f"}}],
        post=post,
    )
    assert "tools" in seen  # forwarded to the provider
    assert reply.message["tool_calls"] == tc  # preserved on the reply
    assert reply.text == ""


def test_think_tags_stripped():
    post = make_post({"x.test": (200, openai_body("<think>secret reasoning</think>final answer"))})
    reply = C.call(
        P, "zai-glm-4.7", [{"role": "user", "content": "hi"}], api_key="k", env={}, post=post
    )
    assert reply.text == "final answer"


# ---- streaming connection lifecycle (the real _StreamLines.close path) ----


class _SpyLines:
    """A closeable line iterator that records whether close() was called."""

    def __init__(self, lines):
        self._lines = list(lines)
        self.closed = False

    def __iter__(self):
        yield from self._lines

    def close(self):
        self.closed = True


def _sse(*deltas):
    return [f"data: {json.dumps({'choices': [{'delta': {'content': d}}]})}" for d in deltas] + [
        "data: [DONE]"
    ]


def test_stream_call_closes_on_non_200():
    spy = _SpyLines([])

    def stream_post(url, headers, body, timeout):
        return 500, spy

    gen = C.stream_call(
        P, "m", [{"role": "user", "content": "hi"}], api_key="k", env={}, stream_post=stream_post
    )
    with pytest.raises(ProviderHTTPError):
        next(gen)  # status check happens on first iteration
    assert spy.closed is True  # connection released before the error propagated


def test_stream_call_closes_on_early_break():
    spy = _SpyLines(_sse("a", "b", "c"))

    def stream_post(url, headers, body, timeout):
        return 200, spy

    gen = C.stream_call(
        P, "m", [{"role": "user", "content": "hi"}], api_key="k", env={}, stream_post=stream_post
    )
    assert next(gen) == "a"
    gen.close()  # consumer abandons the stream early
    assert spy.closed is True  # try/finally released the connection


def test_stream_call_closes_on_exhaustion():
    spy = _SpyLines(_sse("x", "y"))

    def stream_post(url, headers, body, timeout):
        return 200, spy

    out = list(
        C.stream_call(
            P,
            "m",
            [{"role": "user", "content": "hi"}],
            api_key="k",
            env={},
            stream_post=stream_post,
        )
    )
    assert out == ["x", "y"]
    assert spy.closed is True


# ---- connection pooling plumbing (no network) ----


def test_shared_client_is_singleton():
    assert C._client() is C._client()  # one pooled client reused across calls


def test_timeout_has_fast_connect():
    to = C._timeout(90.0)
    assert to.read == 90.0 and to.connect == 10.0  # fast-fail connect
    assert C._timeout(3.0).connect == 3.0  # connect never exceeds the overall timeout


class _CM:
    def __init__(self, resp):
        self.resp = resp

    def __enter__(self):
        return self.resp

    def __exit__(self, *args):
        return False


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._raw = json.dumps(body).encode()

    def iter_bytes(self):
        yield self._raw


def test_default_post_retries_retryable_status(monkeypatch):
    calls = []

    class Client:
        def stream(self, *args, **kwargs):
            calls.append(1)
            status = 503 if len(calls) == 1 else 200
            return _CM(_Resp(status, openai_body("ok")))

    monkeypatch.setattr(C, "_client", lambda: Client())
    monkeypatch.setattr(C, "_RETRY_BACKOFF_S", 0.0)
    result = C.default_post("https://x.test/v1", {}, {}, 30.0)
    assert result.status == 200
    assert len(calls) == 2


def test_default_post_retries_transport_error(monkeypatch):
    import httpx

    calls = []

    class Client:
        def stream(self, *args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise httpx.ConnectError("temporary")
            return _CM(_Resp(200, openai_body("ok")))

    monkeypatch.setattr(C, "_client", lambda: Client())
    monkeypatch.setattr(C, "_RETRY_BACKOFF_S", 0.0)
    result = C.default_post("https://x.test/v1", {}, {}, 30.0)
    assert result.status == 200
    assert len(calls) == 2


def test_client_singleton_under_concurrency():
    import threading as _t

    C._shared = None  # force re-init
    results = []

    def grab():
        results.append(C._client())

    threads = [_t.Thread(target=grab) for _ in range(16)]
    for x in threads:
        x.start()
    for x in threads:
        x.join()
    assert len({id(r) for r in results}) == 1  # all threads got the same client
