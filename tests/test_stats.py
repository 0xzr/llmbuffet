"""Persistent lifetime StatsStore + Pool write-through."""

from __future__ import annotations

from datetime import UTC, datetime

from helpers import make_post

from freellmpool.router import Pool
from freellmpool.stats import StatsStore


def test_stats_persists_and_accumulates_across_instances(tmp_path):
    p = tmp_path / "stats.json"
    s1 = StatsStore(p)
    s1.add(requests=2, prompt_tokens=100, completion_tokens=50)
    s1.add(requests=1, prompt_tokens=10, completion_tokens=5, cache_hits=1)

    s2 = StatsStore(p)  # a fresh instance reads from disk
    snap = s2.snapshot()
    assert snap["requests"] == 3
    assert snap["prompt_tokens"] == 110
    assert snap["completion_tokens"] == 55
    assert snap["cache_hits"] == 1
    assert snap["first_seen"]  # set on the first add


def test_stats_ignores_unknown_and_nonpositive(tmp_path):
    s = StatsStore(tmp_path / "s.json")
    s.add(requests=1, bogus=99, prompt_tokens=0, completion_tokens=-5)
    snap = s.snapshot()
    assert snap["requests"] == 1
    assert "bogus" not in snap
    assert snap["prompt_tokens"] == 0
    assert snap["completion_tokens"] == 0


def test_first_seen_uses_clock(tmp_path):
    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    s = StatsStore(tmp_path / "s.json", clock=lambda: fixed)
    s.add(requests=1)
    assert s.snapshot()["first_seen"] == "2026-01-02T03:04:05Z"


def test_corrupt_file_does_not_crash(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ not json", encoding="utf-8")
    s = StatsStore(p)  # tolerates a garbled file
    assert s.snapshot()["requests"] == 0
    s.add(requests=1)
    assert s.snapshot()["requests"] == 1


def test_stats_save_failure_is_best_effort(tmp_path, monkeypatch):
    s = StatsStore(tmp_path / "s.json")
    monkeypatch.setattr(s, "_save", lambda: (_ for _ in ()).throw(OSError("disk full")))
    s.add(requests=1)  # must not raise
    assert not (tmp_path / "s.json").exists()


def test_pool_writes_through_to_stats_store(providers, env, quota, tmp_path):
    store = StatsStore(tmp_path / "s.json")
    pool = Pool(providers, quota=quota, env=env, post=make_post({}), stats_store=store)
    pool.ask("hello")
    assert store.snapshot()["requests"] >= 1
    assert pool.lifetime_stats()["requests"] >= 1


def test_pool_without_store_reports_session_lifetime(providers, env, quota):
    pool = Pool(providers, quota=quota, env=env, post=make_post({}))
    pool.ask("hi")
    life = pool.lifetime_stats()
    assert life["requests"] >= 1
    assert life["first_seen"] is None


# ---- durability: across installs + backwards/forwards compatibility ----


def test_reads_old_minimal_file_and_stamps_version(tmp_path):
    import json

    p = tmp_path / "s.json"
    p.write_text('{"requests": 5}', encoding="utf-8")  # a pre-version, minimal file
    s = StatsStore(p)
    snap = s.snapshot()
    assert snap["requests"] == 5
    assert snap["prompt_tokens"] == 0  # missing field defaults to 0
    s.add(requests=1)
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["requests"] == 6
    assert saved["version"] == 1  # stamped on first write


def test_preserves_unknown_future_fields_on_roundtrip(tmp_path):
    import json

    p = tmp_path / "s.json"
    p.write_text('{"requests": 2, "version": 999, "future_field": "keep me"}', encoding="utf-8")
    s = StatsStore(p)
    assert s.snapshot()["requests"] == 2
    s.add(prompt_tokens=10)
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["future_field"] == "keep me"  # a newer version's field is not dropped
    assert saved["version"] == 999  # nor its (higher) version stamp downgraded
    assert saved["prompt_tokens"] == 10


def test_corrupt_file_quarantined_not_silently_reset(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ this is : not json", encoding="utf-8")
    s = StatsStore(p)
    # a READ returns zeros without mutating the file
    assert s.snapshot()["requests"] == 0
    assert p.read_text(encoding="utf-8").startswith("{ this is")
    # the next WRITE preserves the garbled file (quarantine) instead of clobbering it
    s.add(requests=3)
    assert s.snapshot()["requests"] == 3
    corrupt = p.with_suffix(p.suffix + ".corrupt")
    assert corrupt.exists()
    assert "not json" in corrupt.read_text(encoding="utf-8")


def test_default_path_is_install_independent(monkeypatch):
    from freellmpool.stats import default_stats_path

    monkeypatch.delenv("FREELLMPOOL_STATS_PATH", raising=False)
    p = default_stats_path()
    assert p.name == "stats.json"
    # user config dir, never inside site-packages → survives pip upgrade/reinstall
    assert ".config/freellmpool" in str(p)
    assert "site-packages" not in str(p)
    monkeypatch.setenv("FREELLMPOOL_STATS_PATH", "/tmp/x/custom.json")
    assert str(default_stats_path()) == "/tmp/x/custom.json"
