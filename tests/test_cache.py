"""Response cache + Pool integration."""

from __future__ import annotations

from helpers import make_post, make_stream_post

from freellmpool.cache import Cache
from freellmpool.router import Pool


def test_cache_get_put_and_ttl(tmp_path):
    t = [100.0]
    c = Cache(ttl=50.0, path=tmp_path / "c.db", clock=lambda: t[0])
    key = c.make_key([{"role": "user", "content": "hi"}], None, None, 1024, 0.0, None)
    assert c.get(key) is None
    c.put(key, {"text": "cached"})
    assert c.get(key)["text"] == "cached"
    t[0] = 200.0  # 100s later, ttl 50 → expired
    assert c.get(key) is None


def test_make_key_includes_tool_choice():
    args = ([{"role": "user", "content": "hi"}], None, None, 1024, 0.0, [{"type": "function"}])
    k_auto = Cache.make_key(*args, "auto")
    k_req = Cache.make_key(*args, "required")
    assert k_auto != k_req  # different tool_choice → different cache entry


def test_make_key_includes_routing():
    # a per-request routing override must not collide with a different mode's cache:
    # a "quality" ask should never be served a cached "fast"-routed reply.
    args = ([{"role": "user", "content": "hi"}], None, None, 1024, 0.0, None, None)
    assert Cache.make_key(*args, routing="fast") != Cache.make_key(*args, routing="quality")
    # the same effective mode still shares a bucket
    assert Cache.make_key(*args, routing="fair") == Cache.make_key(*args, routing="fair")


def test_pool_uses_cache(providers, env, quota, tmp_path):
    cache = Cache(ttl=999.0, path=tmp_path / "c.db")
    post = make_post({})  # returns "ok", counts calls
    pool = Pool(providers, quota=quota, env=env, post=post, cache=cache)

    r1 = pool.ask("hello")
    assert r1.text == "ok" and not r1.cached
    n_after_first = len(post.calls)

    r2 = pool.ask("hello")  # identical → served from cache, no new provider call
    assert r2.text == "ok" and r2.cached
    assert r2.provider_id == r1.provider_id  # cached reply preserves the original provider
    assert len(post.calls) == n_after_first  # no extra network call
    assert pool.stats["cache_hits"] == 1


def test_cache_preserves_tool_calls(providers, env, quota, tmp_path):
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
    cache = Cache(ttl=999.0, path=tmp_path / "c.db")
    pool = Pool(providers, quota=quota, env=env, post=post, cache=cache)
    tools = [{"type": "function", "function": {"name": "f"}}]
    pool.ask("hi", providers=["alpha"], tools=tools)
    n = len(post.calls)
    r2 = pool.ask("hi", providers=["alpha"], tools=tools)  # identical → cached
    assert r2.cached
    assert r2.message["tool_calls"] == tc  # tool_calls survive the round-trip through cache
    assert len(post.calls) == n  # no new provider call


def test_streaming_bypasses_cache(providers, env, quota, tmp_path):
    cache = Cache(ttl=999.0, path=tmp_path / "c.db")
    sp = make_stream_post({})
    pool = Pool(providers, quota=quota, env=env, post=make_post({}), stream_post=sp, cache=cache)
    list(pool.stream_chat([{"role": "user", "content": "hi"}], providers=["alpha"]))
    list(pool.stream_chat([{"role": "user", "content": "hi"}], providers=["alpha"]))
    assert len(sp.calls) == 2  # streaming is not cached — both hit the provider
    assert pool.stats["cache_hits"] == 0


def test_cache_distinguishes_prompts(providers, env, quota, tmp_path):
    cache = Cache(ttl=999.0, path=tmp_path / "c.db")
    post = make_post({})
    pool = Pool(providers, quota=quota, env=env, post=post, cache=cache)
    pool.ask("first")
    pool.ask("second")  # different prompt → not a cache hit
    assert pool.stats["cache_hits"] == 0


def test_cache_disabled_by_default(providers, env, quota):
    post = make_post({})
    pool = Pool(providers, quota=quota, env=env, post=post)  # no cache
    pool.ask("hello")
    pool.ask("hello")
    assert len(post.calls) == 2  # both hit the provider
