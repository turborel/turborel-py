"""Every request a client sends, encoded as a frame [PROTOCOL Requests].

Each request is a frozen dataclass whose `encode` gives its frame: the
header, then the body as the request's section lays it out, its tail
holding only the fields that say something, so a request of none is its
first form exactly [PROTOCOL The tail]. Whether a request may be sent,
before Ready or without its capability, is the session's to decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from turborel._codec import tail
from turborel._codec.fields import KEY_BYTES, Writer
from turborel._codec.frames import encode_header
from turborel._codec.values import write_row
from turborel._errors import misuse

if TYPE_CHECKING:
    from collections.abc import Sequence

VERSION: Final = 1
"""The protocol's version, the first field of Hello."""

# The kinds of the requests, as a client sends them [PROTOCOL Requests].
HELLO: Final = ord("H")
ANSWER: Final = ord("A")
QUERY: Final = ord("Q")
PREPARE: Final = ord("P")
EXECUTE: Final = ord("E")
FETCH: Final = ord("F")
CLOSE: Final = ord("C")
DEALLOCATE: Final = ord("D")
LOB: Final = ord("L")
CANCEL: Final = ord("Z")
TERMINATE: Final = ord("X")
DESCRIBE: Final = ord("Y")
PING: Final = ord("G")
RESET: Final = ord("W")
CHANGE_USER: Final = ord("U")
COPY_IN: Final = ord("I")
COPY_DATA: Final = ord("J")
COPY_END: Final = ord("N")

# Lob's ops [PROTOCOL Lob 'L'], the request.
LOB_READ: Final = 0
LOB_CREATE: Final = 1
LOB_APPEND: Final = 2
LOB_FREE: Final = 3
LOB_HOLD: Final = 4

# Describe's `what` [PROTOCOL Describe 'Y'].
DESCRIBE_STATEMENT: Final = 0
DESCRIBE_CURSOR: Final = 1


def _framed(kind: int, w: Writer) -> bytes:
    body = w.data()
    return encode_header(kind, len(body)) + body


@dataclass(frozen=True, slots=True)
class Hello:
    """The first message of a connection that logs in [PROTOCOL Hello 'H']."""

    user: str
    mechanism: str
    initial: bytes = b""
    capabilities: Sequence[str] = ()
    attributes: tail.Attributes = ()
    version: int = VERSION

    def encode(self) -> bytes:
        """Its frame: version, user, mechanism, initial bytes, capabilities, tail 1."""
        w = Writer()
        w.u32(self.version)
        w.string(self.user)
        w.string(self.mechanism)
        w.octets(self.initial)
        w.strings(self.capabilities)
        tail.write_attributes(w, self.attributes)
        return _framed(HELLO, w)


@dataclass(frozen=True, slots=True)
class Answer:
    """The client's answer to a Challenge [PROTOCOL Answer 'A']."""

    answer: bytes

    def encode(self) -> bytes:
        """Its frame: the answer, bytes."""
        w = Writer()
        w.octets(self.answer)
        return _framed(ANSWER, w)


@dataclass(frozen=True, slots=True)
class Query:
    """A direct SQL statement, or several with `multi` [PROTOCOL Query 'Q']."""

    sql: str
    ends: bool = False
    attributes: tail.Attributes = ()
    multi: bool = False

    def encode(self) -> bytes:
        """Its frame: sql, ends flag, tail 1 attributes, 2 multi."""
        w = Writer()
        w.string(self.sql)
        w.flag(self.ends)
        tail.write_attributes(w, self.attributes)
        tail.write_mark(w, tail.MULTI, set_=self.multi)
        return _framed(QUERY, w)


@dataclass(frozen=True, slots=True)
class Prepare:
    """A statement prepared under the client's number [PROTOCOL Prepare 'P']."""

    statement: int
    sql: str

    def encode(self) -> bytes:
        """Its frame: statement, sql."""
        w = Writer()
        w.u32(self.statement)
        w.string(self.sql)
        return _framed(PREPARE, w)


