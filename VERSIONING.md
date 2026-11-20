# Versioning

How turborel-py's releases are numbered, which protocol each speaks, and
how a release is published.

[Release numbers](#release-numbers) · [Alpha](#alpha) ·
[The protocol](#the-protocol) · [Where the version is](#where-the-version-is) ·
[Publishing](#publishing)

---

## Release numbers

The driver has no version scheme of its own (RULES.md D9). Its version is
the number of the turborel release it is made for, the same number as the
server's: a turborel release and each driver's release for it share it,
**MAJOR.MINOR.PATCH**, as turborel's
[VERSIONING.md](https://github.com/turborel/turborel/blob/main/VERSIONING.md)
numbers them. What a release may change follows from its number there,
for the driver as for the server.

A driver of a release works with a server of the same release. A fix of
the driver alone, between turborel's releases, waits for the next
release's number.

## Alpha

turborel is in alpha, version **0.0.0**, until its first release, and so
is turborel-py. While the version is 0.y.z nothing is promised: the
driver's API, its behaviour and the protocol it speaks may change in any
build.

## The protocol

The alpha speaks the native protocol's version 1, the only version,
which grows by capabilities, never by a new version
(turborel's doc/client/05-protocol.md). The driver sends version 1 in its
Hello, and asks for the capabilities it implements. A server that does
not speak version 1 refuses the connection (SQLSTATE 08004).

| Driver | turborel | Protocol |
|---|---|---|
| 0.0.0 | 0.0.0 (alpha) | 1 |

## Where the version is

- `pyproject.toml`'s `version`, the package's metadata on PyPI.
- `turborel.__version__`, the same number; a test holds the two to each
  other.

## Publishing

Nothing is published to [PyPI](https://pypi.org/project/turborel/) until
every turborel driver is done, and then the owner publishes them
together. Until then, build from source ([README.md](README.md)).

A release is published by the owner alone, from a pushed commit that has
passed `python -m tools.verify --coverage` in CI:

1. Set the release's number in `pyproject.toml` and
   `src/turborel/__init__.py`, in a commit of its own.
2. Run the workflow **release** by hand, on that commit. It builds the
   sdist and the wheel, checks their metadata, installs the wheel in a
   clean environment and imports it, and keeps them as the run's
   artifacts.
3. The publish job is disabled until the owner enables it, by trusted
   publishing from the workflow to PyPI, with no token kept anywhere.
   Every package carries `LICENSE`.

A version published to PyPI can be yanked, so no new install takes it,
but never published again with other contents. A fix is a new release.
