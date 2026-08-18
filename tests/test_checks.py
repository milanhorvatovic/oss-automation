"""Unit tests for the structural checks, driven by inline workflow fixtures."""

from __future__ import annotations

import pytest

from oss_automation_guards import checks
from oss_automation_guards.model import WorkflowFile, WorkflowLoadError

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
DIGEST = "sha256:" + "ab" * 32


def workflow(text: str) -> WorkflowFile:
    return WorkflowFile.from_text(text)


class TestModel:
    def test_triggers_survive_the_norway_problem(self) -> None:
        parsed = workflow("on:\n  pull_request:\njobs: {}\n")
        assert set(parsed.triggers) == {"pull_request"}

    def test_triggers_accept_list_and_string_forms(self) -> None:
        assert set(workflow("on: [push, pull_request]\njobs: {}\n").triggers) == {
            "push",
            "pull_request",
        }
        assert set(workflow("on: push\njobs: {}\n").triggers) == {"push"}

    def test_non_mapping_document_is_a_load_error(self) -> None:
        with pytest.raises(WorkflowLoadError):
            workflow("- not\n- a\n- workflow\n")

    def test_unparseable_yaml_is_a_load_error(self) -> None:
        with pytest.raises(WorkflowLoadError):
            workflow("jobs: [unclosed\n")


class TestTimeouts:
    def test_job_with_timeout_passes(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                runs-on: ubuntu-latest
                timeout-minutes: 10
                steps: []
            """
        )
        assert checks.jobs_missing_timeout(parsed) == []

    def test_job_without_timeout_is_found(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                runs-on: ubuntu-latest
                steps: []
            """
        )
        findings = checks.jobs_missing_timeout(parsed)
        assert len(findings) == 1
        assert "'build'" in findings[0]

    def test_reusable_call_job_is_exempt(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              call:
                uses: owner/repo/.github/workflows/callee.yaml@{SHA}
            """
        )
        assert checks.jobs_missing_timeout(parsed) == []


class TestUsesPinning:
    def test_sha_pin_with_version_comment_passes(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA} # v7.0.1
            """
        )
        assert checks.unpinned_uses(parsed) == []

    def test_tag_pin_is_found(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                steps:
                  - uses: actions/checkout@v7 # v7
            """
        )
        findings = checks.unpinned_uses(parsed)
        assert len(findings) == 1
        assert "40-character" in findings[0]

    def test_missing_ref_is_found(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                steps:
                  - uses: actions/checkout # v7
            """
        )
        assert any("40-character" in finding for finding in checks.unpinned_uses(parsed))

    def test_sha_pin_without_version_comment_is_found(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA}
            """
        )
        findings = checks.unpinned_uses(parsed)
        assert len(findings) == 1
        assert "version comment" in findings[0]

    def test_each_uncommented_occurrence_is_found(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA} # v7.0.1
                  - uses: actions/checkout@{SHA}
            """
        )
        findings = checks.unpinned_uses(parsed)
        assert len(findings) == 1
        assert "line 6" in findings[0]

    def test_local_action_is_exempt(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                steps:
                  - uses: ./.github/actions/local-thing
            """
        )
        assert checks.unpinned_uses(parsed) == []

    def test_docker_digest_pin_passes_and_tag_is_found(self) -> None:
        pinned = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: docker://alpine@{DIGEST} # 3.20
            """
        )
        assert checks.unpinned_uses(pinned) == []
        floating = workflow(
            """
            jobs:
              build:
                steps:
                  - uses: docker://alpine:3.20 # 3.20
            """
        )
        assert any("digest" in finding for finding in checks.unpinned_uses(floating))

    def test_reusable_workflow_call_is_checked(self) -> None:
        parsed = workflow(
            """
            jobs:
              call:
                uses: owner/repo/.github/workflows/callee.yaml@main # main
            """
        )
        assert any("40-character" in finding for finding in checks.unpinned_uses(parsed))

    def test_commented_example_lines_are_ignored(self) -> None:
        # A caller contract quoted in a header comment must not shadow the
        # real, properly commented step below it.
        parsed = workflow(
            f"""
            # Example caller:
            #   uses: actions/checkout@{SHA}
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA} # v7.0.1
            """
        )
        assert checks.unpinned_uses(parsed) == []

    def test_quoted_uses_value_is_matched(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: "actions/checkout@{SHA}" # v7.0.1
            """
        )
        assert checks.unpinned_uses(parsed) == []

    def test_uses_text_inside_run_blocks_is_ignored(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA} # v7.0.1
                  - run: |
                      echo "uses: actions/checkout@{SHA}"
            """
        )
        assert checks.unpinned_uses(parsed) == []

    def test_folded_scalar_uses_carries_its_comment_on_the_key_line(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              call:
                uses: >- # v1.0.0
                  owner/repo/.github/workflows/callee.yaml@{SHA}
            """
        )
        assert checks.unpinned_uses(parsed) == []

    def test_comment_without_a_version_is_found(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA} # nosemgrep
            """
        )
        findings = checks.unpinned_uses(parsed)
        assert len(findings) == 1
        assert "does not name the pinned version" in findings[0]


