"""Pure structural checks over a parsed workflow file.

Each check returns human-readable findings; an empty list means the
workflow satisfies that guard.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from .expressions import expression_bodies, has_unnegated, normalize
from .model import WorkflowFile

_FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_DOCKER_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}\Z")
_VERSION_SHAPED = re.compile(r"\d")

# GitHub expression contexts are case-insensitive, so every pattern below
# matches that way. The secrets context resolves only inside ${{ }} bodies,
# so only those are scanned — literal text like `echo 'secrets.KEY'` is inert.
_SECRET_DOT = re.compile(r"\bsecrets\.([A-Za-z0-9_]+)", re.IGNORECASE)
# Only a dynamic key survives normalization as an index; it can name any
# secret, so it counts as credentialed.
_SECRET_INDEX = re.compile(r"\bsecrets\s*\[", re.IGNORECASE)
# Bare context use — toJSON(secrets), fromJSON, a naked `secrets` — exposes
# every secret at once, so it can never ride the GITHUB_TOKEN exemption.
_SECRET_CONTEXT = re.compile(r"\bsecrets\b(?!\s*[.\[])", re.IGNORECASE)

_PR_TRIGGERS = frozenset({"pull_request", "pull_request_target"})
_AUTHOR_PIN = "github.event.pull_request.user.login"
_HEAD_REPO_PIN = "github.event.pull_request.head.repo.full_name"


def _delimited(path: str) -> str:
    # Both ends anchored so a longer identifier sharing the path as prefix or
    # suffix (user.login_suffix, xgithub.event...) can never satisfy a pin.
    return rf"(?<![\w.-]){re.escape(path)}(?![\w.-])"


# Equality only: a negated or merely-mentioned pin is not a trust guard.
# Structural, not semantic — the guard proves an equality on the pin exists,
# not that it gates the job (`always() || <pin>` still passes).
#
# The author pin must compare against a string literal — the '' placeholder
# literal-stripping leaves behind — so a tautology (login == login) or a
# comparison against another dynamic context never counts as an identity pin.
_AUTHOR_EQUALITY = re.compile(
    rf"{_delimited(_AUTHOR_PIN)}\s*==\s*''|''\s*==\s*{_delimited(_AUTHOR_PIN)}",
    re.IGNORECASE,
)
# The head pin must compare against github.repository specifically — an
# equality with any other operand (a fork literal, another context) would
# pass a job that runs credentialed on foreign heads.
_HEAD_REPO_EQUALITY = re.compile(
    rf"{_delimited(_HEAD_REPO_PIN)}\s*==\s*{_delimited('github.repository')}"
    rf"|{_delimited('github.repository')}\s*==\s*{_delimited(_HEAD_REPO_PIN)}",
    re.IGNORECASE,
)
# The \b keeps distinct contexts like github.actor_id from matching; the
# indexed spelling arrives here as a dot path via normalization.
_ACTOR_REFERENCE = re.compile(r"github\.actor\b", re.IGNORECASE)


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
        elif not _VERSION_SHAPED.search(comment):
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
    # A secret in the workflow-level env reaches every job, so it makes the
    # whole workflow's jobs credentialed, not just the ones referencing it.
    workflow_credentialed = _references_secret(workflow.data.get("env"))
    for job_id, job in workflow.jobs.items():
        if not (workflow_credentialed or _holds_credentials(job, workflow)):
            continue
        raw_condition = job.get("if")
        condition = normalize(raw_condition if isinstance(raw_condition, str) else "")
        prefix = f"job '{job_id}' holds credentials on a {'/'.join(pr_triggers)} trigger"
        if not has_unnegated(_AUTHOR_EQUALITY, condition):
            findings.append(
                f"{prefix} but its `if:` does not pin the pull-request author by"
                f" comparing {_AUTHOR_PIN} against a literal identity"
            )
        if not has_unnegated(_HEAD_REPO_EQUALITY, condition):
            findings.append(
                f"{prefix} but its `if:` does not pin the head repository via"
                f" {_HEAD_REPO_PIN} == github.repository"
            )
        if _ACTOR_REFERENCE.search(condition):
            findings.append(
                f"job '{job_id}' keys trust on github.actor; a synchronize event emitted"
                " by another actor (e.g. an automation App updating the branch) carries"
                f" that actor, not the PR author — key on {_AUTHOR_PIN} instead"
            )
    return findings


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
    for key_node, value_node in node.value:
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
    # An expression resolves at run time and cannot be judged here; a
    # container or boolean never denotes minutes.
    if isinstance(value, str):
        return bool(value.strip())
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


def _references_secret(node: Any) -> bool:
    names = set()
    for body in expression_bodies(json.dumps(node, default=str)):
        expression = normalize(body)
        names.update(name.lower() for name in _SECRET_DOT.findall(expression))
        if _SECRET_INDEX.search(expression):
            names.add("<dynamic>")
        if _SECRET_CONTEXT.search(expression):
            names.add("<context>")
    return bool(names - {"github_token"})


def _grants_write(job: dict[str, Any], workflow: WorkflowFile) -> bool:
    permissions = job.get("permissions", workflow.data.get("permissions"))
    if permissions == "write-all":
        return True
    if isinstance(permissions, dict):
        return "write" in permissions.values()
    return False
