"""Tests of declared types: tail 19 of Prepared and Description, types written."""

from __future__ import annotations

import pytest
from tests.kit import text, u32

from turborel import NUMBER, STRING, OperationalError, TypeCode
from turborel._codec.composites import Column, Declared
from turborel._codec.datatypes import (
    ApproximateType,
    ArrayType,
    BinaryType,
    BooleanType,
    CharacterType,
    DataType,
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
)
from turborel._codec.replies import Description, Prepared, decode
from turborel._codec.written import written

INTEGER_COLUMN = u32(1) + b"\x01" + text("K") + b"\x02" + u32(10) + u32(0) + b"\x00"
SHAPE = StructuredType(QualifiedName("S", "SHAPE"), ())


def test_tail_19_gives_each_column_its_declared_type() -> None:
    """Verifies: [PROTOCOL Declared types] tail 19, of a Description and a Prepared.

    [PROTOCOL The tail] 19 declared: a count, then each column's name as
    DATA_TYPE gives it and its type as SQL writes it; without it, the
    columns alone.
    """
    declared = b"\x13" + u32(1) + text("INTEGER") + text("INTEGER")
    told = decode(ord("D"), INTEGER_COLUMN + declared)
    assert isinstance(told, Description)
    assert told.columns[0].declared == Declared("INTEGER", "INTEGER")
    assert told.columns[0].type_written == "INTEGER"
    prepared = decode(ord("P"), u32(1) + u32(0) + INTEGER_COLUMN + declared)
    assert isinstance(prepared, Prepared)
    assert prepared.columns[0].declared == Declared("INTEGER", "INTEGER")
    plain = decode(ord("D"), INTEGER_COLUMN)
    assert isinstance(plain, Description)
    assert plain.columns[0].declared is None
    assert plain.columns[0].type_written == "NUMERIC(10,0)"


@pytest.mark.parametrize(
    "tail",
    [
        b"\x13" + u32(2) + text("A") + text("A") + text("B") + text("B"),
        b"\x13" + u32(0),
        b"\x12",
    ],
    ids=["two for one column", "none for one column", "a tag not Description's"],
)
def test_a_declared_tail_not_one_for_each_column_is_malformed(tail: bytes) -> None:
    """Verifies: [PROTOCOL Declared types] one declared type for each column, in order.

    Another count, or another tag, is a malformed frame: SQLCODE -919,
    SQLSTATE 08006.
    """
    with pytest.raises(OperationalError) as failure:
        decode(ord("D"), INTEGER_COLUMN + tail)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")


DAY_SECOND = Qualifier(IntervalField.DAY, IntervalField.SECOND, 2, 6)


