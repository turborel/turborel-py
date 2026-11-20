"""Tests of values: read as the spec's table lays them out, and written back."""

from __future__ import annotations

import datetime as dt
import math
import uuid
from decimal import Decimal

import pytest

from turborel import DataError, NotSupportedError, OperationalError
from turborel._codec.datatypes import IntervalField, Qualifier
from turborel._codec.fields import I128_MAX, I128_MIN, Reader, Writer
from turborel._codec.jsonwrite import encode as json_document
from turborel._codec.values import read_row, read_value, write_row
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


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def u64(n: int) -> bytes:
    """A `u64`, little-endian."""
    return n.to_bytes(8, "little", signed=n < 0)


def i128(n: int) -> bytes:
    """An `i128`, little-endian."""
    return n.to_bytes(16, "little", signed=True)


def text(s: str) -> bytes:
    """A string: its length, then its UTF-8."""
    return u32(len(s.encode())) + s.encode()


def read(data: bytes) -> object:
    """The one value `data` holds, all of it read."""
    r = Reader(data, "reply")
    value = read_value(r)
    r.finish()
    return value


def sent(value: object) -> bytes:
    """The bytes `value` is written as, alone."""
    w = Writer()
    write_row(w, [value])
    return w.data()[4:]


def datetime_body(zoned: int, zone: int, utc: int) -> bytes:
    """A datetime's body: zoned, precision 6, the zone's bits, the instant."""
    return bytes([zoned, 6]) + u32(zone & 0xFFFF) + u64(utc)


DAY = 86_400_000_000
MINUTE = 60_000_000
WEST = dt.timezone(-dt.timedelta(hours=12, minutes=59))
YEAR_MONTH = Qualifier(IntervalField.YEAR, IntervalField.MONTH, 2, 0)
DAY_SECOND = Qualifier(IntervalField.DAY, IntervalField.SECOND, 9, 6)
ID = uuid.UUID("919108f7-52d1-4320-9bac-f847db4148a8")

READ = [
    (bytes([0]), None),
    (bytes([1]) + text("abcd"), "abcd"),
    (bytes([5]) + text("é"), "é"),
    (bytes([2]) + i128(1) + u32(0), 1),  # the worked example's value
    (bytes([2]) + i128(-12_345) + u32(2), Decimal("-123.45")),
    (bytes([2]) + i128(I128_MAX) + u32(0), I128_MAX),
    (bytes([3]) + u64(0x3FE0_0000_0000_0000), 0.5),
    (
        bytes([4]) + text("POINT") + text("(1, 2)") + u32(2) + bytes([1, 2]),
        PluginValue("POINT", "(1, 2)", b"\x01\x02"),
    ),
    (bytes([6]) + u32(3) + bytes([0xAB, 0, 0xC0]), b"\xab\x00\xc0"),
    (bytes([7]) + u32(0), b""),
    (bytes([8]) + datetime_body(0, 0, 0), dt.date(1, 1, 1)),
    (
        bytes([9]) + datetime_body(1, -779, DAY - 1),
        dt.time(11, 0, 59, 999_999, tzinfo=WEST),
    ),
    (bytes([10]) + datetime_body(0, 0, MINUTE), dt.time(0, 1)),
    (bytes([11]) + datetime_body(0, 0, 0), dt.datetime(1, 1, 1)),  # noqa: DTZ001
    (
        bytes([12]) + datetime_body(1, 840, 0),
        dt.datetime(1, 1, 1, 14, tzinfo=dt.timezone(dt.timedelta(hours=14))),
    ),
    (
        bytes([13]) + u32(0) + u32(1) + u32(2) + u32(0) + i128(-14),
        Interval(YEAR_MONTH, -14),
    ),
    (
        bytes([13]) + u32(2) + u32(5) + u32(9) + u32(6) + i128(-1_500_000),
        Interval(DAY_SECOND, -1_500_000),
    ),
    (bytes([14, 1]), True),
    (bytes([14, 0]), False),
    (bytes([15]) + i128(-15) + u32(0xFFFF_FFFF), Decimal("-1.5")),
    (bytes([16]) + u32(1) + bytes([16]) + u32(2) + bytes([14, 1, 0]), [[True, None]]),
    (bytes([17]) + u32(1) + bytes([1]) + text("x"), ("x",)),
    (bytes([20, 0]) + text("aé"), "aé"),
    (bytes([20, 1]) + u32(2) + bytes([0, 0xFF]), b"\x00\xff"),
    (bytes([21, 0]) + u32(7) + u64(300) + u64(200), LobLocator(False, 7, 300, 200)),  # noqa: FBT003
    (
        bytes([22]) + u32(2) + bytes([0]) + bytes([22]) + u32(0),
        Multiset((None, Multiset(()))),
    ),
    (
        bytes([23]) + text("S") + text("T") + u32(1) + bytes([14, 1]),
        Structured("S", "T", (True,)),
    ),
    (bytes([24]) + u32(2) + bytes([1, 2]), Reference(b"\x01\x02")),
    (
        bytes([25]) + u32(len(json_document({"a": 1}))) + json_document({"a": 1}),
        {"a": 1},
    ),
    (bytes([26]) + text("<b/>"), Xml("<b/>")),
    (bytes([27]) + u32(16) + ID.bytes, ID),
]


