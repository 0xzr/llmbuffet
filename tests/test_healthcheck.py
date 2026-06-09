from __future__ import annotations

from helpers import make_post

from freellmpool.healthcheck import HealthRow, render_health_table, run_healthcheck
from freellmpool.models import Model, Provider
from freellmpool.router import Pool


def test_render_health_table_empty():
    assert render_health_table([]) == "No configured providers to check."


def test_render_health_table_rows():
    text = render_health_table([HealthRow("demo/model", "ok", 12.0, "responded")])
    assert "demo/model" in text
    assert "ok" in text
    assert "1/1 providers ok" in text


def test_run_healthcheck_success():
    provider = Provider(
        id="demo",
        label="Demo",
        adapter="openai",
        base_url="https://example.test/v1",
        auth="none",
        models=(Model("model"),),
    )

    pool = Pool([provider], post=make_post({}))
    rows = run_healthcheck(pool, timeout=1)
    assert len(rows) == 1
    assert rows[0].ok
    assert rows[0].target == "demo/model"


def test_run_healthcheck_uses_discovered_model_when_catalog_is_stale(monkeypatch):
    from freellmpool import benchmark

    provider = Provider(
        id="hugging_face",
        label="Hugging Face",
        adapter="openai",
        base_url="https://router.huggingface.co/v1",
        auth="none",
        models=(Model("meta-llama/Meta-Llama-3.1-8B-Instruct"),),
    )
    post = make_post({})

    monkeypatch.setattr(
        benchmark,
        "discover_openai_models",
        lambda *args, **kwargs: ["Qwen/Qwen3-Coder-30B-A3B-Instruct"],
    )

    rows = run_healthcheck(Pool([provider], post=post), timeout=1)

    assert rows[0].ok
    assert rows[0].target == "hugging_face/Qwen/Qwen3-Coder-30B-A3B-Instruct"
    assert post.calls[0]["body"]["model"] == "Qwen/Qwen3-Coder-30B-A3B-Instruct"


def test_run_healthcheck_falls_back_to_catalog_model_when_discovery_is_empty(monkeypatch):
    from freellmpool import benchmark

    provider = Provider(
        id="demo",
        label="Demo",
        adapter="openai",
        base_url="https://example.test/v1",
        auth="none",
        models=(Model("catalog-model"),),
    )
    post = make_post({})

    monkeypatch.setattr(
        benchmark,
        "discover_openai_models",
        lambda *args, **kwargs: [],
    )

    rows = run_healthcheck(Pool([provider], post=post), timeout=1)

    assert rows[0].ok
    assert rows[0].target == "demo/catalog-model"
    assert post.calls[0]["body"]["model"] == "catalog-model"


def test_run_healthcheck_does_not_post_pinned_model_missing_from_discovery(monkeypatch):
    from freellmpool import benchmark

    provider = Provider(
        id="demo",
        label="Demo",
        adapter="openai",
        base_url="https://example.test/v1",
        auth="none",
        models=(Model("stale"),),
    )
    post = make_post({})

    monkeypatch.setattr(
        benchmark,
        "discover_openai_models",
        lambda *args, **kwargs: ["live"],
    )

    rows = run_healthcheck(Pool([provider], post=post), model="stale", timeout=1)

    assert not rows[0].ok
    assert rows[0].target == "demo/stale"
    assert rows[0].note == "model not listed by /models: stale"
    assert post.calls == []


def test_run_healthcheck_failure_and_rate_limit(monkeypatch):
    from freellmpool import healthcheck

    class FakeRow:
        def __init__(self, target: str, error: str):
            self.target = target
            self.ok = False
            self.latency_ms = None
            self.tokens = None
            self.error = error

    monkeypatch.setattr(
        healthcheck,
        "benchmark",
        lambda *args, **kwargs: [
            FakeRow("demo/a", "429 Too Many Requests"),
            FakeRow("demo/b", "500 Internal Error"),
        ],
    )

    rows = run_healthcheck(Pool([]), timeout=1)

    assert [row.status for row in rows] == ["rate_limited", "fail"]
    assert not rows[0].ok
    assert not rows[1].ok


def test_run_healthcheck_notes_for_tokens_and_empty_tokens(monkeypatch):
    from freellmpool import healthcheck

    class FakeRow:
        def __init__(self, target: str, tokens):
            self.target = target
            self.ok = True
            self.latency_ms = 10.0
            self.tokens = tokens
            self.error = None

    monkeypatch.setattr(
        healthcheck,
        "benchmark",
        lambda *args, **kwargs: [FakeRow("demo/a", 123), FakeRow("demo/b", None)],
    )

    text = render_health_table(run_healthcheck(Pool([]), timeout=1))

    assert "123 tok" in text
    assert "responded" in text


def test_render_health_table_uses_first_error_line_and_truncates_note():
    first_line = "X" * 90
    text = render_health_table([HealthRow("demo/model", "fail", None, first_line + "\nsecond")])

    assert "second" not in text
    assert "X" * 80 in text
    assert "X" * 81 not in text
