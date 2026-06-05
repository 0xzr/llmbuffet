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
