"""Pooled audio transcription: catalog, client.transcribe, Pool.transcribe, failover."""

from __future__ import annotations

import pytest

from freellmpool import client as C
from freellmpool.config import configured_transcribers, load_transcribers
from freellmpool.errors import AllProvidersExhausted, NoProvidersConfigured
from freellmpool.models import Model, Provider
from freellmpool.router import Pool


def _transcriber(tid: str, key_env: str) -> Provider:
    return Provider(
        id=tid,
        label=tid,
        adapter="openai",
        base_url=f"https://{tid}.test/v1",
        key_env=key_env,
        models=(Model("whisper-large-v3-turbo"),),
    )


def test_transcriber_catalog_loads():
    cat = load_transcribers()
    ids = {t.id for t in cat}
    assert "groq" in ids
    for t in cat:
        assert t.base_url.startswith("https://")
        assert t.models


def test_configured_transcribers_filter():
    cat = load_transcribers()
    got = {t.id for t in configured_transcribers(cat, {"GROQ_API_KEY": "x"})}
    assert got == {"groq"}
    assert configured_transcribers(cat, {}) == []  # no key → nothing configured


def test_client_transcribe_shape():
    def post(url, headers, files, data, timeout):
        assert url.endswith("/audio/transcriptions")
        assert files["file"][0] == "a.wav"
        assert files["file"][1] == b"AUDIO"
        assert data["model"] == "whisper-large-v3-turbo"
        assert headers["Authorization"] == "Bearer k"
        return C.HTTPResult(200, {"text": "hello world"}, "")

    t = _transcriber("groq", "GROQ_API_KEY")
    reply = C.transcribe(
        t, "whisper-large-v3-turbo", b"AUDIO", "a.wav", api_key="k", env={}, post=post
    )
    assert reply.text == "hello world"
    assert reply.provider_id == "groq"


def test_client_transcribe_text_format_plain_body():
    def post(url, headers, files, data, timeout):
        # response_format=text → transport returns plain text body
        return C.HTTPResult(200, {"text": "plain transcript"}, "plain transcript")

    t = _transcriber("groq", "GROQ_API_KEY")
    reply = C.transcribe(
        t,
        "whisper-large-v3-turbo",
        b"A",
        "a.wav",
        api_key="k",
        env={},
        response_format="text",
        post=post,
    )
    assert reply.text == "plain transcript"


def test_pool_transcribe_failover():
    def post(url, headers, files, data, timeout):
        if "alpha.test" in url:
            return C.HTTPResult(429, {"error": {"message": "rl"}}, "")
        return C.HTTPResult(200, {"text": "ok"}, "")

    transcribers = [_transcriber("alpha", "A_KEY"), _transcriber("beta", "B_KEY")]
    pool = Pool(
        [], env={"A_KEY": "a", "B_KEY": "b"}, transcribers=transcribers, transcribe_post=post
    )
    reply = pool.transcribe(b"AUDIO", "a.wav")
    assert reply.provider_id == "beta"  # alpha 429 → failover
    assert reply.text == "ok"


def test_pool_transcribe_provider_pin():
    def post(url, headers, files, data, timeout):
        return C.HTTPResult(200, {"text": url}, "")

    transcribers = [_transcriber("alpha", "A_KEY"), _transcriber("beta", "B_KEY")]
    pool = Pool(
        [], env={"A_KEY": "a", "B_KEY": "b"}, transcribers=transcribers, transcribe_post=post
    )
    reply = pool.transcribe(b"AUDIO", "a.wav", providers=["beta"])
    assert reply.provider_id == "beta"
    assert "beta.test" in reply.text


def test_pool_transcribe_no_transcribers_raises():
    pool = Pool([], env={}, transcribers=[])
    with pytest.raises(NoProvidersConfigured):
        pool.transcribe(b"AUDIO", "a.wav")


def test_pool_transcribe_unknown_pin_raises_no_providers():
    # pinning a provider/model that matches nothing must be NoProvidersConfigured (→ 503),
    # not AllProvidersExhausted([]) (→ 502).
    def post(url, headers, files, data, timeout):
        return C.HTTPResult(200, {"text": "ok"}, "")

    pool = Pool(
        [], env={"A_KEY": "a"}, transcribers=[_transcriber("alpha", "A_KEY")], transcribe_post=post
    )
    with pytest.raises(NoProvidersConfigured):
        pool.transcribe(b"AUDIO", "a.wav", providers=["nonexistent"])
    with pytest.raises(NoProvidersConfigured):
        pool.transcribe(b"AUDIO", "a.wav", model="no-such-model")


def test_pool_transcribe_all_fail_raises():
    def post(url, headers, files, data, timeout):
        return C.HTTPResult(500, {}, "")

    pool = Pool(
        [], env={"A_KEY": "a"}, transcribers=[_transcriber("alpha", "A_KEY")], transcribe_post=post
    )
    with pytest.raises(AllProvidersExhausted):
        pool.transcribe(b"AUDIO", "a.wav")
