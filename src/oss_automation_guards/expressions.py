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
# A comparison against a boolean literal, applied to whatever precedes it.
_BOOLEAN_COMPARISON = re.compile(r"\s*(==|!=)\s*(true|false)\b", re.IGNORECASE)
# Redundant parentheses around a bare context path. The lookbehind keeps a
# function call — an identifier immediately before the parenthesis — out.
_GROUPED_PATH = re.compile(r"(?<![\w.\])])\(\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\)")


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
    identity, and pin-shaped text inside a literal stops looking like a pin;
    and parentheses wrapping nothing but a path are dropped, so `(path) == x`
    is the same shape as `path == x`. Dropping them cannot change sense —
    `!(path)` and `!path` are one expression.
    """
    normalized = _STRING_LITERAL.sub(
        "''", _INDEX_KEY.sub(lambda match: f".{match.group(1)}", expression)
    )
    previous = None
    while previous != normalized:
        previous = normalized
        normalized = _GROUPED_PATH.sub(r"\1", normalized)
    return normalized


def has_unnegated(pattern: re.Pattern[str], expression: str) -> bool:
    """Whether `pattern` matches in positive sense anywhere.

    An inverted pin selects the complement of the trusted identity, so a
    match under one is the opposite of the guard it resembles. Three forms
    invert, and they compose: a `!` on an enclosing group, a `!` bound
    directly to the matched operand (`!` binds tighter than `==`, so
    `!path == 'x'` negates the operand, not the comparison), and a boolean
    comparison applied to the result (`( ... ) == false`, `( ... ) != true`).
    Parity decides, so `!(!( ... ))` reads as the positive pin it equals.
    """
    return any(_inversion_parity(expression, match) == 0 for match in pattern.finditer(expression))


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


def _bang_parity(expression: str, index: int) -> int:
    """Whether an odd number of `!` operators binds to the token at `index`."""
    preceding = expression[:index].rstrip()
    return (len(preceding) - len(preceding.rstrip("!"))) % 2


def _inversion_parity(expression: str, match: re.Match[str]) -> int:
    """How many inversions apply to `match`, modulo two."""
    inversions = _bang_parity(expression, match.start())
    inversions += _boolean_inversion(expression, match.end())
    for open_index, close_index in _group_pairs(expression).items():
        if open_index < match.start() and match.end() <= close_index:
            inversions += _bang_parity(expression, open_index)
            inversions += _boolean_inversion(expression, close_index + 1)
    return inversions % 2


def _boolean_inversion(expression: str, index: int) -> int:
    """Whether a boolean comparison at `index` inverts what precedes it."""
    match = _BOOLEAN_COMPARISON.match(expression, index)
    if match is None:
        return 0
    negative = match.group(1) == "==" and match.group(2).lower() == "false"
    negative |= match.group(1) == "!=" and match.group(2).lower() == "true"
    return 1 if negative else 0


def _group_pairs(expression: str) -> dict[int, int]:
    pairs = {}
    stack: list[int] = []
    for index, char in enumerate(expression):
        if char == "(":
            stack.append(index)
        elif char == ")" and stack:
            pairs[stack.pop()] = index
    return pairs
