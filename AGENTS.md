# Agent instructions

[CONTRIBUTING.md](CONTRIBUTING.md) is the contract — setup, the structural rules, commit and pull-request shape. Read it first. This file carries only what an agent gets wrong that a human reading that file would not.

## The guards are the product, not the CI

`oss-automation-guards` is installed by other repositories and read as an assurance about their workflow trees. A guard that passes a tree it should fail is a security bug, so:

- Never weaken or delete a guard to make a change pass. Change the workflow.
- Never add a file to `guards_trust_exempt` without saying, in the same change, why that file is a deliberate exception rather than a violation.
- A new guard ships with unit tests that fail without it, and with its rule written into CONTRIBUTING.md's "What the guards enforce" list.

## Two files nobody edits by hand

`[project] version` in `pyproject.toml` and the `## [X.Y.Z]` section of `CHANGELOG.md` are written by the **Prepare Release** workflow, which exists because the release refuses to publish unless the tag, the manifest and that section agree. Add prose under `## [Unreleased]`; leave the rest alone.

## The verify matrix names required checks

`verify.yaml`'s `python-version` matrix decides the status contexts the default branch's ruleset requires: `verify / test (3.10)` and `verify / test (3.14)`. Rename a leg and its context is renamed with it, leaving every open pull request waiting on a check that will never report — the ruleset is a repository setting, so no commit can fix it. Treat a matrix edit as a ruleset change first: have the required-checks list updated in the same sitting.

`test.yaml` now carries that aggregator — a `verified` job depending on the others, running on `always()`, failing unless each concluded success. It is not required yet, because required contexts are a repository setting rather than a commit. Requiring it and dropping the two matrix contexts ends the coupling above, and makes every job in `test.yaml` gate a merge rather than only the two the ruleset happens to name:

```bash
gh api repos/milanhorvatovic/oss-automation/rulesets/20756252 \
  --jq '.rules[] | select(.type=="required_status_checks")'   # inspect first
```

Then set `required_status_checks` to `gate` and `verified` alone.

## A workflow header is part of the change

Every reusable workflow states its trust model in a comment block above its `on:` key, and consumers set their repositories up from it. A change to behaviour that leaves the header describing the old behaviour is worse than no header: it hands a consumer two incompatible instructions from one file. Update both in the same change.

## Credentialed jobs stay checkout-free

The `pull_request_target` callers hold App credentials and check out nothing, which is the whole reason that trigger is safe here. A guard enforces it, but the rule matters more than the guard: if a step needs the repository's files, it belongs in a different job.

## Before proposing a change

Run the commands CONTRIBUTING.md lists under "Making a change" — the linter, both suites, and whatever coverage pass it names. Do not copy them here; a second copy is a second thing to keep current.

Report what you did not exercise. No run in this repository has ever executed with real App credentials from a local session, and writing "verified" about one is worse than writing nothing.
