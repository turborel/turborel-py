"""Values, read from a reply and written into a request [PROTOCOL Values].

A value is a tag, then its body; the tag says how the value is written,
which is not always its column type's. Each reaches Python as the type
doc/appendix/a-types.md lists, and each Python value a program sends is
written by its type. What turborel-protocol refuses is refused here
(RULES.md D13).
"""

from __future__ import annotations

import datetime as dt
import functools
import struct
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from turborel._codec import datetimes, jsontree, jsonwrite, numbers, tags
from turborel._codec.datatypes import MAX_CARDINALITY, Moment, read_qualifier
from turborel._codec.fields import I128_MAX, I128_MIN, MAX_NESTING, Reader, Writer
from turborel._errors import NUMERIC_OUT_OF_RANGE, beyond_limits, data_error, unsendable
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

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

UUID_OCTETS: Final = 16
"""A UUID's octets (Turborel's RULES.md D184)."""

_DOUBLE: Final = struct.Struct("<d")
_U16_MAX: Final = 0xFFFF
_I16_SIGN: Final = 0x8000
_I16_SPAN: Final = 0x1_0000
_ZONED: Final = 1
_BOOLEANS: Final = (0, 1)

_MOMENT_TAGS: Final = {
    Moment.DATE: tags.VALUE_DATE,
    Moment.TIME: tags.VALUE_TIME,
    Moment.TIMESTAMP: tags.VALUE_TIMESTAMP,
}


def read_value(r: Reader) -> object:
    """The value `r` holds next, as Python holds it.

    Raises:
        OperationalError: SQLSTATE 08006, of a tag of no value or a body
            that cannot be read.
    """
    tag = r.u8()
    read = _READERS.get(tag)
    if read is None:
        msg = f"no value has tag {tag}"
        raise r.malformed(msg)
    return read(r)


def read_row(r: Reader) -> tuple[object, ...]:
    """A row: a list of values."""
    return tuple(r.items(read_value))


def write_row(w: Writer, values: Sequence[object]) -> None:
    """A row, or an Execute's values: their count, then each value.

    Raises:
        ProgrammingError: SQLSTATE 07006, of a value of no type the
            protocol carries.
        DataError: SQLSTATE 22003, of a number past its fields.
        NotSupportedError: SQLSTATE 0A000, of parts nested past 16 levels.
    """
    w.u32(len(values))
    for value in values:
        _write(value, w, 0)


# --- Reading -------------------------------------------------------------


def _exact(r: Reader) -> object:
    units = r.i128()
    return numbers.exact_to_python(units, r.u32())


def _approximate(r: Reader) -> float:
    value: float = _DOUBLE.unpack(r.take(_DOUBLE.size))[0]
    return value


def _plugin(r: Reader) -> PluginValue:
    return PluginValue(r.string(), r.string(), r.octets())


def _datetime(moment: Moment) -> Callable[[Reader], object]:
    def read(r: Reader) -> object:
        zoned, precision, zone, utc = r.u8() == _ZONED, r.u8(), r.u32(), r.i64()
        if zone > _U16_MAX:
            msg = "a time zone displacement is out of range"
            raise r.malformed(msg)
        signed = zone - _I16_SPAN if zone & _I16_SIGN else zone
        fields = datetimes.Fields(moment, zoned, precision, signed, utc)
        try:
            return datetimes.to_python(fields)
        except (OverflowError, ValueError) as e:
            msg = "a datetime is beyond Python's years 1 to 9999"
            raise r.malformed(msg) from e

    return read


def _interval(r: Reader) -> Interval:
    qualifier = read_qualifier(r)
    return Interval(qualifier, r.i128())


def _boolean(r: Reader) -> bool:
    byte = r.u8()
    if byte not in _BOOLEANS:
        msg = f"{byte} is not a truth value"
        raise r.malformed(msg)
    return byte == 1


def _decfloat(r: Reader) -> Decimal:
    coefficient, exponent = r.i128(), r.i32()
    if numbers.decfloat_canonical(coefficient, exponent) != (coefficient, exponent):
        msg = "a DECFLOAT value is malformed"
        raise r.malformed(msg)
    return numbers.decfloat_to_python(coefficient, exponent)


