"""Every reply a server sends, decoded from a frame's body [PROTOCOL Replies].

`decode` reads a reply of a kind, read in the direction it travels, so
`C` from the server is Challenge. A kind of no reply, a body cut short,
a tail out of order, or bytes left after the last field fail the
connection, SQLCODE -919 and SQLSTATE 08006 [PROTOCOL Frames].
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final

from turborel._codec import tail
from turborel._codec.called import Called, read_prepared_tail
from turborel._codec.composites import (
    Column,
    Parameter,
    read_column,
    read_columns,
    read_parameter,
)
from turborel._codec.debug import (
    DEBUG,
    EVENT,
    Debugged,
    Event,
    read_debugged,
    read_event,
)
from turborel._codec.failures import Failure, Notice, read_failure, read_notice
from turborel._codec.fields import Reader
from turborel._codec.values import read_row
from turborel._errors import OperationalError, value_failure

if TYPE_CHECKING:
    from collections.abc import Callable

# The kinds of the replies, as a server sends them [PROTOCOL Replies].
CHALLENGE: Final = ord("C")
READY: Final = ord("R")
PREPARED: Final = ord("P")
DESCRIPTION: Final = ord("D")
ROWS: Final = ord("B")
SUSPENDED: Final = ord("S")
COMPLETE: Final = ord("K")
ERROR: Final = ord("E")
LOB: Final = ord("L")
NOTICE: Final = ord("N")
STATUS: Final = ord("T")
PONG: Final = ord("G")
DEBUGGED: Final = DEBUG
"""Debugged 'V', with `debugger`: what a Debug request gave back."""

# What a Lob reply holds [PROTOCOL Lob 'L'], the reply.
LOB_DATA: Final = 0
LOB_LOCATOR: Final = 1

_COMPLETE_TAIL: Final = frozenset(
    {tail.POSITION, tail.MORE, tail.ROWS, tail.GENERATED, tail.CONDITIONS, tail.TIME}
)


@dataclass(frozen=True, slots=True)
class Challenge:
    """The next step of an authentication exchange [PROTOCOL Challenge 'C']."""

    data: bytes


@dataclass(frozen=True, slots=True)
class Ready:
    """The client authenticated [PROTOCOL Ready 'R']."""

    authorization: str
    key: bytes = field(repr=False)
    """The key that cancels the session's statements: the client's secret."""
    capabilities: tuple[str, ...]
    server: str


@dataclass(frozen=True, slots=True)
class Prepared:
    """A statement prepared or described [PROTOCOL Prepared 'P']."""

    statement: int
    parameters: tuple[Parameter, ...]
    """In the order of their `?` marks."""
    columns: tuple[Column, ...]
    """None of a statement not a query."""
    called: Called | None = None
    """With `parameter-modes`, of a CALL: its procedure and each `?`'s mode."""


@dataclass(frozen=True, slots=True)
class Description:
    """The columns of the rows that follow [PROTOCOL Description 'D']."""

    columns: tuple[Column, ...]


@dataclass(frozen=True, slots=True)
class Rows:
    """A batch of rows [PROTOCOL Rows 'B']."""

    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class Suspended:
    """The rows asked for sent; the cursor has more [PROTOCOL Suspended 'S']."""


@dataclass(frozen=True, slots=True)
class Timing:
    """The server's time for a statement, in microseconds (tail 18)."""

    total: int
    queued: int
    locks: int


@dataclass(frozen=True, slots=True)
class Complete:
    """A statement's completion [PROTOCOL Complete 'K']."""

    sqlcode: int
    sqlstate: str
    active: bool
    position: int | None = None
    """Tag 4: the log position of the commit the statement made."""
    more: bool = False
    """Tag 5: another statement's replies follow."""
    rows: int | None = None
    """Tag 6: the rows the statement counted."""
    generated: tuple[str, ...] = ()
    """Tag 16: each identity value an INSERT generated, as SQL writes it."""
    conditions: tuple[Failure, ...] = ()
    """Tag 17: each condition the statement raised."""
    time: Timing | None = None
    """Tag 18: the server's time for the statement."""


@dataclass(frozen=True, slots=True)
class Error:
    """A statement's failure, or the connection's [PROTOCOL Error 'E']."""

    failure: Failure


@dataclass(frozen=True, slots=True)
class LobData:
    """The data a Lob read asked for [PROTOCOL Lob 'L']."""

    data: bytes


@dataclass(frozen=True, slots=True)
class LobCreated:
    """The locator of the large object a Lob create made [PROTOCOL Lob 'L']."""

    locator: int


