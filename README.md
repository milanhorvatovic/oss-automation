# oss-automation

[![Test](https://github.com/milanhorvatovic/oss-automation/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/milanhorvatovic/oss-automation/actions/workflows/test.yaml) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/milanhorvatovic/oss-automation/badge)](https://scorecard.dev/viewer/?uri=github.com/milanhorvatovic/oss-automation)

Reusable GitHub Actions workflows and structural guard tests powering automation across [milanhorvatovic](https://github.com/milanhorvatovic)'s OSS repositories.

## What is here

- **`dependabot-policy`** — a reusable workflow implementing a tiered Dependabot auto-merge policy: patch/minor updates of unprivileged dependencies are approved and armed for hands-off merge; majors and privileged dependencies are armed but held for a maintainer's approval; veto labels are a hard stop with a reactive disarm. Repo-specific facts (the privileged-dependency list, the automation App's client id) arrive as inputs; the kill switch is a fixed repository variable (`DEPENDABOT_AUTOMERGE_ENABLED`) read from the calling repository, not an input.
- **`dependabot-reconciler`** — a reusable workflow that re-drives approved or armed Dependabot PRs after dropped events or base-branch advances, and deliberately leaves anything else for manual triage.
- **`release-tag` and `release-please`** — release automation in two flavors, so integrators pick the one matching their commit convention. `release-tag` is tag-driven: the caller verifies with its own jobs, then the workflow checks tag/changelog parity — and tag/manifest parity too, once the caller passes the `version-command` that check is gated on — and publishes the GitHub Release with the changelog section as curated notes. `release-please` is Conventional-Commits driven, with a bot-maintained release pull request.
- **`oss-automation-guards`** — a pytest test-pack consumers run against their own workflow trees, guarding job timeouts, full-commit-SHA action pins, explicit token scopes, the trust model of credentialed pull-request workflows, and the two invariants that keep them honest: a credentialed job never checks out, and a `run:` script never interpolates an expression into the shell. The enforced rules are listed in [CONTRIBUTING.md](CONTRIBUTING.md#what-the-guards-enforce).

## Using it

Consumers call the workflows at a full 40-character commit SHA and let Dependabot bump the pin — a `uses:` reference is code that runs against the caller's token, so a tag someone can move is not good enough. The test-pack is a development dependency rather than a workflow reference, so a release tag selects a version fine; pin it to a commit as well if you want that same guarantee for the code grading your tree. Run it from the consumer repository's root:

```bash
pip install "oss-automation-guards @ git+https://github.com/milanhorvatovic/oss-automation@vX.Y.Z"
pytest --pyargs oss_automation_guards
```

Point it at another tree with `--workflow-tree`, and declare a deliberate trust-model exemption per workflow file with the `guards_trust_exempt` pytest ini option.

The Dependabot workflows need more than a `uses:` line — a GitHub App, an Actions secret, two repository variables, two labels, and a default-branch ruleset that lets an armed pull request actually merge. The release workflows need none of that: `release-tag` uses no App, and `release-please` takes the credentials only so its release pull request triggers your CI, falling back to the default token without them — a fallback that needs *Allow GitHub Actions to create and approve pull requests* enabled in the repository's Actions settings. **[docs/consumers.md](docs/consumers.md)** walks through all of it, with copy-paste callers.

## Stability

Workflow pins are commit SHAs, so no workflow changes underneath a consumer. What a new tag can change is what you get when you _move_ a pin: release notes call out every caller-contract change and every guard change that can turn a previously green tree red. Before `v1.0.0`, a minor bump may carry one.

## Dogfooding

This repository is the first consumer of its own Dependabot flavors, and both of its callers reference the workflows locally rather than at a SHA. That is safe rather than expedient: the policy caller runs on `pull_request_target`, whose workflow source GitHub resolves from the default branch, so a pull request cannot supply the code the App credentials reach — which is why the policy is checkout-free and must stay so. The same resolution is why that caller delegates only for pull requests targeting the default branch: any other base would be judged by a configuration it does not carry. Pinning at a release remains open as dogfooding rather than as a fix (see `.github/workflows/dependabot-automerge.yaml`).

## Releasing

This repository releases from `main` with the tag-driven flavor, and does not hand-edit the two files that have to agree with the tag. Run the **Prepare Release** workflow with the version: it opens a pull request bumping `[project] version` in `pyproject.toml` and promoting `## [Unreleased]` into a dated `## [X.Y.Z]` section whose body is GitHub's generated release notes for the range, categorized by `.github/release.yml`, with anything already written under `Unreleased` carried across above the generated list.

Merge that pull request, then tag its merge commit and push:

```bash
git tag -s vX.Y.Z "$MERGE_SHA"
git push origin vX.Y.Z
```

`-s` is worth the keystroke: the tag is what a consumer resolves a pin from, and a signed one carries a Verified badge on the release page once GitHub can check the signature — the public half of the key has to be on your account first. The release workflow does not require it.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers setup, the structural rules a change has to satisfy, and the shape of a commit and a pull request here. [AGENTS.md](AGENTS.md) adds what an agent contributor gets wrong. Participation is under the [Code of Conduct](CODE_OF_CONDUCT.md).

Security problems go through a private advisory, never a public issue — [SECURITY.md](.github/SECURITY.md) says what counts and what to attach.

## License

[MIT](LICENSE)
