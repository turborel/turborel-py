<p align="center">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="artwork/turborel-logo-white.svg">
      <img src="artwork/turborel-logo.svg" alt="turborel" width="360">
    </picture>
</p>

> turborel-py is in alpha, meaning, version 0.0.0. Its version is the
> number of the Turborel release it is made for, and the alpha is made
> for Turborel 0.0.0, which speaks protocol version 1. Anything may
> change from one build to the next, API and behaviour alike. See
> [VERSIONING.md](VERSIONING.md). The latest Turborel alpha is built for
> Linux, macOS and Windows as the pre-release
> [nightly](https://github.com/turborel/turborel/releases/tag/nightly),
> and as the image `ghcr.io/turborel/turborel:nightly`.

turborel-py is the Python driver for
[Turborel](https://github.com/turborel/turborel), a relational database
system. It connects a Python program to a Turborel server,
`turboreld`, over Turborel's [native
protocol](https://github.com/turborel/turborel/blob/main/doc/client/05-protocol.md),
version 1, which it speaks itself, in pure Python on the standard library, with nothing to compile.

Its standard interface is DB-API 2.0 (PEP 249), with `?` parameters, and an asyncio interface beside it, `turborel.aio`. Beneath it is a low-level
client built to do all that Turborel's own client library,
turborel-client, does: TCP, Unix sockets and Windows named pipes, TLS,
SCRAM-SHA-256 and SCRAM-SHA-256-PLUS, prepared statements and cursors,
large objects, bulk copy, import and export, settings from a URI, the
environment and service and password files, several servers, pipelines
and pools.

The driver is built in milestones, M0 to M8, and does not connect to a
server yet. [CONFORMANCE.md](CONFORMANCE.md) shows what is done, row by
row, and [TODO.md](TODO.md) what is open.

## Requirements

- CPython 3.11 or later, on Linux, macOS or Windows ([RULES.md](RULES.md) D3).
- No package beyond the standard library; 3.11 to 3.15 are tested.
- A Turborel server of the same release, which speaks protocol version 1
  ([running the server](https://github.com/turborel/turborel/blob/main/doc/operator/02-turboreld.md)).

## Installing

No package is published yet. The driver's package, `turborel`, goes to
PyPI only once every Turborel driver is done, with the others
([VERSIONING.md](VERSIONING.md#publishing)). Until then, build the
driver from source:

```
git clone https://github.com/turborel/turborel-py
cd turborel-py
uv build                   # the sdist and the wheel, in dist/
pip install dist/turborel-0.0.0-py3-none-any.whl
```

## A first query

This is what the standard API will be once milestone M7 builds it and
M8's audit checks it. None of it runs yet, and its names may change
until then.

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

## The manual

[doc/](doc/README.md) is the manual: a User's Guide, an API Reference
and Appendices, published at
https://turborel.com/docs/drivers/python/. Each
chapter is written as the milestone that fills it lands. The SQL a
program sends, and the server, are described in Turborel's own manual,
[Turborel Documentation](https://github.com/turborel/turborel/blob/main/doc/README.md).
[VERSIONING.md](VERSIONING.md) tells how the driver's releases are
numbered and published.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before making a change: how a
change is made, its commit message, pull requests and issues. Every
change passes `uv run python -m tools.verify`. [RULES.md](RULES.md) says how the
driver is designed, written and verified,
[CONFORMANCE.md](CONFORMANCE.md) is the parity matrix every Turborel
driver keeps, and [TODO.md](TODO.md) lists open work.

## Security

Report a vulnerability privately, never in a public issue, as
[SECURITY.md](SECURITY.md) says.

## License and trademark

The code is under the BSD-2-Clause Plus Patent License, in
[LICENSE](LICENSE). The name Turborel and its logos are not:
[TRADEMARK.md](TRADEMARK.md) says how they may be used.
