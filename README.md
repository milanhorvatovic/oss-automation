# oss-automation

Reusable GitHub Actions workflows and structural guard tests powering automation across [milanhorvatovic](https://github.com/milanhorvatovic)'s OSS repositories.

## What will live here

- **`dependabot-policy`** — a reusable workflow implementing a tiered Dependabot auto-merge policy: patch/minor updates of unprivileged dependencies are approved and armed for hands-off merge; majors and privileged dependencies are armed but held for a maintainer's approval; veto labels are a hard stop with a reactive disarm. Repo-specific facts (the privileged-dependency list) arrive as inputs; the kill switch is a fixed repository variable (`DEPENDABOT_AUTOMERGE_ENABLED`) read from the calling repository, not an input.
- **`dependabot-reconciler`** — a reusable workflow that re-drives approved or armed Dependabot PRs after dropped events or base-branch advances, and deliberately leaves anything else for manual triage.
- **A structural test-pack** — pytest guards consumers run against their own workflow trees: every job carries a timeout, every action is pinned to a full commit SHA with a trailing version comment, default-token write scopes are pinned, and PR-triggered workflows that hold credentials are bound to their declared trust model.

Consumers call the workflows at a full 40-character commit SHA and let Dependabot bump the pin. The test-pack installs the same way — `pip install "oss-automation-guards @ git+https://github.com/milanhorvatovic/oss-automation@<sha>"` — and runs from the consumer repository's root as `pytest --pyargs oss_automation_guards` (point it elsewhere with `--workflow-tree`; declare a deliberate trust-model exemption per workflow file with the `guards_trust_exempt` pytest ini option).

## Status

Under construction — the first tagged release will mark the workflows as consumable. Until then, nothing here is stable.

## License

[MIT](LICENSE)
