"""Integration tests for the guard suite's tree resolution failure modes."""

from __future__ import annotations

import pytest


def _run_guards(pytester: pytest.Pytester) -> pytest.RunResult:
    return pytester.runpytest("--pyargs", "oss_automation_guards")


def test_missing_tree_terminates_with_a_usage_error(pytester: pytest.Pytester) -> None:
    result = _run_guards(pytester)
    assert result.ret != 0
    output = str(result.stdout) + str(result.stderr)
    assert "does not exist" in output


def test_empty_tree_terminates_instead_of_green_skipping(pytester: pytest.Pytester) -> None:
    (pytester.path / ".github" / "workflows").mkdir(parents=True)
    result = _run_guards(pytester)
    assert result.ret != 0
    output = str(result.stdout) + str(result.stderr)
    assert "no workflow files found" in output


def test_populated_tree_runs_the_guards(pytester: pytest.Pytester) -> None:
    tree = pytester.path / ".github" / "workflows"
    tree.mkdir(parents=True)
    (tree / "ci.yaml").write_text(
        "permissions:\n"
        "  contents: read\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 5\n"
        "    steps:\n"
        "      - run: echo ok\n",
        encoding="utf-8",
    )
    result = _run_guards(pytester)
    assert result.ret == 0
