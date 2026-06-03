"""Test helpers: a fake `post` transport and canned response bodies."""

from __future__ import annotations

from freellmpool.client import HTTPResult


def openai_body(text: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5},
    }


def gemini_body(text: str) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 5},
    }


def make_stream_post(script=None):
    """Fake streaming transport: (url, headers, body, timeout) -> (status, lines).

    ``script`` maps url-substring -> (status, [deltas]) or [deltas]. Default:
    200 with a single "ok" content delta.
    """
    import json as _json

    calls: list[dict] = []

    def stream_post(url, headers, body, timeout):
        calls.append({"url": url, "body": body})
        rule = None
        for needle, value in (script or {}).items():
            if needle in url:
                rule = value
                break
        if rule is None:
            status, deltas = 200, ["ok"]
        elif isinstance(rule, tuple):
            status, deltas = rule
        else:
            status, deltas = 200, rule
        lines = ["data: " + _json.dumps({"choices": [{"delta": {"content": d}}]}) for d in deltas]
        lines.append("data: [DONE]")
        return status, iter(lines)

    stream_post.calls = calls
    return stream_post


def make_post(script):
    """Build a fake `post` callable for the client/router.

    ``script`` maps a URL substring -> (status, body) or a callable
    (url, headers, body) -> (status, body). Unmatched URLs return 200 with a
    generic "ok" completion so tests can assert on routing.
    """
    calls: list[dict] = []

    def post(url, headers, json_body, timeout):
        calls.append({"url": url, "headers": headers, "body": json_body})
        rule = None
        for needle, value in script.items():
            if needle in url:
                rule = value
                break
        if rule is None:
            status, body = 200, openai_body("ok")
        elif callable(rule):
            status, body = rule(url, headers, json_body)
        else:
            status, body = rule
        return HTTPResult(status=status, body=body, text=str(body))

    post.calls = calls
    return post
