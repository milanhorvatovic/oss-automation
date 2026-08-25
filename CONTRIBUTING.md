# Contributing to oss-automation

This repository holds reusable GitHub Actions workflows other repositories call at a pinned commit, plus the pytest guard pack those consumers run against their own workflow trees. Both are consumed by machines on a credentialed path, so the bar for a change here is closer to that of a security control than of a helper script.

## Getting started

Python 3.10 or newer.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Confirm a clean baseline before changing anything — both suites, because they cover different things:

```bash
pytest                                  # unit tests for the guard implementation
pytest --pyargs oss_automation_guards   # the guards, run against this repository's own workflow tree
```

The second command is the same one consumers run. This repository is a consumer of its own guards, so a workflow change that breaks a structural rule fails here exactly as it would for them.

## Making a change

Branch from `main` with a `feature/<slug>` name. Keep one logical change per pull request.

Before pushing:

```bash
ruff check src tests
ruff format --check src tests
pytest
pytest --pyargs oss_automation_guards
```

### What the guards enforce

Any workflow file you add or edit must satisfy the structural rules, or CI fails:

- Every job declares a `timeout-minutes`.
- Every third-party action is pinned to a full 40-character commit SHA with a trailing comment naming the pinned version (`# v7.0.1`). A comment that merely contains a digit does not satisfy this.
- Default-token write scopes are declared explicitly rather than inherited.
- A PR-triggered workflow that holds credentials is bound to its declared trust model.

The last one is the rule most likely to surprise you. A workflow that gains a `secrets:` reference or a write scope becomes credentialed in the guards' eyes and must carry the matching trust guards; if a file is a deliberate exception, declare it through the `guards_trust_exempt` pytest ini option rather than weakening the guard.

### Changing a reusable workflow's contract

Inputs, secrets, and outputs of `dependabot-policy.yaml`, `dependabot-reconciler.yaml`, `release-tag.yaml`, and `release-please.yaml` are a public interface. When you change one, update in the same pull request: the workflow header that documents it, the callers in `.github/workflows/`, and any example a consumer would copy. A header that contradicts the `on:` block below it is worse than an undocumented one — a consumer takes two incompatible setup instructions from a single file.

## Commit messages

Subjects are imperative and at most 72 characters, with no conventional-commits prefix — match what `git log` shows:

```text
Read the credentialed delegation from the base branch
Match pin comments against a version, not any digit
```

Bodies are optional but usual here, written as flowing paragraphs (one paragraph per line, no hard wrapping) explaining why the change is right rather than restating the diff. Trailers are added only when you mean them.

## Pull requests

There is no PR template; descriptions in this repository follow a consistent shape, and matching it helps review:

- **Summary** — what changes and, more importantly, why this is the right change.
- **Changes** — per-file or per-area, naming the reasoning behind anything non-obvious.
- **Test plan** — the commands you ran and their results, plus what you did _not_ exercise. "Not exercised: no run has executed with credentials" is a useful line; an invented test result is not.
- **Notes** — consequences a reviewer would otherwise have to discover: contract changes, behaviour that got quieter or louder, deliberate trade-offs.

Every pull request needs the `gate` status check green and one approving review. Merges are squash-only, and the branch is deleted afterwards. Copilot reviews each push automatically; its findings are advisory, and disagreeing with one in the thread is a normal outcome.

## Releasing

Maintainer task, documented in the [README](README.md#releasing): bump `[project] version` in `pyproject.toml`, move the `Unreleased` changelog content under a dated `## [X.Y.Z]` section, merge, then push the `vX.Y.Z` tag. The release workflow verifies tag, manifest, and changelog agree before it publishes anything, so a mismatch fails the release rather than shipping one.

## Contribution basis

By contributing you agree that your work is licensed under this project's [MIT license](LICENSE). There is no CLA and no sign-off requirement.
