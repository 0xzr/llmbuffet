from __future__ import annotations

from freellmpool.savings import format_saved, usd_saved


def test_usd_saved_opus_rates():
    # 1M input @ $15 + 1M output @ $75 = $90.00 (Claude Opus 4.8 list pricing)
    assert usd_saved(1_000_000, 1_000_000) == 90.00
    assert usd_saved(0, 0) == 0.0
    assert usd_saved(None, None) == 0.0


def test_format_saved():
    assert "not spent" in format_saved(10, 10)
    assert "Claude Opus 4.8" in format_saved(10, 10)
    assert format_saved(1_000_000, 1_000_000).startswith("~$90.00")
