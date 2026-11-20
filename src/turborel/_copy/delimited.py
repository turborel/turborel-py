"""Delimited text as a source of rows: CSV and tab-separated [CLIENT Importing].

CSV as RFC 4180 §2 defines it, and tab-separated text, each a record a
line, fields split at a delimiter, read a line at a time, a record at
most `max_record` bytes, so a file of any size is read in bounded
memory, and a quote left open is refused at the bound rather than read
to the end of the file.

CSV: a record ends at a line break, CR LF or LF alone, the last one's
optional; a header row may come first; a field may be enclosed in
double quotes, and must be to hold the delimiter, a quote or a line
break, a quote in it written twice. A quote in a field not enclosed, or
anything but the delimiter after a closing quote, is refused.
Tab-separated text has no quoting: a field holds no tab and no line
break.

A field written as the dialect's text for null, not enclosed in quotes,
is null: by default an empty one, so `,,` is a null, and `,"",` the
empty string. Text is UTF-8; a byte order mark beginning the input is
passed over.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Final

from turborel._copy.sources import Heading, Position, Record, SourceError
from turborel._errors import misuse

if TYPE_CHECKING:
    from typing import BinaryIO

DEFAULT_MAX_RECORD: Final = 16 * 1024 * 1024
"""The longest record read by default, in bytes: the protocol's longest
body, as a longer record could not be sent."""

_COMMA: Final = ord(",")
_TAB: Final = ord("\t")
_QUOTE: Final = ord('"')
_LF: Final = ord("\n")
_CR: Final = ord("\r")
_BOM: Final = b"\xef\xbb\xbf"
_UNCLOSED: Final = "[RFC 4180 §2 rule 5] a quoted field is not closed"


@dataclass(frozen=True, slots=True)
class Dialect:
    """How delimited text is written: its delimiter, quoting, header and null."""

    delimiter: int = _COMMA
    quoted: bool = True
    """Whether fields may be enclosed in quotes, as CSV's are."""
    header: bool = False
    """Whether the first record names the fields."""
    null: str = ""
    """What a field not enclosed in quotes is written as to be null."""
    max_record: int = DEFAULT_MAX_RECORD
    """The longest record, in bytes, its line break counted."""

    @classmethod
    def csv(cls) -> Dialect:
        """CSV: fields split at commas, enclosed in quotes as they need; no header."""
        return cls()

    @classmethod
    def tsv(cls) -> Dialect:
        """Tab-separated text: fields split at tabs, never quoted; no header."""
        return cls(delimiter=_TAB, quoted=False)

    def with_delimiter(self, delimiter: str) -> Dialect:
        """The dialect, its fields split at `delimiter`.

        Raises:
            InterfaceError: SQLSTATE TB910, if `delimiter` is not one ASCII
                character other than a quote, CR or LF.
        """
        if (
            len(delimiter) != 1
            or not delimiter.isascii()
            or ord(delimiter) in (_QUOTE, _CR, _LF)
        ):
            msg = (
                "a delimiter is one ASCII character, not a quote or a line break:"
                f" {delimiter!r}"
            )
            raise misuse(msg)
        return dataclasses.replace(self, delimiter=ord(delimiter))

    def with_header(self) -> Dialect:
        """The dialect, its first record naming the fields."""
        return dataclasses.replace(self, header=True)

    def with_null(self, null: str) -> Dialect:
        """The dialect, a field written as `null`, not in quotes, null."""
        return dataclasses.replace(self, null=null)

    def with_max_record(self, octets: int) -> Dialect:
        """The dialect, a record at most `octets` long, its line break counted."""
        return dataclasses.replace(self, max_record=octets)


class _Scan(Enum):
    """Where a scan of a CSV record is: so whether a line break ends it."""

    FIELD_START = auto()
    PLAIN = auto()
    QUOTED = auto()
    QUOTE_IN_QUOTED = auto()

    def after(self, b: int, delimiter: int) -> _Scan:
        """Where the scan is after `b`."""
        if self is _Scan.QUOTED:
            return _Scan.QUOTE_IN_QUOTED if b == _QUOTE else _Scan.QUOTED
        if b == delimiter:
            return _Scan.FIELD_START
        if self is _Scan.PLAIN:
            return _Scan.PLAIN
        return _Scan.QUOTED if b == _QUOTE else _Scan.PLAIN


@dataclass(frozen=True, slots=True)
class _Field:
    text: str
    quoted: bool


class _Refused(Exception):  # noqa: N818  # Caught here alone.
    """A record that cannot be read: why."""


