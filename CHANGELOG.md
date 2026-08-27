# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `dependabot-policy` reusable workflow: a tiered Dependabot auto-merge policy — eligible patch/minor updates are approved and armed, majors and privileged dependencies are armed but held for a maintainer, veto labels are a hard stop with reactive disarm. Callers run on `pull_request_target`, so the delegation carrying the App credentials and the guards around it are read from the default branch rather than from the pull request, and the App's private key lives in the Actions secret store alone, its client id alongside it as a repository variable; a caller delegates only for pull requests targeting the default branch, since that is the tree a `pull_request_target` run executes.
- `dependabot-reconciler` reusable workflow: a scheduled sweep re-driving approved or armed Dependabot PRs after dropped events or base-branch advances, leaving everything else for manual triage.
- `oss-automation-guards` pytest test-pack: structural guards for job timeouts, full-commit-SHA action pins whose trailing comment is the pinned version — a comment that merely contains a digit, such as a branch and a date, does not satisfy it — pinned default-token scopes, and the trust-model binding of credentialed PR-triggered workflows.
- `.github/release.yml`, grouping GitHub's generated notes into categories a consumer reads in priority order. `release-prepare.yaml` writes those notes into the changelog section and `release-tag.yaml` publishes it, so the file shapes both halves of every release.
- Two further structural guards in `oss-automation-guards`: a credentialed job on a pull-request trigger never checks out, and a `run:` script never interpolates a `${{ … }}` expression into the shell it is about to execute. Both were invariants this repository's workflows already held and its comments already claimed; neither was enforced.
- Reusable release workflows in two flavors — `release-tag` (tag-driven with tag/manifest/changelog parity checks and curated-plus-generated notes) and `release-please` (Conventional-Commits driven) — with this repository releasing via the tag-driven flavor behind its full suite.
