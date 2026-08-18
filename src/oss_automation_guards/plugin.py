"""pytest plugin surface: the options the guard tests read."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("oss-automation-guards")
    group.addoption(
        "--workflow-tree",
        default=None,
        help="Directory of GitHub Actions workflow files to guard"
        " (default: <invocation dir>/.github/workflows).",
    )
    parser.addini(
        "guards_trust_exempt",
        type="linelist",
        default=[],
        help="Workflow file names exempt from the pull-request trust-model guard.",
    )


def workflow_tree(config: pytest.Config) -> Path:
    option = config.getoption("--workflow-tree")
    # The invocation directory, not config.rootpath: under `pytest --pyargs`
    # an ancestor ini file can pull rootdir above the consumer repository,
    # which would silently point the guards at the wrong tree.
    tree = Path(option) if option else Path(config.invocation_params.dir, ".github", "workflows")
    if not tree.is_dir():
        raise pytest.UsageError(
            f"workflow tree '{tree}' does not exist; run from the repository root or"
            " pass --workflow-tree"
        )
    return tree
