from __future__ import annotations

from freellmpool.agents import AGENTS, list_agents, render


def test_list_agents():
    out = list_agents()
    for a in ("codex", "aider", "cline", "continue", "cursor", "opencode"):
        assert a in out


def test_render_known():
    out = render("aider")
    assert out is not None
    assert "openai/auto" in out
    assert "freellmpool proxy" in out


def test_render_unknown():
    assert render("bogus") is None


def test_all_agents_render():
    for name in AGENTS:
        assert render(name)
