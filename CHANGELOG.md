# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `dependabot-policy` reusable workflow: a tiered Dependabot auto-merge policy — eligible patch/minor updates are approved and armed, majors and privileged dependencies are armed but held for a maintainer, veto labels are a hard stop with reactive disarm.
- `dependabot-reconciler` reusable workflow: a scheduled sweep re-driving approved or armed Dependabot PRs after dropped events or base-branch advances, leaving everything else for manual triage.
- `oss-automation-guards` pytest test-pack: structural guards for job timeouts, full-commit-SHA action pins whose trailing comment is the pinned version — a comment that merely contains a digit, such as a branch and a date, does not satisfy it — pinned default-token scopes, and the trust-model binding of credentialed PR-triggered workflows.
- Reusable release workflows in two flavors — `release-tag` (tag-driven with tag/manifest/changelog parity checks and curated-plus-generated notes) and `release-please` (Conventional-Commits driven) — with this repository releasing via the tag-driven flavor behind its full suite.
