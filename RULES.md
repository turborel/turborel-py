# turborel-py rules

How turborel-py is designed, written and verified. Every change follows
these rules; `python -m tools.verify` checks those a tool can check, and
review checks the rest.

Rules (R-…) say how code and tests are written. **shall** is mandatory,
and a departure needs a recorded deviation (§6). **should** is expected,
and a reviewer may accept a reasoned exception.

Decisions (D1…) record how the driver is built and why. Change one only
by changing this file in a reviewed commit. A decision says what was
chosen and why, and the module it names holds the mechanism.

Cite both by ID in code, tests, reviews and commit messages, as in
`RULES.md D7` or `R-ERR-2`.

The rules are modelled on turborel's own RULES.md, adapted to Python.
Where Python's library conventions and a rule here disagree, the rule is
kept, and [Python's conventions](#python-conventions-set-aside) lists
where.

Before changing code, read §3 (code rules), §4 (test rules) and the
decisions covering your area. What the driver implements is in
[CONFORMANCE.md](CONFORMANCE.md), and open work is in [TODO.md](TODO.md).

[1 Decisions](#1-decisions) · [2 Layout](#2-project-layout) ·
[3 Code](#3-code-rules) · [4 Tests](#4-test-rules) ·
[5 Coverage](#5-coverage) · [6 Deviations](#6-deviations) ·
[7 Process](#7-process-and-tools) · [8 References](#8-references)

---

## 1. Decisions

| # | Decision |
|---|---|
| **The driver** | |
| D1 | The native protocol, version 1, in pure Python, with no native core |
| D2 | DB-API 2.0 with the qmark style, and asyncio beside it |
| D3 | CPython 3.11 and later, each release until its end of life |
| D7 | Every failure is one of PEP 249's exceptions, carrying its condition |
| D9 | The driver's version is the turborel release it is made for |
| D12 | One private package for each layer, as turborel-client has one module |
| D14 | The codec keeps turborel-protocol's bounds, and refuses what it does |
| **Tooling and process** | |
| D4 | Automation in Python, on the standard library |
| D5 | The build backend is uv_build |
| D6 | ruff, mypy in strict mode, pytest and coverage.py, pinned |
| D8 | Docstrings in Google's style |
| D10 | A coverage floor of 95 %, by branch, that only rises |
| D11 | CI on Linux, macOS and Windows, over every supported Python |
| D13 | Tests cite turborel's documents by their headings |

### The driver

#### D1. The native protocol, version 1, in pure Python, with no native core

The driver speaks turborel's native protocol, version 1, as
doc/client/05-protocol.md in turborel's repository lays it out, itself.
It wraps no library of another language, so it installs from PyPI with
nothing to compile, on every platform CPython runs on. Where that page and
turborel-protocol's code differ, the code is right, and the driver follows
it.

The reference is turborel-client: the driver does all it does, in the
layers of the plan, before it is called done (CONFORMANCE.md). TLS, the
hashes SCRAM needs, and zlib come from the standard library's `ssl`,
`hashlib`, `hmac` and `zlib`; exact numbers are `decimal.Decimal` and
`int`. The `ssl` module gives no `tls-exporter`, so SCRAM-SHA-256-PLUS
binds the channel by `tls-server-end-point` alone, from the certificate
the server presented, over TLS 1.2 and 1.3 alike.

#### D2. DB-API 2.0 with the qmark style, and asyncio beside it

The interface is PEP 249's, DB-API 2.0, so a program and the tools built
for any Python database driver use it as they use the others.
`paramstyle` is `qmark`: a parameter is `?`, as SQL's dynamic parameters
are, so a statement goes to the server as written. An asyncio interface,
`turborel.aio`, stands beside it, with the same objects whose methods
that wait are coroutines.

What turborel-client does that PEP 249 has no place for (pipelines,
pools, copy, large objects by locator, notices, the session's status) is
reached through methods and objects of the driver's own, as PEP 249's
optional extensions are. `threadsafety` is chosen with the connection
object, and says what the connection then allows.

The module holds `apilevel`, `paramstyle` and the exceptions from the
start; `connect`, `threadsafety`, the connection and the cursor come with
the interface, at milestone M7.

#### D3. CPython 3.11 and later, each release until its end of life

The driver supports every Python release the Python core team still
supports, and drops each at its end of life, as Python's own release
cycle (PEP 602) and most libraries do. In November 2026 that is 3.11 to
3.15: 3.10 ended in October 2026, and 3.11 ends in October 2027.

3.11 gives what the driver is written with: `tomllib`, exception groups,
`asyncio.TaskGroup` and `asyncio.timeout`, and `typing.Self`. CPython is
the interpreter tested; another that runs the standard library as
CPython does may work, and is not claimed.

#### D7. Every failure is one of PEP 249's exceptions, carrying its condition

Every failure the driver raises is a `turborel.Error`, or a
`turborel.Warning` for a completion condition of class 01, as PEP 249
arranges them (`_errors.py`). Each carries its SQLCODE, its SQLSTATE and
its message, and, once a failure is read from the server, the rest of
it: the rule it cites, its position, whether a transaction is still
active, and its diagnostics.

The class is chosen by the condition. A connection failure, SQLCODE -919
and SQLSTATE 08006, as turborel-client gives a frame that cannot be read,
is an `OperationalError`. The classes of the other SQLSTATE classes are
fixed as the statements that raise them are built (milestone M3), so a
program may also decide by `sqlstate`.

#### D9. The driver's version is the turborel release it is made for

The driver has no version scheme of its own. Its version is the number
of the turborel release it is made for, the same as the server's: the
alpha is 0.0.0, as turborel's is, and speaks protocol version 1
(VERSIONING.md). The number is written in `pyproject.toml` and
`turborel.__version__`, and a test holds them to each other.

#### D12. One private package for each layer, as turborel-client has one module

Each layer of the plan is a private package of `turborel`, named for its
commit area and mapped to the turborel-client module it follows, so a
reviewer checks one against the other:

| Package | Layer | turborel-client |
|---|---|---|
| `turborel._codec` | frames, fields, the tail, types and values, JSON, compression | `protocol/src` |
| `turborel._transport` | TCP, Unix socket, named pipe, timeouts | `target.rs`, `timeouts.rs`, `pipe.rs` |
| `turborel._auth`, `turborel._tls` | mechanisms, SCRAM and its key cache; TLS | `mechanism.rs`, `scram.rs`, `tls.rs` |
| `turborel._session` | Hello to Ready, status, notices, cancel, terminate | `connection.rs`, `session.rs`, `cancel.rs`, `told.rs` |
| `turborel._statements` | queries, prepared statements, cursors | `statements.rs`, `frames.rs` |
| `turborel._lobs`, `turborel._copy` | large objects; copy, import and export | `lobs.rs`; `copy.rs`, `import/`, `export.rs` |
| `turborel._settings` | the URI, variables, files, hosts and roles | `settings/`, `failover.rs`, `role.rs` |
| `turborel._pipeline`, `turborel._pool` | pipelines; pools | `pipeline.rs`; `pool/` |

The public interface is `turborel` and `turborel.aio` alone (D2). Each
package is added as its milestone begins; `_codec` is the first.

#### D14. The codec keeps turborel-protocol's bounds, and refuses what it does

The codec reads what turborel-protocol reads, and refuses what it
refuses, each failure a connection failure (SQLCODE -919, SQLSTATE
08006). Its bounds are turborel-protocol's: arrays, rows, multisets and
structured values, as values and as types, nest at most 16 deep
(`MAX_TYPE_NESTING`); a multiset holds at most 65 535 elements, and an
array type's maximum cardinality is 1 to 65 535; a row type has a field;
a plug-in's type has at most two parameters; a message carries at most
32 attributes, each name 1 to 64 bytes and each value at most 1024; a
JSON document nests at most 128 deep. Where turborel-protocol reads a
value tag the page does not list, 5, 7, 10 and 12, the codec reads it as
turborel-protocol does; 18 and 19, which it reads as the server's stored
form of a large object, never sent, the codec refuses.

What a program sends is checked before a byte is written, by the same
bounds, so the server never has to refuse it: a number its field cannot
hold is a `DataError` (SQLSTATE 22003), a value of no type the protocol
carries a `ProgrammingError` (07006), parts nested past the bound a
`NotSupportedError` (0A000), and an argument of a request out of its
field's range an `InterfaceError` (turborel's TB910).

### Tooling and process

#### D4. Automation in Python, on the standard library

The project's checks run from `tools/`, Python on the standard library
alone, never shell scripts, so one command serves Linux, macOS and
Windows: `python -m tools.verify`. It runs each tool as a module of the
interpreter running it. The git hook, `.githooks/pre-commit`, is a
script only because git runs hooks as scripts, and it hands over to
`tools.verify` at once.

#### D5. The build backend is uv_build

The package is built by uv's backend, `uv_build`, bounded to the minor
release of the uv that CI pins (`>=0.13.9,<0.14`), as uv's documentation
asks of a backend that may change between minor releases.

Hatchling was the other choice, and serves well. uv_build was chosen
because the project is already managed by uv (its lock file, its Python
versions, its dev tools), and the backend is uv's own, declared stable
in uv 0.7.19 and the default of `uv init --lib` since 0.8. It knows the
`src/` layout without configuration, ships `py.typed` with the package,
writes the PEP 639 license metadata, and validates the metadata and the
module's place, with no plug-ins to configure. It builds pure Python
alone, which is all the driver is (D1). Any PEP 517 front end, pip's or
`python -m build`, builds with it. Its cost is the upper bound, raised
with each minor release of uv, which Dependabot proposes.

#### D6. ruff, mypy in strict mode, pytest and coverage.py, pinned

- **ruff** lints with every stable rule it has (`select = ["ALL"]`), less those
  that conflict with its formatter or with each other, and those listed
  with their reasons in `pyproject.toml`; and it formats.
- **mypy** checks types with `--strict` and further error codes. mypy
  was chosen over pyright because it runs on Python alone, as everything
  else in the project does, where pyright needs Node.js.
- **pytest** runs the tests, and **coverage.py** measures them.

Each is a development dependency only, in `pyproject.toml`'s `dev`
group, pinned to an exact version, since a new release of a linter or a
type checker adds checks; `uv.lock` holds the rest of their tree.
Dependabot proposes each bump, and a bump is its own commit.

#### D8. Docstrings in Google's style

Docstrings follow PEP 257, in Google's style: a summary line, then
`Args:`, `Returns:` and `Raises:` sections. ruff's `pydocstyle` checks
them with that convention. A constant is documented by the string after
it, as Sphinx and the documentation tools read it.

#### D10. A coverage floor of 95 %, by branch, that only rises

coverage.py measures `turborel` by line and branch, over every test, on
Linux. `fail_under` in `pyproject.toml` is the floor, and it only rises.
It is 95 % rather than 100 % because code for one platform alone, the
named pipe of Windows and the Unix socket of the others, is measured on
Linux only.

#### D11. CI on Linux, macOS and Windows, over every supported Python

`verify.yml` runs `python -m tools.verify` on Linux, macOS and Windows,
with each supported Python (D3), and coverage on Linux. Its actions are
pinned by their full commit, with the version in a comment. Live tests
against `ghcr.io/turborel/turborel:nightly` join it with the connection
(milestone M2).

#### D13. Tests cite turborel's documents by their headings

A test cites what it verifies by the heading of the section that says
it: `[PROTOCOL Frames]` for doc/client/05-protocol.md,
`[CLIENT Pipelines]` for 02-library.md and 02-library-connections.md,
each as printed. The driver's own choices are `[DESIGN] D<n>`, and the
tools' rules `[TOOL] R-…`. `tools/headings.py` lists the documents'
headings, at the turborel commit they were taken from, and
`tools.verify` refuses a citation of one that is not there.

---

## 2. Project layout

```
pyproject.toml          the package, its build, every check's configuration
uv.lock                 the development tools, locked (R-CM-1)
.python-version         the Python uv runs locally: 3.11, the oldest
README.md               what the driver is; how to build it
RULES.md                this file
CONFORMANCE.md          the parity matrix: protocol and turborel-client
TODO.md                 open work, by milestone
VERSIONING.md           versions, alpha and publishing
CONTRIBUTING.md         changes, commit messages, pull requests, issues
SECURITY.md             how to report a vulnerability
TRADEMARK.md            the name and logos
AGENTS.md               the guide for coding agents
CLAUDE.md               points Claude Code to AGENTS.md
.github/                CI (workflows/), issue forms, pull request
                        template, labels, Dependabot
.githooks/pre-commit    hands over to tools.verify (D4)
artwork/                the logos
doc/                    the manual (R-DOC-6): user/, client/, appendix/,
                        laid out as turborel's for its docs site
src/turborel/           the package: its public interface
  __init__.py           the module, its globals and exceptions (D2)
  _errors.py            PEP 249's exceptions (D7)
  _codec/               the protocol's codec, without I/O (D12)
  py.typed              says the package is typed (PEP 561)
tests/                  the tests, by layer: tests/codec/ for _codec
tools/                  the checks: verify.py, rules.py, headings.py
```

---

## 3. Code rules

### R-STYLE: formatting and idiom

| ID | Rule | Checked by |
|---|---|---|
| R-STYLE-1 | Code **shall** be formatted by `ruff format`. | `ruff format --check` |
| R-STYLE-2 | Code **shall** pass every ruff rule, less those `pyproject.toml` lists with their reasons. | `ruff check` |
| R-STYLE-3 | Names **shall** follow PEP 8; code implementing a message or field is named after it, as the spec names it. | ruff `N`; review |
| R-STYLE-4 | Library code **shall not** print, or log but through the `logging` module. | ruff `T20` |
| R-STYLE-5 | What is not public **shall** be private by its leading underscore, its module's or its own. | review |

### R-SIZE: short functions and files

| ID | Rule | Checked by |
|---|---|---|
| R-SIZE-1 | A function **shall** have at most 50 lines of code, its docstring, comments and blank lines not counted. | `tools/rules.py` |
| R-SIZE-2 | A source file **shall** have at most 600 lines. | `tools/rules.py` |
| R-SIZE-3 | A function **shall** take at most 5 parameters; else a dataclass or keyword object. | ruff `PLR0913`, `PLR0917` |
| R-SIZE-4 | A function's cyclomatic complexity **shall** be at most 10, and a module **should** hold one concept, said in its docstring. | ruff `C901`; review |

### R-DOC: comments and documentation

| ID | Rule | Checked by |
|---|---|---|
| R-DOC-1 | Every public module, class, function and constant **shall** have a docstring, in Google's style (D8), with `Raises:` for each exception it raises. | ruff `D`; review |
| R-DOC-2 | Comments **shall** say *why*: the rule implemented, the choice made, the invariant relied on. | review |
| R-DOC-3 | No commented-out code, no `TODO`, `FIXME` or `XXX` comments: open work goes in TODO.md, and code never cites TODO.md. | ruff `ERA`, `FIX`, `TD` |
| R-DOC-4 | Behaviour the protocol or turborel-client governs **shall** cite it by its heading, `[PROTOCOL Frames]`, `[CLIENT Pools]`; the driver's own choices cite their decision. | review; `tools/rules.py` (R-TRACE-2) |
| R-DOC-5 | Every file **shall** begin with a docstring giving its responsibility. | ruff `D100`, `D104` |
| R-DOC-6 | A change a program can see **shall** update the manual, `doc/`, in the same commit; every claim is checked against the code, and every example is run. | review |

### R-CONST: no magic numbers or strings

| ID | Rule | Checked by |
|---|---|---|
| R-CONST-1 | Library numbers other than `0` or `1` **shall** be named `Final` constants, documenting the value's source. | ruff `PLR2004`; review |
| R-CONST-2 | Every protocol tag, kind, capability and status name **shall** be a named constant, defined once, in the codec. | review |
| R-CONST-3 | Strings matched or looked up (settings, option names, paths) **shall** be named constants. Messages for people are not. | review |
| R-CONST-4 | Tests may use literal fixtures, as the spec prints its bytes. | ruff configuration |

### R-ERR: errors

| ID | Rule | Checked by |
|---|---|---|
| R-ERR-1 | Every failure the library raises **shall** be one of the driver's exceptions (D7): no stray `ValueError`, `struct.error`, `OSError` or `KeyError` reaches a program, no `assert` decides, and no library code exits the process. | ruff `S101`, `TRY`; tests; review |
| R-ERR-2 | Each **shall** carry its SQLCODE, SQLSTATE and message, and, once read from a server, the rest of its failure. | tests |
| R-ERR-3 | An exception **shall not** be silenced; one caught and raised again as the driver's keeps its cause (`raise ... from`). | ruff `BLE`, `S110`, `B904` |
| R-ERR-4 | A length or count a server sends **shall** be checked against its bound before anything is held for it, so no reply takes the client's memory without bound. | tests; review |

### R-TYPE: types

| ID | Rule | Checked by |
|---|---|---|
| R-TYPE-1 | Code **shall** pass `mypy --strict`, with the further error codes `pyproject.toml` enables. | mypy |
| R-TYPE-2 | No `Any` in a public signature. | ruff `ANN401`; mypy |
| R-TYPE-3 | A `type: ignore` **shall** name its error code and say why. | mypy `ignore-without-code`; ruff `PGH003`; review |

### R-LINT: warnings

| ID | Rule | Checked by |
|---|---|---|
| R-LINT-1 | A warning is an error: of ruff, of mypy, and of Python itself while the tests run. | ruff; mypy; pytest `filterwarnings = ["error"]` |

### R-DEP: dependencies

| ID | Rule | Checked by |
|---|---|---|
| R-DEP-1 | The package **shall** depend on nothing but the standard library, unless a decision here admits a dependency, with its reason, version, license and review. | review |
| R-DEP-2 | A dependency, of the package or of its tools, **shall** be production-grade by its own claims: a stable release, maintained. | review |

### R-SAFE: what a server sends

| ID | Rule | Checked by |
|---|---|---|
| R-SAFE-1 | What a server sends **shall** never be run, unpickled or imported: no `eval`, `exec`, `pickle` or dynamic import of it. | ruff `S`; review |
| R-SAFE-2 | TLS **shall** verify as asked, and secrets (a password, a SCRAM key, a cancel key) **shall** never be logged, shown by `repr`, or put in an exception's message. | tests; review |

### R-PLAT: platforms

| ID | Rule | Checked by |
|---|---|---|
| R-PLAT-1 | The driver **shall** run on Linux, macOS and Windows. Code for one platform is chosen by `sys.platform`, and elsewhere refused with the driver's error, saying so. | CI (D11) |

### Python conventions set aside

- PEP 249 names an exception `Warning`, which shadows the builtin in the
  module that defines it and the one that exports it. PEP 249 wins, with
  a `noqa` saying so.
- Python's libraries commonly raise `ValueError` or `TypeError` for an
  argument out of range. Here every failure is the driver's (R-ERR-1),
  so a program catches `turborel.Error` alone.
- ruff's copyright rule, `CPY001`, is off: LICENSE covers every file,
  as in turborel, and no file repeats it.

---

## 4. Test rules

### R-TEST: levels and layout

| ID | Rule | Checked by |
|---|---|---|
| R-TEST-1 | Tests **shall** be pytest functions in `tests/`, a folder for each layer as `src/turborel/` has one; shared fixtures go in a `conftest.py`, written once. No other framework. | review |
| R-TEST-2 | Tests **shall** derive from the spec and turborel-client, not from the code: normal cases at their bounds, and robustness cases with the exact SQLCODE and SQLSTATE expected. | review |
| R-TEST-3 | A test's name **shall** say the behaviour checked. | review |
| R-TEST-4 | Test code may assert and use literal fixtures; every other rule applies. | ruff configuration |
| R-TEST-5 | Tests **shall** be deterministic and independent: no clock, randomness, network beyond loopback, or order dependence. A case generator uses a fixed seed. | review |
| R-TEST-6 | Every fixed defect **shall** get a regression test that fails without the fix, its docstring saying so. | review |

### R-TRACE: traceability

| ID | Rule | Checked by |
|---|---|---|
| R-TRACE-1 | Every test **shall** have a docstring beginning `Verifies:` and a tag: `[PROTOCOL <heading>]`, `[CLIENT <heading>]`, `[DESIGN] D<n>` or `[TOOL] R-…` (D13). | `tools/rules.py` |
| R-TRACE-2 | A citation **shall** name a heading, decision or rule that exists. | `tools/rules.py` |
| R-TRACE-3 | CONFORMANCE.md **shall** change with the change that implements a row of it. | review |

---

## 5. Coverage

| ID | Rule | Checked by |
|---|---|---|
| R-COV-1 | Coverage **shall** be measured by coverage.py, by line and branch, over `turborel`, by `python -m tools.verify --coverage`. | `tools.verify` |
| R-COV-2 | Coverage **shall not** fall below the floor, `fail_under` in `pyproject.toml` (D10); a change raising it **should** raise the floor. | coverage.py |
| R-COV-3 | A gap is closed by a test derived from a requirement, or by removing dead code; never by a test of no requirement, and never by excluding the code. | review |

---

## 6. Deviations

| ID | Rule | Checked by |
|---|---|---|
| R-DEV-1 | Every `noqa` **shall** name its rule, and say why on its line or the line above. | ruff `PGH004`; review |
| R-DEV-2 | A `noqa` or `type: ignore` no longer needed **shall** be removed. | ruff `RUF100`; mypy `warn_unused_ignores` |

---

## 7. Process and tools

| ID | Rule | Checked by |
|---|---|---|
| R-PROC-1 | `python -m tools.verify` **shall** pass before every commit: format, lint, types, the rules of `tools/rules.py`, and every test. `--coverage` adds the floor. | pre-commit hook; CI |
| R-PROC-2 | Every change **shall** be reviewed against the checklist below. | review |
| R-PROC-3 | Commits **should** be small and single-purpose, in CONTRIBUTING.md's form, citing the rules applied or changed. | review |
| R-PROC-4 | A threshold change **shall** change RULES.md, `pyproject.toml` and `tools/` together. | review |
| R-PROC-5 | A release **shall** be published only as VERSIONING.md says, by the owner. | review |
| R-TOOL-1 | Project automation **shall** be Python in `tools/`, on the standard library, never shell scripts (D4). | review |
| R-TOOL-2 | `tools/` **shall** follow these rules and test its own checks, as `[TOOL]` requirements. | `tools.verify` |
| R-CM-1 | `uv.lock` **shall** be under version control; a change of a tool's version is its own commit. | review |

The review checklist:

- the spec or turborel-client cited in code (R-DOC-4) and tests
  (R-TRACE-1);
- normal and robustness tests (R-TEST-2), a failing-first test for a fix
  (R-TEST-6);
- no magic numbers or strings (R-CONST);
- every failure the driver's, carrying its condition (R-ERR);
- comments explain why (R-DOC-2);
- CONFORMANCE.md (R-TRACE-3), the manual (R-DOC-6) and TODO.md updated
  where they change.

---

## 8. References

- turborel's doc/client/05-protocol.md, the native protocol, version 1;
  doc/client/02-library.md and 02-library-connections.md, the client
  library; and turborel-protocol and turborel-client, its code.
- PEP 249, *Python Database API Specification v2.0*.
- PEP 8, *Style Guide for Python Code*; PEP 257, *Docstring
  Conventions*; PEP 561, *Distributing and Packaging Type Information*;
  PEP 517, PEP 621 and PEP 639, the build and metadata of a package;
  PEP 602, Python's annual release cycle; PEP 735, dependency groups.
- RFC 5802 and RFC 7677, SCRAM and SCRAM-SHA-256; RFC 5929, TLS channel
  bindings; RFC 1950, zlib.
