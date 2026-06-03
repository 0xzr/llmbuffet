from __future__ import annotations

from freellmpool.savings import format_saved, usd_saved


def test_usd_saved_gpt4o_rates():
    # 1M input @ $2.50 + 1M output @ $10.00 = $12.50
    assert usd_saved(1_000_000, 1_000_000) == 12.50
    assert usd_saved(0, 0) == 0.0
    assert usd_saved(None, None) == 0.0


def test_format_saved():
    assert "not paid to OpenAI" in format_saved(10, 10)
    assert format_saved(1_000_000, 1_000_000).startswith("~$12.50")
