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

    def test_bare_null_timeout_is_found(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                runs-on: ubuntu-latest
                timeout-minutes:
                steps: []
            """
        )
        assert len(checks.jobs_missing_timeout(parsed)) == 1

    def test_container_shaped_timeout_is_found(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                runs-on: ubuntu-latest
                timeout-minutes: []
                steps: []
            """
        )
        findings = checks.jobs_missing_timeout(parsed)
        assert len(findings) == 1
        assert "not a positive number of minutes" in findings[0]

    @pytest.mark.parametrize("value", ['"0"', "unlimited", '"-5"', '""'])
    def test_unusable_timeout_strings_are_found(self, value: str) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                runs-on: ubuntu-latest
                timeout-minutes: {value}
                steps: []
            """
        )
        assert len(checks.jobs_missing_timeout(parsed)) == 1

    def test_numeric_string_timeout_passes(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                runs-on: ubuntu-latest
                timeout-minutes: "10"
                steps: []
            """
        )
        assert checks.jobs_missing_timeout(parsed) == []

    def test_expression_valued_timeout_passes(self) -> None:
        parsed = workflow(
            """
            jobs:
              build:
                runs-on: ubuntu-latest
                timeout-minutes: ${{ inputs.timeout }}
                steps: []
            """
        )
        assert checks.jobs_missing_timeout(parsed) == []

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

    def test_branch_and_date_comment_is_found(self) -> None:
        parsed = workflow(
            f"""
            jobs:
              call:
                uses: owner/repo/.github/workflows/callee.yaml@{SHA} # main 2026-08-17
            """
        )
        findings = checks.unpinned_uses(parsed)
        assert len(findings) == 1
        assert "does not name the pinned version" in findings[0]

    @pytest.mark.parametrize(
        "comment",
        ["v7", "3.20", "3.20-alpine", "v1.2.3-rc.1", "v1.2.3-alpha-beta", "v1.2.3-rc.1+build.5"],
    )
    def test_version_shaped_comments_pass(self, comment: str) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA} # {comment}
            """
        )
        assert checks.unpinned_uses(parsed) == []

    @pytest.mark.parametrize("comment", ["2026-08-17", "v1.2.3-...", "v1.2.3-", "v1.2.3-rc..1"])
    def test_non_version_comments_are_found(self, comment: str) -> None:
        parsed = workflow(
            f"""
            jobs:
              build:
                steps:
                  - uses: actions/checkout@{SHA} # {comment}
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

    def test_list_shaped_permissions_are_found(self) -> None:
        parsed = workflow(
            """
            permissions: [contents]
            jobs:
              build:
                steps: []
            """
        )
        findings = checks.unpinned_permissions(parsed)
        assert any("pins no token scopes" in finding for finding in findings)
        assert any("default token scopes" in finding for finding in findings)

    def test_list_shaped_job_permissions_are_found_under_a_valid_workflow_block(self) -> None:
        # The workflow block satisfies the inheritance check, so the job's
        # unusable value is only caught by judging the value itself.
        parsed = workflow(
            """
            permissions:
              contents: read
            jobs:
              build:
                permissions: [contents]
                steps: []
            """
        )
        findings = checks.unpinned_permissions(parsed)
        assert len(findings) == 1
        assert "pins no token scopes" in findings[0]

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

    def test_reusable_call_does_not_inherit_the_workflow_env(self) -> None:
        # Workflow-level env reaches runner steps; a call job has none, and
        # the callee never sees the caller's env.
        parsed = workflow(
            """
            on:
              pull_request:
            env:
              TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            jobs:
              call:
                uses: owner/repo/.github/workflows/callee.yaml@main
              build:
                steps:
                  - run: build
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert findings
        assert all("'build'" in finding for finding in findings)

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
        assert any("literal identity" in finding for finding in findings)
        assert any("github.repository" in finding for finding in findings)

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

    def test_negated_equalities_are_not_a_trust_guard(self) -> None:
        # Both pins sit under a unary negation, selecting exactly the
        # untrusted author and foreign head the guard exists to exclude.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  !(github.event.pull_request.user.login == 'dependabot[bot]') &&
                  !(github.event.pull_request.head.repo.full_name == github.repository)
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2

    def test_double_negated_pins_still_pass(self) -> None:
        # !!x is x; parity keeps the guard from reading it as a negation.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  !!(github.event.pull_request.user.login == 'dependabot[bot]') &&
                  !!(github.event.pull_request.head.repo.full_name == github.repository)
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_pins_compared_against_false_are_not_a_trust_guard(self) -> None:
        # (pin) == false selects the complement, exactly as !(pin) does.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  (github.event.pull_request.user.login == 'dependabot[bot]') == false &&
                  (github.event.pull_request.head.repo.full_name == github.repository) == false
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2

    def test_pins_compared_against_not_true_are_not_a_trust_guard(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  (github.event.pull_request.user.login == 'dependabot[bot]') != true &&
                  github.event.pull_request.head.repo.full_name == github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "literal identity" in findings[0]

    def test_pins_compared_against_true_still_pass(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  (github.event.pull_request.user.login == 'dependabot[bot]') == true &&
                  (github.event.pull_request.head.repo.full_name == github.repository) != false
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_nested_double_negation_still_passes(self) -> None:
        # !(!(x)) is x; the enclosing-negation count is read modulo two.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  !(!(github.event.pull_request.user.login == 'dependabot[bot]')) &&
                  !(!(github.event.pull_request.head.repo.full_name == github.repository))
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_triple_negation_is_not_a_trust_guard(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  !(!(!(github.event.pull_request.user.login == 'dependabot[bot]'))) &&
                  github.event.pull_request.head.repo.full_name == github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "literal identity" in findings[0]

    def test_secret_inside_a_computed_index_is_credentialed(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                steps:
                  - run: deploy
                    env:
                      VALUE: ${{ env[secrets.DEPLOY_TOKEN] }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_actor_inside_a_computed_index_is_found(self) -> None:
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  {TRUSTED_IF} && vars.allowlist[github.actor] == 'yes'
                secrets: inherit
                uses: owner/repo/.github/workflows/callee.yaml@main
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "github.actor" in findings[0]

    def test_partially_wrapped_condition_pins_nothing(self) -> None:
        # Actions substitutes the expression result into a string here, and a
        # non-empty string is truthy, so the pins gate nothing.
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              deploy:
                if: "${{{{ {TRUSTED_IF} }}}} && false"
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{{{ secrets.DEPLOY_TOKEN }}}}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2

    def test_two_wrapped_expressions_in_one_condition_pin_nothing(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: "${{ github.event.pull_request.user.login == 'dependabot[bot]' }}
                  ${{ github.event.pull_request.head.repo.full_name == github.repository }}"
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2

    def test_computed_github_dereference_is_reported(self) -> None:
        # github[format('{0}', 'actor')] resolves to github.actor only at run
        # time; the guard reports what it cannot rule out.
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  {TRUSTED_IF} && github[format('{{0}}', 'actor')] == 'dependabot[bot]'
                secrets: inherit
                uses: owner/repo/.github/workflows/callee.yaml@main
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "computed key" in findings[0]

    def test_computed_dereference_of_another_context_is_not_reported(self) -> None:
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  {TRUSTED_IF} && vars.allowlist[inputs.name] == 'yes'
                secrets: inherit
                uses: owner/repo/.github/workflows/callee.yaml@main
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_uncommon_number_literals_do_not_break_the_pins(self) -> None:
        # Hexadecimal and exponent literals are valid; failing to lex them
        # would discard the whole condition and report the pins missing.
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  {TRUSTED_IF} && github.run_attempt < 0xff &&
                  github.run_number > -2.99e-2
                secrets: inherit
                uses: owner/repo/.github/workflows/callee.yaml@main
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_spaced_call_around_the_author_path_is_not_a_pin(self) -> None:
        # Whitespace before the parenthesis still makes this a call, whose
        # result — not the author path — is what the equality compares.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  hashFiles (github.event.pull_request.user.login) == 'x' &&
                  github.event.pull_request.head.repo.full_name == github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "literal identity" in findings[0]

    def test_spaced_negation_operators_are_counted(self) -> None:
        # Three NOT operators separated by whitespace still invert the pin.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  ! !!(github.event.pull_request.user.login == 'dependabot[bot]') &&
                  github.event.pull_request.head.repo.full_name == github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "literal identity" in findings[0]

    def test_left_hand_boolean_comparison_inverts_the_pin(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  false == (github.event.pull_request.user.login == 'dependabot[bot]') &&
                  false == (github.event.pull_request.head.repo.full_name == github.repository)
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2

    def test_unparseable_condition_pins_nothing(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: "github.event.pull_request.user.login == && ("
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2

    def test_condition_wrapped_in_an_expression_is_parsed(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  ${{ github.event.pull_request.user.login == 'dependabot[bot]' &&
                  github.event.pull_request.head.repo.full_name == github.repository }}
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_grouped_operands_are_accepted(self) -> None:
        # Redundant parentheses around a bare path do not change the pin.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  (github.event.pull_request.user.login) == 'dependabot[bot]' &&
                  (github.event.pull_request.head.repo.full_name) == (github.repository)
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_grouped_operands_under_negation_are_still_rejected(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  !((github.event.pull_request.user.login) == 'dependabot[bot]') &&
                  (github.event.pull_request.head.repo.full_name) == (github.repository)
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "literal identity" in findings[0]

    def test_index_syntax_pins_are_accepted(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  github['event']['pull_request']['user']['login'] == 'dependabot[bot]' &&
                  github['event']['pull_request']['head']['repo']['full_name'] ==
                  github['repository']
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_secret_after_a_literal_containing_the_terminator_is_credentialed(self) -> None:
        # The '{0} }}' literal must not be mistaken for the expression's end,
        # which would hide the secret reference that follows it.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                steps:
                  - run: echo "${{ format('{0} }}', secrets.DEPLOY_TOKEN) }}"
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_author_self_comparison_is_not_a_trust_guard(self) -> None:
        # login == login is true for every author; only a comparison against
        # a literal identity counts as the pin.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  github.event.pull_request.user.login == github.event.pull_request.user.login &&
                  github.event.pull_request.head.repo.full_name == github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "literal identity" in findings[0]

    def test_suffixed_pin_identifiers_are_not_a_trust_guard(self) -> None:
        # A longer identifier sharing the pin path as its prefix must not
        # satisfy the guard in either operand order.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  'x' == github.event.pull_request.user.login_suffix &&
                  github.repository == github.event.pull_request.head.repo.full_name_suffix
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2

    def test_head_pin_against_a_literal_repository_is_not_a_trust_guard(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  github.event.pull_request.user.login == 'dependabot[bot]' &&
                  github.event.pull_request.head.repo.full_name == 'attacker/fork'
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "github.repository" in findings[0]

    def test_whole_secrets_context_is_credentialed(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              dump:
                steps:
                  - run: echo '${{ toJSON(secrets) }}'
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_object_filter_over_the_secrets_context_is_credentialed(self) -> None:
        # secrets.* dereferences every secret at once, so it can never ride
        # the GITHUB_TOKEN exemption.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              dump:
                steps:
                  - run: echo '${{ toJSON(secrets.*) }}'
            """
        )
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_directly_negated_author_operand_is_not_a_trust_guard(self) -> None:
        # `!` binds tighter than `==`, so this compares a negated operand,
        # never the author path itself.
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  !github.event.pull_request.user.login == 'dependabot[bot]' &&
                  github.event.pull_request.head.repo.full_name == github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "literal identity" in findings[0]

    def test_negation_on_an_unrelated_call_leaves_the_pins_intact(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  !contains(github.event.pull_request.labels.*.name, 'hold') &&
                  github.event.pull_request.user.login == 'dependabot[bot]' &&
                  github.event.pull_request.head.repo.full_name == github.repository
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_secret_lookalike_text_outside_expressions_is_ignored(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              docs:
                steps:
                  - run: echo 'reference secrets.KEY in your workflow'
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

    def test_index_syntax_actor_keying_is_found(self) -> None:
        parsed = workflow(
            f"""
            on:
              pull_request:
            jobs:
              policy:
                if: >-
                  {TRUSTED_IF} && github['actor'] == 'dependabot[bot]'
                secrets: inherit
                uses: owner/repo/.github/workflows/callee.yaml@main
            """
        )
        findings = checks.unguarded_pr_credentials(parsed)
        assert len(findings) == 1
        assert "github.actor" in findings[0]

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

    def test_indexed_github_token_stays_exempt(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              build:
                steps:
                  - run: gh pr view
                    env:
                      GH_TOKEN: ${{ secrets['GITHUB_TOKEN'] }}
            """
        )
        assert checks.unguarded_pr_credentials(parsed) == []

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

    def test_write_scopes_on_plain_pull_request_are_credentialed(self) -> None:
        # Same-repo pull_request runs receive the declared write scopes (only
        # a public repo's fork PRs are force-downgraded), so write scopes are
        # credentials on either PR trigger.
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
        assert checks.unguarded_pr_credentials(parsed) != []

    def test_pins_inside_a_string_literal_are_not_a_trust_guard(self) -> None:
        parsed = workflow(
            """
            on:
              pull_request:
            jobs:
              deploy:
                if: >-
                  'github.event.pull_request.user.login == dependabot &&
                  github.event.pull_request.head.repo.full_name == github.repository'
                  != ''
                steps:
                  - run: deploy
                    env:
                      TOKEN: ${{ secrets.DEPLOY_TOKEN }}
            """
        )
        assert len(checks.unguarded_pr_credentials(parsed)) == 2
