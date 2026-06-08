"""OpenAI-compatible proxy: routes, response shape, model parsing."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest
from helpers import gemini_body, make_post, make_stream_post

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


def test_models_route_accepts_query_string(server):
    with urllib.request.urlopen(server + "/v1/models?limit=100") as resp:  # noqa: S310
        body = json.load(resp)
    assert body["object"] == "list"
    assert any(m["id"] == "auto" for m in body["data"])


def test_anthropic_model_discovery_shape(server):
    req = urllib.request.Request(
        server + "/v1/models?limit=100",
        headers={"anthropic-version": "2023-06-01", "User-Agent": "claude-code"},
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        body = json.load(resp)
    assert body["has_more"] is False
    assert body["data"][0]["type"] == "model"
    assert body["data"][0]["id"] == "auto"
    assert body["data"][0]["display_name"] == "auto"
    ids = {m["id"] for m in body["data"]}
    assert "claude-3-5-haiku-latest" in ids


def test_dashboard(server):
    with urllib.request.urlopen(server + "/dashboard") as resp:  # noqa: S310
        assert resp.status == 200
        assert "text/html" in resp.headers["Content-Type"]
        body = resp.read().decode()
    assert "freellmpool" in body
    assert "providers configured" in body
    assert "not spent (Claude Opus 4.8)" in body


def test_healthz(server):
    with urllib.request.urlopen(server + "/healthz") as resp:  # noqa: S310
        assert resp.status == 200


def test_tokenmax_route(server):
    status, body = _post_json(server + "/tokenmax", {"prompt": "hi", "max_models": 3})
    assert status == 200
    assert body["total"] >= 1
    assert isinstance(body["answers"], list)
    assert any(a["text"] == "ok" for a in body["answers"])  # openai-adapter fakes answer "ok"


def test_tokenmax_requires_prompt(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_json(server + "/tokenmax", {})
    assert exc.value.code == 400


def test_status_has_tokenmax_field_idle(server):
    with urllib.request.urlopen(server + "/status") as resp:  # noqa: S310
        s = json.load(resp)
    assert s["tokenmax"]["active"] is False  # default snapshot before any run


def test_status_tokenmax_active_during_run(providers, env, quota):
    """A barrier-blocked swarm lets /status observe tokenmax.active live (the signal the
    OpenCode TUI throbs on), then settle to done==total when it finishes."""
    import time

    from helpers import openai_body

    from freellmpool.client import HTTPResult

    release = threading.Event()

    def slow_post(url, headers, json_body, timeout):
        release.wait(2.0)  # hold every fan-out call open until the test releases it
        return HTTPResult(status=200, body=openai_body("ok"), text="ok")

    pool = Pool(providers, quota=quota, env=env, post=slow_post, stream_post=make_stream_post({}))
    httpd = serve(pool, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        runner = threading.Thread(
            target=lambda: _post_json(base + "/tokenmax", {"prompt": "hi", "max_models": 3}),
            daemon=True,
        )
        runner.start()
        active_seen = False
        for _ in range(100):  # poll until the swarm is in flight
            with urllib.request.urlopen(base + "/status") as resp:  # noqa: S310
                tm = json.load(resp)["tokenmax"]
            if tm.get("active"):
                active_seen = True
                assert tm["total"] == 3
                break
            time.sleep(0.02)
        release.set()
        runner.join(timeout=3)
        assert active_seen, "tokenmax.active was never observable during the run"
        with urllib.request.urlopen(base + "/status") as resp:  # noqa: S310
            tm2 = json.load(resp)["tokenmax"]
        assert tm2["active"] is False
        assert tm2["done"] == tm2["total"] == 3
    finally:
        release.set()
        httpd.shutdown()
        httpd.server_close()


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
    chunks = [
        json.loads(ln[len("data: ") :])
        for ln in raw.splitlines()
        if ln.startswith("data: ") and "[DONE]" not in ln
    ]
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)
    assert chunks[0]["choices"][0]["delta"].get("role") == "assistant"  # role delta first
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"  # stop chunk last
    content = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert content == "ok"


def test_streaming_counts_tokens(providers, env, quota):
    """Streamed responses must accrue token usage (else $ saved / tokens / tok/s never
    move for streaming clients like OpenCode). Tokens are estimated from the streamed
    text, so /status reflects the stream after it drains."""
    stream = make_stream_post({"alpha": ["Hello there, ", "this is a ", "streamed answer."]})
    pool = Pool(providers, quota=quota, env=env, post=make_post({}), stream_post=stream)
    httpd = serve(pool, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        req = urllib.request.Request(
            base + "/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "alpha/alpha-small",  # pin the openai-adapter provider
                    "stream": True,
                    "messages": [{"role": "user", "content": "hello there"}],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            resp.read()  # drain the whole stream so end-of-stream accounting runs
        with urllib.request.urlopen(base + "/status") as resp:  # noqa: S310
            pool_stats = json.load(resp)["pool"]
        assert pool_stats["completion_tokens"] > 0  # streamed output is now counted
        assert pool_stats["prompt_tokens"] > 0
    finally:
        httpd.shutdown()
        httpd.server_close()


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


def _serve(pool, api_key=None):
    httpd = serve(pool, host="127.0.0.1", port=0, api_key=api_key)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_auth_required_on_all_post_routes(providers, env, quota):
    pool = Pool(
        providers, quota=quota, env=env, post=make_post({}), stream_post=make_stream_post({})
    )
    httpd, base = _serve(pool, api_key="secret")
    routes = {
        "/v1/chat/completions": {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        "/v1/embeddings": {"model": "auto", "input": ["x"]},
        "/v1/responses": {"model": "auto", "input": "hi"},
        "/v1/messages": {
            "model": "claude",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "hi"}],
        },
        "/v1/messages/count_tokens": {"messages": [{"role": "user", "content": "hi"}]},
    }
    try:
        for path, body in routes.items():
            assert _expect_status(base + path, body) == 401, f"{path} unauth should be 401"
            got = _expect_status(base + path, body, {"Authorization": "Bearer secret"})
            assert got != 401, f"{path} with key should not be 401 (got {got})"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_anthropic_messages_route_accepts_query_string(server):
    status, body = _post_json(
        server + "/v1/messages?beta=true",
        {
            "model": "claude-3-5-sonnet",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert status == 200
    assert body["type"] == "message"


def test_gemini_adapter_via_proxy(providers, env, quota):
    # 'gee' is a gemini-adapter provider; routing model="gee" must use the gemini body shape
    post = make_post({"gee.test": (200, gemini_body("hi from gemini"))})
    pool = Pool(providers, quota=quota, env=env, post=post)
    httpd, base = _serve(pool)
    try:
        status, body = _post_json(
            base + "/v1/chat/completions",
            {"model": "gee", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "hi from gemini"
        gee_call = next(c for c in post.calls if "gee.test" in c["url"])
        assert "contents" in gee_call["body"]  # gemini shape, not OpenAI
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
    # catalog model names with '/' whose prefix isn't a provider id stay whole
    assert _parse_model("openai/gpt-oss-120b", ids) == (None, "openai/gpt-oss-120b")
    assert _parse_model("qwen/qwen3-coder:free", ids) == (None, "qwen/qwen3-coder:free")


def test_get_routes_gated_by_key(providers, env, quota):
    from freellmpool.proxy import serve

    pool = Pool(providers, quota=quota, env=env, post=make_post({}))
    httpd = serve(pool, host="127.0.0.1", port=0, api_key="secret")
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        for path in ("/dashboard", "/v1/models"):
            req = urllib.request.Request(base + path)
            try:
                urllib.request.urlopen(req)  # noqa: S310
                raise AssertionError(f"{path} should require auth")
            except urllib.error.HTTPError as e:
                assert e.code == 401
        # healthz stays open
        with urllib.request.urlopen(base + "/healthz") as r:  # noqa: S310
            assert r.status == 200
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_streaming_request_with_tools_carries_tool_calls(providers, env, quota):
    # stream:true + tools uses the buffered SSE path; tool_calls must survive.
    tc = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    post = make_post(
        {"alpha.test": (200, {"choices": [{"message": {"content": None, "tool_calls": tc}}]})}
    )
    pool = Pool(providers, quota=quota, env=env, post=post)
    httpd, base = _serve(pool)
    try:
        req = urllib.request.Request(
            base + "/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "alpha",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hi"}],
                    "tools": [{"type": "function", "function": {"name": "f"}}],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            raw = resp.read().decode()
        chunks = [
            json.loads(ln[len("data: ") :])
            for ln in raw.splitlines()
            if ln.startswith("data: ") and "[DONE]" not in ln
        ]
        tc_deltas = [c for c in chunks if c["choices"][0]["delta"].get("tool_calls")]
        assert tc_deltas, "no tool_calls delta emitted"
        streamed = tc_deltas[0]["choices"][0]["delta"]["tool_calls"]
        assert streamed[0]["index"] == 0  # OpenAI streaming requires per-call index
        assert streamed[0]["id"] == "c1"
        assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_messages_empty_returns_anthropic_shaped_400(server):
    code = _expect_status(server + "/v1/messages", {"model": "claude", "messages": []})
    assert code == 400


def test_messages_empty_error_envelope_is_anthropic(providers, env, quota):
    pool = Pool(providers, quota=quota, env=env, post=make_post({}))
    httpd, base = _serve(pool)
    try:
        req = urllib.request.Request(
            base + "/v1/messages",
            data=json.dumps({"model": "claude", "messages": []}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req)  # noqa: S310
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as e:
            body = json.load(e)
        assert body["type"] == "error"  # Anthropic envelope, not OpenAI
        assert body["error"]["type"] == "invalid_request_error"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_null_assistant_content_not_stringified():
    # OpenAI sends content:null on assistant tool-call turns; it must not become "None"
    from freellmpool.proxy import _normalize_messages

    out = _normalize_messages([{"role": "assistant", "content": None, "tool_calls": [{"id": "x"}]}])
    assert out[0]["content"] == ""
    assert out[0]["tool_calls"] == [{"id": "x"}]


# ---- JSON /status endpoint + per-request routing control ----


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (localhost test)
        return resp.status, json.load(resp)


def test_status_endpoint_shape(server):
    status, body = _get_json(server + "/status")
    assert status == 200
    assert "routing" in body
    for k in ("requests", "prompt_tokens", "completion_tokens", "cache_hits", "usd_saved"):
        assert k in body["pool"]
    assert isinstance(body["providers"], list) and body["providers"]
    p = body["providers"][0]
    assert {"id", "configured", "cooldown_remaining_s", "models"} <= set(p)
    assert isinstance(body["recent"], list)


def test_status_v1_alias(server):
    assert _get_json(server + "/v1/status")[0] == 200


def test_status_records_served_target(server):
    _post_json(
        server + "/v1/chat/completions",
        {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    _, body = _get_json(server + "/status")
    assert body["recent"], "expected a recent entry after a chat"
    assert {"provider", "model", "attempts"} <= set(body["recent"][0])
    assert body["pool"]["requests"] >= 1


def test_models_route_includes_routing_aliases(server):
    with urllib.request.urlopen(server + "/v1/models") as resp:  # noqa: S310
        ids = {m["id"] for m in json.load(resp)["data"]}
    assert {"auto", "fast", "quality", "fair", "spread"} <= ids  # spread discoverable


def test_spread_alias_routes(server):
    # bare + provider-qualified aliases all route and serve (incl. freellmpool/auto, which
    # must NOT be treated as a literal provider filter → 503)
    for name in ("spread", "freellmpool/spread", "freellmpool/auto", "auto"):
        status, body = _post_json(
            server + "/v1/chat/completions",
            {"model": name, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert status == 200, name
        assert body["choices"][0]["message"]["content"] == "ok", name
        assert "x_freellmpool" in body


def test_model_name_is_treated_as_routing_keyword(server):
    # "fast" is a routing keyword, not a literal model id → served as auto + fast routing
    status, body = _post_json(
        server + "/v1/chat/completions",
        {"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert status == 200
    assert "x_freellmpool" in body


def test_header_routing_override_accepted(server):
    status, body = _post_json_with_headers(
        server + "/v1/chat/completions",
        {"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
        {"X-Freellmpool-Routing": "fast"},
    )
    assert status == 200
    assert "x_freellmpool" in body


def test_parse_multipart_form_unit():
    from freellmpool.proxy import _parse_multipart_form

    ct = "multipart/form-data; boundary=XB"
    body = (
        b'--XB\r\nContent-Disposition: form-data; name="model"\r\n\r\nm1\r\n'
        b'--XB\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\nAUDIO\x00\x01\r\n--XB--\r\n"
    )
    f = _parse_multipart_form(ct, body)
    assert f["model"] == "m1"
    assert f["file"] == ("a.wav", b"AUDIO\x00\x01")  # binary bytes preserved


def test_parse_multipart_form_binary_safe_embedded_boundary():
    # Audio bytes that contain "--XB" (NOT preceded by CRLF) must NOT be treated as a
    # delimiter — the payload must survive intact.
    from freellmpool.proxy import _parse_multipart_form

    audio = b"PRE--XB-and-more\x00\xff"
    ct = "multipart/form-data; boundary=XB"
    body = (
        b'--XB\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n\r\n'
        + audio
        + b"\r\n--XB--\r\n"
    )
    f = _parse_multipart_form(ct, body)
    assert f["file"] == ("a.wav", audio)


def test_parse_multipart_form_missing_closing_boundary_raises():
    from freellmpool.proxy import _parse_multipart_form

    ct = "multipart/form-data; boundary=XB"
    # no trailing "--XB--"
    body = b'--XB\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n\r\nAUDIO'
    with pytest.raises(ValueError, match="closing"):
        _parse_multipart_form(ct, body)


def _multipart_audio(boundary, audio, model="whisper-large-v3-turbo", with_file=True):
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'.encode()
    ]
    if with_file:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n".encode()
            + audio
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def _transcribe_server(providers, env, quota, text="the transcript"):
    from freellmpool.client import HTTPResult
    from freellmpool.models import Model, Provider

    tr = [
        Provider(
            id="groq",
            label="Groq",
            adapter="openai",
            base_url="https://api.groq.com/openai/v1",
            key_env="GROQ_API_KEY",
            models=(Model("whisper-large-v3-turbo"),),
        )
    ]

    def fake_mp(url, headers, files, data, timeout):
        assert url.endswith("/audio/transcriptions")
        assert files["file"][0] == "a.wav"
        return HTTPResult(status=200, body={"text": text}, text=text)

    pool = Pool(
        providers,
        quota=quota,
        env={**env, "GROQ_API_KEY": "x"},
        post=make_post({}),
        stream_post=make_stream_post({}),
        transcribers=tr,
        transcribe_post=fake_mp,
    )
    httpd = serve(pool, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_audio_transcription_route(providers, env, quota):
    httpd, base = _transcribe_server(providers, env, quota)
    try:
        body = _multipart_audio("BOUND1", b"RIFF\x00fakeaudio")
        req = urllib.request.Request(
            base + "/v1/audio/transcriptions",
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary=BOUND1"},
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            d = json.load(resp)
        assert d["text"] == "the transcript"
        assert d["x_freellmpool"]["provider"] == "groq"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_audio_transcription_missing_file_400(providers, env, quota):
    httpd, base = _transcribe_server(providers, env, quota)
    try:
        body = _multipart_audio("BOUND1", b"", with_file=False)
        req = urllib.request.Request(
            base + "/v1/audio/transcriptions",
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary=BOUND1"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)  # noqa: S310
        assert exc.value.code == 400
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post_json_with_headers(url, payload, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (localhost test)
        return resp.status, json.load(resp)


# ---- shareable SVG badge / summary + lifetime stats ----


def test_badge_svg_route(server):
    with urllib.request.urlopen(server + "/badge.svg") as resp:  # noqa: S310
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("image/svg+xml")
        body = resp.read().decode()
    assert body.startswith("<svg")
    assert "freellmpool" in body


def test_summary_svg_route(server):
    with urllib.request.urlopen(server + "/summary.svg") as resp:  # noqa: S310
        assert resp.status == 200
        body = resp.read().decode()
    assert "<svg" in body


def test_status_has_lifetime_block(server):
    status, body = _get_json(server + "/status")
    assert status == 200
    assert "lifetime" in body
    for k in (
        "requests",
        "prompt_tokens",
        "completion_tokens",
        "cache_hits",
        "usd_saved",
        "first_seen",
    ):
        assert k in body["lifetime"]


def test_badge_requires_auth_when_keyed(providers, env, quota, monkeypatch):
    monkeypatch.delenv("FREELLMPOOL_PUBLIC_BADGE", raising=False)
    pool = Pool(
        providers, quota=quota, env=env, post=make_post({}), stream_post=make_stream_post({})
    )
    httpd, base = _serve(pool, api_key="secret")
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base + "/badge.svg")  # noqa: S310
        assert exc.value.code == 401
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_badge_public_when_opted_in(providers, env, quota, monkeypatch):
    monkeypatch.setenv("FREELLMPOOL_PUBLIC_BADGE", "1")
    pool = Pool(
        providers, quota=quota, env=env, post=make_post({}), stream_post=make_stream_post({})
    )
    httpd, base = _serve(pool, api_key="secret")
    try:
        with urllib.request.urlopen(base + "/badge.svg") as resp:  # noqa: S310
            assert resp.status == 200  # public despite the proxy key
    finally:
        httpd.shutdown()
        httpd.server_close()
