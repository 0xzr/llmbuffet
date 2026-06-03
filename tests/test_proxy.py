"""OpenAI-compatible proxy: routes, response shape, model parsing."""

from __future__ import annotations

import json
import threading
import urllib.request

import pytest
from helpers import make_post

from llmbuffet.proxy import _parse_model, serve
from llmbuffet.router import Buffet


@pytest.fixture
def server(providers, env, quota):
    post = make_post({})
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    httpd = serve(buffet, host="127.0.0.1", port=0)  # port 0 = ephemeral
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
    assert "x_llmbuffet" in body


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


def test_parse_model():
    ids = {"groq", "cerebras"}
    assert _parse_model("auto", ids) == (None, None)
    assert _parse_model("", ids) == (None, None)
    assert _parse_model("groq", ids) == (["groq"], None)
    assert _parse_model("groq/llama-3.1-8b", ids) == (["groq"], "llama-3.1-8b")
    assert _parse_model("llama-3.3-70b", ids) == (None, "llama-3.3-70b")
