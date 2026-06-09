"""Measure each configured provider with a tiny prompt and report a table.

Backs ``freellmpool benchmark``. It calls the client directly — one model per
provider (the first enabled one, or a pinned ``model``) — so it measures raw
provider latency, and records the results into the given pool's
:class:`~freellmpool.metrics.Metrics`. In a long-running process (a library
embedding, or a proxy that calls ``benchmark(pool)`` on its own pool) that warms
``routing="fast"``; the one-shot ``freellmpool benchmark`` CLI exits afterward, so
there it only serves as a latency report.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import client as _client
from .catalog import discover_openai_models
from .errors import ProviderHTTPError
from .router import Pool

_PROMPT = "Reply with the single word: ok"


@dataclass
class BenchRow:
    target: str
    ok: bool
    latency_ms: float | None
    tokens: int | None
    error: str | None


def _pick_model(provider, model: str | None) -> str | None:
    if model:
        m = provider.model(model)
        return m.name if m else None
    for m in provider.models:
        if m.enabled:
            return m.name
    return provider.models[0].name if provider.models else None


def _pick_model_for_health(
    provider, model: str | None, pool: Pool, timeout: float
) -> tuple[str | None, str | None]:
    """Pick a probe model, preferring ids currently listed by /models.

    The packaged/user catalog can drift. Health checks should report real health,
    not burn a request on a retired model when the provider exposes discovery.
    """
    discovered: set[str] | None = None
    if provider.adapter == "openai":
        try:
            discovered = set(
                discover_openai_models(
                    provider.base_url,
                    api_key=provider.api_key(pool.env),
                    timeout=min(timeout, 10.0),
                )
            )
        except ValueError:
            discovered = None

    if model:
        if discovered is not None and model not in discovered:
            return None, f"model not listed by /models: {model}"
        picked = provider.model(model)
        return (picked.name if picked else model), None

    if discovered:
        for m in provider.models:
            if m.enabled and m.name in discovered:
                return m.name, None
        return sorted(discovered)[0], None

    return _pick_model(provider, model), None


def benchmark(
    pool: Pool,
    *,
    model: str | None = None,
    providers=None,
    prompt: str = _PROMPT,
    max_tokens: int = 16,
    timeout: float = 30.0,
    workers: int = 8,
) -> list[BenchRow]:
    """Time one call per configured provider, concurrently. Returns rows sorted
    fastest-first (successes), then failures."""
    include = {p.strip() for p in providers} if providers else None
    targets: list[tuple] = []
    skipped: list[BenchRow] = []
    for p in pool.providers:
        if include is not None and p.id not in include:
            continue
        name, skip_note = _pick_model_for_health(p, model, pool, timeout)
        if skip_note:
            skipped.append(BenchRow(f"{p.id}/{model}", False, None, None, skip_note))
            continue
        if name:
            targets.append((p, name))

    def run(item) -> BenchRow:
        provider, mname = item
        key = f"{provider.id}/{mname}"
        started = time.monotonic()
        try:
            reply = _client.call(
                provider,
                mname,
                [{"role": "user", "content": prompt}],
                api_key=provider.api_key(pool.env),
                env=pool.env,
                max_tokens=max_tokens,
                temperature=0.0,
                timeout=timeout,
                post=pool._post,
            )
        except ProviderHTTPError as exc:
            pool.metrics.record_failure(key, str(exc))
            return BenchRow(key, False, None, None, str(exc))
        except Exception as exc:  # noqa: BLE001 — report it, don't abort the sweep
            pool.metrics.record_failure(key, f"{type(exc).__name__}: {exc}")
            return BenchRow(key, False, None, None, f"{type(exc).__name__}: {exc}")
        elapsed = (time.monotonic() - started) * 1000.0
        if reply.text:
            pool.metrics.record_success(key, elapsed)
            return BenchRow(key, True, elapsed, reply.completion_tokens, None)
        pool.metrics.record_failure(key, "empty completion")
        return BenchRow(key, False, None, None, "empty completion")

    if not targets:
        return skipped
    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as ex:
        rows = list(ex.map(run, targets))
    rows.extend(skipped)
    rows.sort(key=lambda r: (not r.ok, r.latency_ms if r.latency_ms is not None else 1e18))
    return rows


def render_table(rows: list[BenchRow]) -> str:
    """Format benchmark rows as a fixed-width table."""
    if not rows:
        return "No configured providers to benchmark (set an API key first)."
    width = max(len(r.target) for r in rows)
    lines = [f"  {'provider/model':<{width}}  {'status':<6}  {'latency':>9}  note"]
    for r in rows:
        if r.ok:
            lat = f"{r.latency_ms:,.0f} ms" if r.latency_ms is not None else "-"
            note = f"{r.tokens} tok" if r.tokens else ""
            lines.append(f"  {r.target:<{width}}  {'ok':<6}  {lat:>9}  {note}")
        else:
            err_lines = (r.error or "").splitlines()
            note = err_lines[0][:60] if err_lines else ""
            lines.append(f"  {r.target:<{width}}  {'FAIL':<6}  {'-':>9}  {note}")
    ok = sum(1 for r in rows if r.ok)
    lines.append(f"\n  {ok}/{len(rows)} providers responded")
    return "\n".join(lines)
