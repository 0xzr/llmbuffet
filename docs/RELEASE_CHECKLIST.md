# Release Checklist

Prepared release: `0.11.3`

This checklist is for the operator after the polish PR is merged. Do not publish,
push tags, or create a GitHub release from the polish automation branch.

## Verify

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
scripts/check-counts
python3 scripts/validate_catalog.py
python3 scripts/check_release_ready.py --skip-build
python3 scripts/check_release_ready.py
```

## Tag

Run after the PR is merged and the verified commit is on `main`:

```bash
git switch main
git pull --ff-only
git tag -a v0.11.3 -m "freellmpool 0.11.3"
```

## Build And Publish

Only the operator should run the publish step:

```bash
rm -rf dist
python3 -m build
python3 -m twine check dist/*
python3 -m twine upload dist/*
```

After upload, smoke-test the published artifact:

```bash
python3 scripts/check_release_ready.py --check-pypi
```

## Post-Release

```bash
git push origin v0.11.3
```

Create the GitHub release from the pushed tag and paste the `0.11.3` changelog
entry. Do not include API keys, provider credentials, or unpublished issue draft
details in the release notes.
