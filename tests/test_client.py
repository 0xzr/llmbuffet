"""Adapter behavior: thinking-model handling, header shaping."""

from __future__ import annotations

from helpers import make_post, openai_body

from llmbuffet import client as C
from llmbuffet.models import Model, Provider

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
    assert seen["max_tokens"] >= 8192  # reasoning model got headroom


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


def test_think_tags_stripped():
    post = make_post({"x.test": (200, openai_body("<think>secret reasoning</think>final answer"))})
    reply = C.call(
        P, "zai-glm-4.7", [{"role": "user", "content": "hi"}], api_key="k", env={}, post=post
    )
    assert reply.text == "final answer"
