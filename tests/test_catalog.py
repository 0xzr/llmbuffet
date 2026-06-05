from __future__ import annotations

from freellmpool.catalog import parse_external_catalog


def test_parse_external_catalog_rate_limits():
    data = {
        "providers": [
            {
                "name": "Small",
                "category": "provider_api",
                "url": "https://example.test/small",
                "baseUrl": "https://api.example.test/v1",
                "description": "small plan",
                "models": [{"id": "a", "rateLimit": "10 RPM, 100 RPD"}],
            },
            {
                "name": "Large",
                "category": "provider_api",
                "url": "https://example.test/large",
                "baseUrl": "https://api2.example.test/v1",
                "description": "large plan",
                "models": [{"id": "b", "rateLimit": "2k RPM, 1M TPD"}],
            },
        ]
    }
    providers = parse_external_catalog(data)
    assert [p.name for p in providers] == ["Large", "Small"]
    assert providers[0].best_rpm == 2000
    assert providers[0].best_tpd == 1_000_000
    assert providers[1].best_rpd == 100


def test_import_external_provider_to_user_catalog(tmp_path, monkeypatch):
    from freellmpool.catalog import (
        default_external_catalog_path,
        import_external_provider_to_user_catalog,
    )

    cache = tmp_path / "provider_catalog.json"
    user_catalog = tmp_path / "providers.toml"
    cache.write_text(
        '{"providers":[{"name":"ModelScope","baseUrl":"https://api-inference.modelscope.cn/v1",'
        '"models":[{"id":"Qwen/Qwen3.5-27B","modality":"Text","rateLimit":"2,000 RPD total; <=500 RPD/model"},'
        '{"id":"+ API-Inference-enabled models","modality":"LLM","rateLimit":"Dynamic quotas"}]}]}'
    )
    monkeypatch.setenv("FREELLMPOOL_EXTERNAL_CATALOG_PATH", str(cache))
    monkeypatch.setenv("FREELLMPOOL_CONFIG", str(user_catalog))

    assert default_external_catalog_path() == cache
    local_id = import_external_provider_to_user_catalog("ModelScope")
    assert local_id == "modelscope"
    written = user_catalog.read_text()
    assert 'id = "modelscope"' in written
    assert 'key_env = "MODELSCOPE_API_KEY"' in written
    assert 'Qwen/Qwen3.5-27B' in written
    assert '+ API-Inference-enabled models' not in written
    assert 'rpd = 500' in written
