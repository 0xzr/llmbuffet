"""CLI helpers that don't need network."""

from __future__ import annotations

from llmbuffet.cli import _strip_fences


def test_strip_plain_json():
    assert _strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fenced_json():
    assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_bare_fence():
    assert _strip_fences("```\nhello\n```") == "hello"