@pytest.mark.parametrize(("data", "expected"), READ)
def test_values_read_by_their_tags(data: bytes, expected: object) -> None:
    """Verifies: [PROTOCOL Values] every value tag, 0 to 27, and its body.

    Tags 5, 7, 10 and 12, which turborel-protocol reads as their types'
    kinds write them (RULES.md D13); UUID, tag 27, its 16 octets as bytes
    (Turborel's RULES.md D184); the worked example's exact number 1.
    """
    value = read(data)
    assert value == expected
    assert type(value) is type(expected)


def test_approximate_numbers_keep_nan_and_negative_zero() -> None:
    """Verifies: [PROTOCOL Values] an IEEE 754 double's bits: NaN and -0.0 kept."""
    negative_zero = read(sent(-0.0))
    assert isinstance(negative_zero, float)
    assert math.copysign(1.0, negative_zero) == -1.0
    nan = read(sent(math.nan))
    assert isinstance(nan, float)
    assert math.isnan(nan)
    assert sent(-0.0) == bytes([3, 0, 0, 0, 0, 0, 0, 0, 0x80])


WRITTEN = [
    None,
    "é",
    0,
    I128_MIN,
    Decimal("-1.50"),
    DecFloat(Decimal("1.5")),
    1.5e300,
    b"\x00\xff",
    True,
    dt.date(2024, 2, 29),
    dt.time(23, 59, 59, 500_000, tzinfo=WEST),
    dt.datetime(9999, 12, 31, 23, 59, 59, 999_999),  # noqa: DTZ001
    dt.datetime(2026, 11, 19, 1, 2, 3, tzinfo=dt.UTC),
    Interval(DAY_SECOND, I128_MAX),
    [1, [2, None]],
    ("x", (1,)),
    Multiset((1, None)),
    Structured("S", "T", (1, "a")),
    Reference(b"\x07"),
    Xml("<a>&lt;</a>"),
    ID,
    PluginValue("POINT", "(1, 2)", b"\x01\x02"),
    LobLocator(True, 3, 9, 9),  # noqa: FBT003
]


@pytest.mark.parametrize("value", WRITTEN)
def test_values_read_back_as_written(value: object) -> None:
    """Verifies: [PROTOCOL Values] each Python value written under its tag.

    A plug-in's value goes back as it came, its name, text and bytes
    unchanged; a DECFLOAT reads back as its Decimal.
    """
    expected = value.value if isinstance(value, DecFloat) else value
    assert read(sent(value)) == expected


def test_values_written_byte_for_byte() -> None:
    """Verifies: [PROTOCOL Values] a character string, an exact number, JSON, XML.

    JSON and XML are marked by their wrappers, a large object sent whole
    by its own; a bytearray and a memoryview are binary strings.
    """
    assert sent("AB") == bytes([1]) + text("AB")
    assert sent(Decimal("-0.5")) == bytes([2]) + i128(-5) + u32(1)
    document = json_document([1])
    assert sent(Json([1])) == bytes([25]) + u32(len(document)) + document
    assert sent(LargeObject("é")) == bytes([20, 0]) + text("é")
    assert sent(LargeObject(b"\x01")) == bytes([20, 1]) + u32(1) + b"\x01"
    assert (
        sent(bytearray(b"\x01"))
        == sent(memoryview(b"\x01"))
        == bytes([6]) + u32(1) + b"\x01"
    )
    assert read(sent(Json({"k": [None]}))) == {"k": [None]}


