"""Promote the Unreleased changelog section into a dated release section.

Run by release-prepare.yaml. The generated body comes from GitHub's
release-notes endpoint; everything here is the surgery around it — carrying
hand-written Unreleased prose across, keeping the Keep a Changelog link
references current, and bumping the manifest so the three things
release-tag.yaml compares cannot disagree.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

CHANGELOG = Path("CHANGELOG.md")
MANIFEST = Path("pyproject.toml")

_UNRELEASED_HEADING = "## [Unreleased]"
_SECTION_HEADING = re.compile(r"^## \[")
_LINK_REFERENCE = re.compile(r"^\[[^\]]+\]:\s")
_VERSION_LINE = re.compile(r'^version = "[^"]*"$', re.MULTILINE)


def split_unreleased(text: str) -> tuple[str, str, str]:
    """Return the text above Unreleased, its body, and everything below it."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == _UNRELEASED_HEADING)
    except StopIteration:
        raise SystemExit(f"{CHANGELOG}: no '{_UNRELEASED_HEADING}' heading to promote") from None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _SECTION_HEADING.match(lines[index]) or _LINK_REFERENCE.match(lines[index]):
            end = index
            break
    head = "\n".join(lines[:start])
    body = "\n".join(lines[start + 1 : end]).strip()
    tail = "\n".join(lines[end:])
    return head, body, tail


def clean_notes(body: str) -> str:
    """Strip the parts of GitHub's notes that belong to a release page, not a file.

    The 'New Contributors' block and the 'Full Changelog' link are rendered by
    GitHub beside every release; repeated in the file they age badly, since the
    link points at a comparison the file already spans by construction.
    """
    kept: list[str] = []
    for line in body.splitlines():
        if line.startswith("## New Contributors"):
            break
        if line.startswith("## "):
            # The generator's own '## What's Changed' heading; this file nests
            # the list under a section heading of its own instead.
            continue
        if line.startswith("**Full Changelog**"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def render_section(version: str, date: str, carried: str, notes: str) -> str:
    parts = [f"## [{version}] - {date}"]
    if carried:
        parts.append(carried)
    if notes:
        parts.append("### Merged pull requests")
        parts.append(notes)
    return "\n\n".join(parts)


def render_links(tail: str, version: str, repo: str) -> str:
    """Refresh the Unreleased comparison and add this version's tag link."""
    base = f"https://github.com/{repo}"
    existing = [
        line
        for line in tail.splitlines()
        if _LINK_REFERENCE.match(line) and not line.startswith("[Unreleased]:")
    ]
    links = [
        f"[Unreleased]: {base}/compare/v{version}...HEAD",
        f"[{version}]: {base}/releases/tag/v{version}",
        *existing,
    ]
    return "\n".join(links)


def rewrite_changelog(text: str, version: str, date: str, notes: str, repo: str) -> str:
    head, carried, tail = split_unreleased(text)
    sections = [line for line in tail.splitlines() if not _LINK_REFERENCE.match(line)]
    body = "\n".join(sections).strip()
    blocks = [
        head.rstrip(),
        _UNRELEASED_HEADING,
        render_section(version, date, carried, clean_notes(notes)),
    ]
    if body:
        blocks.append(body)
    blocks.append(render_links(tail, version, repo))
    return "\n\n".join(blocks) + "\n"


def bump_manifest(text: str, version: str) -> str:
    # Count before substituting: subn with count=1 can never report more than
    # one, so a manifest carrying a second `version = "..."` line — a tool
    # table with its own — would pass the check and get the wrong line bumped.
    found = len(_VERSION_LINE.findall(text))
    if found != 1:
        raise SystemExit(f"{MANIFEST}: found {found} version lines to bump, expected exactly 1")
    return _VERSION_LINE.sub(f'version = "{version}"', text, count=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--notes", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    notes = args.notes.read_text(encoding="utf-8")
    CHANGELOG.write_text(
        rewrite_changelog(
            CHANGELOG.read_text(encoding="utf-8"), args.version, args.date, notes, args.repo
        ),
        encoding="utf-8",
    )
    MANIFEST.write_text(
        bump_manifest(MANIFEST.read_text(encoding="utf-8"), args.version), encoding="utf-8"
    )
    print(f"CHANGELOG.md carries [{args.version}] - {args.date}; pyproject.toml bumped")


if __name__ == "__main__":
    main()
