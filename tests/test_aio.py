"""AsyncPool: async failover, gemini shape, and shared metrics/quota bookkeeping.

Driven with asyncio.run so no pytest-asyncio dependency is needed.
"""

from __future__ import annotations

import asyncio

from helpers import gemini_body, make_post

from freellmpool.aio import AsyncPool
from freellmpool.router import Pool


def _async_post(script):
    """Adapt the sync fake transport into an async one (await apost(...))."""
    sync = make_post(script)

    async def apost(url, headers, body, timeout):
        return sync(url, headers, body, timeout)

    apost.calls = sync.calls
    return apost


def test_aask_succeeds(providers, env, quota):
    pool = AsyncPool(Pool(providers, quota=quota, env=env), apost=_async_post({}))
    reply = asyncio.run(pool.aask("hi"))
    assert reply.text == "ok"
    assert reply.provider_id in {p.id for p in providers}


def test_async_failover_skips_500(providers, env, quota):
    apost = _async_post({"alpha.test": (500, {"error": "boom"})})
    pool = AsyncPool(Pool(providers, quota=quota, env=env), apost=apost)
    reply = asyncio.run(
        pool.achat([{"role": "user", "content": "hi"}], providers=["alpha", "beta"])
    )
    assert reply.provider_id == "beta"  # alpha 500'd, failed over to beta
    assert pool.metrics.get("alpha/alpha-small").fail >= 1
    assert pool.metrics.get("beta/beta-1").ok == 1


def test_async_gemini_shape(providers, env, quota):
    apost = _async_post({"gee.test": (200, gemini_body("hi from gemini"))})
    pool = AsyncPool(Pool(providers, quota=quota, env=env), apost=apost)
    reply = asyncio.run(pool.achat([{"role": "user", "content": "hi"}], providers=["gee"]))
    assert reply.text == "hi from gemini"


def test_async_records_quota_and_stats(providers, env, quota):
    pool = AsyncPool(Pool(providers, quota=quota, env=env), apost=_async_post({}))
    asyncio.run(pool.aask("hi"))
    assert pool.stats["requests"] == 1


def test_async_context_manager_closes(providers, env, quota):
    async def run():
        async with AsyncPool(Pool(providers, quota=quota, env=env), apost=_async_post({})) as pool:
            return await pool.aask("hi")

    reply = asyncio.run(run())
    assert reply.text == "ok"


def test_async_no_providers_raises(quota):
    from freellmpool.errors import NoProvidersConfigured

    pool = AsyncPool(Pool([], quota=quota, env={}), apost=_async_post({}))
    try:
        asyncio.run(pool.aask("hi"))
        raise AssertionError("expected NoProvidersConfigured")
    except NoProvidersConfigured:
        pass


def test_async_uses_response_cache(providers, env, quota, tmp_path):
    from freellmpool.cache import Cache

    apost = _async_post({})
    cache = Cache(ttl=60, path=tmp_path / "cache.sqlite")  # isolated, not the shared default
    pool = AsyncPool(Pool(providers, quota=quota, env=env, cache=cache), apost=apost)

    async def run():
        first = await pool.aask("same question")
        second = await pool.aask("same question")
        return first, second

    first, second = asyncio.run(run())
    assert first.cached is False
    assert second.cached is True  # served from cache, no second upstream call
    assert pool.stats["cache_hits"] == 1
    # only one real upstream call happened
    assert len(apost.calls) == 1


def test_async_cache_key_includes_pool_routing(providers, env, quota, tmp_path):
    from freellmpool.cache import Cache

    cache = Cache(ttl=60, path=tmp_path / "cache.sqlite")
    fast_post = _async_post({})
    fast = AsyncPool(
        Pool(providers, quota=quota, env=env, cache=cache, routing="fast"),
        apost=fast_post,
    )
    asyncio.run(fast.aask("same question", providers=["alpha", "beta"]))
    assert len(fast_post.calls) == 1

    quality_post = _async_post({})
    quality = AsyncPool(
        Pool(providers, quota=quota, env=env, cache=cache, routing="quality"),
        apost=quality_post,
    )
    reply = asyncio.run(quality.aask("same question", providers=["alpha", "beta"]))

    assert reply.cached is False
    assert len(quality_post.calls) == 1
    assert quality.stats["cache_hits"] == 0


def test_async_custom_adapter_runs_via_thread(quota):
    from freellmpool import plugins
    from freellmpool.models import Model, Provider, Reply

    plugins._reset_for_tests()
    try:

        def my_adapter(provider, model, messages, **kw):
            return Reply(text="from-plugin", provider_id=provider.id, model=model, raw={})

        plugins.register_adapter("weird", my_adapter)
        prov = Provider(
            id="w",
            label="W",
            adapter="weird",
            base_url="https://w.test",
            auth="none",
            models=(Model("w-1"),),
        )
        pool = AsyncPool(Pool([prov], quota=quota, env={}), apost=_async_post({}))
        reply = asyncio.run(pool.aask("hi"))
        assert reply.text == "from-plugin"  # plugin adapter reached on the async path
    finally:
        plugins._reset_for_tests()
