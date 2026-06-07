"""MCP server: JSON-RPC message handling (no real stdio needed)."""

from __future__ import annotations

from helpers import make_post, openai_body

from freellmpool.mcp_server import handle_message
from freellmpool.router import Pool


def _pool(providers, env, quota, post=None):
    return Pool(providers, quota=quota, env=env, post=post or make_post({}))


def test_initialize(providers, env, quota):
    pool = _pool(providers, env, quota)
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        version="0.6.0",
    )
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "freellmpool"
    assert resp["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in resp["result"]["capabilities"]
    # The handshake teaches agents to invoke tools directly (not via the CLI), which is
    # what lets tokenmax's live progress reach the user instead of a hidden subprocess.
    instructions = resp["result"]["instructions"]
    assert "tokenmax" in instructions
    assert "directly" in instructions.lower()
    assert "freellmpool tokenmax" in instructions  # how the human sees the flashing animation


def test_notification_gets_no_reply(providers, env, quota):
    pool = _pool(providers, env, quota)
    assert handle_message(pool, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list(providers, env, quota):
    pool = _pool(providers, env, quota)
    resp = handle_message(pool, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {
        "free_llm_ask",
        "free_llm_panel",
        "tokenmax",
        "free_llm_route",
        "free_llm_models",
        "free_llm_quota",
        "free_llm_stats",
    }


def test_tools_call_quota(providers, env, quota):
    pool = _pool(providers, env, quota)
    pool.ask("hi")  # record some usage
    resp = handle_message(
        pool,
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "free_llm_quota"}},
    )
    text = resp["result"]["content"][0]["text"]
    assert "usage" in text.lower()
    assert "session:" in text


def test_tools_call_ask(providers, env, quota):
    pool = _pool(providers, env, quota, post=make_post({}))  # returns "ok"
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "free_llm_ask", "arguments": {"prompt": "hi"}},
        },
    )
    text = resp["result"]["content"][0]["text"]
    assert text.startswith("ok")
    assert "via alpha/" in text  # provenance footer names the serving model
    assert resp["result"]["isError"] is False


def test_tools_call_panel(providers, env, quota):
    pool = _pool(providers, env, quota)  # all providers return "ok"
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "free_llm_panel", "arguments": {"prompt": "hi", "n": 2}},
        },
    )
    text = resp["result"]["content"][0]["text"]
    assert "panel" in text.lower()
    assert text.count("###") >= 2  # one section per model asked


def test_tools_call_tokenmax(providers, env, quota):
    pool = _pool(providers, env, quota)  # all providers return "ok"
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "tokenmax", "arguments": {"prompt": "hi", "max_models": 3}},
        },
    )
    text = resp["result"]["content"][0]["text"]
    assert "TOKENMAX" in text
    assert "synthesize" in text.lower()  # the caller is told to synthesize
    assert text.count("###") >= 1  # at least one model's answer included


def test_tokenmax_default_respects_hard_cap(providers, env, quota, monkeypatch):
    import freellmpool.tokenmax as TM

    monkeypatch.setattr(TM, "HARD_CAP", 2)  # even "all" must obey the ceiling
    pool = _pool(providers, env, quota)
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {"name": "tokenmax", "arguments": {"prompt": "hi"}},  # no max_models -> ALL
        },
    )
    assert "to 2 models" in resp["result"]["content"][0]["text"]


def test_tokenmax_result_has_rainbow_banner(providers, env, quota):
    from freellmpool.tokenmax import RAINBOW_BANNER

    pool = _pool(providers, env, quota)
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {"name": "tokenmax", "arguments": {"prompt": "hi"}},
        },
    )
    assert RAINBOW_BANNER in resp["result"]["content"][0]["text"]  # color lands in every host


def test_tokenmax_emits_progress_when_token_present(providers, env, quota):
    pool = _pool(providers, env, quota)
    sent: list = []
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {
                "name": "tokenmax",
                "arguments": {"prompt": "hi"},
                "_meta": {"progressToken": "tok-1"},
            },
        },
        send_notification=sent.append,
    )
    assert resp["result"]["isError"] is False
    progs = [m for m in sent if m.get("method") == "notifications/progress"]
    assert progs, "expected progress notifications when a progressToken is supplied"
    last = progs[-1]["params"]
    assert last["progressToken"] == "tok-1"
    assert last["progress"] == last["total"]  # the final tick reaches 100%
    assert "TOKENMAXXING" in last["message"]


