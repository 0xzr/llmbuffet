"""Adapter behavior: thinking-model handling, header shaping."""

from __future__ import annotations

from helpers import make_post, openai_body

from freellmpool import client as C
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
