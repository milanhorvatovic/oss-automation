"""Structural guards a repository runs against its own workflow tree.

From the consumer repository's root:

    pytest --pyargs oss_automation_guards

or point the guards elsewhere with --workflow-tree. Each guard is
parametrized per workflow file, so a failure names the file and the finding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oss_automation_guards import checks
from oss_automation_guards.model import discover_workflows, load_workflow
from oss_automation_guards.plugin import workflow_tree


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "workflow_path" in metafunc.fixturenames:
        tree = workflow_tree(metafunc.config)
        paths = discover_workflows(tree)
        if not paths:
            # Zero parametrized cases would skip every guard and exit green;
            # an empty tree is the same failure class as a missing one.
            raise pytest.UsageError(f"no workflow files found in '{tree}'")
        metafunc.parametrize("workflow_path", paths, ids=[path.name for path in paths])


def _assert_clean(findings: list[str]) -> None:
    assert not findings, "\n" + "\n".join(findings)


def test_every_job_carries_a_timeout(workflow_path: Path) -> None:
    _assert_clean(checks.jobs_missing_timeout(load_workflow(workflow_path)))


def test_every_action_is_pinned_to_a_commit_sha(workflow_path: Path) -> None:
    _assert_clean(checks.unpinned_uses(load_workflow(workflow_path)))


def test_default_token_scopes_are_pinned(workflow_path: Path) -> None:
    _assert_clean(checks.unpinned_permissions(load_workflow(workflow_path)))


def test_pr_credentials_are_bound_to_the_trust_model(
    workflow_path: Path, pytestconfig: pytest.Config
) -> None:
    if workflow_path.name in set(pytestconfig.getini("guards_trust_exempt")):
        pytest.skip(f"{workflow_path.name} is declared exempt via guards_trust_exempt")
    _assert_clean(checks.unguarded_pr_credentials(load_workflow(workflow_path)))
