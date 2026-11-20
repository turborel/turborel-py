"""A JSON value written as its stored form, D89's tree [PROTOCOL Values].

As Turborel's `binary/write.rs` writes it: each node after its tag; an
exact number in the narrowest of its three forms; an array's and an
object's offsets after their count and size, an object's members in the
order given and its directory sorted by key octets, of one key in that
order (`jsontree.py` reads it back).

A parameter is a JSON value when a program wraps it in `turborel.Json`:
None, a bool, an int, a Decimal, a `turborel.DecFloat`, a float, a str,
a date, a time or a datetime, a list or tuple of them, or a dict of them
by str keys.
"""

from __future__ import annotations

import datetime as dt
import functools
import struct
from decimal import Decimal
from typing import Final

from turborel._codec import datetimes, numbers
from turborel._codec.jsontree import (
    APPROXIMATE,
    ARRAY,
    DATETIME,
    DECFLOAT,
    DECIMAL,
    FALSE,
    FORMAT_VERSION,
    INTEGER,
    MAX_DEPTH,
    MAX_DOCUMENT_OCTETS,
    NULL,
    OBJECT,
    STRING,
    TRUE,
    WIDE,
)
from turborel._errors import beyond_limits, unsendable
from turborel._values import DecFloat

_WORD: Final = struct.Struct("<I")
_I64: Final = struct.Struct("<q")
_DOUBLE: Final = struct.Struct("<d")
_I16_BYTES: Final = 2
_I32_BYTES: Final = 4
_I64_BYTES: Final = 8
_I128_BYTES: Final = 16
_I64_MIN: Final = -(1 << 63)
_I64_MAX: Final = (1 << 63) - 1
_U8_MAX: Final = 0xFF


def encode(value: object) -> bytes:
    """The stored form of the JSON value `value`.

    Raises:
        ProgrammingError: SQLSTATE 07006, of a part no JSON value holds,
            or an object's key that is not a str.
        DataError: SQLSTATE 22003, of a number past its node's fields.
        NotSupportedError: SQLSTATE 0A000, past 128 levels of nesting or
            256 MiB.
    """
    document = bytes([FORMAT_VERSION]) + _node(value, 0)
    if len(document) > MAX_DOCUMENT_OCTETS:
        msg = "a JSON value's stored form is longer than 256 MiB"
        raise beyond_limits(msg)
    return document


def _node(value: object, depth: int) -> bytes:
    if depth > MAX_DEPTH:
        msg = "a JSON value's arrays and objects nest deeper than 128"
        raise beyond_limits(msg)
    return _write(value, depth)


@functools.singledispatch
def _write(value: object, _: int) -> bytes:
    """The node of `value`, by its type; of a type no node holds, refused."""
    msg = f"a JSON value holds no {type(value).__name__}"
    raise unsendable(msg)


@_write.register
def _write_null(_: None, __: int) -> bytes:
    return bytes([NULL])


@_write.register
def _write_truth(value: bool, _: int) -> bytes:  # noqa: FBT001  # Dispatched by its type.
    return bytes([TRUE if value else FALSE])


@_write.register
def _write_decfloat(value: DecFloat, _: int) -> bytes:
    coefficient, exponent = numbers.python_to_decfloat(value.value)
    exponent_bytes = exponent.to_bytes(_I32_BYTES, "little", signed=True)
    return _tagged(DECFLOAT, _i128(coefficient), exponent_bytes)


@_write.register
def _write_approximate(value: float, _: int) -> bytes:
    return _tagged(APPROXIMATE, _DOUBLE.pack(value))


@_write.register
def _write_text(value: str, _: int) -> bytes:
    return _tagged(STRING, _string(value))


@_write.register
def _write_array(value: list | tuple, depth: int) -> bytes:  # type: ignore[type-arg]  # Any list.
    return _container(ARRAY, [_node(v, depth + 1) for v in value])


def _tagged(tag: int, *fields: bytes) -> bytes:
    return bytes([tag]) + b"".join(fields)


def _i128(n: int) -> bytes:
    return n.to_bytes(_I128_BYTES, "little", signed=True)


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return _WORD.pack(len(raw)) + raw


@_write.register
def _exact(value: int | Decimal, _: int) -> bytes:
    """An exact number, in the narrowest node that holds it."""
    units, scale = numbers.python_to_exact(value)
    narrow = _I64_MIN <= units <= _I64_MAX
    if narrow and scale == 0:
        return _tagged(INTEGER, _I64.pack(units))
    if narrow and scale <= _U8_MAX:
        return _tagged(DECIMAL, _I64.pack(units), bytes([scale]))
    return _tagged(WIDE, _i128(units), _WORD.pack(scale))


@_write.register
def _datetime(value: dt.date | dt.time, _: int) -> bytes:
    fields = datetimes.from_python(value)
    return _tagged(
        DATETIME,
        bytes([fields.moment]),
        fields.utc.to_bytes(_I64_BYTES, "little", signed=True),
        fields.zone.to_bytes(_I16_BYTES, "little", signed=True),
        bytes([fields.zoned, fields.precision]),
    )


def _container(tag: int, parts: list[bytes]) -> bytes:
    """An array: its count, its size, each part's offset, then the parts."""
    offsets, at = [], 0
    for part in parts:
        offsets.append(_WORD.pack(at))
        at += len(part)
    return _tagged(tag, _WORD.pack(len(parts)), _WORD.pack(at), *offsets, *parts)


@_write.register
def _object(value: dict, depth: int) -> bytes:  # type: ignore[type-arg]  # Any dict.
    """An object: its members in the order given, its directory sorted by key."""
    members: list[bytes] = []
    directory: list[tuple[bytes, int]] = []
    at = 0
    for key, part in value.items():
        if not isinstance(key, str):
            msg = f"a JSON object's key is a str, not {type(key).__name__}"
            raise unsendable(msg)
        member = _string(key) + _node(part, depth + 1)
        directory.append((key.encode("utf-8"), at))
        members.append(member)
        at += len(member)
    directory.sort(key=lambda entry: entry[0])
    offsets = [_WORD.pack(offset) for _, offset in directory]
    return _tagged(OBJECT, _WORD.pack(len(members)), _WORD.pack(at), *offsets, *members)