def _lob_kind(r: Reader) -> bool:
    kind = r.u8()
    if kind not in (tags.LOB_CHARACTER, tags.LOB_BINARY):
        msg = "not a kind of large object"
        raise r.malformed(msg)
    return kind == tags.LOB_BINARY


def _lob_whole(r: Reader) -> str | bytes:
    binary = _lob_kind(r)
    data = r.octets()
    if binary:
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        msg = "a character large object is not UTF-8"
        raise r.malformed(msg) from e


def _lob_locator(r: Reader) -> LobLocator:
    binary = _lob_kind(r)
    return LobLocator(binary, r.u32(), r.u64(), r.u64())


def _multiset(r: Reader) -> Multiset:
    elements = r.nested(read_row)
    if len(elements) > MAX_CARDINALITY:
        msg = "a multiset has more elements than its maximum cardinality"
        raise r.malformed(msg)
    return Multiset(elements)


def _structured(r: Reader) -> Structured:
    def read(r: Reader) -> Structured:
        schema, name = r.string(), r.string()
        return Structured(schema, name, read_row(r))

    return r.nested(read)


def _json(r: Reader) -> object:
    return jsontree.decode(r.octets(), r.malformed)


def _uuid(r: Reader) -> uuid.UUID:
    raw = r.octets()
    if len(raw) != UUID_OCTETS:
        msg = "a UUID is 16 octets"
        raise r.malformed(msg)
    return uuid.UUID(bytes=raw)


_READERS: Final[dict[int, Callable[[Reader], object]]] = {
    tags.VALUE_NULL: lambda _: None,
    tags.VALUE_CHARACTER: Reader.string,
    tags.VALUE_VARYING: Reader.string,
    tags.VALUE_EXACT: _exact,
    tags.VALUE_APPROXIMATE: _approximate,
    tags.VALUE_PLUGIN: _plugin,
    tags.VALUE_BINARY: Reader.octets,
    tags.VALUE_BINARY_VARYING: Reader.octets,
    tags.VALUE_DATE: _datetime(Moment.DATE),
    tags.VALUE_TIME: _datetime(Moment.TIME),
    tags.VALUE_TIME_ZONED: _datetime(Moment.TIME),
    tags.VALUE_TIMESTAMP: _datetime(Moment.TIMESTAMP),
    tags.VALUE_TIMESTAMP_ZONED: _datetime(Moment.TIMESTAMP),
    tags.VALUE_INTERVAL: _interval,
    tags.VALUE_BOOLEAN: _boolean,
    tags.VALUE_DECFLOAT: _decfloat,
    tags.VALUE_ARRAY: lambda r: list(r.nested(read_row)),
    tags.VALUE_ROW: lambda r: r.nested(read_row),
    tags.VALUE_LOB_WHOLE: _lob_whole,
    tags.VALUE_LOB_LOCATOR: _lob_locator,
    tags.VALUE_MULTISET: _multiset,
    tags.VALUE_STRUCTURED: _structured,
    tags.VALUE_REFERENCE: lambda r: Reference(r.octets()),
    tags.VALUE_JSON: _json,
    tags.VALUE_XML: lambda r: Xml(r.string()),
    tags.VALUE_UUID: _uuid,
}


# --- Writing ----------------------------------------------------------------


@functools.singledispatch
def _write(value: object, _: Writer, __: int) -> None:
    """Write `value` by its type; of a type the protocol carries not, refuse it."""
    msg = f"no value of the protocol is a {type(value).__name__}"
    raise unsendable(msg)


@_write.register
def _write_null(_: None, w: Writer, __: int) -> None:
    w.u8(tags.VALUE_NULL)


@_write.register
def _write_boolean(value: bool, w: Writer, _: int) -> None:  # noqa: FBT001  # By its type.
    w.u8(tags.VALUE_BOOLEAN)
    w.u8(1 if value else 0)


@_write.register
def _write_exact(value: int | Decimal, w: Writer, _: int) -> None:
    units, scale = numbers.python_to_exact(value)
    w.u8(tags.VALUE_EXACT)
    w.i128(units)
    w.u32(scale)


