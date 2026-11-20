"""Tests of JSON values' stored form, Turborel's RULES.md D89 binary tree."""

from __future__ import annotations

import datetime as dt
import math
import struct
from decimal import Decimal

import pytest

from turborel import DataError, NotSupportedError, OperationalError, ProgrammingError
from turborel._codec import jsonwrite
from turborel._codec.fields import Reader
from turborel._codec.jsontree import JsonValue, decode
from turborel._codec.jsonwrite import encode
from turborel._values import DecFloat


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def i64(n: int) -> bytes:
    """An `i64`, little-endian."""
    return n.to_bytes(8, "little", signed=True)


def key(text: str) -> bytes:
    """A member's key: its octets' count, then its UTF-8."""
    return u32(len(text.encode())) + text.encode()


def read(document: bytes) -> JsonValue:
    """The JSON value of `document`, as a reply's value."""
    return decode(document, Reader(b"", "reply").malformed)


# {"b": 1, "a": 2}, by D89's layout: version 1, object 11, count 2, size
# 28, the directory sorted by key ("a" at 14, "b" at 0), then the members
# in written order, each key and an integer node 3.
OBJECT = (
    bytes([1, 11])
    + u32(2)
    + u32(28)
    + u32(14)
    + u32(0)
    + key("b")
    + bytes([3])
    + i64(1)
    + key("a")
    + bytes([3])
    + i64(2)
)

# [true, null, "x"]: array 10, count 3, size 8, offsets 0, 1 and 2.
ARRAY = (
    bytes([1, 10])
    + u32(3)
    + u32(8)
    + u32(0)
    + u32(1)
    + u32(2)
    + bytes([2, 0, 8])
    + key("x")
)


def test_an_object_is_its_members_in_written_order_and_a_sorted_directory() -> None:
    """Verifies: [PROTOCOL Values] JSON node 11, the object, both ways.

    Turborel's RULES.md D89: count, size, an offset of each member in key
    order, the members in written order; written order kept.
    """
    value = read(OBJECT)
    assert value == {"b": 1, "a": 2}
    assert isinstance(value, dict)
    assert list(value) == ["b", "a"]
    assert encode({"b": 1, "a": 2}) == OBJECT


def test_an_array_is_its_elements_after_their_offsets() -> None:
    """Verifies: [PROTOCOL Values] JSON nodes 10, the array, 0, 2 and 8."""
    assert read(ARRAY) == [True, None, "x"]
    assert encode([True, None, "x"]) == ARRAY
    assert encode((True, None, "x")) == ARRAY


@pytest.mark.parametrize(
    ("value", "node"),
    [
        (None, 0),
        (False, 1),
        (True, 2),
        (7, 3),
        (-(1 << 63), 3),
        (1 << 63, 5),
        (Decimal("-1.25"), 4),
        (Decimal((0, (5,), -300)), 5),
        (DecFloat(Decimal("1.5")), 6),
        (-0.25, 7),
        ("é", 8),
        (dt.date(2024, 2, 29), 9),
        (dt.time(23, 59, tzinfo=dt.timezone(dt.timedelta(hours=-12, minutes=-59))), 9),
        (dt.datetime(2026, 11, 19, 1, 2, 3, 4), 9),  # noqa: DTZ001  # Without a zone.
    ],
)
def test_scalars_read_back_in_their_narrowest_node(value: object, node: int) -> None:
    """Verifies: [PROTOCOL Values] JSON nodes 0 to 9, each read back as written.

    An exact number is written in the narrowest of nodes 3, 4 and 5
    (Turborel's RULES.md D89); a DECFLOAT reads back as a Decimal.
    """
    document = encode(value)
    assert document[0] == 1
    assert document[1] == node
    expected = value.value if isinstance(value, DecFloat) else value
    assert read(document) == expected


def test_approximate_numbers_keep_their_bits() -> None:
    """Verifies: [PROTOCOL Values] JSON node 7, an f64's bits: NaN and -0.0 kept."""
    negative_zero = read(encode(-0.0))
    assert isinstance(negative_zero, float)
    assert math.copysign(1.0, negative_zero) == -1.0
    nan = read(encode(math.nan))
    assert isinstance(nan, float)
    assert math.isnan(nan)
    assert encode(-0.0)[2:] == struct.pack("<d", -0.0)


def test_a_decfloat_node_rounds_to_34_digits() -> None:
    """Verifies: [PROTOCOL Values] JSON node 6, coefficient `i128`, exponent `i32`."""
    long = bytes([1, 6]) + (10**34 + 15).to_bytes(16, "little", signed=True) + u32(0)
    assert read(long) == Decimal(f"{10**33 + 2}E1")


def test_of_one_key_the_first_member_is_kept() -> None:
    """Verifies: [PROTOCOL Values] an object's members of one key, in written order.

    The directory lists them by key, then by written order; Python's dict
    keeps the first, as Turborel's member accessor takes it.
    """
    twice = (
        bytes([1, 11])
        + u32(2)
        + u32(28)
        + u32(0)
        + u32(14)
        + key("a")
        + bytes([3])
        + i64(1)
        + key("a")
        + bytes([3])
        + i64(2)
    )
    assert read(twice) == {"a": 1}


def nested(depth: int) -> bytes:
    """A document of `depth` arrays, each holding the next, the last empty."""
    node = bytes([10]) + u32(0) + u32(0)
    for _ in range(depth - 1):
        node = bytes([10]) + u32(1) + u32(len(node)) + u32(0) + node
    return bytes([1]) + node


