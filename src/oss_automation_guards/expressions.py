"""Scanning helpers for GitHub Actions expressions.

Expressions are matched structurally rather than as raw text: `}}` and pin
paths both occur inside string literals, and the same property dereference
has two syntaxes. Each helper below normalizes one of those away so the
guards in `checks` can match on shape.
"""

from __future__ import annotations

import re

_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
# Index dereference with a literal property name — the indexed spelling of a
# dot path. Property names are identifiers; anything else is a value.
_INDEX_KEY = re.compile(r"\[\s*'([A-Za-z_][A-Za-z0-9_-]*)'\s*\]")


def expression_bodies(text: str) -> list[str]:
    """Bodies of every `${{ ... }}` expression in `text`.

    Terminators are found with quote tracking, not a regex: `}}` inside a
    single-quoted literal — `format('{0} }}', secrets.TOKEN)` — does not end
    the expression, and treating it as the end would hide everything after it.
    """
    bodies = []
    index = 0
    while True:
        start = text.find("${{", index)
        if start == -1:
            return bodies
        cursor = start + 3
        while cursor < len(text):
            if text[cursor] == "'":
                cursor = _past_literal(text, cursor)
                continue
            if text.startswith("}}", cursor):
                break
            cursor += 1
        bodies.append(text[start + 3 : cursor])
        index = cursor + 2 if cursor < len(text) else len(text)


def normalize(expression: str) -> str:
    """Rewrite an expression so equivalent spellings match one pattern.

    Index dereferences with a literal property name become dot paths, so
    `github['actor']` and `github.actor` are one shape; every remaining
    literal — a value, never a path segment — collapses to `''`, so a pin
    compared against a literal identity is recognizable without knowing which
    identity, and pin-shaped text inside a literal stops looking like a pin.
    """
    return _STRING_LITERAL.sub("''", _INDEX_KEY.sub(lambda match: f".{match.group(1)}", expression))


def has_unnegated(pattern: re.Pattern[str], expression: str) -> bool:
    """Whether `pattern` matches in positive sense anywhere.

    A pin under `!( ... )` selects the complement of the trusted identity, so
    a match there is the opposite of the guard it resembles. Each enclosing
    negation flips the sense, so an even count — none, or `!(!( ... ))` —
    reads as the positive pin it is equivalent to.
    """
    depths = _negation_depths(expression)
    return any(depths[match.start()] % 2 == 0 for match in pattern.finditer(expression))


def _past_literal(text: str, start: int) -> int:
    cursor = start + 1
    while cursor < len(text):
        if text[cursor] == "'":
            # A doubled quote is an escaped quote, not the terminator.
            if text.startswith("''", cursor):
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    return len(text)


def _negation_depths(expression: str) -> list[int]:
    """Per character, how many negated groups enclose it.

    The caller reads this modulo two; the raw count is kept so nesting and
    stacked `!` operators compose.
    """
    depths = []
    stack: list[bool] = []
    for index, char in enumerate(expression):
        if char == "(":
            preceding = expression[:index].rstrip()
            # Parity, so `!!(x)` reads as the no-op it is.
            bangs = len(preceding) - len(preceding.rstrip("!"))
            stack.append(bangs % 2 == 1)
        depths.append(sum(stack))
        if char == ")" and stack:
            stack.pop()
    return depths
