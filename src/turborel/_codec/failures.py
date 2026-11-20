"""Failures and notices, as Error, Notice and Complete carry them.

[PROTOCOL Composite fields] [PROTOCOL Errors and notices]

    failure      sqlcode i32 as u32; sqlstate, string of 5; message, string;
                 cited flag; the rule, string, if cited;
                 placed flag; the position, u64, if placed;
                 active flag; tail 7 to 15
    notice       sqlstate, string of 5; message, string; tail 7 to 15

The tail says more with `diagnostics` granted: severity, detail, hint,
context, schema, table, column, data type and constraint.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Final

from turborel._codec import tail

if TYPE_CHECKING:
    from turborel._codec.fields import Reader

# Severities [PROTOCOL Errors and notices].
ERROR: Final = "ERROR"
"""A statement's failure: the session goes on."""
FATAL: Final = "FATAL"
"""A failure that ends the connection."""
WARNING: Final = "WARNING"
"""A completion condition of class 01, or a SIGNAL of class 01 or 02 unhandled."""
NOTICE: Final = "NOTICE"
"""A notice of the server's own."""

# The SQLSTATEs the server defines of its own [PROTOCOL Errors and notices].
RESET_ROLLED_BACK: Final = "01T01"
"""Reset or ChangeUser rolled back the transaction that was active."""
REPLICA_BEHIND: Final = "TBR01"
"""The replica had not applied REPLICATION.READ_AFTER's position in time."""


@dataclass(frozen=True, slots=True)
class Diagnostics:
    """What a failure or a notice says beyond its SQLSTATE and message."""

    severity: str | None = None
    detail: str | None = None
    hint: str | None = None
    context: str | None = None
    schema: str | None = None
    table: str | None = None
    column: str | None = None
    data_type: str | None = None
    constraint: str | None = None


@dataclass(frozen=True, slots=True)
class Failure:
    """A failure as the server sends it: all its error says."""

    sqlcode: int
    sqlstate: str
    message: str
    rule: str | None
    """The rule of a standard it cites, if it cites one."""
    position: int | None
    """Where in the statement, in characters, if known."""
    active: bool
    """Whether the session's transaction is active after it."""
    diagnostics: Diagnostics | None = field(default=None)
    """Its tail, with `diagnostics` granted."""


@dataclass(frozen=True, slots=True)
class Notice:
    """A condition a statement raised, or a notice of the server's own."""

    sqlstate: str
    message: str
    diagnostics: Diagnostics


_FIELD_NAMES: Final = tuple(f.name for f in fields(Diagnostics))


def read_diagnostics(r: Reader) -> Diagnostics | None:
    """A tail of diagnostics alone, tags 7 to 15: None if it is empty."""
    reading = tail.Tail(tail.DIAGNOSTICS)
    found: dict[str, str] = {}
    while (tag := reading.next(r)) is not None:
        found[_FIELD_NAMES[tag - tail.SEVERITY]] = r.string()
    return Diagnostics(**found) if found else None


def read_failure(r: Reader) -> Failure:
    """A failure, its tail to the end of the body."""
    sqlcode, sqlstate, message = r.i32(), r.string(), r.string()
    rule = r.string() if r.flag() else None
    position = r.u64() if r.flag() else None
    active = r.flag()
    return Failure(
        sqlcode, sqlstate, message, rule, position, active, read_diagnostics(r)
    )


def read_notice(r: Reader) -> Notice:
    """A Notice's body."""
    sqlstate, message = r.string(), r.string()
    return Notice(sqlstate, message, read_diagnostics(r) or Diagnostics())
