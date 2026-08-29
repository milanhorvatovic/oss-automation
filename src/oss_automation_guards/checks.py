"""Pure structural checks over a parsed workflow file.

Each check returns human-readable findings; an empty list means the
workflow satisfies that guard.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from .expressions import (
    ContextPath,
    ExpressionError,
    Value,
    context_paths,
    expression_bodies,
    parse,
    parse_condition,
    positive_equalities,
)
from .model import WorkflowFile

_FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_DOCKER_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}\Z")
# The whole comment must be the version — matching a substring let
# `# main 2026-08-17` pass on the date's digits alone. A prerelease or build
# suffix is admitted only after a dotted core, so a bare date cannot parse as
# one without banning the hyphens semver allows inside identifiers.
# Deliberately looser than semver: docker tags (`3.20-alpine`) and bare majors
# (`v7`) are versions a pin legitimately names.
_IDENTIFIER = r"[0-9A-Za-z-]+"
_VERSION_COMMENT = re.compile(
    rf"v?\d+(?:\.\d+)+"
    rf"(?:-{_IDENTIFIER}(?:\.{_IDENTIFIER})*)?"
    rf"(?:\+{_IDENTIFIER}(?:\.{_IDENTIFIER})*)?"
    rf"|v?\d+"
)
# Only consulted when an expression does not parse, to decide whether the
# unknown could have been a credential.
_SECRETS_MENTION = re.compile(r"\bsecrets\b", re.IGNORECASE)

_PR_TRIGGERS = frozenset({"pull_request", "pull_request_target"})
# Context paths are matched case-insensitively, as GitHub resolves them.
_AUTHOR_PIN = "github.event.pull_request.user.login"
_HEAD_REPO_PIN = "github.event.pull_request.head.repo.full_name"
_REPOSITORY = "github.repository"
_ACTOR = "github.actor"
_GITHUB_CONTEXT = "github"
_DEFAULT_TOKEN = "github_token"
# Named absolutely rather than keyed on a `ref:` that resolves to the pull
# request's head: on pull_request the default ref is already the merge commit,
# and on pull_request_target a base checkout is one edit away from a head one.
# "A credentialed job does not check out" is the rule a reader can hold.
_CHECKOUT_ACTION = "actions/checkout"


def jobs_missing_timeout(workflow: WorkflowFile) -> list[str]:
    findings = []
    for job_id, job in workflow.jobs.items():
        if "uses" in job:
            # A reusable-workflow call cannot carry timeout-minutes; the
            # callee's own jobs are where this guard applies.
            continue
        timeout = job.get("timeout-minutes")
        # A bare `timeout-minutes:` is a YAML null — key present, no value —
        # and leaves the job on the default exactly like a missing key.
        if timeout is None:
            findings.append(
                f"job '{job_id}' declares no timeout-minutes; a hung run would hold its"
                " runner for GitHub's 6-hour default"
            )
        elif not _is_usable_timeout(timeout):
            findings.append(
                f"job '{job_id}' sets timeout-minutes to {timeout!r}, which is not a"
                " positive number of minutes, so no timeout is imposed"
            )
    return findings


def unpinned_uses(workflow: WorkflowFile) -> list[str]:
    findings = []
    lines = workflow.text.splitlines()
    for location, value, lineno in _uses_targets(workflow):
        if value.startswith("./"):
            continue
        if value.startswith("docker://"):
            if not _DOCKER_DIGEST.search(value):
                findings.append(f"{location} uses '{value}' without a sha256 digest pin")
        else:
            ref = value.partition("@")[2]
            if not _FULL_COMMIT_SHA.fullmatch(ref):
                findings.append(
                    f"{location} uses '{value}', which is not pinned to a full"
                    " 40-character commit SHA"
                )
        comment = _trailing_comment(lines[lineno - 1]) if lineno <= len(lines) else None
        if comment is None:
            findings.append(f"line {lineno} pins '{value}' without a trailing version comment")
        elif not _VERSION_COMMENT.fullmatch(comment):
            findings.append(
                f"line {lineno} annotates '{value}' with '# {comment}', which does not"
                " name the pinned version"
            )
    return findings


def unpinned_permissions(workflow: WorkflowFile) -> list[str]:
    findings = []
    workflow_value = workflow.data.get("permissions")
    findings += _permission_value_findings(
        "workflow-level", "permissions" in workflow.data, workflow_value
    )
    workflow_pinned = _is_scope_pin(workflow_value)
    for job_id, job in workflow.jobs.items():
        job_value = job.get("permissions")
        findings += _permission_value_findings(f"job '{job_id}'", "permissions" in job, job_value)
        if not workflow_pinned and not _is_scope_pin(job_value):
            findings.append(
                f"job '{job_id}' inherits the repository's default token scopes; pin them"
                " with a `permissions:` block at the workflow or job level"
            )
    return findings


def unguarded_pr_credentials(workflow: WorkflowFile) -> list[str]:
    pr_triggers = sorted(set(workflow.triggers) & _PR_TRIGGERS)
    if not pr_triggers:
        return []
    findings = []
    for job_id, job in _credentialed_pr_jobs(workflow):
        raw_condition = job.get("if")
        # An unparseable condition proves nothing, so it pins nothing: the
        # guard reports both pins missing rather than assume the best.
        try:
            condition = parse_condition(raw_condition) if isinstance(raw_condition, str) else None
        except ExpressionError:
            condition = None
        equalities = positive_equalities(condition) if condition is not None else []
        paths = context_paths(condition) if condition is not None else []
        prefix = f"job '{job_id}' holds credentials on a {'/'.join(pr_triggers)} trigger"
        if not _pins_literal_identity(equalities, _AUTHOR_PIN):
            findings.append(
                f"{prefix} but its `if:` does not pin the pull-request author by"
                f" comparing {_AUTHOR_PIN} against a literal identity"
            )
        if not _pins_paths(equalities, _HEAD_REPO_PIN, _REPOSITORY):
            findings.append(
                f"{prefix} but its `if:` does not pin the head repository via"
                f" {_HEAD_REPO_PIN} == github.repository"
            )
        if any(_is_path(path, _ACTOR) for path in paths):
            findings.append(
                f"job '{job_id}' keys trust on github.actor; a synchronize event emitted"
                " by another actor (e.g. an automation App updating the branch) carries"
                f" that actor, not the PR author — key on {_AUTHOR_PIN} instead"
            )
        elif any(_may_reach_actor(path) for path in paths):
            findings.append(
                f"job '{job_id}' dereferences the github context with a computed key,"
                " which this guard cannot resolve; if it names 'actor', the job keys"
                f" trust on the event actor rather than on {_AUTHOR_PIN}"
            )
    return findings


def credentialed_jobs_that_check_out(workflow: WorkflowFile) -> list[str]:
    pr_triggers = sorted(set(workflow.triggers) & _PR_TRIGGERS)
    if not pr_triggers:
        return []
    triggers = "/".join(pr_triggers)
    findings = []
    for job_id, job in _credentialed_pr_jobs(workflow):
        for index, step in _steps(job):
            uses = step.get("uses")
            if isinstance(uses, str) and _names_action(uses, _CHECKOUT_ACTION):
                findings.append(
                    f"job '{job_id}' step {index} checks out while holding credentials on"
                    f" a {triggers} trigger; keep credentialed jobs checkout-free so no"
                    " tree a pull request can steer shares a runner with them"
                )
    return findings


def interpolated_run_scripts(workflow: WorkflowFile) -> list[str]:
    findings = []
    for job_id, job in workflow.jobs.items():
        for index, step in _steps(job):
            script = step.get("run")
            if not isinstance(script, str):
                continue
            for body in expression_bodies(script):
                expression = "${{" + body + "}}"
                findings.append(
                    f"job '{job_id}' step {index} interpolates {expression} into its `run:`"
                    " script; the value is pasted into the shell before it runs, so one"
                    " carrying shell syntax executes — bind it to an `env:` variable and"
                    " read that instead"
                )
    return findings


def _credentialed_pr_jobs(workflow: WorkflowFile) -> list[tuple[str, dict[str, Any]]]:
    """Jobs a credential reaches, for a workflow carrying a pull-request trigger."""
    # A secret in the workflow-level env reaches the steps of every runner
    # job, so those are credentialed whether or not they name it. A job that
    # calls a reusable workflow has no steps of its own and the callee does
    # not inherit the caller's env, so it is credentialed only by what it
    # passes down.
    workflow_credentialed = _references_secret(workflow.data.get("env"))
    return [
        (job_id, job)
        for job_id, job in workflow.jobs.items()
        if (workflow_credentialed and "uses" not in job) or _holds_credentials(job, workflow)
    ]


def _steps(job: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """Step mappings with their 1-based position, which non-mappings still occupy."""
    steps = job.get("steps")
    if not isinstance(steps, list):
        return []
    return [(index, step) for index, step in enumerate(steps, start=1) if isinstance(step, dict)]


def _names_action(uses: str, action: str) -> bool:
    if uses.startswith(("./", "docker://")):
        return False
    return uses.partition("@")[0].strip().lower() == action


def _uses_targets(workflow: WorkflowFile) -> list[tuple[str, str, int]]:
    """Every `uses:` target as (location, value, 1-based line of the value node).

    Walks the composed YAML node graph instead of scanning raw lines, so text
    inside comments or `run:` blocks is never mistaken for a step, and folded
    or quoted scalars resolve to their real value and source line.
    """
    targets = []
    jobs = _mapping_entry(yaml.compose(workflow.text, yaml.SafeLoader), "jobs")
    if not isinstance(jobs, yaml.MappingNode):
        return []
    for job_key, job_node in jobs.value:
        job_id = job_key.value if isinstance(job_key, yaml.ScalarNode) else "?"
        job_uses = _mapping_entry(job_node, "uses")
        if isinstance(job_uses, yaml.ScalarNode):
            targets.append((f"job '{job_id}'", job_uses.value, job_uses.start_mark.line + 1))
        steps = _mapping_entry(job_node, "steps")
        if not isinstance(steps, yaml.SequenceNode):
            continue
        for index, step in enumerate(steps.value, start=1):
            step_uses = _mapping_entry(step, "uses")
            if isinstance(step_uses, yaml.ScalarNode):
                targets.append(
                    (
                        f"job '{job_id}' step {index}",
                        step_uses.value,
                        step_uses.start_mark.line + 1,
                    )
                )
    return targets


def _mapping_entry(node: yaml.Node | None, key: str) -> yaml.Node | None:
    if not isinstance(node, yaml.MappingNode):
        return None
    # The stubs leave MappingNode.value untyped; a mapping node holds the
    # (key, value) node pairs its entries were parsed from.
    pairs: list[tuple[yaml.Node, yaml.Node]] = node.value
    for key_node, value_node in pairs:
        if isinstance(key_node, yaml.ScalarNode) and key_node.value == key:
            return value_node
    return None


def _trailing_comment(raw_line: str) -> str | None:
    in_single = in_double = False
    for index, char in enumerate(raw_line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif (
            char == "#"
            and not in_single
            and not in_double
            and (index == 0 or raw_line[index - 1] in " \t")
        ):
            return raw_line[index + 1 :].strip() or None
    return None


def _is_usable_timeout(value: Any) -> bool:
    # A container or boolean never denotes minutes.
    if isinstance(value, str):
        text = value.strip()
        # An expression resolves at run time and cannot be judged here; any
        # other string has to read as a positive number of minutes.
        if "${{" in text:
            return True
        try:
            return float(text) > 0
        except ValueError:
            return False
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) and value > 0


def _permission_value_findings(owner: str, present: bool, value: Any) -> list[str]:
    if not present:
        return []
    if value == "write-all":
        return [
            f"{owner} `permissions: write-all` grants every scope; enumerate the scopes instead"
        ]
    if value is None:
        return [
            f"{owner} bare `permissions:` parses as a YAML null, not the empty scope map;"
            " write `permissions: {}` or enumerate the scopes"
        ]
    if _is_scope_pin(value):
        return []
    # Anything else — a list, a bare scope name — pins nothing, and silence
    # here would read as a satisfied guard.
    return [
        f"{owner} `permissions: {value!r}` is not a scope map or read-all/write-all,"
        " so it pins no token scopes"
    ]


def _is_scope_pin(value: Any) -> bool:
    return isinstance(value, dict) or (
        isinstance(value, str) and value in {"read-all", "write-all"}
    )


def _holds_credentials(job: dict[str, Any], workflow: WorkflowFile) -> bool:
    if job.get("secrets") == "inherit":
        return True
    # A `secrets:` mapping on a reusable-workflow call is covered by the
    # reference scan below, so passing only the default token stays exempt.
    if _references_secret(job):
        return True
    # Declared write scopes are credentials on either PR trigger: only a
    # public repository's fork PRs get a force-downgraded token on
    # pull_request — same-repo runs receive the declared scopes, and private
    # repositories can extend write tokens to fork PRs by settings.
    return _grants_write(job, workflow)


def _is_path(node: Any, dotted: str) -> bool:
    return (
        isinstance(node, ContextPath) and not node.dynamic and node.dotted.lower() == dotted.lower()
    )


def _may_reach_actor(node: Any) -> bool:
    """Whether a computed dereference of the github context could name `actor`.

    `github[format('{0}', 'actor')]` resolves to `github.actor` only at run
    time, so the guard reports what it cannot rule out instead of reading a
    key it cannot see. Statically resolvable keys are deliberately not
    constant-folded: the conservative answer covers them too.
    """
    return (
        isinstance(node, ContextPath)
        and node.dynamic
        and bool(node.segments)
        and node.segments[0].lower() == _GITHUB_CONTEXT
    )


def _pins_literal_identity(equalities: list[tuple[Any, Any]], path: str) -> bool:
    """Whether some asserted equality compares `path` to a string literal."""
    for left, right in equalities:
        for candidate, other in ((left, right), (right, left)):
            if _is_path(candidate, path) and isinstance(other, Value) and other.kind == "string":
                return True
    return False


def _pins_paths(equalities: list[tuple[Any, Any]], path: str, expected: str) -> bool:
    """Whether some asserted equality compares the two given paths."""
    for left, right in equalities:
        for candidate, other in ((left, right), (right, left)):
            if _is_path(candidate, path) and _is_path(other, expected):
                return True
    return False


def _references_secret(node: Any) -> bool:
    """Whether any expression in `node` reads a secret other than the default token.

    The secrets context resolves only inside `${{ }}`, so literal text such
    as `echo 'secrets.KEY'` is inert.
    """
    for body in expression_bodies(json.dumps(node, default=str)):
        try:
            expression = parse(body)
        except ExpressionError:
            # An unreadable expression could name any secret.
            if _SECRETS_MENTION.search(body):
                return True
            continue
        for path in context_paths(expression):
            if not path.segments or path.segments[0].lower() != "secrets":
                continue
            # A whole-context read — `secrets`, `secrets.*`, a computed key —
            # exposes every secret, so it can never ride the exemption.
            if path.dynamic or len(path.segments) == 1 or path.segments[1] == "*":
                return True
            if path.segments[1].lower() != _DEFAULT_TOKEN:
                return True
    return False


def _grants_write(job: dict[str, Any], workflow: WorkflowFile) -> bool:
    permissions = job.get("permissions", workflow.data.get("permissions"))
    if permissions == "write-all":
        return True
    if isinstance(permissions, dict):
        return "write" in permissions.values()
    return False