@dataclass(frozen=True, slots=True)
class Execute:
    """A prepared statement executed with its values [PROTOCOL Execute 'E']."""

    statement: int
    values: Sequence[object] = ()
    rows: int = 0
    """The most rows sent now: 0 for all."""
    ends: bool = False
    attributes: tail.Attributes = ()
    cursor: int = 0

    def encode(self) -> bytes:
        """Its frame: statement, values, rows, ends, tail 1 attributes, 3 cursor."""
        w = Writer()
        w.u32(self.statement)
        write_row(w, self.values)
        w.u32(self.rows)
        w.flag(self.ends)
        tail.write_attributes(w, self.attributes)
        tail.write_number(w, tail.CURSOR, self.cursor)
        return _framed(EXECUTE, w)


@dataclass(frozen=True, slots=True)
class Fetch:
    """More rows of an open cursor [PROTOCOL Fetch 'F']."""

    statement: int
    rows: int = 0
    cursor: int = 0

    def encode(self) -> bytes:
        """Its frame: statement, rows, tail 3 cursor."""
        w = Writer()
        w.u32(self.statement)
        w.u32(self.rows)
        tail.write_number(w, tail.CURSOR, self.cursor)
        return _framed(FETCH, w)


@dataclass(frozen=True, slots=True)
class Close:
    """An open cursor closed [PROTOCOL Close 'C']."""

    statement: int
    cursor: int = 0

    def encode(self) -> bytes:
        """Its frame: statement, tail 3 cursor."""
        w = Writer()
        w.u32(self.statement)
        tail.write_number(w, tail.CURSOR, self.cursor)
        return _framed(CLOSE, w)


@dataclass(frozen=True, slots=True)
class Deallocate:
    """A prepared statement destroyed [PROTOCOL Deallocate 'D']."""

    statement: int

    def encode(self) -> bytes:
        """Its frame: statement."""
        w = Writer()
        w.u32(self.statement)
        return _framed(DEALLOCATE, w)


@dataclass(frozen=True, slots=True)
class LobRead:
    """At most `count` octets, or characters, of a large object from `start`."""

    locator: int
    start: int
    count: int
    characters: bool = False

    def encode(self) -> bytes:
        """Its frame [PROTOCOL Lob 'L']: op 0, locator, from, count, characters flag."""
        w = Writer()
        w.u8(LOB_READ)
        w.u32(self.locator)
        w.u64(self.start)
        w.u64(self.count)
        w.flag(self.characters)
        return _framed(LOB, w)


@dataclass(frozen=True, slots=True)
class LobCreate:
    """An empty large object made, character or binary, to append to."""

    binary: bool

    def encode(self) -> bytes:
        """Its frame [PROTOCOL Lob 'L']: op 1, kind."""
        w = Writer()
        w.u8(LOB_CREATE)
        w.u8(1 if self.binary else 0)
        return _framed(LOB, w)


@dataclass(frozen=True, slots=True)
class LobAppend:
    """Octets added to a large object Create made."""

    locator: int
    data: bytes

    def encode(self) -> bytes:
        """Its frame [PROTOCOL Lob 'L']: op 2, locator, bytes."""
        w = Writer()
        w.u8(LOB_APPEND)
        w.u32(self.locator)
        w.octets(self.data)
        return _framed(LOB, w)


@dataclass(frozen=True, slots=True)
class LobFree:
    """A locator ended."""

    locator: int

    def encode(self) -> bytes:
        """Its frame [PROTOCOL Lob 'L']: op 3, locator."""
        return _lob_locator(LOB_FREE, self.locator)


@dataclass(frozen=True, slots=True)
class LobHold:
    """A locator kept valid past its transaction's commit."""

    locator: int

    def encode(self) -> bytes:
        """Its frame [PROTOCOL Lob 'L']: op 4, locator."""
        return _lob_locator(LOB_HOLD, self.locator)


def _lob_locator(op: int, locator: int) -> bytes:
    w = Writer()
    w.u8(op)
    w.u32(locator)
    return _framed(LOB, w)


