"""A JSON value's stored form, Turborel's RULES.md D89 binary tree [PROTOCOL Values].

On the wire a JSON value, tag 25, is its stored form: a version octet,
1, then its root node, each node a tag and its body, integers
little-endian. The page says only "its stored form"; D89 lays it out,
and `src/json/binary.rs` and `binary/write.rs` in Turborel write it:

    0 null | 1 false | 2 true
    3 integer: i64 | 4 decimal: units i64, scale u8
    5 wide decimal: units i128, scale u32
    6 decimal floating point: coefficient i128, exponent i32
    7 approximate: f64 bits | 8 string: octets u32, UTF-8
    9 datetime: moment u8, utc i64, zone minutes i16, zoned u8, precision u8
    10 array: count u32, size u32, an offset u32 of each element, the elements
    11 object: count u32, size u32, an offset u32 of each member in key
       order, the members in written order, each key and its value

A document is checked whole as it is read, as Turborel's `validate`
does: every node within it, every string UTF-8, each offset where its
element or member is, an object's directory sorted by key octets and of
one key by written order. Damaged octets fail the connection.

A document reaches Python as its JSON value: None, a bool, an int, a
Decimal, a float, a str, a datetime, a list, or a dict in written order,
the first member of a key kept, as Turborel's member accessor takes it.
"""

from __future__ import annotations

import datetime as dt
import struct
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from turborel._codec import datetimes, numbers
from turborel._codec.datatypes import Moment

if TYPE_CHECKING:
    from collections.abc import Callable

    from turborel._errors import OperationalError

FORMAT_VERSION: Final = 1
"""The first octet of every document."""

MAX_DEPTH: Final = 128
"""The deepest arrays and objects nest: Turborel's `json::MAX_NESTING`."""

MAX_DOCUMENT_OCTETS: Final = 1 << 28
"""The longest document: Turborel's `MAX_DOCUMENT_OCTETS`, 256 MiB."""

# The tags of the nodes (D89).
NULL: Final = 0
FALSE: Final = 1
TRUE: Final = 2
INTEGER: Final = 3
DECIMAL: Final = 4
WIDE: Final = 5
DECFLOAT: Final = 6
APPROXIMATE: Final = 7
STRING: Final = 8
DATETIME: Final = 9
ARRAY: Final = 10
OBJECT: Final = 11

# The widths of a node's fields.
_WORD: Final = 4
_LONG: Final = 8
_WIDE_WORD: Final = 16
_CONTAINER_HEAD: Final = 2 * _WORD
# A datetime's body: its moment, then where its instant, its zone, its
# zoned flag and its precision begin, and its length.
_UTC_AT: Final = 1
_ZONE_AT: Final = _UTC_AT + _LONG
_ZONED_AT: Final = _ZONE_AT + 2
_PRECISION_AT: Final = _ZONED_AT + 1
_DATETIME_BODY: Final = _PRECISION_AT + 1
_DOUBLE: Final = struct.Struct("<d")
_FLAGS: Final = (0, 1)

JsonValue = (
    None
    | bool
    | int
    | Decimal
    | float
    | str
    | dt.date
    | dt.time
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)
"""A JSON value as Python holds it."""

_Read = tuple[JsonValue, int]


def decode(data: bytes, fail: Callable[[str], OperationalError]) -> JsonValue:
    """The JSON value of the document `data`, checked whole.

    Args:
        data: The document's octets.
        fail: Makes the error of damaged octets, given why.

    Raises:
        OperationalError: SQLSTATE 08006, from `fail`, if the octets are
            damaged, or more than 256 MiB.
    """
    if len(data) > MAX_DOCUMENT_OCTETS:
        msg = f"a JSON value's stored form is longer than {MAX_DOCUMENT_OCTETS} octets"
        raise fail(msg)
    if len(data) < 2 or data[0] != FORMAT_VERSION:  # noqa: PLR2004  # Its version, then a node.
        msg = "a JSON value does not begin with its format's version"
        raise fail(msg)
    value, length = _Tree(data, fail).node(1, len(data), 0)
    if 1 + length != len(data):
        msg = "octets follow a JSON value's root"
        raise fail(msg)
    return value


