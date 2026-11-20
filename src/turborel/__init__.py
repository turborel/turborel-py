"""turborel: the Python driver for the turborel relational database system.

The driver speaks turborel's native protocol, version 1, itself, in pure
Python on the standard library, with no native code to build (RULES.md
D1). Its interface is DB-API 2.0 (PEP 249), with the `qmark` parameter
style, and an asyncio interface beside it, `turborel.aio` (RULES.md D2);
under both, the low-level client, `turborel.client`, has every feature
of turborel-client.

This is version 0.0.0, an alpha (VERSIONING.md). The package holds
`connect`, PEP 249's globals, the connection and cursor, the type
objects and constructors, the exceptions, and the classes of the values
Python has no type of its own for (doc/appendix/a-types.md).
"""

from __future__ import annotations

from typing import Final

from turborel._api.dbapi import Connection, Cursor, connect
from turborel._api.types import (
    BINARY,
    DATETIME,
    NUMBER,
    ROWID,
    STRING,
    Binary,
    Date,
    DateFromTicks,
    Time,
    TimeFromTicks,
    Timestamp,
    TimestampFromTicks,
)
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

threadsafety: Final = 1
"""Threads may share the module, not a connection; a pool shares them (PEP 249)."""

__all__ = [
    "BINARY",
    "DATETIME",
    "NUMBER",
    "ROWID",
    "STRING",
    "Binary",
    "Connection",
    "Cursor",
    "DataError",
    "DatabaseError",
    "Date",
    "DateFromTicks",
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
    "Time",
    "TimeFromTicks",
    "Timestamp",
    "TimestampFromTicks",
    "Warning",
    "Xml",
    "__version__",
    "apilevel",
    "connect",
    "paramstyle",
    "threadsafety",
]
