from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_faq_lists_every_builtin_chat_provider():
    with (ROOT / "src/freellmpool/providers.toml").open("rb") as fh:
        providers = tomllib.load(fh)["provider"]

    faq = (ROOT / "FAQ.md").read_text(encoding="utf-8")

    assert len(providers) == 18
    for provider in providers:
        assert f"`{provider['id']}`" in faq


def test_readme_links_faq_prominently():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    first_screen = readme.split("## Run a coding agent on free models", 1)[0]

    assert "[FAQ](FAQ.md)" in first_screen
