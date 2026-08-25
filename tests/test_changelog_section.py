import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/write_changelog_section.py"
_spec = importlib.util.spec_from_file_location("write_changelog_section", _SCRIPT)
assert _spec and _spec.loader
changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog)


CHANGELOG = """# Changelog

Preamble.

## [Unreleased]

### Added

- A thing worth explaining.

[Unreleased]: https://github.com/owner/repo/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/owner/repo/releases/tag/v0.1.0
"""

NOTES = """## What's Changed
* Add a guard by @someone in https://github.com/owner/repo/pull/1

## New Contributors
* @someone made their first contribution

**Full Changelog**: https://github.com/owner/repo/compare/v0.1.0...v0.2.0
"""


def rewrite(text=CHANGELOG, notes=NOTES, version="0.2.0"):
    return changelog.rewrite_changelog(text, version, "2026-01-02", notes, "owner/repo")


def test_hand_written_entries_survive_promotion():
    assert "- A thing worth explaining." in rewrite()


def test_generated_list_lands_under_the_new_version():
    result = rewrite()
    heading = result.index("## [0.2.0] - 2026-01-02")
    assert result.index("* Add a guard by @someone", heading) > heading


def test_category_headings_survive_demoted():
    notes = (
        "## What's Changed\n"
        "## Dependencies\n"
        "* Bump ruff by @dependabot in https://github.com/owner/repo/pull/2\n"
    )
    result = rewrite(notes=notes)
    assert "#### Dependencies" in result
    assert "## Dependencies" not in result.replace("#### Dependencies", "")


def test_release_page_furniture_is_dropped():
    result = rewrite()
    assert "New Contributors" not in result
    assert "**Full Changelog**" not in result
    assert "What's Changed" not in result


def test_unreleased_is_left_empty_for_the_next_cycle():
    result = rewrite()
    unreleased = result.index("## [Unreleased]")
    assert result[unreleased:].index("## [0.2.0]") < result[unreleased:].index("- A thing")


def test_links_track_the_new_version_and_keep_older_ones():
    result = rewrite()
    assert "[Unreleased]: https://github.com/owner/repo/compare/v0.2.0...HEAD" in result
    assert "[0.2.0]: https://github.com/owner/repo/releases/tag/v0.2.0" in result
    assert "[0.1.0]: https://github.com/owner/repo/releases/tag/v0.1.0" in result


def test_section_terminates_where_release_tag_stops_reading():
    # release-tag.yaml extracts until the next '## [' or a link reference, so
    # the generated list must sit above both.
    result = rewrite()
    section = result.split("## [0.2.0] - 2026-01-02", 1)[1]
    body = section.split("\n[", 1)[0]
    assert "* Add a guard by @someone" in body


def test_a_changelog_without_unreleased_is_refused():
    with pytest.raises(SystemExit):
        rewrite(text="# Changelog\n\n## [0.1.0] - 2026-01-01\n")


def test_empty_unreleased_still_produces_a_section():
    text = "# Changelog\n\n## [Unreleased]\n\n[Unreleased]: https://github.com/owner/repo\n"
    result = rewrite(text=text)
    assert "## [0.2.0] - 2026-01-02" in result
    assert "* Add a guard by @someone" in result


def test_manifest_bump_replaces_the_project_version():
    manifest = '[project]\nname = "x"\nversion = "0.1.0"\n'
    assert (
        changelog.bump_manifest(manifest, "0.2.0") == '[project]\nname = "x"\nversion = "0.2.0"\n'
    )


def test_manifest_bump_refuses_a_file_with_no_version():
    with pytest.raises(SystemExit):
        changelog.bump_manifest('[project]\nname = "x"\n', "0.2.0")


def test_manifest_bump_refuses_a_second_version_line():
    manifest = '[project]\nversion = "0.1.0"\n\n[tool.other]\nversion = "9.9.9"\n'
    with pytest.raises(SystemExit):
        changelog.bump_manifest(manifest, "0.2.0")
