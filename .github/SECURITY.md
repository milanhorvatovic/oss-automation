# Security Policy

## Supported versions

No tagged release exists yet, so nothing here is supported for production use. Once `v0.1.0` ships, the latest tag is the supported line; older tags receive fixes only when a consumer is demonstrably pinned to one.

Consumers call these workflows at a full 40-character commit SHA rather than a tag, so a fix reaches you when the pin moves — Dependabot's `github-actions` ecosystem raises that bump like any other.

## Reporting a vulnerability

Report privately through GitHub's **Report a vulnerability** button on this repository's [Security tab](https://github.com/milanhorvatovic/oss-automation/security). That opens a draft advisory visible only to you and the maintainer.

Do **not** open a public issue, pull request, or discussion for a security problem. This repository's product is the automation that merges dependency updates across other repositories; a public report describes an attack path against every consumer before a fix exists.

Expect an acknowledgement within five working days and an assessment with a fix or mitigation timeline after triage. This is a single-maintainer project, so those are best-effort commitments rather than a contractual SLA. Coordinated disclosure is appreciated, and reporters who want credit will get it in the advisory and the changelog entry.

## What counts as a vulnerability here

The interesting failures are in the trust model rather than in memory safety. Reports in these classes are in scope:

- **Reaching merge without satisfying the policy** — any path by which a Dependabot pull request is approved, armed, or merged when the tier rules say it should be held: a major bump, a privileged dependency, or a live veto label.
- **Credentials meeting pull-request code** — anything that puts App credentials in a job that executes code a pull request supplied, or that lets a pull request choose the workflow definition a credentialed run loads.
- **Defeating the tamper check** — commits that pass `dependabot-policy.yaml`'s authorship, committer and signature verification without having been authored by Dependabot or the automation App.
- **A guard that passes a tree it should fail** — a false negative in `oss-automation-guards` is a security bug, not a test bug: consumers run it as a gate and read a green result as an assurance about their own workflow tree.
- **Revocation that does not revoke** — a disarm or approval dismissal that reports success while auto-merge stays armed.

Out of scope: behaviour that requires a consumer to have disabled a documented requirement (the kill-switch variable, the required `gate` context, stale-review dismissal), and findings in GitHub Actions itself rather than in this repository's use of it. Report those to GitHub.

## Reporting a weakness in your own repository

If you run these workflows and believe your repository merged something it should not have, the artefacts worth attaching are the run logs of the `caller` and `gate` jobs, the pull request's commit list, and the resolved value of `DEPENDABOT_AUTOMERGE_ENABLED` at the time. The policy logs its switch state on every run precisely so that this question has an answer.
