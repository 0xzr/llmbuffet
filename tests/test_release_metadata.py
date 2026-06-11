from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from freellmpool import __version__, client

ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_versions_match_package() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]
    server = json.loads((ROOT / "server.json").read_text())
    docs = (ROOT / "docs" / "index.html").read_text()
    demo = (ROOT / "assets" / "demo.svg").read_text()
    readme = (ROOT / "README.md").read_text()

    assert __version__ == version
    assert server["version"] == version
    assert server["packages"][0]["version"] == version
    project_description = pyproject["project"]["description"]
    provider_count = re.search(r"(\d+) LLM providers", project_description)
    model_count = re.search(r"(\d+\+) cataloged models", project_description)
    live_count = re.search(r"\((\d+\+) live-validated,", readme)
    assert provider_count is not None
    assert model_count is not None
    assert live_count is not None
    assert f"{provider_count.group(1)} LLM providers" in server["description"]
    assert f"{provider_count.group(1)} LLM providers" in readme
    assert f"{model_count.group(1)} cataloged" in readme
    assert f"{live_count.group(1)} live-validated" in docs
    assert f"{model_count.group(1)} cataloged" in docs
    assert f"Latest release: {version}" in docs
    assert f'"softwareVersion": "{version}"' in docs
    assert f"freellmpool-{version}" in demo
    assert f"{provider_count.group(1)} free tiers" in demo
    assert f"{provider_count.group(1)} providers" in demo


def test_client_user_agent_uses_package_version() -> None:
    assert f"freellmpool/{__version__}" in client._USER_AGENT


def test_pypi_metadata_has_launch_surfaces() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = pyproject["project"]
    discovery = (ROOT / "docs/GITHUB_DISCOVERY.md").read_text(encoding="utf-8")

    assert len(project["description"]) <= 120
    assert f"> {project['description']}" in discovery

    urls = project["urls"]
    for name in ("Docs", "Changelog", "Issues", "Repository"):
        assert name in urls

    for keyword in (
        "anthropic",
        "claude",
        "cursor",
        "mcp",
        "model-context-protocol",
        "rate-limiting",
        "speech-to-text",
    ):
        assert keyword in project["keywords"]

    for classifier in (
        "Framework :: AsyncIO",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ):
        assert classifier in project["classifiers"]

    dev_deps = project["optional-dependencies"]["dev"]
    assert any(dep.startswith("build>=") for dep in dev_deps)
    assert any(dep.startswith("twine>=") for dep in dev_deps)
