"""Estimate the money you *didn't* pay OpenAI by routing through free tiers.

Numbers are deliberately conservative (GPT-4o list pricing as of 2026) and the
label always says "avoided cost", never "earnings" — it's a fun, honest metric.
"""

from __future__ import annotations

# GPT-4o list price (USD per token). Conservative reference point.
_GPT4O_INPUT = 2.50 / 1_000_000
_GPT4O_OUTPUT = 10.00 / 1_000_000


def usd_saved(prompt_tokens: int | None, completion_tokens: int | None) -> float:
    """USD this many tokens would have cost on GPT-4o."""
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    return pt * _GPT4O_INPUT + ct * _GPT4O_OUTPUT


def format_saved(prompt_tokens: int | None, completion_tokens: int | None) -> str:
    amount = usd_saved(prompt_tokens, completion_tokens)
    if amount < 0.01:
        return f"~${amount:.4f} not paid to OpenAI (gpt-4o rates)"
    return f"~${amount:.2f} not paid to OpenAI (gpt-4o rates)"
