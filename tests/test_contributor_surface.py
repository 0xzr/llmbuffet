from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_good_first_issue_drafts_are_ready_to_file():
    index = (ROOT / "docs/GOOD_FIRST_ISSUES.md").read_text(encoding="utf-8")
    drafts = sorted((ROOT / "docs/good-first-issues").glob("*.md"))

    assert 5 <= len(drafts) <= 8
    assert "Do not run these commands during the polish pass." in index

    for draft in drafts:
        body = draft.read_text(encoding="utf-8")
        assert f"docs/good-first-issues/{draft.name}" in index
        assert "gh issue create" in index
        assert "Labels:" in body
        assert "`good first issue`" in body
        assert "Estimate:" in body
        assert "## Context" in body
        assert "## Pointers" in body
        assert "## Acceptance" in body


def test_issue_and_pr_templates_exist():
    templates = ROOT / ".github/ISSUE_TEMPLATE"

    for name in ("add-provider.md", "bug_report.md", "docs-improvement.md", "integration.md"):
        text = (templates / name).read_text(encoding="utf-8")
        assert "labels:" in text

    pr_template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
    assert "ruff check ." in pr_template
    assert "pytest" in pr_template
    assert "provider secrets" in pr_template


def test_contributing_lists_current_dev_loop():
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    for command in (
        'python -m pip install -e ".[dev]"',
        "ruff check .",
        "pytest",
        "scripts/check-counts",
        "python3 scripts/validate_catalog.py",
        "python3 scripts/check_release_ready.py --skip-build",
    ):
        assert command in contributing

    assert "docs/GOOD_FIRST_ISSUES.md" in contributing
