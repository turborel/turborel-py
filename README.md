<p align="center">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="artwork/turborel-logo-white.svg">
      <img src="artwork/turborel-logo.svg" alt="turborel" width="360">
    </picture>
</p>

> turborel-py is in alpha, meaning, version 0.0.0. Its version is the
> number of the turborel release it is made for, and the alpha is made
> for turborel 0.0.0, which speaks protocol version 1. Anything may
> change from one build to the next, API and behaviour alike. See
> [VERSIONING.md](VERSIONING.md).

turborel-py is the Python driver for
[Turborel](https://github.com/turborel/turborel), a relational database
system. It speaks Turborel's native protocol itself, in pure Python on
the standard library: nothing to compile and no dependency to install.
Its interface is to be DB-API 2.0 (PEP 249), with `?` parameters, and an
asyncio interface beside it, `turborel.aio`. It is built to do all that
Turborel's own client library, turborel-client, does, from TLS and SCRAM
to pipelines, pools, bulk copy and large objects.

The driver is being built in milestones, M0 to M8, and does not connect
to a server yet. [CONFORMANCE.md](CONFORMANCE.md) says what is
implemented, and [TODO.md](TODO.md) what is open.

## What it needs

CPython 3.11 or later, on Linux, macOS or Windows. Each Python release
is supported until its end of life, and 3.11 to 3.15 are tested (RULES.md
D3).

## Installing

No package is published yet; packages go to PyPI once every Turborel
driver is done ([VERSIONING.md](VERSIONING.md#publishing)). Until then,
build from source with [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/turborel/turborel-py
cd turborel-py
uv build                   # the sdist and wheel, in dist/
pip install dist/turborel-0.0.0-py3-none-any.whl
```

## A first query

This is the interface as it will be once the DB-API is built, at
milestone M7; it does not run yet.

```python
import turborel

conn = turborel.connect(
    "turborel://ann@db.example/?tls_mode=verify-full&tls_roots=/etc/turborel/ca.pem"
)
cur = conn.cursor()
cur.execute("SELECT ID, NAME FROM STAFF WHERE ID < ? ORDER BY ID", (3,))
for row in cur.fetchall():
    print(row)
conn.commit()
conn.close()
```

## Documents

- [doc/](doc/README.md): the manual, a User's Guide, an API Reference
  and appendices, published on turborel.com's documentation site.
- [VERSIONING.md](VERSIONING.md): versions, alpha, and publishing.
- [CONFORMANCE.md](CONFORMANCE.md): what is implemented, against the
  protocol and turborel-client.
- [RULES.md](RULES.md): how the driver is designed, written and verified.
- [TODO.md](TODO.md): open work.
- [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md):
  contributing, and reporting an issue or a vulnerability.
- [LICENSE](LICENSE) and [TRADEMARK.md](TRADEMARK.md): the code is
  under the BSD-2-Clause Plus Patent License; the name Turborel and its
  logos are not, and TRADEMARK.md says how they may be used.
