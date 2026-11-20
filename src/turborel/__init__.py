"""turborel: the Python driver for the turborel relational database system.

The driver speaks turborel's native protocol, version 1, itself, in pure
Python on the standard library, with no native code to build (RULES.md
D1). Its interface is to be DB-API 2.0 (PEP 249), with the `qmark`
parameter style, and an asyncio interface beside it, `turborel.aio`
(RULES.md D2).

This is version 0.0.0, an alpha, and it does not connect to a server
yet. The package holds PEP 249's exceptions, the two module globals
already settled, `apilevel` and `paramstyle`, and the classes of the
values Python has no type of its own for (doc/appendix/a-types.md).
`connect`, `threadsafety`, the connection and cursor objects and
`turborel.aio` come with the interface itself. CONFORMANCE.md, in the
driver's repository, says what is implemented.
"""

from __future__ import annotations

from typing import Final

from turborel._codec.datatypes import IntervalField, Qualifier
from turborel._errors import (
    DatabaseError,
    DataError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
    Warning,  # noqa: A004  # PEP 249 names it.
)
from turborel._values import (
    DecFloat,
    Interval,
    Json,
    LargeObject,
    LobLocator,
    Multiset,
    PluginValue,
    Reference,
    Structured,
    Xml,
)

__version__: Final = "0.0.0"
"""The driver's version: 0.0.0 while it is in alpha (VERSIONING.md)."""

apilevel: Final = "2.0"
"""The DB-API level the driver follows, PEP 249's 2.0 (RULES.md D2)."""

paramstyle: Final = "qmark"
"""Parameters are marked `?`, as SQL's dynamic parameters are (RULES.md D2)."""

__all__ = [
    "DataError",
    "DatabaseError",
    "DecFloat",
    "Error",
    "IntegrityError",
    "InterfaceError",
    "InternalError",
    "Interval",
    "IntervalField",
    "Json",
    "LargeObject",
    "LobLocator",
    "Multiset",
    "NotSupportedError",
    "OperationalError",
    "PluginValue",
    "ProgrammingError",
    "Qualifier",
    "Reference",
    "Structured",
    "Warning",
    "Xml",
    "__version__",
    "apilevel",
    "paramstyle",
]
