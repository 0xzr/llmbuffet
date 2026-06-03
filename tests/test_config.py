"""Catalog loading + configured-provider filtering."""

from __future__ import annotations

from freellmpool.config import configured_providers, load_catalog


def test_packaged_catalog_loads():
    catalog = load_catalog()
    ids = {p.id for p in catalog}
    assert {"groq", "cerebras", "openrouter", "gemini"} <= ids
    for p in catalog:
        assert p.models  # every provider ships at least one model
        assert p.base_url.startswith("https://")


def test_keyless_providers_always_configured():
    # OVH (auth=none) and LLM7 (key_optional) are usable with an empty env.
    catalog = load_catalog()
    ids = {p.id for p in configured_providers(catalog, {})}
    assert "ovh" in ids  # keyless
    assert "llm7" in ids  # key optional
    assert "pollinations" in ids  # keyless
    assert "groq" not in ids  # needs a key


def test_configured_filter_by_env():
    catalog = load_catalog()
    ids = {p.id for p in configured_providers(catalog, {"GROQ_API_KEY": "x"})}
    assert "groq" in ids
    assert "cerebras" not in ids  # no key → excluded
    assert "ovh" in ids  # keyless → always present


def test_cloudflare_requires_extra_env():
    catalog = load_catalog()
    # token alone is not enough; account id is also required
    with_token = {p.id for p in configured_providers(catalog, {"CLOUDFLARE_API_TOKEN": "t"})}
    assert "cloudflare" not in with_token
    with_both = {
        p.id
        for p in configured_providers(
            catalog, {"CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ACCOUNT_ID": "acc"}
        )
    }
    assert "cloudflare" in with_both


def test_user_override(tmp_path):
    override = tmp_path / "providers.toml"
    override.write_text(
        "[[provider]]\n"
        'id = "groq"\n'
        'label = "My Groq"\n'
        'adapter = "openai"\n'
        'base_url = "https://example.test/v1"\n'
        'key_env = "GROQ_API_KEY"\n'
        'models = [{ name = "custom-model", rpd = 42 }]\n'
    )
    catalog = load_catalog(path=override)
    groq = next(p for p in catalog if p.id == "groq")
    assert groq.label == "My Groq"
    assert groq.models[0].name == "custom-model"