def nested_arrays(depth: int) -> bytes:
    """Arrays `depth` deep, each holding the next, the last empty."""
    data = bytes([16]) + u32(0)
    for _ in range(depth - 1):
        data = bytes([16]) + u32(1) + data
    return data


@pytest.mark.parametrize(
    "data",
    [
        bytes([28]),
        bytes([99]),
        bytes([20, 2]) + u32(0),  # a large object of kind 2
        bytes([20, 0]) + u32(1) + b"\xff",  # a CLOB not UTF-8
        bytes([27]) + u32(15) + bytes(15),  # a UUID of 15 octets
        bytes([11, 0, 6]) + u32(0x1_0000) + u64(0),  # a displacement past 16 bits
        bytes([11, 0, 6]) + u32(0) + u64(1 << 62),  # past year 9999
        bytes([15]) + i128(150) + u32((-2) & 0xFFFF_FFFF),  # a DECFLOAT not canonical
        bytes([22]) + u32(65_536) + bytes(65_536),  # past a multiset's cardinality
        bytes([13]) + u32(6) + u32(0) + u32(0) + u32(0) + i128(0),  # no field 6
        nested_arrays(17),
    ],
)
def test_a_value_that_cannot_be_read_fails_the_connection(data: bytes) -> None:
    """Verifies: [PROTOCOL Values] a tag of no value, a body out of range.

    [DESIGN] D13 turborel-protocol's bounds: 16 levels, 65 535 elements of
    a multiset, a canonical DECFLOAT.
    """
    with pytest.raises(OperationalError) as failure:
        read(data)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")


@pytest.mark.parametrize(
    ("data", "sqlstate"),
    [
        (bytes([18]), "TB916"),  # the server's stored form of a CLOB, never sent
        (bytes([19]), "TB916"),
        (bytes([14, 2]), "TB916"),  # a truth value of 2
        (bytes([25]) + u32(2) + bytes([2, 0]), "TB916"),  # a JSON value of version 2
        (bytes([25]) + u32(2) + bytes([1, 99]), "TB916"),  # a node of no tag
    ],
)
def test_a_value_the_client_cannot_take_is_refused_alone(
    data: bytes, sqlstate: str
) -> None:
    """Verifies: [PROTOCOL Values and fields] a value the client cannot take.

    Its request fails with the value's error, not of class 08: SQLCODE
    -916, SQLSTATE TB916; tags 18 and 19 among them (RULES.md D8).
    """
    with pytest.raises(OperationalError) as failure:
        read(data)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-916, sqlstate)


def test_arrays_nest_16_deep() -> None:
    """Verifies: [DESIGN] D13 values nest 16 deep, both ways, and no deeper."""
    assert isinstance(read(nested_arrays(16)), list)
    deep: list[object] = []
    for _ in range(15):
        deep = [deep]
    assert read(sent(deep)) == deep
    with pytest.raises(NotSupportedError):
        sent([deep])


@pytest.mark.parametrize(
    ("value", "error", "sqlstate"),
    [
        ({1, 2}, DataError, "22000"),
        ({"a": 1}, DataError, "22000"),
        (object(), DataError, "22000"),
        (I128_MAX + 1, DataError, "22003"),
        (Decimal("Infinity"), DataError, "22003"),
        (Interval(YEAR_MONTH, I128_MIN - 1), DataError, "22003"),
        (Multiset((None,) * 65_536), NotSupportedError, "0A000"),
    ],
)
def test_what_no_value_carries_is_refused(
    value: object, error: type[Exception], sqlstate: str
) -> None:
    """Verifies: [DESIGN] D13 refused before a byte is sent, by its condition."""
    with pytest.raises(error) as failure:
        sent(value)
    assert getattr(failure.value, "sqlstate", None) == sqlstate


def test_a_row_is_a_list_of_values() -> None:
    """Verifies: [PROTOCOL Composite fields] row: a list of values."""
    w = Writer()
    write_row(w, [1, None, "a"])
    assert w.data()[:4] == u32(3)
    assert read_row(Reader(w.data(), "reply")) == (1, None, "a")
