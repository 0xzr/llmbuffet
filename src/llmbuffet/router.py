"""The Buffet: provider selection and failover.

A :class:`Buffet` holds the configured providers, a quota store, and the
strategy for ordering candidate (provider, model) targets. :meth:`ask` walks
that ordered list, calling each target until one succeeds, recording quota use
and per-day budgets as it goes.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

from . import client as _client
from .client import PostFn, default_post
from .config import configured_providers, load_catalog
from .errors import AllProvidersExhausted, NoProvidersConfigured, ProviderHTTPError
from .models import Provider, Reply
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


class Buffet:
    def __init__(
        self,
        providers: list[Provider],
        *,
        quota: QuotaStore | None = None,
        env: dict[str, str] | None = None,
        post: PostFn = default_post,
    ):
        self.providers = providers
        self.quota = quota or QuotaStore()
        self.env = env if env is not None else dict(os.environ)
        self._post = post

    # ---- construction -------------------------------------------------

    @classmethod
    def from_default_config(
        cls,
        *,
        env: dict[str, str] | None = None,
        quota: QuotaStore | None = None,
        post: PostFn = default_post,
    ) -> Buffet:
        env = env if env is not None else dict(os.environ)
        providers = configured_providers(load_catalog(), env)
        return cls(providers, quota=quota, env=env, post=post)

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
                if model is not None and m.name != model:
                    continue
                targets.append(Target(provider, m.name, m.rpd))
        return targets

    def _order(self, targets: list[Target]) -> list[Target]:
        """Least-used-first ordering, so load spreads across free tiers.

        Targets already over their daily budget hint are pushed to the back
        (they may still be tried if everything else fails).
        """

        def sort_key(t: Target) -> tuple[int, int]:
            used = self.quota.used(t.provider.id, t.model)
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
    ) -> Reply:
        """Like :meth:`ask` but takes raw OpenAI-style ``messages``."""
        if not self.providers:
            raise NoProvidersConfigured(
                "no provider has an API key set; see .env.example for the env vars"
            )

        targets = self._order(self._all_targets(include=providers, model=model))
        if not targets:
            raise NoProvidersConfigured("no candidate (provider, model) matched the given filters")

        attempts: list[tuple[str, str]] = []
        for target in targets:
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
                    post=self._post,
                )
            except ProviderHTTPError as exc:
                attempts.append((target.name, str(exc)))
                continue
            except Exception as exc:  # network error, etc. — try the next one
                attempts.append((target.name, f"{type(exc).__name__}: {exc}"))
                continue

            if not reply.text:
                attempts.append((target.name, "empty completion"))
                continue

            self.quota.record(target.provider.id, target.model)
            return reply

        raise AllProvidersExhausted(attempts)
