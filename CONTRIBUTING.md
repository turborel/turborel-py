# Contributing to turborel-py

turborel-py carries data between programs and a database people depend
on, and a value sent or read wrongly may be stored wrongly for good. So a
change is judged first on whether it keeps what crosses the connection
correct and the connection secure, and then on what it adds. The process
follows the Linux kernel's, adapted to pull requests and to a driver.

[Before you start](#before-you-start) · [Setting up](#setting-up) ·
[Making a change](#making-a-change) ·
[Changes that touch the protocol](#changes-that-touch-the-protocol) ·
[Commit messages](#commit-messages) · [Pull requests](#pull-requests) ·
[Review](#review) · [Reporting issues](#reporting-issues) ·
[Security](#security) · [License](#license)

---

## Before you start

Read [RULES.md](RULES.md) §3 (code), §4 (tests), §7 (process) and the
decisions for your area. Every rule applies to every change, and
`python -m tools.verify` checks those a tool can.
[CONFORMANCE.md](CONFORMANCE.md) says what is implemented, against the
protocol and turborel-client, and [TODO.md](TODO.md) lists open work.

Open an issue first for anything larger than a fix. That covers new
features, changes to a decision in RULES.md, and new dependencies
(R-DEP-1). Agreeing on the design first saves everyone a rewrite.

The protocol is turborel's doc/client/05-protocol.md, and the reference
is turborel-client; where the page and turborel's code differ, the code
is right. Read the section before writing code, and cite it by its
heading, as in `[PROTOCOL Frames]`. Never cite from memory.

## Setting up

The project is managed by [uv](https://docs.astral.sh/uv/), which
installs the Python versions and the tools it needs on its own.

```
uv sync --locked                        # the environment, with the tools uv.lock pins
git config core.hooksPath .githooks     # run verify before each commit (once per clone)
uv run python -m tools.verify           # every check a change must pass
uv run python -m tools.verify --coverage
                                        # and the coverage floor, as CI runs it
uv run --python 3.15 python -m tools.verify
                                        # the same, on another supported Python
```

CI runs `verify` on Linux, macOS and Windows, on each supported Python,
and coverage on Linux (RULES.md D11). A change that passes on one
platform and fails on another isn't done.

## Making a change

Keep one logical change per commit, and make each commit pass
`python -m tools.verify` on its own, because anyone bisecting may land on
it. Move code in one commit and change it in another. Don't mix a
reformat or rename with a change of behaviour.

Tests come with the change (R-TEST-1). Cover normal cases, boundaries,
and robustness cases with the exact SQLCODE and SQLSTATE expected
(R-TEST-2). Each test's docstring begins `Verifies:` and a tag
(R-TRACE-1). A fixed defect gets a test that fails without the fix
(R-TEST-6).

Documents change in the same commit. Update CONFORMANCE.md for a row
implemented (R-TRACE-3), RULES.md for a decision made or changed, and
TODO.md for open work done or found. Code never cites TODO.md.

The manual changes in the same commit too (R-DOC-6). A change to what a
program sees updates each page of [doc/](doc/README.md) that states it,
with its examples run again. The manual is laid out as turborel's, since
turborel.com's documentation site reads it from every repository: a
chapter begins with its `# Title` and a line `[Contents](README.md)`,
links between pages are relative `.md` links, and each volume's
README.md lists its chapters. Its pages link only to pages in `doc/`, or
by full URL elsewhere.

Some rules deserve a reminder.

- Every failure is one of the driver's exceptions, carrying its SQLCODE
  and SQLSTATE (R-ERR-1, R-ERR-2), and no dependency is added without a
  decision in RULES.md (R-DEP-1).
- Performance claims cite measurements, with the numbers and their
  costs in memory and latency.
- The coverage floor only rises (R-COV-2).

## Changes that touch the protocol

These need more than passing tests. Say in the commit message what was
done for each that applies.

A codec change is tested byte by byte against the spec's layout, and
read back as written, at each field's bounds. Bytes a server sends are
read with every length and count checked before anything is held for it
(R-ERR-4); a malformed frame fails the connection with SQLCODE -919 and
SQLSTATE 08006, never with another exception.

A change to authentication or TLS says what an attacker in the middle
of the connection sees and can do, and shows that a secret is never
sent where it was refused (R-SAFE-2).

A change that departs from turborel-client, in a value's mapping, an
error's SQLSTATE or a default, is refused unless a decision in RULES.md
says why.

## Commit messages

The form is Linux's.

```
area: summary in the imperative, at most 75 characters

The problem: what goes wrong, or is missing, and who it affects. A
wrong value, a crash or a refusal is said first, with the call that
shows it.

Why this change, and how it solves the problem. Mention the choices
made and the alternatives rejected, the rules and sections applied
(RULES.md D7, R-ERR-4, [PROTOCOL Frames]), and what was measured,
with numbers.

Fixes: 54a4f0239f2e ("codec: read a row's values in order")
Closes: <link to the issue>
Reported-by: A Reporter <reporter@example.org>
```

The subject is `area: summary`, at most 75 characters, in the imperative
("refuse a frame...", not "refused"), with no full stop. It says what
changes, isn't a file name, and isn't reused within a series.

The body is wrapped at 75 columns and written for someone reading
`git log` years later with no context. Say what the change does in plain
prose, since the diff shows how. Don't write "as discussed" or "v2".

Pick the area where most of the change is.

| Area | Covers |
|---|---|
| `codec` | `_codec/`: frames, fields, the tail, types and values, JSON, compression |
| `transport` | `_transport/`: TCP, Unix socket, named pipe, timeouts |
| `auth` | `_auth/`: mechanisms, SCRAM, the key cache |
| `tls` | `_tls/` |
| `session` | `_session/`: Hello to Ready, status, notices, cancel, terminate |
| `statements` | `_statements/`: queries, prepared statements, cursors |
| `lobs` | `_lobs/` |
| `copy` | `_copy/`: copy, import and export |
| `settings` | `_settings/`: the URI, variables, files, hosts and roles |
| `pipeline` | `_pipeline/` |
| `pool` | `_pool/` |
| `api` | the public interface: `turborel`, `turborel.aio`, the exceptions |
| `doc` | `doc/`, README.md, RULES.md, CONFORMANCE.md, TODO.md, VERSIONING.md, AGENTS.md, CLAUDE.md, this file |
| `ci` | `.github/` |
| `build` | `pyproject.toml`, `uv.lock`, `tools/`, `.githooks/`, `.gitattributes`, `.gitignore` |

A test goes with the code it tests, in that code's area.

Trailers go at the end, one per line, never wrapped.

| Trailer | Meaning |
|---|---|
| `Fixes: <12+ hex digits> ("<subject>")` | the commit that introduced the defect fixed |
| `Closes: <link>` | the issue this commit resolves |
| `Link: <link>` | background, such as a discussion or an issue fixed only in part |
| `Reported-by:` | who reported the defect fixed, with `Closes:` |
| `Suggested-by:` | who suggested the idea |
| `Co-authored-by:` | a co-author, as GitHub credits one |
| `Reviewed-by:` | a reviewer who checked the change and is satisfied with it |
| `Acked-by:` | a maintainer of the area who approves it without a full review |
| `Tested-by:` | someone who tested it, saying where if that matters |

`Reported-by:` and `Suggested-by:` may be added without asking. The
others name someone who said so on the record. No trailer names an AI
or a coding agent: no `Co-Authored-By` for one, no "Generated with", and
no `Signed-off-by`. `git log -1 --abbrev=12 --pretty='Fixes: %h ("%s")'
<commit>` writes the `Fixes:` line.

Stage a commit by an explicit list of its paths,
`git add -- <path> ...`, never `git add -A` or `git add .` on the whole
tree, so nothing comes along unasked.

## Pull requests

A pull request is a patch series, and its description is the cover
letter. The template asks for what and why, the series commit by commit,
testing, compatibility and performance. Each commit message still stands
alone.

Base it on `main` and keep it rebased, without merging `main` into it.
When revising, rewrite the commits so the series is again what should be
merged, with no "fix review comments" commits. Force-push, and say in a
comment what changed since the last version.

Trailers given in review go into the commits they cover. Drop them from
a commit that later changes substantially, and say so.

Keep a series to about 15 commits. Split a larger one into series that
each stand alone.

## Review

Reviewers check each commit against RULES.md §7's checklist, and that
the manual is updated (R-DOC-6). For
[changes that touch the protocol](#changes-that-touch-the-protocol),
they also check the byte-level, security and parity checks were done.
Review comments are about the change, never the person. A reviewer who
is satisfied gives `Reviewed-by:`.

## Reporting issues

Use the issue forms, **Bug**, **Conformance**, **Performance** or
**Feature**. Try the latest `main` first, and add to an existing issue
that matches rather than opening another.

Reproduce with the smallest program that shows it, with the statements,
the schema and the data it needs. A problem of the server itself, which
turborel-client shows too, goes to
[turborel](https://github.com/turborel/turborel/issues).

State the impact first. Put it in the title's first word when it is
severe.

| Tag | Meaning |
|---|---|
| `[DATA LOSS]` | data sent or stored wrongly through the driver, or lost |
| `[WRONG RESULT]` | a value or row read wrongly |
| `[CRASH]` | an exception that is not the driver's, a hang, or the interpreter brought down |
| `[REGRESSION]` | worked in an earlier commit (give the last good commit and, if you can, the first bad one) |

Give the commit (`git rev-parse --short=12 HEAD`), the Python version
(`python -VV`), the platform and architecture, the server's version, and
the connection's settings, with any password left out.

## Security

Don't open a public issue for a vulnerability. Report it privately, as
[SECURITY.md](SECURITY.md) says.

## License

turborel-py is under the BSD-2-Clause Plus Patent License in
[LICENSE](LICENSE), and a contribution is made under that license.
Contributors keep their copyright and own their changes. Whoever
submits a change answers for all of it, however it was written.
