# Good First Issue Drafts

This is the local P6 handoff. The polish pass is not allowed to post externally,
so these are ready-to-file drafts for the operator after the PR is merged.

## Labels

Create or refresh the labels first:

```bash
gh label create "good first issue" --repo 0xzr/freellmpool --color 7057ff --description "Small, well-scoped task for a first contribution" --force
gh label create docs --repo 0xzr/freellmpool --color 0075ca --description "Documentation-only or documentation-led change" --force
gh label create cli --repo 0xzr/freellmpool --color d4c5f9 --description "Command-line interface" --force
gh label create tests --repo 0xzr/freellmpool --color c2e0c6 --description "Tests and fixtures" --force
gh label create integration --repo 0xzr/freellmpool --color 0e8a16 --description "Client, editor, coding agent, or proxy integration" --force
gh label create provider-catalog --repo 0xzr/freellmpool --color fbca04 --description "Provider catalog, keys, limits, or model metadata" --force
```

## Draft Issues

Do not run these commands during the polish pass. They create public GitHub
issues.

```bash
gh issue create --repo 0xzr/freellmpool --title "Keep .env.example keyless provider notes in sync" --label "good first issue" --label docs --label provider-catalog --body-file docs/good-first-issues/env-keyless-providers.md

gh issue create --repo 0xzr/freellmpool --title "Add JSON output to freellmpool models" --label "good first issue" --label cli --label tests --body-file docs/good-first-issues/models-json-output.md

gh issue create --repo 0xzr/freellmpool --title "Keep freellmpool code agent recipes aligned with docs" --label "good first issue" --label integration --label tests --body-file docs/good-first-issues/code-agent-recipes-test.md

gh issue create --repo 0xzr/freellmpool --title "Add a README recipe for the summary badge" --label "good first issue" --label docs --body-file docs/good-first-issues/badge-summary-recipe.md

gh issue create --repo 0xzr/freellmpool --title "Document catalog sync and status commands in the capacity guide" --label "good first issue" --label docs --label provider-catalog --body-file docs/good-first-issues/catalog-status-docs.md

gh issue create --repo 0xzr/freellmpool --title "Add a capacity-status fixture for quota edge cases" --label "good first issue" --label tests --label cli --body-file docs/good-first-issues/capacity-status-fixture.md
```

Each draft is scoped to be completable by a newcomer in under two hours and
points at the files where the work should start.
