"""Configuration loading: provider catalog + user overrides.

Resolution order for the provider catalog:

1. The packaged ``providers.toml`` (the built-in catalog).
2. A user catalog at ``$LLMBUFFET_CONFIG`` or
   ``~/.config/llmbuffet/providers.toml`` if present. Providers with the same
   ``id`` override the built-ins; new ids are appended.

Only providers whose API key (and any extra env vars) are present in the
environment are returned by :func:`configured_providers`.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .models import Model, Provider

_PACKAGED_CATALOG = Path(__file__).with_name("providers.toml")


def _user_catalog_path() -> Path | None:
    override = os.environ.get("LLMBUFFET_CONFIG")
    if override:
        return Path(override).expanduser()
    default = Path.home() / ".config" / "llmbuffet" / "providers.toml"
    return default if default.exists() else None


def _parse_catalog(data: dict) -> list[Provider]:
    providers: list[Provider] = []
    for row in data.get("provider", []):
        models = tuple(
            Model(name=m["name"], rpd=int(m.get("rpd", 0))) for m in row.get("models", [])
        )
        providers.append(
            Provider(
                id=row["id"],
                label=row.get("label", row["id"]),
                adapter=row.get("adapter", "openai"),
                base_url=row["base_url"].rstrip("/"),
                key_env=row.get("key_env"),
                auth=row.get("auth", "bearer"),
                key_optional=bool(row.get("key_optional", False)),
                models=models,
                extra_env=tuple(row.get("extra_env", [])),
            )
        )
    return providers


def load_catalog(path: Path | None = None) -> list[Provider]:
    """Load the full provider catalog (built-ins + user overrides)."""
    base_path = path or _PACKAGED_CATALOG
    with base_path.open("rb") as fh:
        providers = _parse_catalog(tomllib.load(fh))

    if path is None:
        user_path = _user_catalog_path()
        if user_path is not None:
            with user_path.open("rb") as fh:
                user_providers = _parse_catalog(tomllib.load(fh))
            by_id = {p.id: p for p in providers}
            for up in user_providers:
                by_id[up.id] = up
            providers = list(by_id.values())

    return providers


def configured_providers(
    catalog: list[Provider] | None = None,
    env: dict[str, str] | None = None,
) -> list[Provider]:
    """Return only providers that have a usable API key in the environment."""
    catalog = catalog if catalog is not None else load_catalog()
    env = env if env is not None else dict(os.environ)
    return [p for p in catalog if p.is_configured(env)]
