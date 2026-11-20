# Guide for coding agents

How to work on turborel-py as a coding agent, with any tool. If this file
disagrees with [RULES.md](RULES.md) or [CONTRIBUTING.md](CONTRIBUTING.md),
follow those.

turborel-py is the Python driver for turborel, a relational database
system. It speaks turborel's native protocol, version 1, in pure Python
on the standard library, and is built to do all turborel-client does.
See [README.md](README.md).

## Before you change anything

Read RULES.md §3 (code), §4 (tests), §7 (process) and the §1 decisions
for your area. Read CONTRIBUTING.md for how a change is made and the
extra checks for changes that touch the protocol. Read the section of
the protocol, or of the client documents, that your change implements.

## Build and check

Every change must pass `python -m tools.verify --coverage` before it is
handed back.

```
uv sync --locked                          # the environment, as uv.lock pins it
uv run python -m tools.verify             # every check a change must pass
uv run python -m tools.verify --coverage  # the same, then the coverage floor
uv run --python 3.15 python -m tools.verify
                                          # on another supported Python, 3.11 to 3.15
uv run pytest tests/codec                 # some tests alone
uv build                                  # the sdist and the wheel, in dist/
```

`verify` runs, in order and stopping at the first failure: `ruff format
--check`, `ruff check`, `mypy`, the rules of `tools/rules.py` (function
and file lengths, each test's citation, each citation's target), and the
tests. CI runs it on Linux, macOS and Windows with each supported Python,
and coverage on Linux (D11). The floor is `fail_under` in
`pyproject.toml`, and only rises (R-COV-2).

uv installs the Python versions it needs itself (`uv python install
3.11 3.15`). Project automation is Python in `tools/`, never shell
scripts (D4, R-TOOL-1).

## Where things are

| Path | What |
|---|---|
| `src/turborel/__init__.py` | the package: its docstring, PEP 249's globals and exceptions |
| `src/turborel/_errors.py` | PEP 249's exceptions, each carrying SQLCODE and SQLSTATE (D7) |
| `src/turborel/_codec/` | the protocol's codec, without I/O; `frames.py`, a frame's header |
| `tests/` | the tests, a folder for each layer: `tests/codec/` for `_codec` |
| `tools/` | the checks: `verify.py` runs them, `rules.py` holds the project's own, `headings.py` lists the headings tests cite |
| `doc/` | the manual: `user/` (Volume I, User's Guide), `client/` (Volume II, API Reference), `appendix/`; laid out as turborel's, which turborel.com's docs site reads |

Each layer of the plan becomes a private package of its own as its
milestone begins, mapped to the turborel-client module it follows
(D12). The public interface is `turborel` and, from M7, `turborel.aio`.

The protocol is turborel's `doc/client/05-protocol.md`, the client's
features `doc/client/02-library.md` and `02-library-connections.md`, and
the reference code `protocol/src/` and `client/src/`, all in
[turborel](https://github.com/turborel/turborel). Where the page and the
code differ, the code is right.

## Rules that are broken most often

`verify` treats every warning as an error. RULES.md §3 and §4 have the
full list.

- Every failure is one of the driver's exceptions with its SQLCODE and
  SQLSTATE (R-ERR-1). No `ValueError`, `struct.error`, `IndexError` or
  `OSError` may reach a program; catch it and raise the driver's, `from`
  the original (R-ERR-3).
- No `assert` in library code, and no `print` (R-ERR-1, R-STYLE-4).
- Check every length or count a server sends against its bound before
  reading or reserving for it (R-ERR-4).
- Keep functions to 50 lines of code and 5 parameters, and files to 600
  lines (R-SIZE).
- No magic numbers or strings: protocol tags, kinds and capability names
  are `Final` constants in the codec (R-CONST).
- Every public module, class, function and constant has a docstring, in
  Google's style, with `Raises:` (R-DOC-1, D8).
- Comments say why (R-DOC-2). No `TODO` comments or commented-out code
  (R-DOC-3).
- `mypy --strict` passes, with no `Any` in a public signature; a
  `type: ignore` names its code (R-TYPE).
- A `noqa` names its rule and says why (R-DEV-1).
- No dependency without a decision in RULES.md (R-DEP-1).
- Code for one platform is chosen by `sys.platform` and refused
  elsewhere with the driver's error (R-PLAT-1).
- Secrets never reach a log, a `repr` or an exception's message
  (R-SAFE-2).

## Tests

Every test is a pytest function whose docstring begins `Verifies:` and a
tag (R-TRACE-1, D13):

- `[PROTOCOL <heading>]`, a section of 05-protocol.md, as
  `[PROTOCOL Frames]`;
- `[CLIENT <heading>]`, a section of 02-library.md or
  02-library-connections.md, as `[CLIENT Pipelines]`;
- `[DESIGN] D<n>`, a decision of RULES.md;
- `[TOOL] R-…`, a rule `tools/` checks.

The headings are listed in `tools/headings.py`, and `verify` refuses one
that is not there. Tests are deterministic, with no clock, randomness or
network beyond loopback (R-TEST-5). Shared fixtures go in a
`conftest.py`. A fixed defect gets a regression test that fails without
the fix (R-TEST-6).

## Citing the spec

Check every citation against the document before writing it, by its
heading as printed. Never cite from memory. Code never cites TODO.md.

## Documents

A finished feature updates these in the same change:

- RULES.md, if it made a decision, including the row in §1's table;
- CONFORMANCE.md, each row it implements (R-TRACE-3);
- TODO.md, which only holds open work;
- [doc/](doc/README.md), for anything a program sees (R-DOC-6), every
  example run: each chapter keeps its `# Title` and its
  `[Contents](README.md)` line, and links only within `doc/` or by full
  URL, as the docs site reads it;
- README.md, if what the driver is or needs changes.

## Commits

- Commit only when the maintainer asks, and never push without approval.
- Follow CONTRIBUTING.md's form, with one logical change per commit.
- Add no AI or agent attribution to a commit or pull request. That means
  no `Co-Authored-By` for an agent, no "Generated with" and no
  `Signed-off-by`.
- Stage with an explicit path list, `git add -- <path> ...`. Never use
  `git add -A` or `git add .` on the whole tree.
- Never stage `LICENSE` or scratch files.
- Code for one platform can't be verified locally on another. Say so
  when handing it back.
