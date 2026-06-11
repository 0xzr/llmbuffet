from __future__ import annotations

import re
import struct
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_P9_TOPICS = {
    "anthropic",
    "claude",
    "cursor",
    "speech-to-text",
    "rate-limiting",
}

RECOMMENDED_TOPICS = {
    "anthropic",
    "claude",
    "codex",
    "cursor",
    "failover",
    "free-llm",
    "free-llm-api",
    "gemini",
    "groq",
    "llm-gateway",
    "llm-router",
    "mcp",
    "mcp-server",
    "model-context-protocol",
    "openai",
    "openai-proxy",
    "openrouter",
    "python",
    "rate-limiting",
    "speech-to-text",
}


def test_github_discovery_checklist_has_complete_topic_plan():
    doc = (ROOT / "docs/GITHUB_DISCOVERY.md").read_text(encoding="utf-8")

    for topic in REQUIRED_P9_TOPICS:
        assert topic in doc

    recommended = doc.split("Recommended 20-topic set:", 1)[1].split(
        "This removes", 1
    )[0]
    for topic in RECOMMENDED_TOPICS:
        assert f"`{topic}`" in recommended

    assert len(RECOMMENDED_TOPICS) == 20
    assert "Do not run these write commands during the polish pass." in doc
    assert "No external writes were performed" in doc


def test_github_discovery_description_stays_within_about_limit():
    doc = (ROOT / "docs/GITHUB_DISCOVERY.md").read_text(encoding="utf-8")
    match = re.search(r"Recommended description \((\d+) chars\):\n\n> (.+)", doc)

    assert match is not None
    expected_len = int(match.group(1))
    description = match.group(2)
    assert len(description) == expected_len
    assert len(description) <= 120
    assert "zero keys to start" in description
    assert "18 LLM providers" in description
    assert "failover" in description


def test_github_discovery_includes_operator_only_actions():
    doc = (ROOT / "docs/GITHUB_DISCOVERY.md").read_text(encoding="utf-8")

    assert "gh repo edit 0xzr/freellmpool" in doc
    assert "--remove-topic ai" in doc
    assert "--add-topic anthropic" in doc
    assert "assets/social-preview.svg" in doc
    assert "Pin `0xzr/freellmpool`" in doc


def test_social_preview_svg_matches_github_preview_requirements():
    svg_path = ROOT / "assets/social-preview.svg"
    preview = svg_path.read_text(encoding="utf-8")
    parsed = xml.dom.minidom.parseString(preview)
    root = parsed.documentElement

    assert root.tagName == "svg"
    assert root.getAttribute("viewBox") == "0 0 1280 640"
    assert root.getAttribute("width") == "1280"
    assert root.getAttribute("height") == "640"
    assert svg_path.stat().st_size < 1_000_000

    for text in (
        "zero keys",
        "18 providers",
        "200+ models",
        "OpenAI +",
        "Anthropic proxy",
        "failover",
        "rate limits",
        "transcription",
    ):
        assert text in preview


def test_social_preview_png_is_upload_ready():
    png_path = ROOT / "assets/social-preview.png"
    data = png_path.read_bytes()

    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert png_path.stat().st_size < 1_000_000
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (1280, 640)
