<!--
The headings below are the shape CONTRIBUTING.md specifies and review here
expects. Delete one that genuinely does not apply rather than leaving it
empty — an empty heading reads as an unanswered question rather than as an
absent one.
-->

## Summary

<!-- What changes, and why this is the right change rather than the
alternatives. The diff already says what moved. -->

## Changes

<!-- Per file or per area, naming the reasoning behind anything
non-obvious. -->

## Test plan

<!-- The commands CONTRIBUTING.md lists under "Making a change", their
results, and what you did not exercise. "Not exercised: no run has executed
with credentials" is a useful line; an invented result is not. -->

## Notes

<!-- Consequences a reviewer would otherwise have to discover: contract
changes, behaviour that got quieter or louder, deliberate trade-offs. -->

---

### Before merge

- [ ] **Labelled** — carries one of `contract-change`, `security`, `enhancement`, `bug`, `documentation`, or `chore`. `.github/release.yml` sorts the generated release notes by label and `release-prepare.yaml` writes those notes into the changelog, so an unlabelled pull request lands under **Other changes** however consequential it was. `dependencies` is Dependabot's own.
- [ ] A changed input, secret, output, or **required** permission of a reusable workflow is labelled `contract-change`, and the workflow header documenting it, the callers in `.github/workflows/`, and any example a consumer copies all move in this pull request. Tightening a callee's own scopes without changing what a caller must grant is not a contract change.
- [ ] A new or tightened guard ships with unit tests that fail without it, and with its rule written into [What the guards enforce](https://github.com/milanhorvatovic/oss-automation/blob/main/CONTRIBUTING.md#what-the-guards-enforce). It is `contract-change` when it can turn a previously green consumer tree red.
- [ ] `[project] version` in `pyproject.toml` and the `## [X.Y.Z]` sections of `CHANGELOG.md` are untouched — **Prepare Release** writes both. Prose added under `## [Unreleased]` is fine, and is carried across.
