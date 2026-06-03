"""The Pool: provider selection and failover.

A :class:`Pool` holds the configured providers, a quota store, and the
strategy for ordering candidate (provider, model) targets. :meth:`ask` walks
that ordered list, calling each target until one succeeds, recording quota use
and per-day budgets as it goes.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from . import client as _client
from .cache import Cache
from .client import PostFn, StreamPostFn, default_post, default_stream_post
from .config import (
    configured_embedders,
    configured_providers,
    effective_env,
    load_catalog,
    load_embedders,
    settings,
)
from .errors import AllProvidersExhausted, NoProvidersConfigured, ProviderHTTPError
from .models import EmbedReply, Provider, Reply
from .quota import QuotaStore


@dataclass(frozen=True)
class Target:
    """A concrete (provider, model) pair the router can call."""

    provider: Provider
    model: str
    rpd: int

    @property
    def name(self) -> str:
        return f"{self.provider.id}/{self.model}"


class Pool:
    def __init__(
        self,
        providers: list[Provider],
        *,
        quota: QuotaStore | None = None,
        env: dict[str, str] | None = None,
        post: PostFn = default_post,
        cooldown_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
        embedders: list[Provider] | None = None,
        stream_post: StreamPostFn = default_stream_post,
        cache: Cache | None = None,
    ):
        self.providers = providers
        self.embedders = embedders or []
        self.quota = quota or QuotaStore()
        self.env = env if env is not None else dict(os.environ)
        self._post = post
        self._stream_post = stream_post
        self._cache = cache
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock or time.monotonic
        # provider_id -> monotonic time until which to deprioritize after a 429
        self._cooldown_until: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        # cumulative usage for the "$ saved vs OpenAI" metric
        self.stats = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cache_hits": 0}

    def _mark_cooldown(self, provider_id: str, now: float) -> None:
        until = now + self.cooldown_seconds
        with self._cooldown_lock:
            self._cooldown_until[provider_id] = max(
                self._cooldown_until.get(provider_id, 0.0), until
            )

    def _cooled(self, provider_id: str, now: float) -> bool:
        with self._cooldown_lock:
            return self._cooldown_until.get(provider_id, 0.0) > now

    # ---- construction -------------------------------------------------

    @classmethod
    def from_default_config(
        cls,
        *,
        env: dict[str, str] | None = None,
        quota: QuotaStore | None = None,
        post: PostFn = default_post,
    ) -> Pool:
        # Merge config.toml [keys] underneath the real environment.
        env = effective_env(env)
        providers = configured_providers(load_catalog(), env)
        embedders = configured_embedders(load_embedders(), env)
        cfg = settings(env)
        cooldown = float(cfg.get("cooldown_seconds", 60.0))
        ttl = float(env.get("FREELLMPOOL_CACHE_TTL") or cfg.get("cache_ttl", 0) or 0)
        cache = Cache(ttl) if ttl > 0 else None
        return cls(
            providers,
            quota=quota,
            env=env,
            post=post,
            cooldown_seconds=cooldown,
            embedders=embedders,
            cache=cache,
        )

    def embed(
        self,
        texts: str | list[str],
        *,
        model: str | None = None,
        providers: Iterable[str] | None = None,
        timeout: float = 90.0,
    ) -> EmbedReply:
        """Embed one or more texts, failing over across configured embedders."""
        inputs = [texts] if isinstance(texts, str) else list(texts)
        if not self.embedders:
            raise NoProvidersConfigured(
                "no embedder configured; set a key for one of: cohere, github, "
                "cloudflare, mistral, nvidia (see docs/ACCOUNTS.md)"
            )
        include = {p.strip() for p in providers} if providers else None
        attempts: list[tuple[str, str]] = []
        for emb in self.embedders:
            if include is not None and emb.id not in include:
                continue
            for m in emb.models:
                if model is not None and m.name != model:
                    continue
                try:
                    return _client.embed(
                        emb,
                        m.name,
                        inputs,
                        api_key=emb.api_key(self.env),
                        env=self.env,
                        timeout=timeout,
                        post=self._post,
                    )
                except Exception as exc:  # noqa: BLE001 — try the next embedder
                    attempts.append((f"{emb.id}/{m.name}", f"{type(exc).__name__}: {exc}"))
        raise AllProvidersExhausted(attempts)

    # ---- candidate ordering -------------------------------------------

    def _all_targets(
        self,
        include: Iterable[str] | None = None,
        model: str | None = None,
    ) -> list[Target]:
        include_set = {p.strip() for p in include} if include else None
        targets: list[Target] = []
        for provider in self.providers:
            if include_set is not None and provider.id not in include_set:
                continue
            for m in provider.models:
                if model is not None:
                    if m.name != model:
                        continue
                    # explicit model pin: allow it even if disabled by default
                elif not m.enabled:
                    continue  # auto routing skips off-by-default models
                targets.append(Target(provider, m.name, m.rpd))
        return targets

    def _order(self, targets: list[Target]) -> list[Target]:
        """Least-used-first ordering, so load spreads across free tiers.

        Targets already over their daily budget hint are pushed to the back
        (they may still be tried if everything else fails).
        """

        # One snapshot instead of a locked read per target (matters for large catalogs).
        snap = self.quota.snapshot()

        def sort_key(t: Target) -> tuple[int, int]:
            used = int(snap.get(f"{t.provider.id}::{t.model}", 0))
            over = 1 if (t.rpd > 0 and used >= t.rpd) else 0
            return (over, used)

        return sorted(targets, key=sort_key)

    # ---- the main entrypoint ------------------------------------------

    def ask(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        providers: Iterable[str] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 90.0,
        tools: list | None = None,
        tool_choice=None,
    ) -> Reply:
        """Send ``prompt`` to the first provider that succeeds.

        ``model`` / ``providers`` optionally restrict the candidate set.
        Raises :class:`NoProvidersConfigured` if nothing is usable, or
        :class:`AllProvidersExhausted` if every candidate failed.
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(
            messages,
            model=model,
            providers=providers,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            tools=tools,
            tool_choice=tool_choice,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        providers: Iterable[str] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 90.0,
        tools: list | None = None,
        tool_choice=None,
    ) -> Reply:
        """Like :meth:`ask` but takes raw OpenAI-style ``messages``."""
        if not self.providers:
            raise NoProvidersConfigured(
                "no provider has an API key set; see .env.example for the env vars"
            )

        provider_list = list(providers) if providers else None
        cache_key = None
        if self._cache is not None:
            cache_key = self._cache.make_key(
                messages, model, provider_list, max_tokens, temperature, tools, tool_choice
            )
            hit = self._cache.get(cache_key)
            if hit is not None:
                self.stats["cache_hits"] += 1
                return Reply(
                    text=hit.get("text", ""),
                    provider_id=hit.get("provider_id", "cache"),
                    model=hit.get("model", "?"),
                    raw={},
                    prompt_tokens=hit.get("prompt_tokens"),
                    completion_tokens=hit.get("completion_tokens"),
                    message=hit.get("message"),
                    cached=True,
                )

        targets = self._order(self._all_targets(include=provider_list, model=model))
        if not targets:
            raise NoProvidersConfigured("no candidate (provider, model) matched the given filters")

        # Providers recently rate-limited (429) are tried last, not skipped — so
        # a transient cooldown never makes a request fail outright.
        now = self._clock()
        available = [t for t in targets if not self._cooled(t.provider.id, now)]
        cooled = [t for t in targets if self._cooled(t.provider.id, now)]
        sequence = available + cooled

        attempts: list[tuple[str, str]] = []
        rate_limited: set[str] = set()  # providers that 429'd during THIS request
        for target in sequence:
            if target.provider.id in rate_limited:
                # Already 429'd this request — don't waste calls on its other models.
                attempts.append((target.name, "skipped (provider rate-limited this request)"))
                continue
            api_key = target.provider.api_key(self.env)
            if api_key is None and not target.provider.keyless:  # pragma: no cover
                attempts.append((target.name, "missing api key"))
                continue
            try:
                reply = _client.call(
                    target.provider,
                    target.model,
                    messages,
                    api_key=api_key,
                    env=self.env,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                    tools=tools,
                    tool_choice=tool_choice,
                    post=self._post,
                )
            except ProviderHTTPError as exc:
                if exc.status == 429:
                    self._mark_cooldown(target.provider.id, self._clock())
                    rate_limited.add(target.provider.id)
                attempts.append((target.name, str(exc)))
                continue
            except Exception as exc:  # network error, etc. — try the next one
                attempts.append((target.name, f"{type(exc).__name__}: {exc}"))
                continue

            has_tool_calls = bool(reply.message and reply.message.get("tool_calls"))
            if not reply.text and not has_tool_calls:
                attempts.append((target.name, "empty completion"))
                continue

            self.quota.record(target.provider.id, target.model)
            reply.attempts = len(attempts) + 1
            self.stats["requests"] += 1
            self.stats["prompt_tokens"] += reply.prompt_tokens or 0
            self.stats["completion_tokens"] += reply.completion_tokens or 0
            if self._cache is not None and cache_key is not None:
                self._cache.put(
                    cache_key,
                    {
                        "text": reply.text,
                        "provider_id": reply.provider_id,
                        "model": reply.model,
                        "prompt_tokens": reply.prompt_tokens,
                        "completion_tokens": reply.completion_tokens,
                        "message": reply.message,
                    },
                )
            return reply

        raise AllProvidersExhausted(attempts)

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        providers: Iterable[str] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 90.0,
    ):
        """Stream content deltas with token-level streaming.

        Yields a meta dict ``{"provider", "model"}`` first, then content-delta
        strings. Failover happens *before* the first token (on a non-200); once
        tokens flow, freellmpool is committed to that provider. Gemini-adapter
        providers are skipped (no OpenAI-shape stream).
        """
        if not self.providers:
            raise NoProvidersConfigured("no provider has an API key set")
        targets = self._order(self._all_targets(include=providers, model=model))
        targets = [t for t in targets if t.provider.adapter != "gemini"]
        if not targets:
            raise NoProvidersConfigured("no streamable (provider, model) matched the filters")

        now = self._clock()
        available = [t for t in targets if not self._cooled(t.provider.id, now)]
        cooled = [t for t in targets if self._cooled(t.provider.id, now)]
        attempts: list[tuple[str, str]] = []
        rate_limited: set[str] = set()
        for target in available + cooled:
            if target.provider.id in rate_limited:
                continue
            api_key = target.provider.api_key(self.env)
            if api_key is None and not target.provider.keyless:
                continue
            gen = _client.stream_call(
                target.provider,
                target.model,
                messages,
                api_key=api_key,
                env=self.env,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                stream_post=self._stream_post,
            )
            try:
                first = next(gen)  # triggers connection + status check
            except StopIteration:
                attempts.append((target.name, "empty stream"))
                continue
            except ProviderHTTPError as exc:
                if exc.status == 429:
                    self._mark_cooldown(target.provider.id, self._clock())
                    rate_limited.add(target.provider.id)
                attempts.append((target.name, str(exc)))
                continue
            except Exception as exc:  # noqa: BLE001
                attempts.append((target.name, f"{type(exc).__name__}: {exc}"))
                continue

            self.quota.record(target.provider.id, target.model)
            self.stats["requests"] += 1
            yield {"provider": target.provider.id, "model": target.model}
            yield first
            yield from gen
            return

        raise AllProvidersExhausted(attempts)
