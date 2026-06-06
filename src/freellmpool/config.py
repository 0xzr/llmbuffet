"""Configuration loading: provider catalog + user overrides.

Resolution order for the provider catalog:

1. The packaged ``providers.toml`` (the built-in catalog).
2. A user catalog at ``$FREELLMPOOL_CONFIG`` or
   ``~/.config/freellmpool/providers.toml`` if present. Providers with the same
   ``id`` override the built-ins; new ids are appended.

Only providers whose API key (and any extra env vars) are present in the
environment are returned by :func:`configured_providers`.
"""

from __future__ import annotations

import os
import re
import tomllib
from functools import lru_cache
from pathlib import Path

from .models import Model, Provider

_PACKAGED_CATALOG = Path(__file__).with_name("providers.toml")

# Common OpenAI / Anthropic model names mapped to a free target, so existing
# code (which hardcodes e.g. "gpt-4o-mini") works against freellmpool unchanged.
# "auto" means "let the pool pick the least-used free provider". Override or add
# your own with env vars, e.g.  FREELLMPOOL_ALIAS_gpt-4o-mini=groq/llama-3.3-70b-versatile
_DEFAULT_ALIASES: dict[str, str] = {
    "gpt-4o-mini": "auto",
    "gpt-4o": "auto",
    "gpt-4.1": "auto",
    "gpt-4.1-mini": "auto",
    "gpt-4.1-nano": "auto",
    "gpt-4-turbo": "auto",
    "gpt-4": "auto",
    "gpt-3.5-turbo": "auto",
    "o1-mini": "auto",
    "o3-mini": "auto",
    "o4-mini": "auto",
    "claude-3-haiku-20240307": "auto",
    "claude-3-5-haiku-latest": "auto",
    "claude-3-5-sonnet-latest": "auto",
    "claude-3-7-sonnet-latest": "auto",
    "claude-3-opus-latest": "auto",
}

_ALIAS_ENV_PREFIX = "FREELLMPOOL_ALIAS_"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def resolve_alias(name: str, env: dict[str, str] | None = None) -> str:
    """Map a well-known model name to its free target. User env overrides win;
    unknown names pass through unchanged."""
    env = env if env is not None else dict(os.environ)
    target = _norm(name)
    # Sorted so that when two env vars normalize to the same alias, the winner is
    # deterministic rather than dict-iteration-order dependent.
    for key, value in sorted(env.items()):
        if key.startswith(_ALIAS_ENV_PREFIX) and _norm(key[len(_ALIAS_ENV_PREFIX) :]) == target:
            return value or name
    cfg_aliases = load_config_file(env).get("aliases", {})
    if name in cfg_aliases:
        return str(cfg_aliases[name])
    if name in _DEFAULT_ALIASES:
        return _DEFAULT_ALIASES[name]
    # Prefix fallback: any unknown OpenAI/Anthropic frontier name routes to a free
    # model, so e.g. Claude Code's "claude-sonnet-4-..." just works.
    low = name.lower()
    if low.startswith(("claude-", "claude ", "gpt-", "o1-", "o3-", "o4-", "chatgpt")):
        return "auto"
    return name


def known_aliases(env: dict[str, str] | None = None) -> list[str]:
    """Model aliases understood by :func:`resolve_alias`.

    Used by gateway model discovery so clients can choose a well-known Claude or
    OpenAI model name and still have the proxy resolve it to the free pool.
    """
    env = env if env is not None else dict(os.environ)
    return list(_known_aliases_cached(_alias_cache_key(env)))


def _alias_cache_key(env: dict[str, str]) -> tuple:
    """Stable cache key for alias discovery.

    Only alias-related env vars and config-file path metadata affect
    ``known_aliases``. File mtime/size keep gateway discovery fresh after config
    edits without re-reading TOML on every `/v1/models` request.
    """
    path = _config_file_path(env)
    try:
        stat = path.stat() if path is not None else None
    except OSError:
        stat = None
    config_sig = (
        str(path) if path is not None else "",
        stat.st_mtime_ns if stat is not None else 0,
        stat.st_size if stat is not None else 0,
    )
    env_aliases = tuple(
        sorted((k, v) for k, v in env.items() if k.startswith(_ALIAS_ENV_PREFIX))
    )
    return config_sig + (env_aliases,)


