# Add a README recipe for the summary badge

Labels: `good first issue`, `docs`
Estimate: 30-60 minutes

## Context

The CLI and proxy can render both a small badge and a larger summary card, but
the README mostly shows the badge path. A short recipe would help users embed
their lifetime free-token totals.

## Pointers

- [`README.md`](../../README.md)
- [`src/freellmpool/svg.py`](../../src/freellmpool/svg.py)
- [`tests/test_svg.py`](../../tests/test_svg.py)

## Acceptance

- Add a concise README example for `freellmpool badge --summary -o summary.svg`.
- Mention that the proxy can serve `/summary.svg` when public badges are enabled.
- Do not add a new dependency or change SVG rendering behavior.
- `ruff check .` and `pytest tests/test_svg.py` pass.
