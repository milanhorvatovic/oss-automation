# Release notes template

The Release workflow assembles each release's notes from two halves:

1. **Curated** — the `## [X.Y.Z]` section of `CHANGELOG.md`, written before tagging, in Keep a Changelog categories (Added / Changed / Deprecated / Removed / Fixed / Security).
2. **Generated** — GitHub's generated notes (merged PRs and contributors), appended automatically by the release API.

What the curated half owes consumers, when relevant:

- Whether consumers have to move their workflow and test-pack pins, and why — not the SHA itself. A commit cannot carry its own hash, and the section is written before the tag exists; the tagged commit is what the release page shows and what Dependabot bumps pins to.
- Any caller-contract change — inputs, secrets, `permissions` blocks, concurrency requirements — called out under **Changed** with a one-line migration note.
- Any guard-behavior change that can turn a previously green consumer tree red, called out under **Changed** or **Fixed**.
