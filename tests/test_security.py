"""Security hardening: SSRF base_url validation, header-injection guards, redirects."""

from __future__ import annotations

from freellmpool.config import _parse_rows


def _row(base_url, pid="p", model="m"):
    return {"id": pid, "base_url": base_url, "models": [{"name": model}]}


def test_rejects_ssrf_and_malformed_base_urls(monkeypatch):
    monkeypatch.delenv("FREELLMPOOL_ALLOW_LOCAL_PROVIDERS", raising=False)
    bad = [
        "http://127.0.0.1/v1",  # loopback
        "http://localhost:8080/v1",  # loopback by name
        "http://10.0.0.5/v1",  # private
        "http://192.168.1.1/v1",  # private
        "http://169.254.169.254/latest/meta-data",  # cloud metadata (link-local)
        "http://[::1]/v1",  # ipv6 loopback
        "http://0.0.0.0/v1",  # unspecified
        "http://foo.local/v1",  # mDNS
        "ftp://api.test/v1",  # non-http scheme
        "file:///etc/passwd",  # non-http scheme
        "http://user:pass@api.test/v1",  # embedded credentials
        "http://api.test/v1\r\nX-Evil: 1",  # CRLF in url
        "http://api .test/v1",  # whitespace
    ]
    for u in bad:
        assert _parse_rows([_row(u)]) == [], u


def test_rejects_ip_encoding_and_trailing_dot_bypasses(monkeypatch):
    # resolvers accept these alternate encodings of 127.0.0.1 / loopback — they must
    # not smuggle an SSRF target past the literal-IP check.
    monkeypatch.delenv("FREELLMPOOL_ALLOW_LOCAL_PROVIDERS", raising=False)
    bad = [
        "http://2130706433/v1",  # decimal-encoded 127.0.0.1
        "http://0x7f000001/v1",  # hex-encoded
        "http://017700000001/v1",  # octal-encoded
        "http://127.1/v1",  # short form
        "http://127.0.0.1./v1",  # trailing dot (FQDN root)
        "http://localhost./v1",  # trailing-dot localhost
        "http://[::ffff:127.0.0.1]/v1",  # IPv4-mapped IPv6 loopback
        "http://127。0。0。1/v1",  # fullwidth ideographic dots → 127.0.0.1
        "http://１２７.0.0.1/v1",  # fullwidth digits → 127.0.0.1
        "http://ⓛocalhost/v1",  # unicode look-alike → localhost
        "http://%31%32%37.0.0.1/v1",  # percent-encoded host
    ]
    for u in bad:
        assert _parse_rows([_row(u)]) == [], u


def test_allows_public_base_urls(monkeypatch):
    monkeypatch.delenv("FREELLMPOOL_ALLOW_LOCAL_PROVIDERS", raising=False)
    for u in ["https://api.openai.com/v1", "https://api.groq.com/openai/v1", "http://8.8.8.8/v1"]:
        assert len(_parse_rows([_row(u)])) == 1, u


def test_local_providers_opt_in(monkeypatch):
    monkeypatch.delenv("FREELLMPOOL_ALLOW_LOCAL_PROVIDERS", raising=False)
    assert _parse_rows([_row("http://127.0.0.1:11434/v1")]) == []  # blocked by default
    monkeypatch.setenv("FREELLMPOOL_ALLOW_LOCAL_PROVIDERS", "1")
    assert len(_parse_rows([_row("http://127.0.0.1:11434/v1")])) == 1  # Ollama etc.


def test_rejects_control_chars_in_id_and_model():
    assert _parse_rows([_row("https://api.test/v1", pid="ev\nil")]) == []
    provs = _parse_rows(
        [
            {
                "id": "p",
                "base_url": "https://api.test/v1",
                "models": [{"name": "a\r\nb"}, {"name": "ok"}],
            }
        ]
    )
    assert len(provs) == 1
    assert [m.name for m in provs[0].models] == ["ok"]  # bad model dropped, good kept


def test_obs_headers_strip_control_chars():
    from freellmpool.proxy import _header_safe

    assert _header_safe("groq\r\nX-Injected: 1") == "groqX-Injected: 1"
    assert "\n" not in _header_safe("a\nb") and "\r" not in _header_safe("a\r\nb")


def test_client_does_not_follow_redirects():
    from freellmpool.client import _client

    assert _client().follow_redirects is False  # SSRF-via-redirect / key-exfil guard
