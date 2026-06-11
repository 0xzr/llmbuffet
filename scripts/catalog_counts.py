"""Catalog-derived public count helpers."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderCounts:
    id: str
    label: str
    enabled_models: int
    cataloged_models: int


@dataclass(frozen=True)
class CatalogCounts:
    providers: int
    enabled_chat_models: int
    cataloged_chat_models: int
    enabled_all_models: int
    cataloged_all_models: int
    by_provider: tuple[ProviderCounts, ...]

    @property
    def live_bucket(self) -> str:
        return bucket(self.enabled_chat_models)

    @property
    def cataloged_bucket(self) -> str:
        return bucket(self.cataloged_chat_models)


def bucket(value: int) -> str:
    if value < 100:
        return str(value)
    return f"{(value // 100) * 100}+"


def catalog_counts(root: Path) -> CatalogCounts:
    data = tomllib.loads((root / "src" / "freellmpool" / "providers.toml").read_text())
    chat_providers = data.get("provider") or []

    provider_labels = {provider["id"]: provider["label"] for provider in chat_providers}
    by_provider: dict[str, list[int]] = {provider["id"]: [0, 0] for provider in chat_providers}
    enabled_chat = 0
    cataloged_chat = 0
    enabled_all = 0
    cataloged_all = 0

    for section in ("provider", "embedder", "transcriber"):
        for provider in data.get(section, []):
            models = provider.get("models") or []
            cataloged = len(models)
            enabled = sum(1 for model in models if model.get("enabled", True))
            cataloged_all += cataloged
            enabled_all += enabled
            if section == "provider":
                cataloged_chat += cataloged
                enabled_chat += enabled
            if provider["id"] in by_provider:
                by_provider[provider["id"]][0] += enabled
                by_provider[provider["id"]][1] += cataloged

    return CatalogCounts(
        providers=len(chat_providers),
        enabled_chat_models=enabled_chat,
        cataloged_chat_models=cataloged_chat,
        enabled_all_models=enabled_all,
        cataloged_all_models=cataloged_all,
        by_provider=tuple(
            ProviderCounts(
                id=provider_id,
                label=provider_labels[provider_id],
                enabled_models=counts[0],
                cataloged_models=counts[1],
            )
            for provider_id, counts in by_provider.items()
        ),
    )
