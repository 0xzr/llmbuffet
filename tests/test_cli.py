"""CLI helpers that don't need network."""

from __future__ import annotations

from freellmpool.cli import _strip_fences


def test_strip_plain_json():
    assert _strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fenced_json():
    assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_bare_fence():
    assert _strip_fences("```\nhello\n```") == "hello"


def test_cli_capacity_status_smoke(monkeypatch, capsys):
    from freellmpool.cli import main

    monkeypatch.setenv("FREELLMPOOL_KEYS_PATH", "/tmp/freellmpool-test-missing-keys.toml")
    assert main(["capacity", "status", "--target", "1", "--no-catalog-sync"]) == 0
    out = capsys.readouterr().out
    assert "LLM capacity:" in out


def test_cli_keys_checklist_smoke(monkeypatch, capsys):
    from freellmpool.cli import main

    monkeypatch.setenv("FREELLMPOOL_KEYS_PATH", "/tmp/freellmpool-test-missing-keys.toml")
    assert main(["keys", "checklist", "--target", "1"]) == 0
    out = capsys.readouterr().out
    assert "healthy providers" in out or "Manual key checklist" in out


def test_cli_providers_health_smoke(monkeypatch, capsys):
    from freellmpool.cli import main

    monkeypatch.setattr(
        "freellmpool.cli.cmd_providers_health",
        lambda args: print("health smoke") or 0,
    )
    assert main(["providers", "health"]) == 0
    assert "health smoke" in capsys.readouterr().out


def test_dashboard_contains_capacity(monkeypatch):
    from freellmpool.models import Model, Provider
    from freellmpool.proxy import _dashboard_html
    from freellmpool.router import Pool

    provider = Provider(
        id="demo",
        label="Demo",
        adapter="openai",
        base_url="https://example.test/v1",
        auth="none",
        models=(Model("model"),),
    )
    html = _dashboard_html(Pool([provider]))
    assert "healthy providers" in html
    assert "capacity" in html
    assert "demo" in html