@dataclass(frozen=True, slots=True)
class Status:
    """A setting of the session [PROTOCOL Status 'T']: empty for a null."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class Pong:
    """The answer to Ping [PROTOCOL Pong 'G']."""


Reply = (
    Challenge
    | Ready
    | Prepared
    | Description
    | Rows
    | Suspended
    | Complete
    | Error
    | LobData
    | LobCreated
    | Notice
    | Status
    | Pong
    | Debugged
    | Event
)
"""Any reply a server sends."""


def decode(kind: int, body: bytes) -> Reply:
    """The reply of kind `kind` whose body is `body`, all of it read.

    Raises:
        OperationalError: SQLSTATE TB916, of a value the client cannot take,
            its frame read whole; SQLSTATE 08006, of a kind of no reply or a body
            that cannot be read.
    """
    r = Reader(body, "reply")
    read = _READERS.get(kind)
    if read is None:
        msg = f"no reply is of kind {kind}"
        raise r.malformed(msg)
    reply = read(r)
    r.finish()
    return reply


def _ready(r: Reader) -> Ready:
    authorization, key = r.string(), r.key()
    return Ready(authorization, key, tuple(r.strings()), r.string())


def _prepared(r: Reader) -> Prepared:
    statement = r.u32()
    parameters = tuple(r.items(read_parameter))
    columns, called = read_prepared_tail(r, tuple(r.items(read_column)))
    return Prepared(statement, parameters, columns, called)


def _condition(r: Reader) -> Failure:
    """A condition of Complete's tag 17: one that cannot be read is a value refused."""
    inner = Reader(r.octets(), "condition")
    try:
        condition = read_failure(inner)
        inner.finish()
    except OperationalError as e:
        raise value_failure(e.message) from e
    return condition


def _complete(r: Reader) -> Complete:
    complete = Complete(r.i32(), r.string(), r.flag())
    reading = tail.Tail(_COMPLETE_TAIL)
    while (tag := reading.next(r)) is not None:
        if tag == tail.POSITION:
            complete = replace(complete, position=r.u64())
        elif tag == tail.MORE:
            complete = replace(complete, more=True)
        elif tag == tail.ROWS:
            complete = replace(complete, rows=r.u64())
        elif tag == tail.GENERATED:
            complete = replace(complete, generated=tuple(r.strings()))
        elif tag == tail.CONDITIONS:
            complete = replace(complete, conditions=tuple(r.items(_condition)))
        else:
            complete = replace(complete, time=Timing(r.u64(), r.u64(), r.u64()))
    return complete


def _lob(r: Reader) -> LobData | LobCreated:
    what = r.u8()
    if what == LOB_DATA:
        return LobData(r.octets())
    if what == LOB_LOCATOR:
        return LobCreated(r.u32())
    msg = f"no Lob reply is of kind {what}"
    raise r.malformed(msg)


_READERS: Final[dict[int, Callable[[Reader], Reply]]] = {
    CHALLENGE: lambda r: Challenge(r.octets()),
    READY: _ready,
    PREPARED: _prepared,
    DESCRIPTION: lambda r: Description(read_columns(r)),
    ROWS: lambda r: Rows(tuple(r.items(read_row))),
    SUSPENDED: lambda _: Suspended(),
    COMPLETE: _complete,
    ERROR: lambda r: Error(read_failure(r)),
    LOB: _lob,
    NOTICE: read_notice,
    STATUS: lambda r: Status(r.string(), r.string()),
    PONG: lambda _: Pong(),
    DEBUGGED: read_debugged,
    EVENT: read_event,
}


def completed_head(kind: int, body: bytes) -> Complete | None:
    """The head of a frame of kind `kind`, if a Complete whose head reads.

    Its SQLCODE, SQLSTATE and whether a transaction is active, and of its
    tail the commit's position and whether more replies follow, which
    come before any field a client may fail to take [PROTOCOL Values and
    fields].
    """
    if kind != COMPLETE:
        return None
    r = Reader(body, "reply")
    try:
        head = Complete(r.i32(), r.string(), r.flag())
        reading = tail.Tail(_COMPLETE_TAIL)
        while (tag := reading.next(r)) is not None:
            if tag == tail.POSITION:
                head = replace(head, position=r.u64())
            elif tag == tail.MORE:
                head = replace(head, more=True)
            else:
                break
    except OperationalError:
        return None
    return head


def ends_request(kind: int, body: bytes) -> bool:
    """Whether a reply of kind `kind`, decoded or not, is its request's last.

    A Description, Rows, a Notice, a Status or an Event, sent unasked,
    has more after it; a
    Complete has if its tail says more (tag 5); any other reply ends its
    request's.
    """
    if kind in (DESCRIPTION, ROWS, NOTICE, STATUS, EVENT):
        return False
    if kind == COMPLETE:
        head = completed_head(kind, body)
        return head is None or not head.more
    return True