@lru_cache(maxsize=64)
def _known_aliases_cached(cache_key: tuple) -> tuple[str, ...]:
    path_str, _, _, env_aliases = cache_key
    aliases = set(_DEFAULT_ALIASES)
    if path_str:
        cfg = load_config_file({"FREELLMPOOL_CONFIG_FILE": path_str})
        aliases.update(str(k) for k in cfg.get("aliases", {}))
    aliases.update(k[len(_ALIAS_ENV_PREFIX) :] for k, _ in env_aliases)
    return tuple(sorted(aliases))


def _user_catalog_path() -> Path | None:
    override = os.environ.get("FREELLMPOOL_CONFIG")
    if override:
        return Path(override).expanduser()
    default = Path.home() / ".config" / "freellmpool" / "providers.toml"
    return default if default.exists() else None


def _config_file_path(env: dict[str, str]) -> Path | None:
    override = env.get("FREELLMPOOL_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    default = Path.home() / ".config" / "freellmpool" / "config.toml"
    return default if default.exists() else None


def load_config_file(env: dict[str, str] | None = None) -> dict:
    """Load the optional config.toml. Returns {} if none exists.

    Recognized tables:
        [keys]      PROVIDER_API_KEY = "..."   (provider key env vars)
        [aliases]   "gpt-4o-mini" = "auto"     (model name -> free target)
        [settings]  cooldown_seconds = 60, proxy_key = "...", host/port
    """
    env = env if env is not None else dict(os.environ)
    path = _config_file_path(env)
    if path is None:
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def effective_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Real environment with config-file ``[keys]`` filled in underneath, so
    actual env vars always win but config.toml provides defaults."""
    env = env if env is not None else dict(os.environ)
    keys = load_config_file(env).get("keys", {})
    merged = {str(k): str(v) for k, v in keys.items() if v}
    merged.update(env)
    return merged


def settings(env: dict[str, str] | None = None) -> dict:
    """The ``[settings]`` table from config.toml (or {})."""
    return load_config_file(env).get("settings", {})


def _maybe_int(value, *, positive: bool = False) -> int | None:
    """Best-effort int from possibly-bad input; None on failure (and, when
    ``positive``, on a non-positive value — so ``context = 0`` reads as unknown)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if positive and n <= 0:
        return None
    return n


def _parse_rows(rows: list) -> list[Provider]:
    """Parse provider rows tolerantly: a malformed row (missing id/base_url/name,
    bad int) is skipped, not fatal, so one typo in a user catalog can't brick the
    whole tool. The packaged catalog is valid, so this is a no-op for it."""
    providers: list[Provider] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id") or not row.get("base_url"):
            continue
        models = []
        for m in row.get("models", []):
            if not isinstance(m, dict) or not m.get("name"):
                continue
            models.append(
                Model(
                    name=str(m["name"]),
                    rpd=_maybe_int(m.get("rpd", 0)) or 0,
                    enabled=bool(m.get("enabled", True)),
                    context=_maybe_int(m.get("context"), positive=True),
                )
            )
        providers.append(
            Provider(
                id=str(row["id"]),
                label=str(row.get("label", row["id"])),
                adapter=str(row.get("adapter", "openai")),
                base_url=str(row["base_url"]).rstrip("/"),
                key_env=row.get("key_env"),
                auth=str(row.get("auth", "bearer")),
                key_optional=bool(row.get("key_optional", False)),
                models=tuple(models),
                extra_env=tuple(row.get("extra_env", [])),
            )
        )
    return providers


def _parse_catalog(data: dict) -> list[Provider]:
    return _parse_rows(data.get("provider", []))


def load_embedders(path: Path | None = None) -> list[Provider]:
    """Load the embedder catalog ([[embedder]] rows). Same shape as providers."""
    base_path = path or _PACKAGED_CATALOG
    with base_path.open("rb") as fh:
        return _parse_rows(tomllib.load(fh).get("embedder", []))


def configured_embedders(
    catalog: list[Provider] | None = None, env: dict[str, str] | None = None
) -> list[Provider]:
    catalog = catalog if catalog is not None else load_embedders()
    env = env if env is not None else dict(os.environ)
    return [p for p in catalog if p.is_configured(env)]


def load_catalog(path: Path | None = None) -> list[Provider]:
    """Load the full provider catalog (built-ins + user overrides)."""
    base_path = path or _PACKAGED_CATALOG
    with base_path.open("rb") as fh:
        providers = _parse_catalog(tomllib.load(fh))

    if path is None:
        user_path = _user_catalog_path()
        if user_path is not None:
            try:
                with user_path.open("rb") as fh:
                    user_providers = _parse_catalog(tomllib.load(fh))
            except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError, AttributeError):
                user_providers = []  # a broken user catalog must not brick the tool
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
