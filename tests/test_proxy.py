"""OpenAI-compatible proxy: routes, response shape, model parsing."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest
from helpers import make_post, make_stream_post

from freellmpool.proxy import _parse_model, serve
from freellmpool.router import Pool


@pytest.fixture
def server(providers, env, quota):
    post = make_post({})
    pool = Pool(providers, quota=quota, env=env, post=post, stream_post=make_stream_post({}))
    httpd = serve(pool, host="127.0.0.1", port=0)  # port 0 = ephemeral
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def _post_json(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (localhost test)
        return resp.status, json.load(resp)


def test_chat_completions_shape(server):
    status, body = _post_json(
        server + "/v1/chat/completions",
        {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert status == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "ok"
    assert "x_freellmpool" in body


def test_models_route(server):
    with urllib.request.urlopen(server + "/v1/models") as resp:  # noqa: S310
        body = json.load(resp)
    ids = {m["id"] for m in body["data"]}
    assert "auto" in ids
    assert any(i.startswith("alpha/") for i in ids)


def test_healthz(server):
    with urllib.request.urlopen(server + "/healthz") as resp:  # noqa: S310
        assert resp.status == 200


def test_content_parts_flattened(server):
    status, body = _post_json(
        server + "/v1/chat/completions",
        {
            "model": "auto",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
                }
            ],
        },
    )
    assert status == 200


def test_streaming_sse(server):
    req = urllib.request.Request(
        server + "/v1/chat/completions",
        data=json.dumps(
            {"model": "auto", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        assert resp.headers["Content-Type"] == "text/event-stream"
        raw = resp.read().decode()
    assert raw.strip().endswith("[DONE]")
    content = ""
    for line in raw.splitlines():
        if line.startswith("data: ") and "[DONE]" not in line:
            chunk = json.loads(line[len("data: ") :])
            content += chunk["choices"][0]["delta"].get("content", "")
    assert content == "ok"


def _expect_status(url, payload, headers=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def test_malformed_body_returns_400_not_crash(server):
    # non-object body
    assert _expect_status(server + "/v1/chat/completions", [1, 2, 3]) == 400
    # missing messages
    assert _expect_status(server + "/v1/chat/completions", {"model": "auto"}) == 400
    # bad types
    assert (
        _expect_status(
            server + "/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "max_tokens": "lots"},
        )
        == 400
    )
    # server still alive afterward
    assert (
        _post_json(
            server + "/v1/chat/completions",
            {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        )[0]
        == 200
    )


def test_proxy_auth(providers, env, quota):
    from freellmpool.proxy import serve

    pool = Pool(providers, quota=quota, env=env, post=make_post({}))
    httpd = serve(pool, host="127.0.0.1", port=0, api_key="secret")
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    body = {"model": "auto", "messages": [{"role": "user", "content": "hi"}]}
    try:
        assert _expect_status(base + "/v1/chat/completions", body) == 401  # no token
        assert (
            _expect_status(base + "/v1/chat/completions", body, {"Authorization": "Bearer secret"})
            == 200
        )
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_responses_shim_nonstream(server):
    status, body = _post_json(
        server + "/v1/responses",
        {"model": "auto", "instructions": "be terse", "input": "hi"},
    )
    assert status == 200
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output_text"] == "ok"
    assert body["output"][0]["content"][0]["type"] == "output_text"


def test_responses_shim_input_items(server):
    status, body = _post_json(
        server + "/v1/responses",
        {
            "model": "auto",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
        },
    )
    assert status == 200
    assert body["output_text"] == "ok"


def test_responses_shim_streaming(server):
    req = urllib.request.Request(
        server + "/v1/responses",
        data=json.dumps({"model": "auto", "stream": True, "input": "hi"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        raw = resp.read().decode()
    assert "event: response.created" in raw
    assert "event: response.output_text.delta" in raw
    assert "event: response.completed" in raw


def test_responses_missing_input_400(server):
    assert _expect_status(server + "/v1/responses", {"model": "auto"}) == 400


def test_proxy_alias_routes(server):
    # an OpenAI model name the pool doesn't have still routes (alias → auto)
    status, body = _post_json(
        server + "/v1/chat/completions",
        {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert status == 200
    assert body["choices"][0]["message"]["content"] == "ok"


def test_proxy_observability_headers(server):
    req = urllib.request.Request(
        server + "/v1/chat/completions",
        data=json.dumps(
            {"model": "auto", "messages": [{"role": "user", "content": "hi"}]}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        assert resp.headers.get("X-Freellmpool-Provider")
        assert resp.headers.get("X-Freellmpool-Model")
        assert resp.headers.get("X-Freellmpool-Attempts")


def test_proxy_tool_calls_passthrough(providers, env, quota):
    tc = [{"id": "c", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    post = make_post(
        {
            "alpha.test": (
                200,
                {
                    "choices": [
                        {"message": {"role": "assistant", "content": None, "tool_calls": tc}}
                    ]
                },
            )
        }
    )
    pool = Pool(providers, quota=quota, env=env, post=post)
    httpd = serve(pool, host="127.0.0.1", port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _, body = _post_json(
            base + "/v1/chat/completions",
            {
                "model": "alpha",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{"type": "function", "function": {"name": "f"}}],
            },
        )
        assert body["choices"][0]["finish_reason"] == "tool_calls"
        assert body["choices"][0]["message"]["tool_calls"] == tc
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_parse_model():
    ids = {"groq", "cerebras"}
    assert _parse_model("auto", ids) == (None, None)
    assert _parse_model("", ids) == (None, None)
    assert _parse_model("groq", ids) == (["groq"], None)
    assert _parse_model("groq/llama-3.1-8b", ids) == (["groq"], "llama-3.1-8b")
    assert _parse_model("llama-3.3-70b", ids) == (None, "llama-3.3-70b")
