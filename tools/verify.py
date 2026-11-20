"""Every check a change must pass, in order, stopping at the first failure.

`python -m tools.verify` runs the formatter's check, the linter, the type
checker, the rules in `tools.rules`, and the tests. `--coverage` runs the
tests under coverage and then holds the floor (RULES.md R-PROC-1,
R-COV-2). Each tool runs as a module of the interpreter running this, so
the same command serves Linux, macOS and Windows (RULES.md D4).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Final

from tools.rules import check

ROOT: Final = Path(__file__).resolve().parent.parent
"""The repository's root, where every check runs."""

SOURCES: Final = ("src", "tests", "tools")
"""The folders whose Python files the checks read."""

_TOOLS: Final = (
    ("format", ("ruff", "format", "--check")),
    ("lint", ("ruff", "check")),
    ("types", ("mypy",)),
)
_TESTS: Final = ("pytest",)
_COVERED_TESTS: Final = ("coverage", "run", "-m", "pytest")
_COVERAGE_FLOOR: Final = ("coverage", "report")


def _run(name: str, module_args: tuple[str, ...]) -> bool:
    print(f"verify: {name}", flush=True)
    command = [sys.executable, "-m", *module_args]
    return subprocess.run(command, cwd=ROOT, check=False).returncode == 0


def _rules() -> bool:
    print("verify: rules", flush=True)
    paths = sorted(path for folder in SOURCES for path in (ROOT / folder).rglob("*.py"))
    rules = (ROOT / "RULES.md").read_text(encoding="utf-8")
    findings = check(paths, rules)
    for finding in findings:
        print(finding)
    return not findings


def steps(*, coverage: bool) -> list[tuple[str, tuple[str, ...]]]:
    """The tools to run after the rules, each its name and its module's command.

    Args:
        coverage: Whether the tests run under coverage, its floor held.

    Returns:
        The steps, in order.
    """
    if coverage:
        return [("tests", _COVERED_TESTS), ("coverage", _COVERAGE_FLOOR)]
    return [("tests", _TESTS)]


def main(argv: list[str] | None = None) -> int:
    """Run every check, and say whether all passed.

    Args:
        argv: The command's arguments, `sys.argv`'s by default.

    Returns:
        The exit status: 0 if every check passed, else 1.
    """
    parser = argparse.ArgumentParser(prog="python -m tools.verify")
    parser.add_argument(
        "--coverage", action="store_true", help="run the tests under coverage"
    )
    coverage = parser.parse_args(argv).coverage
    passed = all(_run(name, args) for name, args in _TOOLS) and _rules()
    passed = passed and all(_run(name, args) for name, args in steps(coverage=coverage))
    print("verify: passed" if passed else "verify: failed", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
