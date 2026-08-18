"""A parser for the GitHub Actions expression language.

The guards ask structural questions of a workflow's conditions — does this
job pin the pull-request author to a literal identity, does it key trust on
`github.actor`, does it read a secret. Answering those by matching text
fails wherever the language allows a spelling the pattern did not anticipate:
whitespace between tokens, redundant grouping, index versus dot dereference,
an inverted comparison written with the boolean on the left. Parsing removes
that whole class of gap — every spelling of one expression yields one tree.

The grammar implemented here (GitHub's documented operator set, no
arithmetic):

    or         := and ('||' and)*
    and        := comparison ('&&' comparison)*
    comparison := unary (('==' | '!=' | '<' | '<=' | '>' | '>=') unary)*
    unary      := '!' unary | postfix
    postfix    := primary ('.' name | '.' '*' | '[' or ']')*
    primary    := literal | name | call | '(' or ')'
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN = re.compile(
    r"""
      (?P<space>\s+)
    | (?P<string>'(?:[^']|'')*')
    | (?P<number>-?(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?))
    | (?P<name>[A-Za-z_][A-Za-z0-9_-]*)
    | (?P<operator>==|!=|<=|>=|&&|\|\||[()\[\].,*!<>])
    """,
    re.VERBOSE,
)
_COMPARISONS = frozenset({"==", "!=", "<", "<=", ">", ">="})


class ExpressionError(Exception):
    """An expression could not be parsed; callers treat this as unknown."""


@dataclass(frozen=True)
class Value:
    """A literal — a string, a boolean, or a number."""

    kind: str
    value: object


@dataclass(frozen=True)
class ContextPath:
    """A context dereference such as `github.event.pull_request.user.login`.

    `indices` holds the expressions of any computed segment — `env[name]` —
    which are kept rather than collapsed, both because such a path's full
    identity is unknown until run time and because the index itself may
    dereference a context the guards care about.
    """

    segments: tuple[str, ...]
    indices: tuple[Node, ...] = ()

    @property
    def dotted(self) -> str:
        return ".".join(self.segments)

    @property
    def dynamic(self) -> bool:
        return bool(self.indices)


@dataclass(frozen=True)
class FunctionCall:
    name: str
    arguments: tuple[Node, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Negation:
    operand: Node


@dataclass(frozen=True)
class Operation:
    operator: str
    left: Node
    right: Node


@dataclass(frozen=True)
class Access:
    """A dereference of something other than a context path — `f(x).y`."""

    base: Node
    index: Node | None = None


Node = Value | ContextPath | FunctionCall | Negation | Operation | Access


def expression_bodies(text: str) -> list[str]:
    """Bodies of every `${{ ... }}` expression in `text`.

    Terminators are found with quote tracking: `}}` inside a single-quoted
    literal — `format('{0} }}', secrets.TOKEN)` — does not end the
    expression, and treating it as the end would hide everything after it.
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


def parse_condition(text: str) -> Node:
    """Parse a job `if:` value, whose `${{ }}` wrapper is optional."""
    stripped = text.strip()
    if stripped.startswith("${{"):
        bodies = expression_bodies(stripped)
        if len(bodies) == 1:
            stripped = bodies[0]
    return parse(stripped)


def parse(expression: str) -> Node:
    parser = _Parser(_tokenize(expression))
    node = parser.parse_or()
    parser.expect_end()
    return node


def positive_equalities(node: Node) -> list[tuple[Node, Node]]:
    """Operand pairs of every equality the expression asserts positively.

    Inversions compose and cancel: each `!`, and each comparison against a
    boolean literal in either operand order (`x == false`, `false == x`,
    `x != true`), flips the sense of what it wraps. An equality reached under
    an odd number of them asserts inequality, so it is not returned; a `!=`
    reached under an odd number asserts equality, so it is.
    """
    found: list[tuple[Node, Node]] = []
    _collect_equalities(node, False, found)
    return found


def context_paths(node: Node) -> list[ContextPath]:
    """Every context path the expression dereferences."""
    found: list[ContextPath] = []
    _collect_paths(node, found)
    return found


def _collect_equalities(node: Node, inverted: bool, found: list[tuple[Node, Node]]) -> None:
    if isinstance(node, Negation):
        _collect_equalities(node.operand, not inverted, found)
        return
    if isinstance(node, FunctionCall):
        for argument in node.arguments:
            _collect_equalities(argument, inverted, found)
        return
    if not isinstance(node, Operation):
        return
    if node.operator in {"&&", "||"}:
        _collect_equalities(node.left, inverted, found)
        _collect_equalities(node.right, inverted, found)
        return
    if node.operator not in {"==", "!="}:
        _collect_equalities(node.left, inverted, found)
        _collect_equalities(node.right, inverted, found)
        return
    for literal, other in ((node.left, node.right), (node.right, node.left)):
        if isinstance(literal, Value) and literal.kind == "bool":
            flips = (node.operator == "==") != bool(literal.value)
            _collect_equalities(other, inverted != flips, found)
            return
    if (node.operator == "==") != inverted:
        found.append((node.left, node.right))


def _collect_paths(node: Node, found: list[ContextPath]) -> None:
    if isinstance(node, ContextPath):
        found.append(node)
        # A computed segment can itself read a context the guards care about.
        for index in node.indices:
            _collect_paths(index, found)
    elif isinstance(node, Negation):
        _collect_paths(node.operand, found)
    elif isinstance(node, Access):
        _collect_paths(node.base, found)
        if node.index is not None:
            _collect_paths(node.index, found)
    elif isinstance(node, Operation):
        _collect_paths(node.left, found)
        _collect_paths(node.right, found)
    elif isinstance(node, FunctionCall):
        for argument in node.arguments:
            _collect_paths(argument, found)


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


def _number_value(text: str) -> float:
    """The value of any number literal GitHub accepts, hexadecimal included."""
    sign = -1.0 if text.startswith("-") else 1.0
    digits = text.lstrip("+-")
    if digits[:2].lower() == "0x":
        return sign * int(digits, 16)
    return sign * float(digits)


def _tokenize(expression: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    position = 0
    while position < len(expression):
        match = _TOKEN.match(expression, position)
        if match is None:
            raise ExpressionError(f"unexpected character at offset {position}")
        position = match.end()
        kind = match.lastgroup
        text = match.group()
        if kind == "space":
            continue
        if kind == "string":
            tokens.append(("string", text[1:-1].replace("''", "'")))
        elif kind == "number":
            tokens.append(("number", _number_value(text)))
        elif kind == "name" and text.lower() in {"true", "false"}:
            tokens.append(("bool", text.lower() == "true"))
        else:
            tokens.append((kind or "operator", text))
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, object]]) -> None:
        self._tokens = tokens
        self._position = 0

    def parse_or(self) -> Node:
        node = self.parse_and()
        while self._take_operator("||"):
            node = Operation("||", node, self.parse_and())
        return node

    def parse_and(self) -> Node:
        node = self.parse_comparison()
        while self._take_operator("&&"):
            node = Operation("&&", node, self.parse_comparison())
        return node

    def parse_comparison(self) -> Node:
        node = self.parse_unary()
        while True:
            operator = self._peek_comparison()
            if operator is None:
                return node
            self._position += 1
            node = Operation(operator, node, self.parse_unary())

    def parse_unary(self) -> Node:
        if self._take_operator("!"):
            return Negation(self.parse_unary())
        return self.parse_postfix(self.parse_primary())

    def parse_postfix(self, node: Node) -> Node:
        while True:
            if self._take_operator("."):
                node = self._extend_segment(node, self._read_segment())
            elif self._take_operator("["):
                index = self.parse_or()
                self._expect_operator("]")
                node = self._extend_index(node, index)
            else:
                return node

    def parse_primary(self) -> Node:
        kind, value = self._next()
        if kind in {"string", "number", "bool"}:
            return Value({"string": "string", "number": "number", "bool": "bool"}[kind], value)
        if kind == "operator" and value == "(":
            node = self.parse_or()
            self._expect_operator(")")
            return node
        if kind != "name":
            raise ExpressionError(f"unexpected token {value!r}")
        name = str(value)
        if self._take_operator("("):
            return FunctionCall(name, tuple(self._read_arguments()))
        return ContextPath((name,))

    def expect_end(self) -> None:
        if self._position != len(self._tokens):
            raise ExpressionError("trailing tokens")

    def _read_arguments(self) -> list[Node]:
        arguments: list[Node] = []
        if self._take_operator(")"):
            return arguments
        while True:
            arguments.append(self.parse_or())
            if self._take_operator(")"):
                return arguments
            self._expect_operator(",")

    def _read_segment(self) -> str | None:
        kind, value = self._next()
        if kind == "name" or (kind == "operator" and value == "*"):
            return str(value)
        if kind == "bool":
            # `true` / `false` are only keywords in value position.
            return "true" if value else "false"
        raise ExpressionError(f"unexpected path segment {value!r}")

    def _extend_segment(self, node: Node, segment: str) -> Node:
        if not isinstance(node, ContextPath):
            return Access(node)
        return ContextPath((*node.segments, segment), node.indices)

    def _extend_index(self, node: Node, index: Node) -> Node:
        # A literal key is the indexed spelling of a dot segment, so both
        # forms of one path produce one shape.
        if isinstance(index, Value) and index.kind == "string":
            return self._extend_segment(node, str(index.value))
        if not isinstance(node, ContextPath):
            return Access(node, index)
        return ContextPath(node.segments, (*node.indices, index))

    def _next(self) -> tuple[str, object]:
        if self._position >= len(self._tokens):
            raise ExpressionError("unexpected end of expression")
        token = self._tokens[self._position]
        self._position += 1
        return token

    def _peek_comparison(self) -> str | None:
        if self._position >= len(self._tokens):
            return None
        kind, value = self._tokens[self._position]
        if kind == "operator" and value in _COMPARISONS:
            return str(value)
        return None

    def _take_operator(self, operator: str) -> bool:
        if self._position >= len(self._tokens):
            return False
        kind, value = self._tokens[self._position]
        if kind == "operator" and value == operator:
            self._position += 1
            return True
        return False

    def _expect_operator(self, operator: str) -> None:
        if not self._take_operator(operator):
            raise ExpressionError(f"expected {operator!r}")
