"""In-process per-target performance metrics: latency and success rate.

Every (provider, model) call records a success (with its wall-clock latency) or a
failure here. The router reads it back to keep load off providers that are slow or
currently failing, and ``freellmpool benchmark`` prints it as a table.

This is live routing signal, not persistence: it lives in memory, is thread-safe,
and resets on restart. Latency is smoothed with an EWMA so one slow call doesn't
banish a provider and one fast call doesn't crown it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

_ALPHA = 0.3  # EWMA weight on the newest latency sample
_FAIL_MIN_SAMPLES = 3  # don't judge a target failing until it has a few calls
_FAIL_RATE = 0.5  # success rate below this (with enough samples) = "failing"
# Routing penalty for a target we've never measured. Sits *behind* any healthy
# measured target (whose penalty is latency_s * 0.1, i.e. < 0.5 under ~5s) but
# *ahead* of a failing one (penalty >= ~5), so `fast` routing prefers known-fast
# providers, samples unknowns next, and tries failing ones last.
_UNKNOWN_SCORE = 0.5


@dataclass
class Stat:
    """Accumulated metrics for one (provider, model) target."""

    ok: int = 0
    fail: int = 0
    ewma_ms: float | None = None  # smoothed latency of successful calls
    last_ms: float | None = None
    last_error: str | None = None

    @property
    def total(self) -> int:
        return self.ok + self.fail

    @property
    def success_rate(self) -> float:
        return 1.0 if self.total == 0 else self.ok / self.total

    @property
    def failing(self) -> bool:
        """True once a target has enough samples and is mostly failing."""
        return self.total >= _FAIL_MIN_SAMPLES and self.success_rate < _FAIL_RATE


class Metrics:
    """Thread-safe store of per-target :class:`Stat`s."""

    def __init__(self, alpha: float = _ALPHA):
        self._alpha = alpha
        self._stats: dict[str, Stat] = {}
        self._lock = threading.Lock()

    def record_success(self, key: str, latency_ms: float) -> None:
        with self._lock:
            st = self._stats.setdefault(key, Stat())
            st.ok += 1
            st.last_ms = latency_ms
            st.ewma_ms = (
                latency_ms
                if st.ewma_ms is None
                else self._alpha * latency_ms + (1 - self._alpha) * st.ewma_ms
            )

    def record_failure(self, key: str, error: str = "") -> None:
        with self._lock:
            st = self._stats.setdefault(key, Stat())
            st.fail += 1
            st.last_error = (error[:200] or None) if error else st.last_error

    def get(self, key: str) -> Stat | None:
        with self._lock:
            st = self._stats.get(key)
            return None if st is None else _copy(st)

    def snapshot(self) -> dict[str, Stat]:
        with self._lock:
            return {k: _copy(v) for k, v in self._stats.items()}

    def failing(self, key: str) -> bool:
        with self._lock:
            st = self._stats.get(key)
            return bool(st and st.failing)

    def score(self, key: str) -> float:
        """Routing penalty for a target — lower is better.

        Unmeasured targets get a neutral baseline (:data:`_UNKNOWN_SCORE`) that
        sits behind healthy measured targets but ahead of failing ones. Known
        targets are penalized mostly by failure rate, with latency as a tiebreak.
        """
        with self._lock:
            return score_stat(self._stats.get(key))


def _copy(st: Stat) -> Stat:
    return Stat(st.ok, st.fail, st.ewma_ms, st.last_ms, st.last_error)


def score_stat(st: Stat | None) -> float:
    """Routing penalty for a copied :class:`Stat`; mirrors :meth:`Metrics.score`."""
    if st is None or st.total == 0:
        return _UNKNOWN_SCORE
    lat_s = (st.ewma_ms or 0.0) / 1000.0
    return (1.0 - st.success_rate) * 10.0 + min(lat_s, 10.0) * 0.1
