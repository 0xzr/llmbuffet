#!/usr/bin/env python3
"""Local hot-path benchmarks for routing/cache/quota/proxy-free operations.

This intentionally avoids network and benchmark dependencies. It prints JSON so
nightly/manual CI can retain comparable numbers without failing normal PRs over
machine variance.
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from freellmpool.cache import Cache  # noqa: E402
from freellmpool.client import HTTPResult  # noqa: E402
from freellmpool.models import Model, Provider  # noqa: E402
from freellmpool.quota import QuotaStore  # noqa: E402
from freellmpool.router import Pool  # noqa: E402


def _providers(n_providers: int = 32, n_models: int = 12) -> list[Provider]:
    return [
        Provider(
            id=f"p{i}",
            label=f"P{i}",
            adapter="openai",
            base_url=f"https://p{i}.test/v1",
            auth="none",
            models=tuple(Model(f"m{j}", rpd=1000) for j in range(n_models)),
        )
        for i in range(n_providers)
    ]


def _post(url, headers, body, timeout):
    return HTTPResult(
        200,
        {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        },
        "ok",
    )


def _time(fn, iterations: int) -> dict:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return {
        "iterations": iterations,
        "mean_ms": round(statistics.mean(samples), 4),
        "p95_ms": round(sorted(samples)[int(iterations * 0.95) - 1], 4),
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        quota = QuotaStore(path=root / "quota.json", flush_every=1000)
        cache = Cache(ttl=3600, path=root / "cache.db", max_entries=1000)
        pool = Pool(_providers(), quota=quota, env={}, post=_post, cache=cache, routing="spread")
        messages = [{"role": "user", "content": "hello"}]

        results = {
            "rank_targets_large_catalog": _time(lambda: pool.rank_targets(messages), 1000),
            "chat_cache_hit": _time(lambda: pool.chat(messages), 500),
            "quota_batched_record": _time(lambda: quota.record("p0", "m0"), 2000),
            "cache_get_put": _time(
                lambda: (cache.put("bench", {"text": "ok"}), cache.get("bench")),
                1000,
            ),
        }
        quota.flush()
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
