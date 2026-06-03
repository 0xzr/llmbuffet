"""Router selection + failover behavior."""

from __future__ import annotations

import pytest
from helpers import gemini_body, make_post, openai_body

from llmbuffet.errors import AllProvidersExhausted, NoProvidersConfigured
from llmbuffet.router import Buffet


def test_ask_returns_first_success(providers, env, quota):
    post = make_post({})  # everything returns 200 "ok"
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    reply = buffet.ask("hello")
    assert reply.text == "ok"
    assert len(post.calls) == 1  # stopped at the first success


def test_failover_skips_429(providers, env, quota):
    post = make_post(
        {
            "alpha.test": (429, {"error": {"message": "rate limited"}}),
            "beta.test": (200, openai_body("from beta")),
        }
    )
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    reply = buffet.ask("hello", providers=["alpha", "beta"])
    assert reply.text == "from beta"
    assert reply.provider_id == "beta"
    # alpha had 2 models, both 429 → 2 calls, then beta succeeds → 3 total
    assert len(post.calls) == 3


def test_all_exhausted_raises(providers, env, quota):
    post = make_post(
        {
            "alpha.test": (500, {}),
            "beta.test": (503, {}),
            "gee.test": (500, {}),
            "free.test": (500, {}),
        }
    )
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    with pytest.raises(AllProvidersExhausted) as exc:
        buffet.ask("hello")
    assert exc.value.attempts  # every target recorded a reason


def test_no_providers_configured():
    buffet = Buffet([], env={})
    with pytest.raises(NoProvidersConfigured):
        buffet.ask("hello")


def test_least_used_first_ordering(providers, env, quota):
    post = make_post({})
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    # Pre-load alpha usage so beta should be picked first.
    quota.record("alpha", "alpha-small", 5)
    quota.record("alpha", "alpha-big", 5)
    reply = buffet.ask("hello")
    assert reply.provider_id != "alpha"  # not the heavily-used alpha


def test_over_budget_sinks_to_back(providers, env, quota):
    # alpha-small has rpd=2; record 2 so it is over budget and other models win.
    quota.record("alpha", "alpha-small", 2)
    post = make_post({})
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    reply = buffet.ask("hi", model="alpha-small", providers=["alpha"])
    # only candidate is the over-budget one → still served (best-effort), recorded 3rd
    assert reply.text == "ok"
    assert quota.used("alpha", "alpha-small") == 3


def test_model_filter(providers, env, quota):
    post = make_post({})
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    buffet.ask("hi", model="beta-1")
    assert all("beta.test" in c["url"] for c in post.calls)


def test_gemini_adapter_shape(providers, env, quota):
    post = make_post({"gee.test": (200, gemini_body("hi from gemini"))})
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    reply = buffet.ask("hello", system="be terse", providers=["gee"])
    assert reply.text == "hi from gemini"
    body = post.calls[0]["body"]
    assert "contents" in body and "systemInstruction" in body  # gemini shape
    assert post.calls[0]["headers"].get("x-goog-api-key") == "g"


def test_keyless_provider_sends_no_auth_header(providers, env, quota):
    post = make_post({"free.test": (200, openai_body("free!"))})
    # empty env: only the keyless provider is usable
    buffet = Buffet(providers, quota=quota, env={}, post=post)
    reply = buffet.ask("hello", providers=["free"])
    assert reply.text == "free!"
    assert reply.provider_id == "free"
    assert "Authorization" not in post.calls[0]["headers"]


def test_empty_completion_is_failure(providers, env, quota):
    post = make_post({"alpha.test": (200, openai_body("")), "beta.test": (200, openai_body("x"))})
    buffet = Buffet(providers, quota=quota, env=env, post=post)
    reply = buffet.ask("hi", providers=["alpha", "beta"])
    assert reply.provider_id == "beta"  # empty alpha skipped
