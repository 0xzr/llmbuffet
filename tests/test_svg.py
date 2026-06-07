"""Zero-dependency SVG badge + summary rendering."""

from __future__ import annotations

import xml.dom.minidom

from freellmpool import svg


def _is_valid_xml(s: str) -> bool:
    xml.dom.minidom.parseString(s)  # raises on malformed XML
    return True


def test_badge_svg_well_formed_and_shows_tokens():
    out = svg.badge_svg({"prompt_tokens": 1_000_000, "completion_tokens": 200_000, "requests": 50})
    assert _is_valid_xml(out)
    assert out.startswith("<svg")
    assert "1.2M tokens free" in out
    assert "freellmpool" in out


def test_badge_svg_metric_variants():
    s = {"prompt_tokens": 1000, "completion_tokens": 1000, "requests": 7}
    assert "saved" in svg.badge_svg(s, metric="saved")
    assert "served" in svg.badge_svg(s, metric="requests")
    assert _is_valid_xml(svg.badge_svg(s, metric="saved"))


def test_summary_svg_has_numbers_and_leaderboard():
    s = {
        "prompt_tokens": 500_000,
        "completion_tokens": 500_000,
        "requests": 123,
        "first_seen": "2026-01-01T00:00:00Z",
    }
    out = svg.summary_svg(s, [("groq", 1.0), ("cohere", 0.5)])
    assert _is_valid_xml(out)
    assert "123" in out  # requests
    assert "groq" in out and "cohere" in out
    assert "2026-01-01" in out


def test_summary_svg_no_leaderboard_ok():
    out = svg.summary_svg({"prompt_tokens": 0, "completion_tokens": 0, "requests": 0})
    assert _is_valid_xml(out)


def test_summary_svg_truncates_before_escaping():
    # '&' positioned so a naive escape-then-truncate would split an entity mid-string
    name = "aaaaaaaaaaaaaa&&&&&&&&"  # >16 chars, ampersands straddle the cut point
    out = svg.summary_svg(
        {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}, [(name, 1.0)]
    )
    assert _is_valid_xml(out)  # must stay well-formed (no half '&amp;' entity)


def test_svg_escapes_untrusted_text():
    out = svg.summary_svg(
        {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}, [("<b>&z", 1.0)]
    )
    assert _is_valid_xml(out)
    assert "<b>&z" not in out  # raw injection must be escaped
    assert "&lt;b&gt;" in out
