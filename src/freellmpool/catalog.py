"""Advisory external provider catalog sync.

This imports metadata from mnfst/awesome-free-llm-apis into a local cache. It is
advisory only: the executable provider configuration remains providers.toml.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_URL = "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json"


def default_external_catalog_path() -> Path:
    override = os.environ.get("FREELLMPOOL_EXTERNAL_CATALOG_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "freellmpool" / "provider_catalog.json"


@dataclass(frozen=True)
class ExternalProvider:
    name: str
    slug: str
    category: str | None
    url: str | None
    base_url: str | None
    description: str
    model_count: int
    best_rpd: int
    best_rpm: int
    best_tpd: int
    generous_score: int


def sync_external_catalog(
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    path: Path | None = None,
    timeout: float = 20.0,
) -> tuple[Path, list[ExternalProvider]]:
    path = path or default_external_catalog_path()
    with urllib.request.urlopen(source_url, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    providers = parse_external_catalog(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path, providers


def load_external_catalog(path: Path | None = None) -> list[ExternalProvider]:
    path = path or default_external_catalog_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    return parse_external_catalog(data)


def parse_external_catalog(data: Any) -> list[ExternalProvider]:
    rows = data.get("providers", []) if isinstance(data, dict) else []
    providers = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        models = row.get("models") if isinstance(row.get("models"), list) else []
        best_rpd = 0
        best_rpm = 0
        best_tpd = 0
        for model in models:
            if not isinstance(model, dict):
                continue
            limit = str(model.get("rateLimit") or "")
            best_rpd = max(best_rpd, _extract_limit(limit, "RPD"))
            best_rpm = max(best_rpm, _extract_limit(limit, "RPM"))
            best_tpd = max(best_tpd, _extract_limit(limit, "TPD"))
        score = best_tpd or best_rpd or best_rpm or 0
        providers.append(
            ExternalProvider(
                name=name,
                slug=_slug(name),
                category=_optional(row.get("category")),
                url=_optional(row.get("url")),
                base_url=_optional(row.get("baseUrl")),
                description=str(row.get("description") or ""),
                model_count=len(models),
                best_rpd=best_rpd,
                best_rpm=best_rpm,
                best_tpd=best_tpd,
                generous_score=score,
            )
        )
    providers.sort(key=lambda p: (-p.generous_score, p.slug))
    return providers


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _extract_model_rpd(text: str) -> int:
    pattern = re.compile(r"([0-9][0-9,.]*\s*[kKmMbB]?)\s*RPD")
    values = [_parse_number(match.group(1)) for match in pattern.finditer(text)]
    values = [value for value in values if value > 0]
    if not values:
        return 0
    return min(values)


def _extract_limit(text: str, unit: str) -> int:
    pattern = re.compile(r"([0-9][0-9,.]*\s*[kKmMbB]?)\s*" + re.escape(unit))
    values = [_parse_number(match.group(1)) for match in pattern.finditer(text)]
    return max(values) if values else 0


def _parse_number(value: str) -> int:
    text = value.strip().replace(",", "")
    multiplier = 1
    if text[-1:].lower() == "k":
        multiplier = 1_000
        text = text[:-1]
    elif text[-1:].lower() == "m":
        multiplier = 1_000_000
        text = text[:-1]
    elif text[-1:].lower() == "b":
        multiplier = 1_000_000_000
        text = text[:-1]
    try:
        return int(float(text.strip()) * multiplier)
    except ValueError:
        return 0


def match_local_provider(external: ExternalProvider, local_providers) -> str | None:
    """Return the local provider id matching an external catalog row, if any."""
    external_base = (external.base_url or "").rstrip("/").lower()
    for provider in local_providers:
        if provider.base_url.rstrip("/").lower() == external_base and external_base:
            return provider.id
    external_slug = external.slug
    for provider in local_providers:
        if _slug(provider.id) == external_slug or _slug(provider.label) == external_slug:
            return provider.id
    aliases = {
        "google-gemini": "gemini",
        "github-models": "github",
        "z-ai-zhipu-glm": "zhipu",
        "llm7-io": "llm7",
        "openrouter": "openrouter",
        "nvidia-nim": "nvidia",
        "groq": "groq",
        "cerebras": "cerebras",
        "cohere": "cohere",
        "mistral-ai": "mistral",
        "sambanova": "sambanova",
        "cloudflare-workers-ai": "cloudflare",
        "ollama-cloud": "ollama",
    }
    wanted = aliases.get(external_slug)
    if wanted and any(provider.id == wanted for provider in local_providers):
        return wanted
    return None


def import_external_provider_to_user_catalog(query: str) -> str:
    """Create a user providers.toml stub from an external-only catalog provider.

    Returns the local provider id that was written. This is intentionally a
    user-catalog append, not a change to the packaged providers.toml.
    """
    data_path = default_external_catalog_path()
    try:
        raw = json.loads(data_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        raise ValueError("external catalog cache is missing; run capacity status first") from None
    needle = _external_lookup_slug(query)
    rows = raw.get("providers", []) if isinstance(raw, dict) else []
    match = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if _external_lookup_slug(name) == needle:
            match = row
            break
    if match is None:
        available = ", ".join(str(row.get("name")) for row in rows[:8] if isinstance(row, dict))
        raise ValueError(f"provider not found in external catalog: {query}. Try one of: {available}")
    base_url = str(match.get("baseUrl") or "").strip()
    if not base_url:
        raise ValueError(f"external provider has no baseUrl: {query}")
    provider_id = _slug(str(match.get("name") or query)).replace("-", "_")
    key_env = provider_id.upper() + "_API_KEY"
    models = []
    for model in match.get("models", []):
        if not isinstance(model, dict):
            continue
        model_id = model.get("id") or model.get("name")
        if not model_id:
            continue
        model_id = str(model_id).strip()
        if not model_id or model_id.startswith("+"):
            continue
        modality = str(model.get("modality") or "").lower()
        if "image" in modality and "text" not in modality:
            continue
        limit = str(model.get("rateLimit") or "")
        rpd = _extract_model_rpd(limit)
        models.append((model_id, rpd))
    if not models:
        raise ValueError(f"external provider has no usable text models: {query}")
    path = _user_provider_catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if f'id = "{provider_id}"' not in existing:
        with path.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write("\n[[provider]]\n")
            fh.write(f'id = "{provider_id}"\n')
            fh.write(f'label = "{_toml_escape(str(match.get("name") or query))}"\n')
            fh.write('adapter = "openai"\n')
            fh.write(f'base_url = "{_toml_escape(base_url)}"\n')
            fh.write(f'key_env = "{key_env}"\n')
            fh.write("models = [\n")
            for model_id, rpd in models:
                fh.write(f'    {{ name = "{_toml_escape(model_id)}", rpd = {rpd} }},\n')
            fh.write("]\n")
    return provider_id


def _external_lookup_slug(value: str) -> str:
    slug = _slug(value)
    aliases = {
        "ai21": "ai21-labs",
        "ai21labs": "ai21-labs",
        "model-scope": "modelscope",
        "modelscope": "modelscope",
        "silicon-flow": "siliconflow",
        "google": "google-gemini",
        "gemini": "google-gemini",
        "github": "github-models",
        "hf": "hugging-face",
        "huggingface": "hugging-face",
    }
    return aliases.get(slug, slug)


def _user_provider_catalog_path() -> Path:
    override = os.environ.get("FREELLMPOOL_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "freellmpool" / "providers.toml"


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
