# The turborel-py Documentation Set

turborel-py is the Python driver for Turborel, a relational database
system. It connects a Python program to a Turborel server, `turboreld`,
over the server's native protocol, version 1, spoken in pure Python on
the standard library. Its interface is to be DB-API 2.0 (PEP 249), with
`?` parameters, and an asyncio interface beside it, and it is built to
do all that Turborel's own client library does. This set of manuals
describes it for those who write programs with it.

turborel-py is in alpha: what these manuals describe may change in any
release until 1.0.0 ([Versions](appendix/d-versions.md)). The driver
does not connect to a server yet, and its chapters are written as the
parts they describe are built. Each change updates the pages it touches,
so the manuals describe the release they come with.

## The volumes

| Volume | For | |
|---|---|---|
| [I. User's Guide](user/README.md) | Anyone who writes a Python program against Turborel | Installing, connecting, statements, transactions, large objects, copying, pipelines and pools, settings and errors, chapter by chapter |
| [II. API Reference](client/README.md) | The same, looking something up | The standard API and the low-level client, a page for each main interface or module |
| [Appendices](appendix/README.md) | Everyone | Types, errors, settings and versions |

Read the User's Guide from the start to learn the driver; turn to the
API Reference and the appendices to look a thing up.

## Conventions

**Examples** of Python and SQL are set in a fixed-width font. SQL key
words are in upper case, names in upper case unless delimited, as the
standard folds them:

```python
cur.execute("SELECT NAME, SALARY FROM STAFF WHERE SALARY > ?", (50000,))
```

**Results** of examples follow them, as the program prints them.

**Citations** name the section of Turborel's documents a behaviour comes
from: [PROTOCOL Frames] is the section "Frames" of
[The Native Protocol](https://github.com/turborel/turborel/blob/main/doc/client/05-protocol.md);
[CLIENT Pipelines] is the section "Pipelines" of Turborel's client
library chapters,
[The Client Library](https://github.com/turborel/turborel/blob/main/doc/client/02-library.md)
and
[Settings, Pipelines and Pools](https://github.com/turborel/turborel/blob/main/doc/client/02-library-connections.md).

**Errors** are given by SQLSTATE, the code the standard defines, and
SQLCODE, the older number; [Appendix B](appendix/b-errors.md) maps them
to the driver's exceptions.
