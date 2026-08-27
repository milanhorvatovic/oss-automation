# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `dependabot-policy` reusable workflow: a tiered Dependabot auto-merge policy — eligible patch/minor updates are approved and armed, majors and privileged dependencies are armed but held for a maintainer, veto labels are a hard stop with reactive disarm. Callers run on `pull_request_target`, so the delegation carrying the App credentials and the guards around it are read from the default branch rather than from the pull request, and the App's private key lives in the Actions secret store alone, its client id alongside it as a repository variable; a caller delegates only for pull requests targeting the default branch, since that is the tree a `pull_request_target` run executes.
- `dependabot-reconciler` reusable workflow: a scheduled sweep re-driving approved or armed Dependabot PRs after dropped events or base-branch advances, leaving everything else for manual triage.
- `oss-automation-guards` pytest test-pack: structural guards for job timeouts, full-commit-SHA action pins whose trailing comment is the pinned version — a comment that merely contains a digit, such as a branch and a date, does not satisfy it — pinned default-token scopes, and the trust-model binding of credentialed PR-triggered workflows.
- A coverage floor of 90% across both suites combined, measured by import name so it reads the installed package CI actually runs.
- `verify` reusable workflow holding the lint-and-both-suites definition that `test.yaml` and `release.yaml` had each carried a copy of, so a tag cannot be published by a weaker check than a pull request faced. Its status contexts are `verify / test (3.10)` and `verify / test (3.14)`.
- `.github/release.yml`, grouping GitHub's generated notes into categories a consumer reads in priority order. `release-prepare.yaml` writes those notes into the changelog section and `release-tag.yaml` publishes it, so the file shapes both halves of every release.
- Two further structural guards in `oss-automation-guards`: a credentialed job on a pull-request trigger never checks out, and a `run:` script never interpolates a `${{ … }}` expression into the shell it is about to execute. Both were invariants this repository's workflows already held and its comments already claimed; neither was enforced.
- `scorecard` workflow running OpenSSF Scorecard weekly and on pushes to the default branch, uploading its SARIF to code scanning and publishing the score so a consumer can check it before calling anything here. `ossf/scorecard-action` and `github/codeql-action` join the privileged-dependency list, since both execute under a write scope.
- Distribution metadata on the guard package — project URLs, classifiers, keywords, and a `py.typed` marker, so an installed copy carries its own provenance and its annotations reach a consumer's type checker.
- Community health files: a Contributor Covenant 2.1 `CODE_OF_CONDUCT.md`, issue forms that route security reports to a private advisory before an issue can be opened, and `AGENTS.md` for the failure modes an agent contributor hits that a human reading CONTRIBUTING.md does not.
- `docs/consumers.md`, the setup a caller needs that no `uses:` line can carry: the automation App and its permissions, the secret store the credentials belong in, the fixed kill-switch variable and veto labels, the repository settings and ruleset that decide whether an armed pull request ever merges, and copy-paste callers for both Dependabot workflows.
- Reusable release workflows in two flavors — `release-tag` (tag-driven: tag/changelog parity by default, tag/manifest parity once the caller passes a `version-command`, and curated-plus-generated notes) and `release-please` (Conventional-Commits driven) — with this repository releasing via the tag-driven flavor behind its full suite.

[Unreleased]: https://github.com/milanhorvatovic/oss-automation/commits/main
