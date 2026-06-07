"""Estimate the money you *didn't* spend by routing through free tiers.

The reference point is **Claude Opus 4.8** list pricing — a frontier-model rate — so
the "avoided cost" reflects what these tokens would have cost on a top-tier paid model.
The label always says "avoided cost", never "earnings" — it's a fun, honest metric
(it states the baseline so the number is interpretable, not inflated by sleight of hand).
"""

from __future__ import annotations

# Claude Opus 4.8 list price (USD per token). A frontier-model reference point.
_OPUS_INPUT = 15.00 / 1_000_000
_OPUS_OUTPUT = 75.00 / 1_000_000

# Human-readable baseline, shown alongside the figure so the number is honest.
BASELINE_LABEL = "Claude Opus 4.8 rates"


def usd_saved(prompt_tokens: int | None, completion_tokens: int | None) -> float:
    """USD this many tokens would have cost on Claude Opus 4.8."""
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    return pt * _OPUS_INPUT + ct * _OPUS_OUTPUT


def format_saved(prompt_tokens: int | None, completion_tokens: int | None) -> str:
    amount = usd_saved(prompt_tokens, completion_tokens)
    if amount < 0.01:
        return f"~${amount:.4f} not spent ({BASELINE_LABEL})"
    return f"~${amount:,.2f} not spent ({BASELINE_LABEL})"