@dataclass(frozen=True, slots=True)
class Cancel:
    """The only message of a connection that cancels another's statement."""

    key: bytes = field(repr=False)
    """The key Ready gave, a secret never shown (R-SAFE-4)."""

    def encode(self) -> bytes:
        """Its frame [PROTOCOL Cancel 'Z']: the key, 16 bytes.

        Raises:
            InterfaceError: SQLSTATE TB910, of a key not 16 bytes.
        """
        if len(self.key) != KEY_BYTES:
            msg = f"a cancel key is {KEY_BYTES} bytes"
            raise misuse(msg)
        w = Writer()
        w.raw(self.key)
        return _framed(CANCEL, w)


@dataclass(frozen=True, slots=True)
class Terminate:
    """The session ended [PROTOCOL Terminate 'X']."""

    def encode(self) -> bytes:
        """Its frame: a header alone."""
        return _framed(TERMINATE, Writer())


@dataclass(frozen=True, slots=True)
class Describe:
    """A prepared statement described, or, with `cursor`, an open cursor."""

    statement: int
    cursor: int | None = None
    """The cursor described; None to describe the statement."""

    def encode(self) -> bytes:
        """Its frame [PROTOCOL Describe 'Y']: what, statement, cursor.

        A statement's cursor is written 0.
        """
        w = Writer()
        w.u8(DESCRIBE_STATEMENT if self.cursor is None else DESCRIBE_CURSOR)
        w.u32(self.statement)
        w.u32(self.cursor or 0)
        return _framed(DESCRIBE, w)


@dataclass(frozen=True, slots=True)
class Ping:
    """Whether the server and the connection are alive [PROTOCOL Ping 'G']."""

    def encode(self) -> bytes:
        """Its frame: a header alone."""
        return _framed(PING, Writer())


@dataclass(frozen=True, slots=True)
class Reset:
    """The session put back as it was at login [PROTOCOL Reset 'W']."""

    def encode(self) -> bytes:
        """Its frame: a header alone."""
        return _framed(RESET, Writer())


@dataclass(frozen=True, slots=True)
class ChangeUser:
    """The connection authenticated again [PROTOCOL ChangeUser 'U']."""

    user: str
    mechanism: str
    initial: bytes = b""

    def encode(self) -> bytes:
        """Its frame: user, mechanism, initial bytes."""
        w = Writer()
        w.string(self.user)
        w.string(self.mechanism)
        w.octets(self.initial)
        return _framed(CHANGE_USER, w)


@dataclass(frozen=True, slots=True)
class CopyIn:
    """A copy of rows into a table begun [PROTOCOL CopyIn 'I']."""

    table: str
    columns: Sequence[str] = ()
    """The columns the rows give, in order; none for every column."""
    ends: bool = False

    def encode(self) -> bytes:
        """Its frame: table, columns, ends flag."""
        w = Writer()
        w.string(self.table)
        w.strings(self.columns)
        w.flag(self.ends)
        return _framed(COPY_IN, w)


@dataclass(frozen=True, slots=True)
class CopyData:
    """Rows of the copy under way [PROTOCOL CopyData 'J']."""

    rows: Sequence[Sequence[object]]

    def encode(self) -> bytes:
        """Its frame: a list of rows."""
        w = Writer()
        w.u32(len(self.rows))
        for row in self.rows:
            write_row(w, row)
        return _framed(COPY_DATA, w)


@dataclass(frozen=True, slots=True)
class CopyEnd:
    """The copy ended, or abandoned [PROTOCOL CopyEnd 'N']."""

    abandon: bool = False

    def encode(self) -> bytes:
        """Its frame: the abandon flag."""
        w = Writer()
        w.flag(self.abandon)
        return _framed(COPY_END, w)


Request = (
    Hello
    | Answer
    | Query
    | Prepare
    | Execute
    | Fetch
    | Close
    | Deallocate
    | LobRead
    | LobCreate
    | LobAppend
    | LobFree
    | LobHold
    | Cancel
    | Terminate
    | Describe
    | Ping
    | Reset
    | ChangeUser
    | CopyIn
    | CopyData
    | CopyEnd
)
"""Any request a client sends."""
