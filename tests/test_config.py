"""Catalog loading + configured-provider filtering."""

from __future__ import annotations

from freellmpool.config import configured_providers, known_aliases, load_catalog, resolve_alias


def test_alias_default_maps_to_auto():
    assert resolve_alias("gpt-4o-mini", {}) == "auto"
    assert resolve_alias("claude-3-5-sonnet-latest", {}) == "auto"


def test_alias_unknown_passthrough():
    assert resolve_alias("groq/llama-3.1-8b-instant", {}) == "groq/llama-3.1-8b-instant"
    assert resolve_alias("auto", {}) == "auto"


def test_alias_env_override():
    env = {"FREELLMPOOL_ALIAS_GPT_4O_MINI": "groq/llama-3.3-70b-versatile"}
    assert resolve_alias("gpt-4o-mini", env) == "groq/llama-3.3-70b-versatile"


def test_known_aliases_include_env_alias():
    env = {"FREELLMPOOL_ALIAS_MY_MODEL": "groq/llama-3.3-70b-versatile"}
    assert "MY_MODEL" in known_aliases(env)


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


def test_split_provider_model_guards_against_slash_model_names():
    from freellmpool.config import split_provider_model

    pids = {"groq", "huggingface", "kilo", "openrouter"}
    # real provider prefix → split
    assert split_provider_model("groq/llama-3.1-8b", pids) == (["groq"], "llama-3.1-8b")
    # slash-bearing model on a real provider → only first slash is the provider boundary
    assert split_provider_model("huggingface/Qwen/Qwen3-Coder-30B-A3B-Instruct", pids) == (
        ["huggingface"],
        "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    )
    # bare slash-model (no valid provider prefix) → kept whole, NOT mis-split into "Qwen"
    assert split_provider_model("Qwen/Qwen3-Coder-30B-A3B-Instruct", pids) == (
        None,
        "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    )
    assert split_provider_model("deepseek-ai/DeepSeek-R1", pids) == (None, "deepseek-ai/DeepSeek-R1")
    # no slash, or no provider set → unchanged
    assert split_provider_model("gpt-4o-mini", pids) == (None, "gpt-4o-mini")
    assert split_provider_model("groq/x", None) == (None, "groq/x")