@_write.register
def _write_decfloat(value: DecFloat, w: Writer, _: int) -> None:
    coefficient, exponent = numbers.python_to_decfloat(value.value)
    w.u8(tags.VALUE_DECFLOAT)
    w.i128(coefficient)
    w.i32(exponent)


@_write.register
def _write_approximate(value: float, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_APPROXIMATE)
    w.raw(_DOUBLE.pack(value))


@_write.register
def _write_character(value: str, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_CHARACTER)
    w.string(value)


@_write.register
def _write_binary(value: bytes | bytearray | memoryview, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_BINARY)
    w.octets(bytes(value))


@_write.register
def _write_datetime(value: dt.date | dt.time, w: Writer, _: int) -> None:
    fields = datetimes.from_python(value)
    w.u8(_MOMENT_TAGS[fields.moment])
    w.u8(_ZONED if fields.zoned else 0)
    w.u8(fields.precision)
    w.u32(fields.zone % _I16_SPAN)
    w.i64(fields.utc)


@_write.register
def _write_interval(value: Interval, w: Writer, _: int) -> None:
    if not I128_MIN <= value.units <= I128_MAX:
        msg = f"an interval of {value.units} units is past an i128"
        raise data_error(msg, NUMERIC_OUT_OF_RANGE)
    q = value.qualifier
    w.u8(tags.VALUE_INTERVAL)
    for n in (q.start, q.end, q.leading_precision, q.fractional_precision):
        w.u32(n)
    w.i128(value.units)


def _parts(w: Writer, parts: Sequence[object], depth: int) -> None:
    """A composite's parts, one level deeper than `depth`."""
    if depth >= MAX_NESTING:
        msg = "arrays, rows and multisets nest deeper than 16"
        raise beyond_limits(msg)
    w.u32(len(parts))
    for part in parts:
        _write(part, w, depth + 1)


@_write.register
def _write_array(value: list, w: Writer, depth: int) -> None:  # type: ignore[type-arg]  # Any list.
    w.u8(tags.VALUE_ARRAY)
    _parts(w, value, depth)


@_write.register
def _write_row(value: tuple, w: Writer, depth: int) -> None:  # type: ignore[type-arg]  # Any tuple.
    w.u8(tags.VALUE_ROW)
    _parts(w, value, depth)


@_write.register
def _write_multiset(value: Multiset, w: Writer, depth: int) -> None:
    if len(value.elements) > MAX_CARDINALITY:
        msg = "a multiset holds at most 65 535 elements"
        raise beyond_limits(msg)
    w.u8(tags.VALUE_MULTISET)
    _parts(w, value.elements, depth)


@_write.register
def _write_structured(value: Structured, w: Writer, depth: int) -> None:
    w.u8(tags.VALUE_STRUCTURED)
    w.string(value.schema)
    w.string(value.name)
    _parts(w, value.attributes, depth)


@_write.register
def _write_reference(value: Reference, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_REFERENCE)
    w.octets(value.octets)


@_write.register
def _write_json(value: Json, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_JSON)
    w.octets(jsonwrite.encode(value.value))


@_write.register
def _write_xml(value: Xml, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_XML)
    w.string(value.text)


@_write.register
def _write_uuid(value: uuid.UUID, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_UUID)
    w.octets(value.bytes)


@_write.register
def _write_plugin(value: PluginValue, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_PLUGIN)
    w.string(value.type_name)
    w.string(value.text)
    w.octets(value.data)


@_write.register
def _write_lob(value: LargeObject, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_LOB_WHOLE)
    if isinstance(value.data, str):
        w.u8(tags.LOB_CHARACTER)
        w.octets(value.data.encode("utf-8"))
    else:
        w.u8(tags.LOB_BINARY)
        w.octets(value.data)


@_write.register
def _write_locator(value: LobLocator, w: Writer, _: int) -> None:
    w.u8(tags.VALUE_LOB_LOCATOR)
    w.u8(tags.LOB_BINARY if value.binary else tags.LOB_CHARACTER)
    w.u32(value.locator)
    w.u64(value.octets)
    w.u64(value.characters)