def _signed(raw: bytes) -> int:
    return int.from_bytes(raw, "little", signed=True)


def _unsigned(raw: bytes) -> int:
    return int.from_bytes(raw, "little")


class _Tree:
    """Reads a document's nodes, each within the bounds its container sets."""

    def __init__(self, data: bytes, fail: Callable[[str], OperationalError]) -> None:
        self._data = data
        self._fail = fail
        self._scalars: dict[int, Callable[[int, int], _Read]] = {
            INTEGER: self.integer,
            DECIMAL: self.decimal,
            WIDE: self.wide,
            DECFLOAT: self.decfloat,
            APPROXIMATE: self.approximate,
            STRING: self.string,
            DATETIME: self.datetime,
        }

    def damaged(self, why: str) -> OperationalError:
        """The error of damaged octets."""
        return self._fail(f"a JSON value's octets are damaged: {why}")

    def take(self, at: int, count: int, end: int) -> bytes:
        """`count` octets from `at`, none past `end`."""
        if at + count > end:
            msg = "a node runs past its document"
            raise self.damaged(msg)
        return self._data[at : at + count]

    def node(self, at: int, end: int, depth: int) -> _Read:
        """The value of the node at `at`, before `end`, and the octets it takes."""
        if depth > MAX_DEPTH:
            msg = "arrays and objects nest too deep"
            raise self.damaged(msg)
        tag = self.take(at, 1, end)[0]
        if tag in (NULL, FALSE, TRUE):
            return (None, False, True)[tag], 1
        if tag in (ARRAY, OBJECT):
            value, taken = self.container(tag, at + 1, (end, depth + 1))
        else:
            read = self._scalars.get(tag)
            if read is None:
                msg = f"a node's tag is {tag}"
                raise self.damaged(msg)
            value, taken = read(at + 1, end)
        return value, 1 + taken

    def integer(self, at: int, end: int) -> _Read:
        """An integer node's body: an i64."""
        return _signed(self.take(at, _LONG, end)), _LONG

    def decimal(self, at: int, end: int) -> _Read:
        """A decimal node's body: units i64, scale u8."""
        raw = self.take(at, _LONG + 1, end)
        return numbers.exact_to_python(_signed(raw[:_LONG]), raw[_LONG]), _LONG + 1

    def wide(self, at: int, end: int) -> _Read:
        """A wide decimal node's body: units i128, scale u32."""
        raw = self.take(at, _WIDE_WORD + _WORD, end)
        units, scale = _signed(raw[:_WIDE_WORD]), _unsigned(raw[_WIDE_WORD:])
        return numbers.exact_to_python(units, scale), len(raw)

    def decfloat(self, at: int, end: int) -> _Read:
        """A DECFLOAT node's body: coefficient i128, exponent i32, rounded."""
        raw = self.take(at, _WIDE_WORD + _WORD, end)
        given = _signed(raw[:_WIDE_WORD]), _signed(raw[_WIDE_WORD:])
        canonical = numbers.decfloat_canonical(*given)
        if canonical is None:
            msg = "a number is out of range"
            raise self.damaged(msg)
        return numbers.decfloat_to_python(*canonical), len(raw)

    def approximate(self, at: int, end: int) -> _Read:
        """An approximate node's body: an f64's bits."""
        value: float = _DOUBLE.unpack(self.take(at, _DOUBLE.size, end))[0]
        return value, _DOUBLE.size

    def string(self, at: int, end: int) -> tuple[str, int]:
        """A string: its octets' count u32, then its UTF-8."""
        length = _unsigned(self.take(at, _WORD, end))
        raw = self.take(at + _WORD, length, end)
        try:
            return raw.decode("utf-8"), _WORD + length
        except UnicodeDecodeError as e:
            msg = "a string is not UTF-8"
            raise self.damaged(msg) from e

    def datetime(self, at: int, end: int) -> _Read:
        """A datetime node's body: moment, utc i64, zone i16, zoned, precision."""
        raw = self.take(at, _DATETIME_BODY, end)
        moment, zoned, precision = raw[0], raw[_ZONED_AT], raw[_PRECISION_AT]
        if moment not in {m.value for m in Moment} or zoned not in _FLAGS:
            msg = "a datetime's moment or zoned flag is out of range"
            raise self.damaged(msg)
        fields = datetimes.Fields(
            Moment(moment),
            zoned=zoned == 1,
            precision=precision,
            zone=_signed(raw[_ZONE_AT:_ZONED_AT]),
            utc=_signed(raw[_UTC_AT:_ZONE_AT]),
        )
        try:
            return datetimes.to_python(fields), _DATETIME_BODY
        except (OverflowError, ValueError) as e:
            msg = "a datetime is beyond Python's"
            raise self.damaged(msg) from e

    def container(self, tag: int, at: int, within: tuple[int, int]) -> _Read:
        """An array's or an object's body: count, size, offsets, then its parts."""
        end, depth = within
        head = self.take(at, _CONTAINER_HEAD, end)
        count, size = _unsigned(head[:_WORD]), _unsigned(head[_WORD:])
        first = at + _CONTAINER_HEAD + count * _WORD
        offsets = self.take(at + _CONTAINER_HEAD, count * _WORD, end)
        directory = [
            _unsigned(offsets[i : i + _WORD]) for i in range(0, len(offsets), _WORD)
        ]
        stop = first + size
        if stop > end:
            msg = "a node runs past its document"
            raise self.damaged(msg)
        parts = _Parts(first, stop, depth)
        if tag == ARRAY:
            value: JsonValue = self.elements(directory, parts)
        else:
            value = self.members(directory, parts)
        return value, stop - at

    def elements(self, directory: list[int], parts: _Parts) -> list[JsonValue]:
        """An array's elements, each where its offset says, one after another."""
        values: list[JsonValue] = []
        at = parts.first
        for offset in directory:
            if parts.first + offset != at:
                msg = "an element's offset is not where it is"
                raise self.damaged(msg)
            value, taken = self.node(at, parts.stop, parts.depth)
            values.append(value)
            at += taken
        if at != parts.stop:
            msg = "an array's size is not its elements'"
            raise self.damaged(msg)
        return values

    def members(self, directory: list[int], parts: _Parts) -> dict[str, JsonValue]:
        """An object's members in written order, its directory checked sorted."""
        found: dict[str, JsonValue] = {}
        starts: dict[int, bytes] = {}
        at = parts.first
        for _ in directory:
            key, taken = self.string(at, parts.stop)
            value, length = self.node(at + taken, parts.stop, parts.depth)
            starts[at - parts.first] = key.encode("utf-8")
            found.setdefault(key, value)
            at += taken + length
        if at != parts.stop:
            msg = "an object's size is not its members'"
            raise self.damaged(msg)
        self.sorted_directory(directory, starts)
        return found

    def sorted_directory(self, directory: list[int], starts: dict[int, bytes]) -> None:
        """That the directory lists each member once, by key, then written order."""
        previous: tuple[bytes, int] | None = None
        for offset in directory:
            key = starts.get(offset)
            entry = (b"" if key is None else key, offset)
            if key is None or (previous is not None and previous >= entry):
                msg = "an object's key directory is not sorted"
                raise self.damaged(msg)
            previous = entry


@dataclass(frozen=True, slots=True)
class _Parts:
    """Where a container's parts are: from `first` to `stop`, at `depth`."""

    first: int
    stop: int
    depth: int
