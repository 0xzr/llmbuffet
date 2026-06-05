from __future__ import annotations

from freellmpool.key_inventory import load_inventory, records_by_provider, redact_secrets


def test_load_inventory_reads_records(tmp_path):
    path = tmp_path / "keys.toml"
    path.write_text(
        '[[keys]]\n'
        'provider = "groq"\n'
        'env_var = "GROQ_API_KEY"\n'
        'label = "main"\n'
        'created_at = "2026-06-05"\n'
        'commercial_allowed = true\n'
    )
    records = load_inventory(path)
    assert len(records) == 1
    assert records[0].provider == "groq"
    assert records[0].env_var == "GROQ_API_KEY"
    assert records[0].display_label == "main"
    assert records[0].commercial_allowed is True


def test_load_inventory_missing_file_is_empty(tmp_path):
    assert load_inventory(tmp_path / "missing.toml") == []


def test_records_by_provider_groups_records(tmp_path):
    path = tmp_path / "keys.toml"
    path.write_text(
        '[[keys]]\nprovider = "groq"\nenv_var = "GROQ_API_KEY"\n'
        '[[keys]]\nprovider = "groq"\nenv_var = "GROQ_API_KEY_2"\n'
        '[[keys]]\nprovider = "mistral"\nenv_var = "MISTRAL_API_KEY"\n'
    )
    grouped = records_by_provider(load_inventory(path))
    assert len(grouped["groq"]) == 2
    assert len(grouped["mistral"]) == 1


def test_redact_secrets_common_shapes():
    text = "before gsk_abcdefghijk after"
    assert redact_secrets(text) == "before [redacted] after"
