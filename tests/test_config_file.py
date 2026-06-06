"""config.toml loading: keys, aliases, settings."""

from __future__ import annotations

from freellmpool.config import (
    effective_env,
    known_aliases,
    load_config_file,
    resolve_alias,
    settings,
)


def _write(tmp_path, body: str) -> dict[str, str]:
    p = tmp_path / "config.toml"
    p.write_text(body)
    return {"FREELLMPOOL_CONFIG_FILE": str(p)}


def test_no_config_file_is_empty():
    assert load_config_file({"FREELLMPOOL_CONFIG_FILE": "/nonexistent/x.toml"}) == {}


def test_keys_fill_under_env(tmp_path):
    env = _write(tmp_path, '[keys]\nGROQ_API_KEY = "from-file"\nCEREBRAS_API_KEY = "from-file"\n')
    env["CEREBRAS_API_KEY"] = "from-env"  # real env wins
    merged = effective_env(env)
    assert merged["GROQ_API_KEY"] == "from-file"
    assert merged["CEREBRAS_API_KEY"] == "from-env"


def test_config_alias(tmp_path):
    env = _write(tmp_path, '[aliases]\n"gpt-4o-mini" = "groq/llama-3.1-8b-instant"\n')
    assert resolve_alias("gpt-4o-mini", env) == "groq/llama-3.1-8b-instant"


def test_known_aliases_include_config_alias(tmp_path):
    env = _write(tmp_path, '[aliases]\n"my-model" = "groq/llama-3.1-8b-instant"\n')
    assert "my-model" in known_aliases(env)


def test_env_alias_beats_config(tmp_path):
    env = _write(tmp_path, '[aliases]\n"gpt-4o-mini" = "from-config"\n')
    env["FREELLMPOOL_ALIAS_GPT_4O_MINI"] = "from-env"
    assert resolve_alias("gpt-4o-mini", env) == "from-env"


def test_settings(tmp_path):
    env = _write(tmp_path, '[settings]\ncooldown_seconds = 30\nproxy_key = "abc"\n')
    s = settings(env)
    assert s["cooldown_seconds"] == 30
    assert s["proxy_key"] == "abc"


def test_malformed_config_is_ignored(tmp_path):
    env = _write(tmp_path, "this is not valid toml = = =")
    assert load_config_file(env) == {}
