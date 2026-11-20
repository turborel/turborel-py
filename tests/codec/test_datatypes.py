"""Tests of data types, read as the spec's table lays them out."""

from __future__ import annotations

import pytest

from turborel import OperationalError
from turborel._codec.datatypes import (
    ApproximateType,
    ArrayType,
    BinaryType,
    BooleanType,
    CharacterType,
    DatetimeType,
    DecFloatType,
    ExactType,
    IntervalField,
    IntervalType,
    JsonType,
    LobType,
    Moment,
    MultisetType,
    PluginType,
    QualifiedName,
    Qualifier,
    ReferenceType,
    RowField,
    RowType,
    StructuredType,
    UuidType,
    XmlPrimary,
    XmlSchemaName,
    XmlSecondary,
    XmlType,
    read_data_type,
)
from turborel._codec.fields import Reader


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def text(s: str) -> bytes:
    """A string: its length, then its UTF-8."""
    return u32(len(s.encode())) + s.encode()


def read(data: bytes) -> object:
    """The one data type `data` holds, all of it read."""
    r = Reader(data, "reply")
    data_type = read_data_type(r)
    r.finish()
    return data_type


SCALARS = [
    (
        bytes([1]) + u32(4) + bytes([0]),
        CharacterType(varying=False, length=4, octets=False),
    ),
    (
        bytes([5]) + u32(10) + bytes([1]),
        CharacterType(varying=True, length=10, octets=True),
    ),
    (bytes([2]) + u32(9) + u32(2), ExactType(9, 2)),
    (bytes([3]) + u32(53), ApproximateType(53)),
    (bytes([6]) + u32(16), BinaryType(varying=False, length=16)),
    (bytes([7]) + u32(3), BinaryType(varying=True, length=3)),
    (bytes([8]) + u32(0), DatetimeType(Moment.DATE, zoned=False, precision=0)),
    (bytes([9]) + u32(2), DatetimeType(Moment.TIME, zoned=False, precision=2)),
    (bytes([10]) + u32(0), DatetimeType(Moment.TIME, zoned=True, precision=0)),
    (bytes([11]) + u32(6), DatetimeType(Moment.TIMESTAMP, zoned=False, precision=6)),
    (bytes([12]) + u32(3), DatetimeType(Moment.TIMESTAMP, zoned=True, precision=3)),
    (bytes([14]), BooleanType()),
    (bytes([15]) + u32(34), DecFloatType(34)),
    (
        bytes([18]) + (1 << 40).to_bytes(8, "little") + bytes([0]),
        LobType(binary=False, length=1 << 40, octets=False),
    ),
    (
        bytes([19]) + (5).to_bytes(8, "little") + bytes([1]),
        LobType(binary=True, length=5, octets=True),
    ),
    (bytes([25]), JsonType()),
    (bytes([27]), UuidType()),
]


@pytest.mark.parametrize(("data", "expected"), SCALARS)
def test_scalar_types_read_by_their_tags(data: bytes, expected: object) -> None:
    """Verifies: [PROTOCOL Data types] tags 1 to 3, 5 to 12, 14, 15, 18, 19, 25.

    Each with what its kind writes after it: a length and its units, a
    precision and a scale, a precision; and UUID, tag 27, with nothing
    after it (turborel's RULES.md D184).
    """
    assert read(data) == expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ((0, 1, 2, 0), Qualifier(IntervalField.YEAR, IntervalField.MONTH, 2, 0)),
        ((2, 5, 9, 6), Qualifier(IntervalField.DAY, IntervalField.SECOND, 9, 6)),
        ((3, 3, 2, 0), Qualifier(IntervalField.HOUR, IntervalField.HOUR, 2, 0)),
        ((4, 5, 2, 3), Qualifier(IntervalField.MINUTE, IntervalField.SECOND, 2, 3)),
    ],
)
def test_an_interval_type_is_its_qualifier(
    fields: tuple[int, int, int, int], expected: Qualifier
) -> None:
    """Verifies: [PROTOCOL Data types] an interval's fields numbered 0 to 5.

    Start field, end field, leading precision, fractional precision, each a
    `u32`: 0 YEAR, 1 MONTH, 2 DAY, 3 HOUR, 4 MINUTE, 5 SECOND.
    """
    data = bytes([13]) + b"".join(u32(n) for n in fields)
    assert read(data) == IntervalType(expected)
    assert expected.year_month == (fields[0] <= 1)


