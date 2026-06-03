"""Shared fixtures: fake providers, env, and a fixed-clock quota store."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from llmbuffet.models import Model, Provider
from llmbuffet.quota import QuotaStore


@pytest.fixture
def providers() -> list[Provider]:
    return [
        Provider(
            id="alpha",
            label="Alpha",
            adapter="openai",
            base_url="https://alpha.test/v1",
            key_env="ALPHA_KEY",
            models=(Model("alpha-small", rpd=2), Model("alpha-big", rpd=0)),
        ),
        Provider(
            id="beta",
            label="Beta",
            adapter="openai",
            base_url="https://beta.test/v1",
            key_env="BETA_KEY",
            models=(Model("beta-1", rpd=0),),
        ),
        Provider(
            id="gee",
            label="Gee",
            adapter="gemini",
            base_url="https://gee.test/v1beta",
            key_env="GEE_KEY",
            models=(Model("gee-flash", rpd=0),),
        ),
        Provider(
            id="free",
            label="Keyless",
            adapter="openai",
            base_url="https://free.test/v1",
            auth="none",
            models=(Model("free-1", rpd=0),),
        ),
    ]


@pytest.fixture
def env() -> dict[str, str]:
    return {"ALPHA_KEY": "a", "BETA_KEY": "b", "GEE_KEY": "g"}


@pytest.fixture
def quota(tmp_path) -> QuotaStore:
    clock = lambda: datetime(2026, 6, 2, 12, 0, tzinfo=UTC)  # noqa: E731
    return QuotaStore(path=tmp_path / "quota.json", clock=clock)
