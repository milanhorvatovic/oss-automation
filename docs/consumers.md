# Setting up a consumer repository

Everything a repository needs before it can call these workflows, in the order it needs it. The reusable workflows document their own inputs in the comment block above each `on:` key; this page covers what the YAML cannot — the App, the secret store, the labels, and the repository settings that decide whether an armed pull request ever merges.

Skip to [the guard pack](#the-guard-pack) if all you want is the structural tests, or to [the release workflows](#6-the-release-workflows) if you are not wiring Dependabot automation; neither needs the App, the variables or the ruleset below.

## What you supply, and what you get

The workflows carry the policy. Your repository carries its own facts: which dependencies are privileged, which App speaks for the automation, whether the kill switch is on. Nothing here reads a value from this repository at run time — a caller passes what it wants judged, and everything else is a fixed convention listed below.

## 1. The automation App

Auto-merge needs an identity that is not the default `GITHUB_TOKEN`, and the reason bites silently: GitHub runs no workflow for an event an Actions token created. Every event this automation makes falls under that guard — the approval it posts, and the branch update it performs onto a moved base — so the required checks never report on the head the automation just produced, and the pull request sits waiting for checks that will never arrive. An App is a separate installation identity, so the events it creates trigger workflows the way a person's do.

Create a GitHub App owned by you or your organization, with **repository permissions**:

| Permission | Level | Used for |
| --- | --- | --- |
| Contents | Read and write | Updating a pull request's branch onto a moved base |
| Pull requests | Read and write | Approving, arming auto-merge, dismissing its own approvals |
| Actions | Read and write — optional | Re-running a policy run the reconciler found dropped. Omitting it costs that one path and nothing else: the reconciler mints the rerun token separately and degrades a failed mint to a notice |
| Issues | Read and write — optional | Only if you pass this App's credentials to `release-please`: it mints its token asking for the issues scope, and an App without the grant cannot mint at all |

Install it on every repository that will call the Dependabot workflows, and on any that wants the App-backed `release-please` flow. `release-tag` never touches an App, and `release-please` runs without one too — though its default-token fallback needs a repository setting of its own, covered under [the release workflows](#6-the-release-workflows). Then, in each of the repositories that do need it:

- **Repository variable `AUTOMATION_CLIENT_ID`** — the App's client id. An identifier, not a credential, which is why it travels as a variable.
- **Actions secret `AUTOMATION_PRIVATE_KEY`** — the App's private key, stored exactly as GitHub handed it to you, newlines and all. The **Actions** store specifically: `pull_request_target` reads that one, not the Dependabot store.

## 2. The fixed conventions

These are not inputs. They are the same in every repository the fleet covers, so a maintainer reading one caller can predict the rest.

- **Repository variable `DEPENDABOT_AUTOMERGE_ENABLED`** — the kill switch. `true` arms the policy, and GitHub compares expression strings case-insensitively, so `TRUE` and `True` arm it just as much; anything else, including the variable being absent, revokes the policy's own approvals and disarms what it armed. To turn automation off, set `false` or remove the variable — any spelling of true leaves it on, whatever the case. Flipping it emits no pull-request event, so it takes effect per pull request on that pull request's next event, or on the reconciler's next completed sweep. GitHub schedules cron runs on a best-effort basis and can delay or drop one, so that sweep is a recovery path rather than a revocation deadline.
- **Labels `trust-boundary` and `security-review-required`** — the veto. Either one is a hard stop: the pull request is left untouched, and a label arriving after the fact disarms auto-merge that was already set.

## 3. Repository settings

| Setting | Value | Why |
| --- | --- | --- |
| Allow auto-merge | on | The policy arms auto-merge; without this it cannot |
| Allow squash merging | on | The policy merges with `--squash` |
| Automatically delete head branches | on | Keeps Dependabot's branches from accumulating |

On the default branch, a ruleset with:

- **Require a pull request before merging**, with at least one approving review — this is what holds a _held_-tier bump until a maintainer acts.
- **Dismiss stale pull request approvals when new commits are pushed** — the policy approves a head it verified; without dismissal that approval outlives the commit it was about.
- **Require status checks to pass**, including the `gate` context described below, and every check that decides whether your code is releasable. A check that is not required does not block auto-merge, so a bump that breaks your test suite merges itself.
- **Squash** as the only allowed merge method.

Do **not** require code-owner review unless you have narrowed `CODEOWNERS` to paths Dependabot never touches. A GitHub App can never be a code owner, so every App-approved pull request would sit at `REVIEW_REQUIRED` forever with nothing failing to explain why.

## 4. The policy caller

Copy this into `.github/workflows/dependabot-automerge.yaml`, replacing `<sha>` with a full 40-character commit SHA of this repository:

```yaml
name: Dependabot Automerge

on:
  pull_request_target:
    types:
      - opened
      - reopened
      - synchronize
      - labeled
      - unlabeled
      - edited

permissions:
  contents: read
  pull-requests: read

jobs:
  caller:
    if: >-
      github.event.pull_request.user.login == 'dependabot[bot]' && github.event.pull_request.head.repo.full_name == github.repository && github.event.pull_request.base.ref == github.event.repository.default_branch
    uses: milanhorvatovic/oss-automation/.github/workflows/dependabot-policy.yaml@<sha> # v0.1.0
    with:
      # The two workflow pins and the token action execute with your App
      # credentials wherever this caller runs. actions/checkout is here
      # because this example assumes a tree where checkout also runs under
      # a write scope; drop it if yours never does.
      privileged-dependencies: |
        milanhorvatovic/oss-automation/.github/workflows/dependabot-policy.yaml
        milanhorvatovic/oss-automation/.github/workflows/dependabot-reconciler.yaml
        actions/create-github-app-token
        actions/checkout
      automation-client-id: ${{ vars.AUTOMATION_CLIENT_ID }}
    secrets:
      automation-private-key: ${{ secrets.AUTOMATION_PRIVATE_KEY }}

  gate:
    needs: caller
    if: always()
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Fail on a failed or cancelled policy run
        env:
          RESULT: ${{ needs.caller.result }}
        run: |
          set -euo pipefail
          if [[ "$RESULT" == "failure" || "$RESULT" == "cancelled" ]]; then
            echo "::error::The Dependabot policy run concluded ${RESULT}."
            exit 1
          fi
          echo "Policy result: ${RESULT}."
```

Four parts of that are load-bearing rather than stylistic:

- **`pull_request_target`, and no checkout anywhere in this file.** The trigger makes GitHub read this workflow from your default branch, so a pull request cannot supply the code your App credentials reach. That property survives only while no credentialed job checks out. Adding one forfeits it.
- **The `edited` trigger type.** A base retarget emits `edited` and nothing else. Without it, a retargeted pull request is never re-judged.
- **The three `if:` conjuncts.** Keyed on the pull request's _author_, never `github.actor` — the reconciler's branch updates emit `synchronize` events whose actor is the App, and an actor-keyed guard would skip exactly those. The third conjunct holds the delegation to pull requests targeting the default branch, because that is the only base for which the policy judging the pull request and the tree it runs against are the same.
- **The `gate` job, and `gate` as the required context.** The `caller` job skips on every non-Dependabot pull request, and a skipped job reports as passing while emitting no child contexts at all. Requiring the callee's contexts would strand every human pull request on a check that never reports; requiring `gate` works because `if: always()` makes it run either way.

`privileged-dependencies` is your list, and the test is the scope a bump's revision executes under, not the file it sits in: anything running in a job that holds a write scope or a secret belongs on it. The list above starts with these workflows themselves, because a bump of one of those pins changes the code your App credentials reach — leave them on it, and add whatever else in your tree runs privileged. Matching is exact and case-insensitive. A match is armed but held for you, never auto-approved.

## 5. The reconciler caller

Events get dropped, auto-merge fires stall, and a kill-switch flip reaches nobody until the next pull-request event. The reconciler is the scheduled recovery sweep for all three — best-effort, since GitHub can delay or skip a cron run under load. Copy into `.github/workflows/dependabot-reconcile.yaml`:

```yaml
name: Dependabot Reconcile

on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:

concurrency:
  group: dependabot-reconciler
  cancel-in-progress: false

permissions: {}

jobs:
  reconcile:
    permissions:
      contents: read
      pull-requests: read
      actions: read
    uses: milanhorvatovic/oss-automation/.github/workflows/dependabot-reconciler.yaml@<sha> # v0.1.0
    with:
      automation-client-id: ${{ vars.AUTOMATION_CLIENT_ID }}
    secrets:
      automation-private-key: ${{ secrets.AUTOMATION_PRIVATE_KEY }}
```

The `permissions:` block is required verbatim: a called workflow can only downgrade the caller's token, never raise it. The workflow-level `concurrency` group is the caller's job too — a called workflow's jobs cannot hold a group past their own lifetime, so overlapping sweeps can only be prevented here.

## 6. The release workflows

Two flavors; pick by your commit convention.

- **`release-tag.yaml`** — you push `vX.Y.Z`, your own jobs verify the tagged commit, and this workflow checks that the tag and the changelog's `## [X.Y.Z]` section agree before publishing. Manifest parity is the half you have to ask for: `version-command` defaults to an empty string, which skips the check, so a consumer that never sets it can publish a tag its manifest disagrees with. It runs no tests of its own: the project owns its suite.
- **`release-please.yaml`** — a bot-maintained release pull request accumulates the version bump and changelog. Requires your commits, or your squash titles, to follow Conventional Commits.

Each is called from a job you gate on your own verification, and that job's `permissions:` block is required verbatim for the same reason the reconciler caller's is — a called workflow can only downgrade the caller's token, never raise it. The two contracts differ. `release-tag.yaml` needs `contents: write`, and documents its inputs — `changelog-path`, `version-command`, `append-generated-notes`, `prerelease` — in its header. `release-please.yaml` needs `contents: write`, `issues: write` and `pull-requests: write`: the issues scope is not spare, since release-please tracks its own release pull request by label and labelling goes through the issues API. Its calling job also owns `concurrency: {group: release-please, cancel-in-progress: false}` — two default-branch merges seconds apart otherwise start two runs reconciling the same release pull request, and the loser leaves a stale body behind. The App credentials stay optional for it, but the default-token fallback carries a repository prerequisite of its own: **Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests** has to be on, or `GITHUB_TOKEN` cannot open the release pull request at all and the job fails before release-please writes anything. Passing the App credentials avoids that setting and is also what makes the release pull request trigger your other workflows.

## The guard pack

The structural tests need no App, no secret, and no settings. Install them from a tag or a commit and run them from your repository root:

```bash
pip install "oss-automation-guards @ git+https://github.com/milanhorvatovic/oss-automation@v0.1.0"
pytest --pyargs oss_automation_guards
```

They read `.github/workflows` by default; `--workflow-tree` points them elsewhere. The rules they enforce are listed in [CONTRIBUTING.md](../CONTRIBUTING.md#what-the-guards-enforce). A workflow file that is a deliberate exception to the trust-model rule is declared through the `guards_trust_exempt` pytest ini option rather than by weakening the guard.

## Checking that it works

The first Dependabot pull request is the test. On an eligible patch or minor bump you should see, in order: auto-merge armed, an approving review from your App, and the merge once your required checks go green. The arm deliberately precedes the approval — the approval can be the last merge requirement, so the merge method has to be settled before it lands. The run closes by annotating the tier it derived, the veto and commit-tamper-check states it read, and whether auto-merge was armed and the update approved — so a held update tells you which gate held it instead of leaving you to infer that from which steps ran. One exception: when the event that triggered the run already carried a veto label, the policy job is skipped and the disarm job annotates that hold instead. A label added after the event was emitted does not skip anything — that run reports the veto from its own live check. The approval corroborates it: it posts only for an eligible update, while a major or a privileged one is armed and left waiting for you.

If the approval posts but the merge never fires, the usual cause is a required check that never reports — most often the callee's contexts required directly instead of `gate`. If nothing happens at all, ask first whether the policy job ran: it logs a kill-switch value on every run it makes, so no logged value narrows it to two families. Either the caller's `if:` never matched — a head that lives in a fork, or a base that is not the default branch, both fall out there — or the callee skipped the policy for a veto label. Check the caller's three conditions before you go looking at labels.
