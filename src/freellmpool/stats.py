"""Persistent lifetime usage totals behind the "served free / avoided cost" metric.

Unlike :mod:`quota` (per-day, advisory, reset at UTC midnight), this accumulates
*monotonically across restarts* so the tokens-served / avoided-cost figure grows
over a pool's whole lifetime — the number behind ``freellmpool stats``, the SVG
badge, and the dashboard. Same robustness as the quota store: a JSON file, a
cross-process flock around the read-modify-write, and an atomic ``os.replace``.

Durability contract (the number must never silently reset):

* **Across sessions / restarts** — it's a disk file, reloaded on every read.
* **Across installs / upgrades** — it lives in the *user config dir*
  (``~/.config/freellmpool/stats.json``, override with ``FREELLMPOOL_STATS_PATH``),
  never inside the installed package, so ``pip install --upgrade`` / reinstall
  leaves it untouched.
* **Backwards/forwards compatible** — the schema is a flat JSON object that only
  ever *gains* fields. Readers default missing fields to 0, ignore unknown ones,
  and **preserve them on write**, so an older freellmpool won't drop a newer one's
  fields and vice-versa. A ``version`` stamp marks the creating schema for any
  future migration; a corrupt/garbled file degrades to zero rather than crashing.

Tiny and dependency-free so tests can drive it with an explicit path + fixed clock.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

try:
    import fcntl  # POSIX advisory file locks
except ImportError:  # pragma: no cover - non-POSIX (Windows)
    fcntl = None

# The cumulative counters we persist. Anything else passed to add() is ignored,
# so a new _bump_stats key can't silently corrupt the file.
_FIELDS = ("requests", "prompt_tokens", "completion_tokens", "cache_hits")
# Schema version stamped into the file. Bump only on a *breaking* layout change
# (additive fields don't need it); a future reader can branch on it to migrate.
_SCHEMA = 1


def default_stats_path() -> Path:
    override = os.environ.get("FREELLMPOOL_STATS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "freellmpool" / "stats.json"


class StatsStore:
    """JSON-backed lifetime counters (monotonic; never reset)."""

    def __init__(self, path: Path | str | None = None, clock: Callable[[], datetime] | None = None):
        self.path = Path(path) if path is not None else default_stats_path()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()  # the proxy is threaded; guard read-modify-write
        self._data: dict = self._load()

    def _load(self) -> dict:
        """Parsed file as a dict, or {} if missing/unreadable/garbled. Pure: a read
        never mutates the file (so a corrupt file read by snapshot() returns zeros
        without touching disk)."""
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return {}

    def _load_for_write(self) -> dict:
        """Like _load, but if the file EXISTS yet is corrupt/garbled, quarantine it
        (rename to .corrupt) before returning {} — so the next add() can never
        silently overwrite a present-but-unreadable file and zero the lifetime
        total. A missing file just starts fresh; a recoverable file loads normally."""
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, OSError, ValueError):
            pass
        # Present but unparseable / not an object: preserve it loudly, don't clobber.
        with contextlib.suppress(OSError):
            if self.path.exists():
                self.path.replace(self.path.with_suffix(self.path.suffix + ".corrupt"))
        return {}

    @contextlib.contextmanager
    def _file_lock(self):
        """Cross-process exclusive lock around a read-modify-write, so proxy + CLI +
        MCP sharing one file can't clobber each other. No-op where flock is absent."""
        if fcntl is None:
            yield
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        try:
            fh = open(lock_path, "w")
        except OSError:
            yield  # best-effort — fall back to in-process locking only
            return
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f"{self.path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

    def add(self, **deltas: int) -> None:
        """Add positive integer deltas to the lifetime counters and persist.

        Unknown keys are ignored. Persistence failures are swallowed — a lifetime
        metric must never abort an otherwise-successful completion."""
        clean = {k: int(v) for k, v in deltas.items() if k in _FIELDS and int(v or 0) > 0}
        if not clean:
            return
        with self._lock, self._file_lock():
            # reload so concurrent processes' adds survive; quarantine (never clobber)
            # a present-but-corrupt file so the lifetime total can't silently reset.
            self._data = self._load_for_write()
            for key, value in clean.items():
                self._data[key] = int(self._data.get(key, 0)) + value
            # setdefault (never overwrite) so an older binary can't downgrade a
            # newer file's stamp, and any unknown fields are preserved on write.
            self._data.setdefault("first_seen", self._iso_now())
            self._data.setdefault("version", _SCHEMA)
            try:
                self._save()
            except OSError:
                pass

    def snapshot(self) -> dict:
        """Lifetime counters (+ first_seen), reloaded from disk so a long-running
        proxy reflects increments other processes made."""
        with self._lock:
            self._data = self._load()
            out: dict = {k: int(self._data.get(k, 0)) for k in _FIELDS}
            out["first_seen"] = self._data.get("first_seen")
            return out

    def _iso_now(self) -> str:
        return self._clock().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