def test_tokenmax_silent_without_progress_token(providers, env, quota):
    pool = _pool(providers, env, quota)
    sent: list = []
    handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 17,
            "method": "tools/call",
            "params": {"name": "tokenmax", "arguments": {"prompt": "hi"}},  # no _meta
        },
        send_notification=sent.append,
    )
    assert not [m for m in sent if m.get("method") == "notifications/progress"]


def test_tools_call_route_is_zero_token(providers, env, quota):
    pool = _pool(providers, env, quota)
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "free_llm_route",
                "arguments": {"prompt": "hi", "routing": "quality"},
            },
        },
    )
    text = resp["result"]["content"][0]["text"]
    assert "difficulty" in text.lower()
    assert "alpha/" in text  # a ranked candidate
    assert pool.stats_snapshot()["requests"] == 0  # explained without spending a token


def test_tools_call_stats(providers, env, quota):
    pool = _pool(providers, env, quota)
    pool.ask("hi")  # record some usage
    resp = handle_message(
        pool,
        {"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "free_llm_stats"}},
    )
    text = resp["result"]["content"][0]["text"]
    assert "lifetime" in text.lower()
    assert "Claude Opus 4.8" in text


def test_tools_call_ask_missing_prompt(providers, env, quota):
    pool = _pool(providers, env, quota)
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "free_llm_ask", "arguments": {}},
        },
    )
    assert resp["result"]["isError"] is True


def test_tools_call_models(providers, env, quota):
    pool = _pool(providers, env, quota)
    resp = handle_message(
        pool,
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "free_llm_models"}},
    )
    text = resp["result"]["content"][0]["text"]
    assert "alpha/alpha-small" in text


def test_unknown_method_errors(providers, env, quota):
    pool = _pool(providers, env, quota)
    resp = handle_message(pool, {"jsonrpc": "2.0", "id": 6, "method": "bogus/method"})
    assert resp["error"]["code"] == -32601


def test_ask_failover_in_tool(providers, env, quota):
    post = make_post({"alpha.test": (500, {}), "beta.test": (200, openai_body("from beta"))})
    pool = _pool(providers, env, quota, post=post)
    resp = handle_message(
        pool,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "free_llm_ask", "arguments": {"prompt": "hi", "provider": "alpha"}},
        },
    )
    # alpha 500s and there's no beta in provider filter → tool error surfaced
    assert resp["result"]["isError"] is True


def test_parse_error_returns_neg32700():
    # serve_stdio emits a JSON-RPC parse error for invalid JSON
    import io

    from freellmpool.mcp_server import serve_stdio

    out = io.StringIO()
    import sys

    old = sys.stdout
    sys.stdin_backup = sys.stdin
    sys.stdin = io.StringIO("{ not json\n")
    sys.stdout = out
    try:
        from freellmpool.router import Pool

        serve_stdio(Pool([], env={}))
    finally:
        sys.stdout = old
        sys.stdin = sys.stdin_backup
    import json

    resp = json.loads(out.getvalue().strip())
    assert resp["error"]["code"] == -32700
    assert resp["id"] is None


def test_invalid_request_missing_method(providers, env, quota):
    from freellmpool.mcp_server import handle_message
    from freellmpool.router import Pool

    pool = Pool(providers, quota=quota, env=env)
    resp = handle_message(pool, {"jsonrpc": "2.0", "id": 5})  # has id, no method
    assert resp["error"]["code"] == -32600
    assert resp["id"] == 5
    # a non-dict is an invalid request with id null
    assert handle_message(pool, 42)["error"]["code"] == -32600


def test_batch_returns_single_json_array(providers, env, quota):
    import io
    import json
    import sys

    from freellmpool.mcp_server import serve_stdio
    from freellmpool.router import Pool

    batch = json.dumps(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},  # no reply
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
    )
    out = io.StringIO()
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin = io.StringIO(batch + "\n")
    sys.stdout = out
    try:
        serve_stdio(Pool(providers, quota=quota, env=env))
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1  # one line, one JSON-RPC array (not 2 separate objects)
    arr = json.loads(lines[0])
    assert isinstance(arr, list) and len(arr) == 2  # notification omitted
    assert {r["id"] for r in arr} == {1, 2}