class Delimited:
    """Delimited text read from a binary stream, a record at a time."""

    def __init__(self, data: BinaryIO, dialect: Dialect | None = None) -> None:
        """Delimited text read from `data`, written as `dialect` says, else as CSV."""
        self._input = data
        self._dialect = dialect or Dialect.csv()
        self._bytes = bytearray()
        self._lines = 0
        self._records = 0
        self._header_pending = self._dialect.header
        self._started = False
        self._done = False

    def headings(self) -> list[Heading] | None:
        """Its header's names, if the dialect has a header; else None.

        Raises:
            SourceError: If there is no header, or it cannot be read.
        """
        return self._header()

    def record(self) -> Record | None:
        """The next record; None at the end.

        Raises:
            SourceError: Why it cannot be read, and where.
        """
        self._header()
        if self._done:
            return None
        number = self._records + 1
        read = self._fields(number)
        if read is None:
            return None
        fields, line = read
        self._records = number
        null = self._dialect.null
        values: list[object] = [
            None if not f.quoted and f.text == null else f.text for f in fields
        ]
        return Record(values, Position(number, line))

    def _header(self) -> list[Heading] | None:
        if not self._header_pending:
            return None
        self._header_pending = False
        read = self._fields(0)
        if read is None:
            raise SourceError(Position(0, 1), "there is no header")
        return [Heading(f.text) for f in read[0]]

    def _fields(self, record: int) -> tuple[list[_Field], int] | None:
        line = self._lines + 1
        try:
            fields = _split(bytes(self._bytes), self._dialect) if self._raw() else None
        except _Refused as e:
            self._done = True
            raise SourceError(Position(record, line), str(e)) from None
        self._done = fields is None
        return None if fields is None else (fields, line)

    def _raw(self) -> bool:
        """Read the next record's bytes, its line break taken off: False at the end."""
        self._bytes.clear()
        at = _Scan.FIELD_START
        most = self._dialect.max_record
        while True:
            start = len(self._bytes)
            room = most - len(self._bytes) + 1
            try:
                chunk = self._input.readline(room)
            except OSError as e:
                msg = f"cannot read: {e}"
                raise _Refused(msg) from e
            self._bytes += chunk
            if len(self._bytes) > most:
                msg = f"the record is longer than {most} bytes"
                raise _Refused(msg)
            if not chunk:
                if at is _Scan.QUOTED:
                    raise _Refused(_UNCLOSED)
                return bool(self._bytes)
            if self._dialect.quoted:
                for b in self._bytes[start:]:
                    at = at.after(b, self._dialect.delimiter)
            self._lines += 1
            if at is not _Scan.QUOTED:
                self._ended()
                return True

    def _ended(self) -> None:
        if self._bytes.endswith(b"\n"):
            del self._bytes[-1]
            if self._bytes.endswith(b"\r"):
                del self._bytes[-1]
        if not self._started and self._bytes.startswith(_BOM):
            del self._bytes[: len(_BOM)]
        self._started = True


def _split(data: bytes, dialect: Dialect) -> list[_Field]:
    """The fields of the record `data`, written as `dialect` says."""
    if not dialect.quoted:
        parts = data.split(bytes([dialect.delimiter]))
        return [_Field(_text(p, n), quoted=False) for n, p in enumerate(parts)]
    fields: list[_Field] = []
    at = 0
    while True:
        n = len(fields)
        quoted = data[at : at + 1] == b'"'
        if quoted:
            written, at = _enclosed(data, at + 1, n)
        else:
            written, at = _plain(data, at, dialect.delimiter, n)
        fields.append(_Field(_text(written, n), quoted=quoted))
        if at >= len(data):
            return fields
        if data[at] != dialect.delimiter:
            msg = (
                f"[RFC 4180 §2 rule 5] field {n + 1}:"
                " a quoted field's closing quote is followed by more"
            )
            raise _Refused(msg)
        at += 1


def _plain(data: bytes, at: int, delimiter: int, n: int) -> tuple[bytes, int]:
    end = at
    while end < len(data) and data[end] != delimiter:
        if data[end] == _QUOTE:
            msg = (
                f"[RFC 4180 §2 rule 5] field {n + 1}:"
                " a quote in a field not enclosed in quotes"
            )
            raise _Refused(msg)
        end += 1
    return data[at:end], end


def _enclosed(data: bytes, at: int, n: int) -> tuple[bytes, int]:
    written = bytearray()
    while True:
        if at >= len(data):
            msg = f"field {n + 1}: {_UNCLOSED}"
            raise _Refused(msg)
        b = data[at]
        at += 1
        if b == _QUOTE:
            if data[at : at + 1] != b'"':
                return bytes(written), at
            at += 1
        written.append(b)


def _text(data: bytes, n: int) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        msg = f"field {n + 1} is not UTF-8"
        raise _Refused(msg) from None