@pytest.mark.parametrize(
    ("data_type", "sql"),
    [
        (CharacterType(varying=False, length=4, octets=False), "CHARACTER(4)"),
        (
            CharacterType(varying=True, length=16, octets=True),
            "CHARACTER VARYING(16 OCTETS)",
        ),
        (ExactType(10, 0), "NUMERIC(10,0)"),
        (ApproximateType(53), "FLOAT(53)"),
        (PluginType("ST_GEOMETRY", ()), "ST_GEOMETRY"),
        (BinaryType(varying=False, length=16), "BINARY(16)"),
        (BinaryType(varying=True, length=255), "BINARY VARYING(255)"),
        (DatetimeType(Moment.DATE, zoned=False, precision=0), "DATE"),
        (DatetimeType(Moment.TIME, zoned=True, precision=3), "TIME(3) WITH TIME ZONE"),
        (DatetimeType(Moment.TIMESTAMP, zoned=False, precision=6), "TIMESTAMP(6)"),
        (IntervalType(DAY_SECOND), "INTERVAL DAY(2) TO SECOND(6)"),
        (
            IntervalType(Qualifier(IntervalField.YEAR, IntervalField.MONTH, 4, 0)),
            "INTERVAL YEAR(4) TO MONTH",
        ),
        (
            IntervalType(Qualifier(IntervalField.SECOND, IntervalField.SECOND, 2, 6)),
            "INTERVAL SECOND(2, 6)",
        ),
        (
            IntervalType(Qualifier(IntervalField.DAY, IntervalField.DAY, 3, 0)),
            "INTERVAL DAY(3)",
        ),
        (BooleanType(), "BOOLEAN"),
        (DecFloatType(34), "DECFLOAT(34)"),
        (ArrayType(3, ExactType(10, 0)), "NUMERIC(10,0) ARRAY[3]"),
        (
            RowType((RowField("X", BooleanType()), RowField("Y", JsonType()))),
            "ROW(X BOOLEAN, Y JSON)",
        ),
        (
            LobType(binary=False, length=1048576, octets=False),
            "CHARACTER LARGE OBJECT(1048576)",
        ),
        (
            LobType(binary=False, length=64, octets=True),
            "CHARACTER LARGE OBJECT(64 OCTETS)",
        ),
        (LobType(binary=True, length=65536, octets=True), "BINARY LARGE OBJECT(65536)"),
        (MultisetType(BooleanType()), "BOOLEAN MULTISET"),
        (SHAPE, "S.SHAPE"),
        (ReferenceType(SHAPE, None), "REF(S.SHAPE)"),
        (
            ReferenceType(SHAPE, QualifiedName("S", "SHAPES")),
            "REF(S.SHAPE) SCOPE S.SHAPES",
        ),
        (JsonType(), "JSON"),
        (UuidType(), "UUID"),
        (
            XmlType(XmlPrimary.DOCUMENT, XmlSecondary.UNTYPED, None),
            "XML(DOCUMENT(UNTYPED))",
        ),
        (XmlType(XmlPrimary.CONTENT, XmlSecondary.ANY, None), "XML(CONTENT(ANY))"),
        (XmlType(XmlPrimary.SEQUENCE, XmlSecondary.UNTYPED, None), "XML(SEQUENCE)"),
        (
            XmlType(
                XmlPrimary.DOCUMENT,
                XmlSecondary.XMLSCHEMA,
                XmlSchemaName("S", "PO", "urn:o'", 'p"o'),
            ),
            "XML(DOCUMENT(XMLSCHEMA ID S.PO NAMESPACE 'urn:o''' ELEMENT \"p\"\"o\"))",
        ),
        (
            XmlType(
                XmlPrimary.CONTENT,
                XmlSecondary.XMLSCHEMA,
                XmlSchemaName("S", "PO", "", None),
            ),
            "XML(CONTENT(XMLSCHEMA ID S.PO NO NAMESPACE))",
        ),
    ],
)
def test_a_type_not_declared_is_written_as_its_tag_says(
    data_type: DataType, sql: str
) -> None:
    """Verifies: [CLIENT Prepared statements] the type written, else as the tag says.

    Turborel's display of each data type, an exact numeric type as
    NUMERIC and an approximate one as FLOAT, as a type read from a reply
    is (RULES.md D13).
    """
    assert written(data_type) == sql


def test_a_type_code_is_the_declared_type_and_its_kind() -> None:
    """Verifies: [DESIGN] D2 `description`'s type code, of the declared type.

    Its string the type as declared, else as its data type says; equal
    to the type object of its kind either way.
    """
    told = TypeCode.of(
        Column(
            "K",
            ExactType(10, 0),
            not_null=True,
            declared=Declared("INTEGER", "INTEGER"),
        )
    )
    assert (told.name, str(told), told == NUMBER, told == STRING) == (
        "INTEGER",
        "INTEGER",
        True,
        False,
    )
    plain = TypeCode.of(Column("K", ExactType(10, 0), not_null=True))
    assert (plain.name, plain.written) == (None, "NUMERIC(10,0)")
    assert plain == NUMBER
    assert (
        TypeCode.of(
            Column(None, LobType(binary=False, length=1, octets=False), not_null=False)
        )
        == STRING
    )