def test_arrays_and_objects_nest_at_most_128_deep() -> None:
    """Verifies: [DESIGN] D13 a JSON document nests at most 128 deep, both ways."""
    assert read(nested(129)) is not None
    with pytest.raises(OperationalError):
        read(nested(130))
    deep: list[object] = []
    for _ in range(129):
        deep = [deep]
    with pytest.raises(NotSupportedError):
        encode(deep)


@pytest.mark.parametrize(
    "document",
    [
        b"",
        bytes([1]),
        bytes([2, 0]),  # another version
        bytes([1, 0, 0]),  # octets after the root
        bytes([1, 12]),  # no node has tag 12
        bytes([1, 3, 0]),  # an integer cut short
        bytes([1, 8]) + u32(5) + b"ab",  # a string past its document
        bytes([1, 8]) + u32(1) + b"\xff",  # not UTF-8
        bytes([1, 9, 3]) + bytes(12),  # a datetime of moment 3
        bytes([1, 9, 2]) + bytes(10) + bytes([2, 0]),  # zoned 2
        bytes([1, 9, 0]) + i64(1 << 62) + bytes(4),  # past year 9999
        bytes([1, 6]) + (1).to_bytes(16, "little") + (6145).to_bytes(4, "little"),
        ARRAY[:-1],  # cut short
        ARRAY[:10] + u32(1) + ARRAY[14:],  # an offset not where its element is
        ARRAY[:6] + u32(9) + ARRAY[10:] + bytes(1),  # a size not its elements'
        OBJECT[:10] + u32(0) + u32(14) + OBJECT[18:],  # a directory not sorted
        OBJECT[:10] + u32(14) + u32(1) + OBJECT[18:],  # an offset of no member
        OBJECT[:6] + u32(29) + OBJECT[10:] + bytes(1),  # a size not its members'
    ],
)
def test_damaged_octets_fail_the_connection(document: bytes) -> None:
    """Verifies: [PROTOCOL Values] a JSON value checked whole as it is read.

    Turborel's RULES.md D89: a version other than 1, a node past its
    document, a string not UTF-8, an offset or a size not its parts', a
    directory not sorted: SQLCODE -919, SQLSTATE 08006.
    """
    with pytest.raises(OperationalError) as failure:
        read(document)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")


@pytest.mark.parametrize(
    ("value", "error"),
    [
        ({1, 2}, ProgrammingError),
        ({1: "a"}, ProgrammingError),
        (b"x", ProgrammingError),
        (1 << 127, DataError),
        (Decimal("NaN"), DataError),
    ],
)
def test_what_no_json_value_holds_is_refused(
    value: object, error: type[Exception]
) -> None:
    """Verifies: [DESIGN] D13 refused before it is sent: no JSON node holds it."""
    with pytest.raises(error):
        encode(value)


def test_a_document_past_256_mib_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies: [DESIGN] D13 a JSON value's stored form is at most 256 MiB.

    The bound is lowered here, so the test needs no 256 MiB of memory.
    """
    monkeypatch.setattr(jsonwrite, "MAX_DOCUMENT_OCTETS", 16)
    assert len(encode("x" * 10)) == 16
    with pytest.raises(NotSupportedError):
        encode("x" * 11)


# The page's example of {"a":[1,"x"]}, its 51 octets as it lays them out.
PAGE_EXAMPLE = bytes.fromhex(
    "01"  # version 1
    "0b"
    "01000000"
    "25000000"
    "00000000"
    "0100000061"  # object, count, size, offset, key
    "0a"
    "02000000"
    "0f000000"
    "00000000"
    "09000000"  # array, count, size, offsets
    "03"
    "0100000000000000"  # integer 1
    "08"
    "0100000078"  # string "x"
)


def test_the_page_s_examples_byte_for_byte() -> None:
    """Verifies: [PROTOCOL JSON values] the 51 octets of {"a":[1,"x"]}, both ways.

    [PROTOCOL Values] JSON nodes; `{"b":1,"a":2}` keeps its members in
    that order, its directory putting `a` first, at 14, then `b` at 0.
    """
    assert len(PAGE_EXAMPLE) == 51
    assert read(PAGE_EXAMPLE) == {"a": [1, "x"]}
    assert encode({"a": [1, "x"]}) == PAGE_EXAMPLE
    ordered = encode({"b": 1, "a": 2})
    assert ordered == OBJECT
    assert ordered[10:18] == u32(14) + u32(0)
    assert list(read(ordered)) == ["b", "a"]  # type: ignore[arg-type]  # An object.


def test_an_exact_number_keeps_its_written_scale() -> None:
    """Verifies: [PROTOCOL JSON values] the narrowest node, the scale as written.

    [PROTOCOL Values] 1.50 is a decimal node of units 150 and scale 2,
    and reads back as 1.50; an integer of scale 0 an integer node; units
    past an `i64`, or a scale past a `u8`, a wide decimal; the limits of
    nesting, 128, and of a document, 256 MiB, are D13's above.
    """
    assert encode(Decimal("1.50")) == bytes([1, 4]) + i64(150) + bytes([2])
    assert str(read(encode(Decimal("1.50")))) == "1.50"
    assert encode(7) == bytes([1, 3]) + i64(7)
    assert encode(Decimal(7)) == bytes([1, 3]) + i64(7)
    wide = Decimal(2**70) / 10
    assert encode(wide)[1] == 5
    assert encode(Decimal("1E-300"))[1] == 5
    assert read(encode(wide)) == wide