class TestPermissions:
    def test_workflow_level_block_passes(self) -> None:
        parsed = workflow(
            """
            permissions:
              contents: read
            jobs:
              build:
                steps: []
            """
        )
        assert checks.unpinned_permissions(parsed) == []

    def test_per_job_blocks_pass_without_workflow_block(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                permissions:
                  contents: read
                steps: []
            """
        )
        assert checks.unpinned_permissions(parsed) == []

    def test_empty_workflow_block_passes(self) -> None:
        parsed = workflow(
            """
            permissions: {}
            jobs:
              build:
                steps: []
            """
        )
        assert checks.unpinned_permissions(parsed) == []

    def test_unpinned_job_is_found(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                steps: []
            """
        )
        findings = checks.unpinned_permissions(parsed)
        assert len(findings) == 1
        assert "default token scopes" in findings[0]

    def test_write_all_is_found_at_both_levels(self) -> None:
        at_workflow = workflow(
            """
            permissions: write-all
            jobs:
              build:
                steps: []
            """
        )
        assert any("write-all" in finding for finding in checks.unpinned_permissions(at_workflow))
        at_job = workflow(
            """
            permissions:
              contents: read
            jobs:
              build:
                permissions: write-all
                steps: []
            """
        )
        assert any("write-all" in finding for finding in checks.unpinned_permissions(at_job))

    def test_read_all_passes(self) -> None:
        parsed = workflow(
            """
            permissions: read-all
            jobs:
              build:
                steps: []
            """
        )
        assert checks.unpinned_permissions(parsed) == []

    def test_list_shaped_permissions_do_not_crash(self) -> None:
        parsed = workflow(
            """
            permissions: [contents]
            jobs:
              build:
                steps: []
            """
        )
        findings = checks.unpinned_permissions(parsed)
        assert any("default token scopes" in finding for finding in findings)

    def test_null_permissions_block_is_found(self) -> None:
        parsed = workflow(
            """
            permissions:
            jobs:
              build:
                steps: []
            """
        )
        findings = checks.unpinned_permissions(parsed)
        assert any("YAML null" in finding for finding in findings)


TRUSTED_IF = (
    "github.event.pull_request.user.login == 'dependabot[bot]' &&"
    " github.event.pull_request.head.repo.full_name == github.repository"
)


class TestTrustModel:
    def test_non_pr_workflow_is_out_of_scope(self) -> None:
        parsed = workflow(
            """
            on:
              workflow_call:
            jobs:
              build:
                steps:
                  - run: echo "${{ secrets.APP_KEY }}"
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_uncredentialed_pr_job_is_out_of_scope(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              build:
                steps:
                  - run: echo hello
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_github_token_alone_is_not_credentialed_on_pull_request(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              build:
                steps:
                  - run: gh pr view
                    env:
                      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_guarded_credentialed_job_passes(self) -> None:
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  {TRUSTED_IF}
                secrets:
                  automation-client-id: ${{{{ secrets.AUTOMATION_CLIENT_ID }}}}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_unguarded_secret_reference_is_found_twice(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 2
        assert any("pull-request author" in finding for finding in findings)
        assert any("head repository" in finding for finding in findings)

    def test_workflow_level_env_secret_credentials_every_job(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            env:
              TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            jobs:
              build:
                steps:
                  - run: deploy
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_secrets_inherit_is_credentialed(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              call:
                uses: owner/repo/.github/workflows/callee.yaml@main
                secrets: inherit
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_actor_keyed_guard_is_found(self) -> None:
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  github.actor == 'dependabot[bot]' && {TRUSTED_IF}
                secrets: inherit
                uses: owner/repo/.github/workflows/callee.yaml@main
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "github.actor" in findings[0]

    def test_write_scopes_on_pull_request_target_are_credentialed(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request_target:
            permissions:
              contents: write
            jobs:
              label:
                steps:
                  - run: gh pr edit
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_negated_pins_are_not_a_trust_guard(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  github.event.pull_request.user.login != 'x' &&
                  github.event.pull_request.head.repo.full_name != github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 2
        assert all("equality" in finding for finding in findings)

    def test_actor_id_is_not_mistaken_for_actor_keying(self) -> None:
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  {TRUSTED_IF} && github.actor_id == 123
                secrets: inherit
                uses: owner/repo/.github/workflows/callee.yaml@main
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_index_syntax_secret_reference_is_credentialed(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets['DEPLOY_TOKEN'] }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_github_token_exemption_is_case_insensitive(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              build:
                steps:
                  - run: gh pr view
                    env:
                      GH_TOKEN: ${{ secrets.github_token }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_secrets_block_passing_only_the_default_token_is_exempt(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              call:
                uses: owner/repo/.github/workflows/callee.yaml@main
                secrets:
                  token: ${{ secrets.GITHUB_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_write_scopes_on_plain_pull_request_are_not_credentialed(self) -> None:
        # A fork PR's token is forced read-only server-side on pull_request;
        # only pull_request_target pairs untrusted context with real writes.
        parsed = workflow(
            """
            on:
              pull_request:
            permissions:
              contents: write
            jobs:
              label:
                steps:
                  - run: gh pr edit
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []
