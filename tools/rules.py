"""The rules no linter checks: lengths, and what each test cites.

R-SIZE-1 (a function's lines), R-SIZE-2 (a file's lines), R-TRACE-1
(each test's `Verifies:` paragraph) and R-TRACE-2 (each citation names a
heading, decision or rule that exists). Each check gives its findings
as lines for a person, empty when the rule holds.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Final

from tools.headings import DOCUMENTS

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

MAX_FILE_LINES: Final = 600
"""R-SIZE-2: the most lines a source file has."""

MAX_FUNCTION_LINES: Final = 50
"""R-SIZE-1: the most lines of code a function has."""

VERIFIES: Final = "Verifies: "
"""R-TRACE-1: how a test's docstring begins."""

TEST_PREFIX: Final = "test_"
"""What pytest collects: a test module's, and a test function's, prefix."""

# R-TRACE-1: a test's first tag, then R-TRACE-2's citations anywhere.
_FIRST_TAG: Final = re.compile(
    r"\[(?:PROTOCOL|CLIENT) [^\]]+\]|\[DESIGN\] D\d+|\[TOOL\] R-[A-Z]+-\d+"
)
_DOCUMENT_CITATION: Final = re.compile(r"\[(PROTOCOL|CLIENT) ([^\]]+)\]")
_DECISION_CITATION: Final = re.compile(r"\[DESIGN\] (D\d+)")
_RULE_CITATION: Final = re.compile(r"\[TOOL\] (R-[A-Z]+-\d+)")
_DECISION_HEADING: Final = re.compile(r"^#### (D\d+)\.", re.MULTILINE)
_RULE_ROW: Final = re.compile(r"^\| (R-[A-Z]+-\d+) \|", re.MULTILINE)

_Function = ast.FunctionDef | ast.AsyncFunctionDef

# A citation's form written out in a document, as `[PROTOCOL <heading>]`,
# names no heading.
_PLACEHOLDER: Final = "<"


def file_length(path: Path, text: str) -> list[str]:
    """R-SIZE-2: the finding if `text`, the file at `path`, is too long."""
    lines = len(text.splitlines())
    if lines <= MAX_FILE_LINES:
        return []
    return [f"{path}: {lines} lines, more than {MAX_FILE_LINES} (R-SIZE-2)"]


def _functions(tree: ast.AST) -> Iterator[_Function]:
    for node in ast.walk(tree):
        if isinstance(node, _Function):
            yield node


def _docstring_lines(function: _Function) -> set[int]:
    first = function.body[0]
    is_docstring = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
    if not is_docstring or first.end_lineno is None:
        return set()
    return set(range(first.lineno, first.end_lineno + 1))


def code_lines(function: _Function, lines: list[str]) -> int:
    """The lines of code in `function`: not blank, a comment or its docstring.

    Args:
        function: The function, parsed.
        lines: The lines of the file it is in.

    Returns:
        How many of its lines are code.
    """
    end = function.end_lineno or function.lineno
    docstring = _docstring_lines(function)
    counted = 0
    for number in range(function.lineno, end + 1):
        line = lines[number - 1].strip()
        if line and not line.startswith("#") and number not in docstring:
            counted += 1
    return counted


def function_length(path: Path, text: str) -> list[str]:
    """R-SIZE-1: a finding for each function in `text` that is too long."""
    lines = text.splitlines()
    return [
        f"{path}:{function.lineno}: {function.name} has {counted} lines of code,"
        f" more than {MAX_FUNCTION_LINES} (R-SIZE-1)"
        for function in _functions(ast.parse(text, filename=str(path)))
        if (counted := code_lines(function, lines)) > MAX_FUNCTION_LINES
    ]


def verifies_tags(path: Path, text: str) -> list[str]:
    """R-TRACE-1: a finding for each test in `text` that cites nothing.

    A test is a function whose name begins `test_` in a module whose does;
    its docstring begins `Verifies: ` and then a tag.
    """
    if not path.name.startswith(TEST_PREFIX):
        return []
    findings = []
    for function in _functions(ast.parse(text, filename=str(path))):
        if not function.name.startswith(TEST_PREFIX):
            continue
        doc = ast.get_docstring(function) or ""
        tagged = doc.startswith(VERIFIES) and _FIRST_TAG.match(doc, len(VERIFIES))
        if not tagged:
            findings.append(
                f"{path}:{function.lineno}: {function.name} has no"
                f" `{VERIFIES}[tag]` docstring (R-TRACE-1)"
            )
    return findings


def citations(path: Path, text: str, rules: str) -> list[str]:
    """R-TRACE-2: a finding for each citation in `text` of nothing.

    Args:
        path: The file `text` is.
        text: Its text.
        rules: The text of RULES.md, whose decisions and rules are cited.

    Returns:
        A finding for each heading, decision or rule cited that does not
        exist.
    """
    decisions = set(_DECISION_HEADING.findall(rules))
    rule_ids = set(_RULE_ROW.findall(rules))
    # A citation wrapped across lines is the heading of its words.
    cited = [(d, " ".join(h.split())) for d, h in _DOCUMENT_CITATION.findall(text)]
    findings = [
        f"{path}: [{document} {heading}] is no heading of {document} (R-TRACE-2)"
        for document, heading in cited
        if heading not in DOCUMENTS[document] and not heading.startswith(_PLACEHOLDER)
    ]
    findings += [
        f"{path}: {decision} is no decision of RULES.md (R-TRACE-2)"
        for decision in _DECISION_CITATION.findall(text)
        if decision not in decisions
    ]
    findings += [
        f"{path}: {rule} is no rule of RULES.md (R-TRACE-2)"
        for rule in _RULE_CITATION.findall(text)
        if rule not in rule_ids
    ]
    return findings


def check(paths: list[Path], rules: str) -> list[str]:
    """Every finding of every rule here, over the files `paths`.

    Args:
        paths: The Python files to check.
        rules: The text of RULES.md.

    Returns:
        Every finding, in the order of the files.
    """
    findings: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        findings += file_length(path, text)
        findings += function_length(path, text)
        findings += verifies_tags(path, text)
        findings += citations(path, text, rules)
    return findings


def check_documents(paths: list[Path], rules: str) -> list[str]:
    """R-TRACE-2's findings over the documents `paths`, such as CONFORMANCE.md.

    Args:
        paths: The Markdown files to check.
        rules: The text of RULES.md.

    Returns:
        A finding for each citation of a heading, decision or rule that
        does not exist.
    """
    findings: list[str] = []
    for path in paths:
        findings += citations(path, path.read_text(encoding="utf-8"), rules)
    return findings