def test_constructed_types_nest() -> None:
    """Verifies: [PROTOCOL Data types] arrays, rows and multisets of types.

    An array is its maximum cardinality, then its element type; a row
    its fields, each a name and a type; a multiset its element type.
    """
    boolean = bytes([14])
    array = bytes([16]) + u32(3) + bytes([16]) + u32(2) + boolean
    assert read(array) == ArrayType(3, ArrayType(2, BooleanType()))
    row = bytes([17]) + u32(2) + text("X") + bytes([1]) + u32(1) + bytes([0])
    row += text("Y") + boolean
    expected_row = RowType(
        (
            RowField("X", CharacterType(varying=False, length=1, octets=False)),
            RowField("Y", BooleanType()),
        )
    )
    assert read(row) == expected_row
    multiset = bytes([22, 22]) + bytes([1]) + u32(2) + bytes([0])
    assert read(multiset) == MultisetType(
        MultisetType(CharacterType(varying=False, length=2, octets=False))
    )


def test_plug_in_structured_and_reference_types() -> None:
    """Verifies: [PROTOCOL Data types] a plug-in's type, by name and parameters.

    A structured type is its schema and name and its proper supertypes; a
    reference type the referenced type's names, then whether it is
    scoped, and if so its scope.
    """
    plugin = bytes([4]) + text("POINT") + u32(2) + u32(1) + u32(7)
    assert read(plugin) == PluginType("POINT", (1, 7))
    names = text("S") + text("T") + u32(1) + text("S") + text("BASE")
    structured = StructuredType(QualifiedName("S", "T"), (QualifiedName("S", "BASE"),))
    assert read(bytes([23]) + names) == structured
    unscoped = bytes([24]) + names + bytes([0])
    assert read(unscoped) == ReferenceType(structured, None)
    scoped = bytes([24]) + names + bytes([1]) + text("S") + text("TT")
    assert read(scoped) == ReferenceType(structured, QualifiedName("S", "TT"))


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (bytes([26, 2, 0]), XmlType(XmlPrimary.SEQUENCE, XmlSecondary.UNTYPED, None)),
        (bytes([26, 0, 1]), XmlType(XmlPrimary.DOCUMENT, XmlSecondary.ANY, None)),
        (bytes([26, 1, 0]), XmlType(XmlPrimary.CONTENT, XmlSecondary.UNTYPED, None)),
        (
            bytes([26, 0, 2])
            + text("A")
            + text("S")
            + bytes([1])
            + text("urn:s")
            + bytes([1])
            + text("e"),
            XmlType(
                XmlPrimary.DOCUMENT,
                XmlSecondary.XMLSCHEMA,
                XmlSchemaName("A", "S", "urn:s", "e"),
            ),
        ),
        (
            bytes([26, 1, 2]) + text("A") + text("S") + bytes([0, 0]),
            XmlType(
                XmlPrimary.CONTENT,
                XmlSecondary.XMLSCHEMA,
                XmlSchemaName("A", "S", None, None),
            ),
        ),
    ],
)
def test_xml_types_carry_their_modifiers(data: bytes, expected: XmlType) -> None:
    """Verifies: [PROTOCOL Data types] XML's primary and secondary modifiers.

    Of XMLSCHEMA, the schema's schema and name, then its namespace and its
    element, each 0 for none or 1 and a string.
    """
    assert read(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        bytes([0]),
        bytes([20]),
        bytes([21]),
        bytes([28]),
        bytes([99]),
        bytes([1]) + u32(1) + bytes([2]),  # units neither 0 nor 1
        bytes([13]) + u32(6) + u32(0) + u32(2) + u32(0),  # no field 6
        bytes([16]) + u32(0) + bytes([14]),  # cardinality 0
        bytes([16]) + u32(65_536) + bytes([14]),  # past 65 535
        bytes([17]) + u32(0),  # a row of no fields
        bytes([4]) + text("P") + u32(3) + u32(1) + u32(2) + u32(3),  # three parameters
        bytes([4]) + text("P") + u32(1) + u32(0xFFFF_FFFF),  # the absent parameter
        bytes([24]) + text("S") + text("T") + u32(0) + bytes([2]),  # scoped 2
        bytes([26, 3, 0]),  # primary 3
        bytes([26, 0, 3]),  # secondary 3
        bytes([26, 2, 1]),  # SEQUENCE typed
        bytes([26, 0, 2]) + text("A") + text("S") + bytes([2]),  # marked 2
        bytes([1]) + u32(4),  # cut short
    ],
)
def test_a_type_that_cannot_be_read_fails_the_connection(data: bytes) -> None:
    """Verifies: [PROTOCOL Data types] a tag of no type, parameters out of range.

    [DESIGN] D13 turborel-protocol's bounds: cardinality 1 to 65 535, a
    row of one field or more, at most two parameters of a plug-in's type.
    """
    with pytest.raises(OperationalError) as failure:
        read(data)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")


def test_types_nest_at_most_16_deep() -> None:
    """Verifies: [DESIGN] D13 arrays of arrays nest 16 deep, and no deeper."""
    element = bytes([14])
    sixteen = (bytes([16]) + u32(1)) * 16 + element
    assert isinstance(read(sixteen), ArrayType)
    with pytest.raises(OperationalError):
        read(bytes([16]) + u32(1) + sixteen)
