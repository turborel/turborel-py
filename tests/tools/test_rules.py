"""Tests of the rules `tools.rules` checks, each by a file that breaks it."""

from __future__ import annotations

from pathlib import Path

from tools.rules import (
    MAX_FILE_LINES,
    MAX_FUNCTION_LINES,
    check,
    citations,
    file_length,
    function_length,
    verifies_tags,
)

# Brackets are joined at run time, so the checks reading this file do not
# take its examples for its own citations.
OPEN = "["
RULES = "#### D1. A decision\n\n| R-SIZE-1 | A rule. | a check |\n"
TESTS = Path("tests/test_example.py")


def function_of(lines: int) -> str:
    """A function of `lines` lines of code, with a docstring, a comment and blanks."""
    body = "".join(f"    x{n} = {n}\n" for n in range(lines - 1))
    return f'def f():\n    """Doc.\n\n    More.\n    """\n    # Why.\n\n{body}'


def test_a_file_of_600_lines_passes_and_601_fails() -> None:
    """Verifies: [TOOL] R-SIZE-2 a source file has at most 600 lines."""
    path = Path("a.py")
    assert file_length(path, "x = 1\n" * MAX_FILE_LINES) == []
    assert file_length(path, "x = 1\n" * (MAX_FILE_LINES + 1)) == [
        "a.py: 601 lines, more than 600 (R-SIZE-2)"
    ]


def test_a_function_of_50_lines_of_code_passes_and_51_fails() -> None:
    """Verifies: [TOOL] R-SIZE-1 a function has at most 50 lines of code.

    Its docstring, comments and blank lines are not counted.
    """
    path = Path("a.py")
    assert function_length(path, function_of(MAX_FUNCTION_LINES)) == []
    assert function_length(path, function_of(MAX_FUNCTION_LINES + 1)) == [
        "a.py:1: f has 51 lines of code, more than 50 (R-SIZE-1)"
    ]


def test_a_test_without_a_tag_fails() -> None:
    """Verifies: [TOOL] R-TRACE-1 each test's docstring begins with a tag.

    Each tag is accepted: a document's heading, a decision, a rule. A
    helper whose name is no test's, and a module no test's, are not read.
    """
    tagged = [
        f"{OPEN}PROTOCOL Frames]",
        f"{OPEN}CLIENT Pipelines]",
        f"{OPEN}DESIGN] D1",
        f"{OPEN}TOOL] R-SIZE-1",
    ]
    for tag in tagged:
        text = f'def test_a():\n    """Verifies: {tag} what."""\n'
        assert verifies_tags(TESTS, text) == []
    untagged = 'def test_b():\n    """Checks."""\n\ndef test_c():\n    pass\n'
    assert len(verifies_tags(TESTS, untagged)) == 2
    assert verifies_tags(TESTS, 'def test_d():\n    """Verifies: what."""\n') != []
    assert verifies_tags(TESTS, "def helper():\n    pass\n") == []
    assert verifies_tags(Path("tests/common.py"), untagged) == []


def test_a_citation_of_nothing_fails() -> None:
    """Verifies: [TOOL] R-TRACE-2 each citation names what exists.

    A heading of the protocol or the client documents, a decision of
    RULES.md, a rule of RULES.md.
    """
    path = Path("a.py")
    good = f"{OPEN}PROTOCOL Frames] {OPEN}DESIGN] D1 {OPEN}TOOL] R-SIZE-1"
    assert citations(path, good, RULES) == []
    bad = f"{OPEN}PROTOCOL Framez] {OPEN}CLIENT Pools!] {OPEN}DESIGN] D2"
    bad += f" {OPEN}TOOL] R-SIZE-9"
    assert len(citations(path, bad, RULES)) == 4


def test_every_check_reads_every_file(tmp_path: Path) -> None:
    """Verifies: [TOOL] R-TRACE-1 the checks run over each file given."""
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1\n", encoding="utf-8")
    broken = tmp_path / "test_broken.py"
    broken.write_text("def test_a():\n    pass\n", encoding="utf-8")
    findings = check([clean, broken], RULES)
    assert len(findings) == 1
    assert "test_a" in findings[0]
