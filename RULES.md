# turborel-py rules

How turborel-py is designed, written and verified. Every change follows
these rules; `uv run python -m tools.verify` checks those a tool can check, and
review checks the rest.

Rules (R-…) say how code and tests are written. **shall** is mandatory,
and a departure needs a decision recorded here (§7). **should** is
expected, and a reviewer may accept a reasoned exception.

Decisions (D1…) record how the driver is built and why. Change one only
by changing this file in a reviewed commit. A decision says what was
chosen and why, and the module it names holds the mechanism.

Cite both by ID in code, tests, reviews and commit messages, as in
`RULES.md D6` or `R-ERR-2`.

The rules are modelled on Turborel's own
[RULES.md](https://github.com/turborel/turborel/blob/main/RULES.md),
adapted to drivers. Every Turborel driver keeps the same requirement IDs
with the same meaning, and the same decisions D1 to D8, so a rule is
cited the same way in every repository; a driver's own decisions begin
at D9, and its own requirements are in families of their own. Where
Python's library conventions and a rule here disagree, the rule is
kept, and D8 lists where.

Before changing code, read §3 (code rules), §4 (test rules) and the
decisions covering your area. What the driver implements is in
[CONFORMANCE.md](CONFORMANCE.md), and open work is in [TODO.md](TODO.md).

[1 Decisions](#1-decisions) · [2 Layout](#2-project-layout) ·
[3 Code](#3-code-rules) · [4 Tests](#4-test-rules) ·
[5 Coverage](#5-coverage) · [6 Process](#6-process-and-tools) ·
[7 The decisions](#7-the-decisions) · [8 References](#8-references)

---

## 1. Decisions

Each is told in full in [§7](#7-the-decisions).

| # | Decision |
|---|---|
| **Shared by every Turborel driver** | |
| D1 | The native protocol, version 1, in layers that follow turborel-client |
| D2 | The language's standard API, over a low-level client of turborel-client's features |
| D3 | The runtime minimum follows the ecosystem's own support |
| D4 | One command runs every check, before each commit and in CI on three platforms |
| D5 | The version is the Turborel release's: 0.0.0 in the alpha, speaking protocol 1 |
| D6 | Tests and code cite Turborel's documents by their headings |
| D7 | A coverage floor, enforced in CI, that only rises |
| D8 | Where these rules depart from Python's conventions |
| **This driver's own** | |
| D9 | Every failure is one of PEP 249's exceptions, carrying its condition |
| D10 | The build backend is uv_build |
| D11 | ruff, mypy in strict mode, pytest and coverage.py, pinned |
| D12 | Docstrings in Google's style |
| D13 | The codec keeps turborel-protocol's bounds, and refuses what it does |
| D14 | Live tests run where TURBOREL_TEST_SERVER names turboreld's command |

---

## 2. Project layout

| Path | What |
|---|---|
| `pyproject.toml` | the package, its build (D10) and every check's configuration (D11) |
| `uv.lock` | the development tools, locked (R-DEP-3) |
| `.python-version` | the Python uv runs locally: 3.11, the oldest |
| `src/turborel/__init__.py` | the package: its docstring, PEP 249's globals and exceptions (D2) |
| `src/turborel/_errors.py` | PEP 249's exceptions, each carrying SQLCODE and SQLSTATE (D9) |
| `src/turborel/_codec/` | the `codec` layer, without I/O: frames, fields, types and values, JSON, the tail, every message, compression (D1) |
| `src/turborel/_values.py` | the classes of values Python has no type of its own for (doc/appendix/a-types.md) |
| `src/turborel/_auth/` | the `auth` layer: trust, password, certificate, SCRAM and its key cache |
| `src/turborel/_tls/` | the `tls` layer: TLS contexts and the channel SCRAM binds |
| `src/turborel/_transport/` | the `transport` layer: TCP, Unix sockets, named pipes, timeouts |
| `src/turborel/_session/` | the `session` layer: each request as steps without I/O, the session's state, and the blocking runner |
| `src/turborel/_statements/` | the `statements` layer, as steps without I/O: queries, several statements at once, prepared statements and their cursors |
| `src/turborel/_lobs/` | the `lobs` layer, as steps without I/O: large objects read by their locators, created, appended to, freed and held |
| `src/turborel/_copy/` | the `copy` layer: bulk copy as steps without I/O; export, as CSV or the protocol's frames, and each value as text; import, its sources and delimited text, and names as SQL writes them |
| `src/turborel/_client/` | the low-level client's parts: a connection's core, its statements, its large objects, its copy and export, cancelling, connecting |
| `src/turborel/client.py` | the low-level client, public: connections, statements, large objects, copy, import and export, mechanisms, TLS, timeouts (D2) |
| `src/turborel/py.typed` | says the package is typed (PEP 561) |
| `tests/` | the tests, a folder for each layer, as `tests/codec/` for `_codec`; `tests/kit.py` the frames and peer they share |
| `tests/server/` | the live tests and their server's set-up (D14) |
| `tools/` | the checks tool: `verify.py` runs every check, `rules.py` and `manual.py` hold the project's own rules, `headings.py` the headings tests cite (D4, D6) |
| `doc/` | the manual (R-DOC-7) |

Each layer of D1 is a private package of `turborel`, added as its
milestone begins: `_codec`, `_transport`, `_auth`, `_tls`, `_session`,
`_statements`, `_lobs`, `_copy`, `_settings`, `_pipeline` and `_pool`.
The public interface is `turborel`, the low-level client
`turborel.client`, and, from M7, `turborel.aio`.

---

## 3. Code rules

The tools named by "the formatter", "the linters", "the type checker" and
"the checks tool" are D4's.

### R-STYLE: formatting and idiom

| ID | Rule | Checked by |
|---|---|---|
| R-STYLE-1 | Code **shall** be formatted by the formatter. | the formatter |
| R-STYLE-2 | Names **shall** follow the language's own conventions; code implementing a message, field or setting is named after it, as the spec names it. | the linters; review |
| R-STYLE-3 | Library code **shall not** print, or write to a stream it was not given. | the linters or the checks tool |
| R-STYLE-4 | What is not public **shall** be private, by the language's own means, so the public API is what is documented. | review |

### R-SIZE: short functions and files

| ID | Rule | Checked by |
|---|---|---|
| R-SIZE-1 | A function **shall** have at most 50 lines of code, blank lines and comments not counted. | the linters or the checks tool |
| R-SIZE-2 | A source file **shall** have at most 600 lines; split by the spec's sections or by layer. | the linters or the checks tool |
| R-SIZE-3 | A function **shall** take at most 5 parameters; else a structure or an options object. | the linters |
| R-SIZE-4 | A module **should** hold one concept, stated in its doc comment. | review |
| R-SIZE-5 | A function's complexity **shall** be at most 15, and its blocks nested at most 5 deep. | the linters |

### R-DOC: comments and documentation

| ID | Rule | Checked by |
|---|---|---|
| R-DOC-1 | Every public item **shall** have a doc comment in the language's documentation format, saying each parameter, what it returns, and each failure it gives. | the linters; review |
| R-DOC-2 | Comments **shall** say *why*: the section implemented, the choice made, the invariant relied on. | review |
| R-DOC-3 | The API reference, where the language's tools build one, **shall** build without warnings. | the checks tool |
| R-DOC-4 | Behaviour the protocol or turborel-client governs **shall** cite it by its heading, `[PROTOCOL Frames]`, `[CLIENT Pools]`; the driver's own choices cite their decision (D6). | review; the checks tool |
| R-DOC-5 | No commented-out code, and no `TODO`, `FIXME` or `XXX` comments: open work goes in TODO.md, and code never cites TODO.md. | the linters or the checks tool |
| R-DOC-6 | Every source file **shall** begin with a doc comment giving its responsibility and the sections it implements. | review |
| R-DOC-7 | A change a program can see **shall** update the manual, `doc/`, in the same commit; every claim is checked against the code, and every example is run. The manual keeps Turborel's layout, which turborel.com's documentation site reads: each page opens with its `# Title` and a line holding only `[Contents](README.md)`, each volume's README.md lists its pages, links within `doc/` and to other files of this repository are relative links that resolve (the site points the latter at GitHub, at the same tag), a link to Turborel's own manual is its GitHub address under `https://github.com/turborel/turborel/blob/main/doc/`, `user/01-installing.md` keeps its name, and `doc/` holds no images. | review; the checks tool |

### R-CONST: no magic numbers or strings

| ID | Rule | Checked by |
|---|---|---|
| R-CONST-1 | Numbers in library code other than `0` or `1` **shall** be named constants, documenting the value's source. | the linters; review |
| R-CONST-2 | Every protocol tag **shall** be a named constant, defined once: a message's kind, a data type's and a value's tag, a tail tag, a capability's name, a mechanism's name, a status name, and each SQLSTATE the driver raises. | review |
| R-CONST-3 | Strings matched or looked up, such as settings' names, URI parts and environment variables, **shall** be named constants. Messages for people are not. | review |
| R-CONST-4 | Related constants **shall** live together in their layer's module, under a comment naming the section they come from. | review |
| R-CONST-5 | Tests may use literal fixtures, as the spec prints its bytes; an expected value restating a constant **should** use it. | review |

### R-ERR: errors

| ID | Rule | Checked by |
|---|---|---|
| R-ERR-1 | Every failure the library gives **shall** be the driver's error (D2): no stray exception, panic, abort, assertion or other error of the language or its libraries reaches a program, and no library code ends the process. | the linters; tests; review |
| R-ERR-2 | Each failure **shall** carry its SQLCODE, SQLSTATE and message, and, once read from a server, the rest of it: the rule it cites, its position, whether a transaction is still active, and its diagnostics. A failure the driver raises itself carries the SQLCODE and SQLSTATE turborel-client gives the same failure. | tests |
| R-ERR-3 | No failure **shall** be silenced. One caught and given again as the driver's keeps its cause; a result left unread says why it cannot matter. | the linters; review |
| R-ERR-4 | A connection that fails **shall** be closed, and every request waiting on it given that failure; a failed call leaks nothing and leaves nothing waiting. | tests; review |

### R-NUM: integers and numbers

| ID | Rule | Checked by |
|---|---|---|
| R-NUM-1 | Every integer of the protocol **shall** be read and written at its width, little-endian, explicitly: never by the platform's byte order, by casting a buffer, or by bitwise operators on numbers wider than the language's operators keep exact. | review; tests |
| R-NUM-2 | A value out of range for its field, or for the type it is read into, **shall** be refused with the driver's error, never truncated, wrapped or rounded. | tests |
| R-NUM-3 | An exact number (units `i128`, scale `u32`) and a DECFLOAT **shall** never pass through a binary floating-point type. | review; tests |
| R-NUM-4 | An approximate number **shall** keep its bits: NaN and -0.0 are read and written as the double they are, and floats are compared bit for bit, never for equality. | tests; review |
| R-NUM-5 | In a language whose integers are bounded, arithmetic on sizes, counts and offsets **shall** be shown not to overflow before it is done. | the linters; review |

### R-LINT: warnings

| ID | Rule | Checked by |
|---|---|---|
| R-LINT-1 | A warning is an error: of the compiler, the linters and the type checker, and of the runtime itself while the tests run. | the checks tool |
| R-LINT-2 | The strictest standard linters and type checking the language has **shall** be on; a check left off says why in the configuration that leaves it off. | review |
| R-LINT-3 | A warning **shall** be silenced only on its line, naming its rule and saying why; a suppression no longer needed **shall** be removed. | the linters; review |

### R-DEP: dependencies

| ID | Rule | Checked by |
|---|---|---|
| R-DEP-1 | The library **shall** depend on nothing but the language's standard library and runtime, unless a decision here admits a dependency, with its reason, version, license and review. | review |
| R-DEP-2 | A dependency, of the library or of its tools, **shall** be production-grade by its makers' own claims: a stable release they support. | review |
| R-DEP-3 | Tools **shall** be pinned by version, with the ecosystem's lock file under version control where it has one; a change of a tool's version is a commit of its own. | review |

### R-SAFE: what a server sends, and secrets

| ID | Rule | Checked by |
|---|---|---|
| R-SAFE-1 | A length or count a server, or a file the driver reads, gives **shall** be checked against what follows and the limit taken before anything is held for it, so no reply takes the program's memory without bound. | tests; review |
| R-SAFE-2 | What a server sends **shall** never be run, loaded or deserialized as code. | the linters; review |
| R-SAFE-3 | TLS **shall** be used and verified as the settings ask, and a connection **shall not** fall back to less than its mode allows. | tests |
| R-SAFE-4 | A secret (a password, anything derived from one, a SCRAM key or proof, a cancel key) **shall** never be logged, put in a failure's message or an object's display form, or sent where it was refused; where the language allows, it is cleared from memory once used. | tests; review |
| R-SAFE-5 | No module-level mutable state: what lasts belongs to an object a program made, such as a connection, a pool or a key cache. | review |
| R-SAFE-6 | The library **shall** start no thread, timer or task but for an object a program made, and a closed connection, cursor or pool leaves none behind. | tests; review |

### R-PLAT: platforms

| ID | Rule | Checked by |
|---|---|---|
| R-PLAT-1 | The driver **shall** run on Linux, macOS and Windows, on every runtime D3 supports; CI checks each (D4). | CI |
| R-PLAT-2 | Code of one platform, such as a Unix socket or a named pipe, **shall** be chosen by the platform, and elsewhere refused with the driver's error, saying so; never silently something else. | tests; review |
| R-PLAT-3 | Paths **shall** be made by the language's path functions, and files kept with LF line endings (`.gitattributes`). | review |
| R-PLAT-4 | Code built for one platform only **shall** say, when handed back, that it was not run on the others. | review |

### R-TYPE: types

| ID | Rule | Checked by |
|---|---|---|
| R-TYPE-1 | Code **shall** pass `mypy --strict`, with the further error codes `pyproject.toml` enables. | the type checker |
| R-TYPE-2 | No `Any` in a public signature. | the linters; the type checker |
| R-TYPE-3 | A `type: ignore` **shall** name its error code and say why. | the type checker; the linters; review |

---

## 4. Test rules

### R-TEST: levels and layout

| ID | Rule | Checked by |
|---|---|---|
| R-TEST-1 | A test **shall** sit at the lowest level that shows its requirement: a codec test of bytes, a test of a layer over a stream the test controls, a test of the API, or a live test against a server. | review |
| R-TEST-2 | Tests **shall** derive from the spec and turborel-client, not from the code: normal cases, boundaries included, and robustness cases with the exact SQLCODE and SQLSTATE expected. | review |
| R-TEST-3 | A test's name **shall** say the behaviour checked. | review |
| R-TEST-4 | Test code may assert, print and use literal fixtures; every other rule applies. | the linters' configuration |
| R-TEST-5 | Tests **shall** be deterministic and independent: no clock, randomness, network beyond loopback, or order between them. A case generator uses a fixed seed. A live test runs against a server on loopback that its own set-up starts, on its own port and data directory. | review |
| R-TEST-6 | Every fixed defect **shall** get a regression test that fails without the fix, its doc comment saying so. | review |
| R-TEST-7 | A fixture or helper shared by tests **shall** be written once, in one place. Tests use the one framework D9 or later names, no other. | review |
| R-TEST-8 | Live tests **shall** run against `ghcr.io/turborel/turborel:nightly` in CI, set up by the repository's own server set-up, with test certificates, SCRAM users and SERVER.TRUST_LOCAL. | CI |
| R-TEST-9 | SCRAM **shall** be tested by RFC 7677's test vector, and settings by the URI, service file, password file and environment cases of turborel-client's settings tests, so every driver reads settings as turborel-client does. | review |

### R-TRACE: traceability

| ID | Rule | Checked by |
|---|---|---|
| R-TRACE-1 | Every test **shall** cite what it verifies, by its docstring, beginning `Verifies:`, beginning with a tag of D6: `[PROTOCOL <heading>]`, `[CLIENT <heading>]`, `[DESIGN] D<n>` or `[TOOL] R-<id>`. | the checks tool |
| R-TRACE-2 | A citation **shall** name a heading, decision or rule that exists. | the checks tool |
| R-TRACE-3 | Code implementing a requirement **shall** cite it (R-DOC-4). | review |
| R-TRACE-4 | CONFORMANCE.md **shall** change with the change that implements or changes a row. A row is marked done only where the driver's code for it exists and tests citing its section pass, or, of a driver built over another, as CONFORMANCE.md says. | review |

---

## 5. Coverage

| ID | Rule | Checked by |
|---|---|---|
| R-COV-1 | Coverage **shall** be measured by `uv run python -m tools.verify --coverage`, over the library and every test. | the checks tool |
| R-COV-2 | Coverage **shall not** fall below the floor (D7); a change raising it **should** raise the floor. | the checks tool, in CI |
| R-COV-3 | A gap is closed by a test derived from a requirement, or by removing dead code; never by a test of no requirement, and never by excluding the code. | review |

---

## 6. Process and tools

| ID | Rule | Checked by |
|---|---|---|
| R-PROC-1 | `uv run python -m tools.verify` **shall** pass before every commit; CI adds every platform, every supported runtime and the coverage floor (D4). | pre-commit hook; CI |
| R-PROC-2 | Every change **shall** be reviewed against the checklist below. | review |
| R-PROC-3 | Commits **should** be small and single-purpose, in CONTRIBUTING.md's form (`area: summary`, then why), citing the rules applied or changed. | review |
| R-PROC-4 | A threshold change **shall** change RULES.md and the configuration that holds it together. | review |
| R-PROC-5 | Project automation **shall** be written in the language's own tooling, never shell scripts; the git hook only hands over to the checks tool. | review |
| R-PROC-6 | CI's actions **shall** be pinned by their full commit SHA, with the version in a comment. | review |
| R-PROC-7 | A release **shall** be published only as VERSIONING.md says, by the owner (D5). | review |

The review checklist:

- the spec or turborel-client cited in code (R-DOC-4) and tests
  (R-TRACE-1);
- normal and robustness tests (R-TEST-2), and a failing-first test for a
  fix (R-TEST-6);
- every failure the driver's, carrying its condition (R-ERR);
- no magic numbers or strings, protocol tags named (R-CONST);
- every length a server sends bounded, no secret disclosed (R-SAFE);
- comments explain why (R-DOC-2);
- CONFORMANCE.md (R-TRACE-4), the manual (R-DOC-7) and TODO.md updated
  where they change.

---

## 7. The decisions

### Shared by every Turborel driver

#### D1. The native protocol, version 1, in layers that follow turborel-client

The driver speaks Turborel's native protocol, version 1, as
`doc/client/05-protocol.md` in Turborel's repository lays it out,
itself, in pure Python on the standard library, with nothing to compile. Where that page and turborel-protocol's code differ,
the code is right, and the driver follows it; CONFORMANCE.md names each
such place.

The reference is turborel-client. The driver does all it does before it
is called done, row by row in CONFORMANCE.md, and is built in the same
layers as turborel-client's modules, so a reviewer checks one against
the other. Each layer is a commit area of CONTRIBUTING.md.

| Layer | What it covers | turborel-client |
|---|---|---|
| `codec` | the 5-byte frame header; fields; the tail and its tag order; the data types and values; JSON values; zlib `z` frames within the length bound; the 16 MiB body limit | `protocol/src` |
| `transport` | TCP on 7422; Unix sockets; the Windows named pipe `\\.\pipe\turborel`; TLS begun on the same port; the connect and read timeouts | `target.rs`, `timeouts.rs`, `pipe.rs` |
| `auth`, `tls` | trust, password, certificate, SCRAM-SHA-256 and -PLUS; secrets refused over plain TCP; the SCRAM key cache; TLS | `mechanism.rs`, `scram.rs`, `tls.rs` |
| `session` | Hello, Ready, Status, notices, conditions, diagnostics, autocommit, cancel, terminate, ping, reset, change-user, query attributes, multi-statement | `connection.rs`, `session.rs`, `cancel.rs`, `told.rs` |
| `statements` | queries and streamed queries; prepare, execute, fetch, close, deallocate; numbered cursors; describe; completions | `statements.rs`, `frames.rs` |
| `lobs`, `copy` | locators, their reads, writes and streams; copy, import and export | `lobs.rs`; `copy.rs`, `import/`, `export.rs` |
| `settings` | the URI, options, variables, service and password files, several hosts, roles, TLS modes, channel binding | `settings/`, `failover.rs`, `role.rs` |
| `pipeline`, `pool` | pipelines; pools; the SQL-agent | `pipeline.rs`; `pool/`, `agent.rs` |
| `api` | the standard API (D2) | the language's own |

In turborel-py each layer is a private package of `turborel`, named for
its commit area: `turborel._codec`, `turborel._transport` and so on. A
request is a generator of the frames it sends and the replies it waits
for (`_session/ops.py`, `_statements/`), so one implementation serves the blocking
connection and the asyncio one; `turborel.client` is the low-level
client's public interface. TLS,
the hashes SCRAM needs and zlib come from the standard library's `ssl`,
`hashlib`, `hmac` and `zlib`. The `ssl` module gives no `tls-exporter`,
so SCRAM-SHA-256-PLUS binds the channel by `tls-server-end-point` alone,
from the certificate the server presented, over TLS 1.2 and 1.3 alike
(D8).

#### D2. The language's standard API, over a low-level client of turborel-client's features

The driver's standard interface is DB-API 2.0 (PEP 249), with `?` parameters, and an asyncio interface beside it, `turborel.aio`, so a program, and the
tools built for Python's database interface, use it as they use
any other driver. It sits over a low-level client that has every feature
of turborel-client. What the standard interface has no place for, such
as pipelines, pools, copy, large objects by locator, notices and the
session's status, is reached through the low-level client or the
driver's own extensions of the standard interface.

Every failure is the driver's error, carrying its SQLCODE and SQLSTATE
(R-ERR). The standard interface is built at milestone M7 and checked in
M8's audit; until then its names may change.

In Python the standard interface is PEP 249's, DB-API 2.0, and
`paramstyle` is `qmark`: a parameter is `?`, as SQL's dynamic parameters
are, so a statement goes to the server as written. `turborel.aio` has
the same objects, with coroutines for the methods that wait. The
driver's error is PEP 249's hierarchy of exceptions (D9). An exact
number is a `decimal.Decimal`, or an `int` of scale 0. The module holds
`apilevel`, `paramstyle` and the exceptions from the start; `connect`,
`threadsafety`, the connection and the cursor come with M7, and
`threadsafety` says what the connection then allows.

#### D3. The runtime minimum follows the ecosystem's own support

The driver supports CPython 3.11 or later. The rule is the ecosystem's own:
support every release its makers still support, and drop each at its
end of life. Where a major framework of the language sets a higher
floor, the driver matches it. The minimum changes in a commit of its
own, which changes this decision, the package's metadata, CI and
README.md together.

In November 2026 Python's core team supports 3.11 to 3.15: 3.10 ended in
October 2026, and 3.11 ends in October 2027 (PEP 602's annual cycle).
3.11 gives what the driver is written with: `tomllib`, exception groups,
`asyncio.TaskGroup` and `asyncio.timeout`, and `typing.Self`. CPython is
the interpreter tested; another that runs the standard library as
CPython does may work, and is not claimed.

#### D4. One command runs every check, before each commit and in CI on three platforms

`uv run python -m tools.verify` runs every check a change must pass, stopping at the
first failure: the formatter, the linters, the type checker where the
language has one, the checks tool's own rules (lengths a linter does not
measure, citations and their targets, open-work markers, the manual's
titles, `[Contents](README.md)` lines and links), and every test.
`uv run python -m tools.verify --coverage` measures coverage and holds it to its floor (D7).

`.githooks/pre-commit` hands over to the same command. It is a script
only because git runs hooks as scripts. CI runs it on Linux, macOS and
Windows, over every runtime D3 supports, with the live tests against the
nightly image and coverage on Linux. Every action is pinned by its full
commit SHA, its version in a comment, and Dependabot proposes each bump.

In turborel-py the checks tool is `tools/`, Python on the standard
library, run as `python -m tools.verify`: it runs `ruff format --check`,
`ruff check`, `mypy`, its own rules (`tools/rules.py`) and pytest, each
tool as a module of the interpreter running it, so one command serves
Linux, macOS and Windows. The tools are named and pinned by D11. CI
runs it with each Python from 3.11 to 3.15.

#### D5. The version is the Turborel release's: 0.0.0 in the alpha, speaking protocol 1

The driver has no version scheme of its own. Its version is the number
of the Turborel release it is made for, the same as the server's: a
Turborel release and each driver's release for it share the number,
**MAJOR.MINOR.PATCH**, as Turborel's VERSIONING.md numbers it. The alpha
is 0.0.0, as Turborel's is, and speaks protocol version 1.

The number is written once, in `pyproject.toml`'s `version`, which `turborel.__version__` is held to. Nothing is
published, and no release is tagged, until every Turborel driver is
done; then the owner publishes them together (VERSIONING.md).

#### D6. Tests and code cite Turborel's documents by their headings

A test cites what it verifies, and code what it implements, by the
heading of the section that says it, as printed:

- `[PROTOCOL <heading>]`, a heading of The Native Protocol,
  `doc/client/05-protocol.md`, as `[PROTOCOL Frames]`;
- `[CLIENT <heading>]`, a heading of The Client Library,
  `doc/client/02-library.md`, or of Settings, Pipelines and Pools,
  `doc/client/02-library-connections.md`, which share no heading, as
  `[CLIENT Pipelines]`;
- `[DESIGN] D<n>`, a decision of this file;
- `[TOOL] R-<id>`, a rule the checks tool holds, for the tool's own
  tests.

What else a test relies on follows the tag, as an RFC by its section:
`[PROTOCOL Mechanisms] [RFC 7677 §3]`. The heading `Lob 'L'` is printed
twice in The Native Protocol, under Requests and under Replies, so a
citation of it says which it means.

The checks tool keeps the headings of those three documents, copied at
the Turborel commit CONFORMANCE.md names, and refuses a citation of a
heading, decision or rule that is not there (R-TRACE-2). In Python,
a test cites by its docstring, beginning `Verifies:`.

#### D7. A coverage floor, enforced in CI, that only rises

`uv run python -m tools.verify --coverage` measures the library's coverage over every test,
and CI fails below the floor. In every Turborel driver the floor is at
least 90 % of lines, and of branches where the tool measures them. It
only rises: a change that raises coverage well above it raises it. A
floor below 100 % says why.

In turborel-py coverage.py measures `turborel` by line and branch, and
the floor is `fail_under` in `pyproject.toml`: 95 %. It is below 100 %
because code for one platform alone, the named pipe of Windows and the
Unix socket of the others, is measured on Linux only.

#### D8. Where these rules depart from Python's conventions

The driver follows its language's library conventions for layout,
naming, packaging, documentation and testing. Where one conflicts with a
rule here, the rule is kept:

- Libraries commonly leave the length of functions and files to taste.
  These are bounded (R-SIZE).
- Libraries commonly fail an argument out of range with the language's
  own error. Here every failure is the driver's, an argument's too, with
  the SQLCODE and SQLSTATE turborel-client gives it (R-ERR-1), so a
  program handles one kind of failure.

- PEP 249 names an exception `Warning`, which shadows the builtin in the
  module that defines it and the one that exports it. PEP 249 wins, with
  a `noqa` saying so.
- ruff's copyright rule, `CPY001`, is off: LICENSE covers every file,
  as in Turborel, and no file repeats it.
- The driver behaves as turborel-client's code does, where the
  protocol's page leaves a choice or says less, but follows the page
  where turborel-client departs from it, and says so here. None is
  left: the two there were, a change of user leaving no transaction
  active and an import's long CLOB field sent by a locator, turborel-client
  does as the page says from b40bd830.
- Python's `ssl` exports no keying material, so SCRAM-SHA-256-PLUS
  binds by `tls-server-end-point`, the certificate the server presented,
  over TLS 1.2 and 1.3 alike, where turborel-client binds by
  `tls-exporter` over TLS 1.3; the server takes either. The owner chose
  this over a dependency that exports it.

### This driver's own

#### D9. Every failure is one of PEP 249's exceptions, carrying its condition

Every failure the driver raises is a `turborel.Error`, or a
`turborel.Warning` for a completion condition of class 01, as PEP 249
arranges them (`_errors.py`). Each carries its SQLCODE, its SQLSTATE and
its message, and, once a failure is read from the server, the rest of
it: the rule it cites, its position, whether a transaction is still
active, and its diagnostics.

The class is chosen by the condition. A connection failure, SQLCODE -919
and SQLSTATE 08006, as turborel-client gives a frame that cannot be read,
is an `OperationalError`. Each other SQLSTATE class takes the class
`_session/raising.py` gives it, as Appendix B of the manual lists, and
a program may also decide by `sqlstate`.

#### D10. The build backend is uv_build

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

#### D11. ruff, mypy in strict mode, pytest and coverage.py, pinned

- **ruff** formats, and lints with every stable rule it has
  (`select = ["ALL"]`), less those that conflict with its formatter or
  with each other, and those listed with their reasons in
  `pyproject.toml`.
- **mypy** checks types with `--strict` and further error codes. mypy
  was chosen over pyright because it runs on Python alone, as everything
  else in the project does, where pyright needs Node.js.
- **pytest** is the one test framework (R-TEST-7), and **coverage.py**
  measures the tests.

Each is a development dependency only, in `pyproject.toml`'s `dev`
group, pinned to an exact version, since a new release of a linter or a
type checker adds checks; `uv.lock` holds the rest of their tree
(R-DEP-3). Dependabot proposes each bump, and a bump is its own commit.

#### D12. Docstrings in Google's style

Docstrings follow PEP 257, in Google's style: a summary line, then
`Args:`, `Returns:` and `Raises:` sections. ruff's `pydocstyle` checks
them with that convention. A constant is documented by the string after
it, as Sphinx and the documentation tools read it.

#### D13. The codec keeps turborel-protocol's bounds, and refuses what it does

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
carries a `DataError` (22000), parts nested past the bound a
`NotSupportedError` (0A000), and an argument of a request out of its
field's range an `InterfaceError` (Turborel's TB910).

#### D14. Live tests run where TURBOREL_TEST_SERVER names turboreld's command

The live tests, in `tests/server/`, run every request and capability
against a real server, and run only where the environment variable
TURBOREL_TEST_SERVER names the command that runs `turboreld`, as shell
words, so the unit tests stay deterministic and need no server
(R-TEST-5). Their set-up makes its own certificates with `openssl`
(TURBOREL_TEST_OPENSSL, else the one on the path), so no secret is ever
committed, and starts one server for the session, held in memory, on
loopback port 17431 (TURBOREL_TEST_PORT) and on a Unix socket under a
directory of its own, with TLS, its client authority, local trust,
SCRAM without TLS too, no delay after a failed login and few PBKDF2
iterations; it stops the server at the end, by its own process.

CI sets the variable on Linux to run `ghcr.io/turborel/turborel:nightly`
by Docker, on the host's network, with `/tmp` shared (R-TEST-8).
GitHub's macOS and Windows runners have no Docker to run the image, so
there the live tests skip, which `verify.yml` says.

---

## 8. References

- Turborel, `doc/client/05-protocol.md`, *The Native Protocol*,
  version 1: the requirements of the codec and every message.
- Turborel, `doc/client/02-library.md`, *The Client Library*, and
  `doc/client/02-library-connections.md`, *Settings, Pipelines and
  Pools*, and the crates turborel-client and turborel-protocol: the
  features to match, and the reference where the spec is silent or
  differs.
- Turborel, `RULES.md` D89, the JSON value's binary tree, and D184, the
  UUID's tag.
- RFC 1950, *ZLIB Compressed Data Format Specification*; RFC 5802 and
  RFC 7677, SCRAM and SCRAM-SHA-256; RFC 5929 and RFC 9266, the
  `tls-server-end-point` and `tls-exporter` channel bindings.
- The standards of Python and of its database interface, named in
  D2 and D3.
