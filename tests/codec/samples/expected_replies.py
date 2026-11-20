"""What each server frame of the sample file decodes to, written from its meaning.

Each entry is the reply a sample's last field, `means`, describes, by
the sample's name [PROTOCOL Sample frames]. A compressed sample's entry
is the reply it inflates to.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Final

from turborel import (
    Interval,
    IntervalField,
    LobLocator,
    Multiset,
    PluginValue,
    Qualifier,
    Reference,
    Structured,
    Xml,
)
from turborel._codec.composites import Column, Declared, Parameter
from turborel._codec.datatypes import (
    ApproximateType,
    ArrayType,
    BinaryType,
    BooleanType,
    CharacterType,
    DatetimeType,
    DecFloatType,
    ExactType,
    IntervalType,
    JsonType,
    LobType,
    Moment,
    MultisetType,
    PluginType,
    QualifiedName,
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
from turborel._codec.failures import Diagnostics, Failure, Notice
from turborel._codec.replies import (
    Challenge,
    Complete,
    Description,
    Error,
    LobCreated,
    LobData,
    Pong,
    Prepared,
    Ready,
    Reply,
    Rows,
    Status,
    Suspended,
    Timing,
)

INTEGER: Final = ExactType(10, 0)
VARYING_5: Final = CharacterType(varying=True, length=5, octets=False)
LONGEST_VARYING: Final = CharacterType(varying=True, length=32767, octets=False)
PARAMETERS: Final = (
    Parameter(varying=True, data_type=LONGEST_VARYING),
    Parameter(varying=False, data_type=INTEGER),
)
TWO_COLUMNS: Final = (
    Column("K", INTEGER, not_null=True),
    Column(None, VARYING_5, not_null=False),
)
SHAPE: Final = StructuredType(
    QualifiedName("S", "SHAPE"), (QualifiedName("S", "FIGURE"),)
)
UNIQUE: Final = "a unique constraint is broken"
TRUNCATED: Final = "string data, right truncation"
RULE: Final = "ISO/IEC 9075-2:2023 §11.7"
POINT: Final = bytes.fromhex(
    "1a00000001e61000000101000000000000000000f03f0000000000000040"
)
REPEATED: Final = "abcdefgh" * 4


def declared(name: str, written: str | None = None) -> Declared:
    """The declared type `name`, written as `written`, else as `name`."""
    return Declared(name, written or name)


def one(data_type: object) -> Description:
    """A Description of one nullable column C of type `data_type`."""
    return Description((Column("C", data_type, not_null=False),))  # type: ignore[arg-type]


def value(v: object) -> Rows:
    """Rows, one row of one value, `v`."""
    return Rows(((v,),))


def complete(sqlstate: str = "00000", **told: object) -> Complete:
    """A Complete of SQLCODE 0, or 100 of 02000, and what its tail told."""
    sqlcode = 100 if sqlstate == "02000" else 0
    active = bool(told.pop("active", False))
    return Complete(sqlcode, sqlstate, active, **told)  # type: ignore[arg-type]


def failure(*, cited: bool = False, diagnostics: Diagnostics | None = None) -> Failure:
    """The unique constraint's failure, cited and placed if `cited`."""
    if not cited:
        return Failure(-803, "23505", UNIQUE, None, None, active=False)
    return Failure(
        -803, "23505", UNIQUE, RULE, 12, active=True, diagnostics=diagnostics
    )


DIAGNOSED: Final = Diagnostics(
    severity="ERROR",
    detail="key (K)=(1)",
    hint="choose another K",
    context="trigger S.TR",
    schema="S",
    table="T",
    column="K",
    data_type="INTEGER",
    constraint="T_PK",
)

MESSAGES: Final[dict[str, Reply]] = {
    "challenge": Challenge(b"r=abcdef,s=c2FsdA==,i=4096"),
    "ready": Ready("ANN", b"\xa5" * 16, ("ping",), "turborel 0.0.0 (alpha)"),
    "prepared": Prepared(1, PARAMETERS, TWO_COLUMNS),
    "prepared-empty": Prepared(2, (), ()),
    "prepared-declared": Prepared(
        1,
        PARAMETERS,
        (Column("K", INTEGER, not_null=True, declared=declared("INTEGER")),),
    ),
    "description": Description(TWO_COLUMNS),
    "description-empty": Description(()),
    "description-declared": Description(
        (
            Column("I", INTEGER, not_null=True, declared=declared("INTEGER")),
            Column("S", ExactType(5, 0), not_null=False, declared=declared("SMALLINT")),
            Column("B", ExactType(18, 0), not_null=False, declared=declared("BIGINT")),
            Column(
                "D",
                ExactType(9, 2),
                not_null=False,
                declared=declared("DECIMAL", "DECIMAL(9,2)"),
            ),
            Column("R", ApproximateType(24), not_null=False, declared=declared("REAL")),
            Column(
                "P",
                ApproximateType(53),
                not_null=False,
                declared=declared("DOUBLE PRECISION"),
            ),
            Column(
                "M",
                ExactType(9, 2),
                not_null=False,
                declared=declared("USER-DEFINED", "S.MONEY"),
            ),
        )
    ),
    "rows": Rows(((1, "a"), (None, ""))),
    "rows-none": Rows(()),
    "rows-empty-row": Rows(((),)),
    "suspended": Suspended(),
    "complete": complete(),
    "complete-active": complete(active=True),
    "complete-no-data": complete("02000"),
    "complete-position": complete(position=4711),
    "complete-more": complete(more=True),
    "complete-rows": complete(rows=1),
    "complete-every": complete(
        position=4711,
        more=True,
        rows=3,
        generated=("7", "8"),
        time=Timing(1500, 20, 300),
    ),
    "complete-conditions": complete(
        "01004",
        active=True,
        conditions=(Failure(0, "01004", TRUNCATED, None, None, active=True),),
    ),
    "error": Error(failure()),
    "error-cited": Error(failure(cited=True)),
    "error-diagnostics": Error(failure(cited=True, diagnostics=DIAGNOSED)),
    "error-connection": Error(
        Failure(-919, "08006", "a malformed message", None, None, active=False)
    ),
    "lob-data": LobData("aé".encode()),
    "lob-data-empty": LobData(b""),
    "lob-locator": LobCreated(4),
    "notice": Notice("01004", TRUNCATED, Diagnostics()),
    "notice-diagnostics": Notice(
        "01004", TRUNCATED, Diagnostics(severity="WARNING", detail="cut to 4")
    ),
    "pong": Pong(),
    "status-server-version": Status("SERVER_VERSION", "turborel 0.0.0 (alpha)"),
    "status-authorization": Status("AUTHORIZATION", "ANN"),
    "status-schema": Status("SCHEMA", "ANN"),
    "status-read-only": Status("READ_ONLY", "NO"),
    "status-server-read-only": Status("SERVER_READ_ONLY", "YES"),
    "status-catalog": Status("CATALOG", "TURBOREL"),
    "status-owner": Status("OWNER", "YES"),
    "status-time-zone": Status("SESSION.TIME_ZONE", "+05:30"),
    "status-null": Status("STATEMENT.TIMEOUT_MS", ""),
    "rows-compressed": Rows(tuple((n, REPEATED) for n in range(64))),
}
"""Each request's and message's sample, but the data types' and values'."""

YEAR_MONTH: Final = Qualifier(IntervalField.YEAR, IntervalField.MONTH, 4, 0)
DAY_SECOND: Final = Qualifier(IntervalField.DAY, IntervalField.SECOND, 2, 6)

TYPES: Final[dict[str, Reply]] = {
    "description-character": one(CharacterType(varying=False, length=4, octets=False)),
    "description-character-octets": one(
        CharacterType(varying=False, length=16, octets=True)
    ),
    "description-exact": one(ExactType(9, 2)),
    "description-approximate": one(ApproximateType(53)),
    "description-plugin-type": one(PluginType("ST_GEOMETRY", ())),
    "description-varying": one(CharacterType(varying=True, length=20, octets=False)),
    "description-binary": one(BinaryType(varying=False, length=16)),
    "description-binary-varying": one(BinaryType(varying=True, length=255)),
    "description-date": one(DatetimeType(Moment.DATE, zoned=False, precision=0)),
    "description-time": one(DatetimeType(Moment.TIME, zoned=False, precision=3)),
    "description-time-zoned": one(DatetimeType(Moment.TIME, zoned=True, precision=0)),
    "description-timestamp": one(
        DatetimeType(Moment.TIMESTAMP, zoned=False, precision=6)
    ),
    "description-timestamp-zoned": one(
        DatetimeType(Moment.TIMESTAMP, zoned=True, precision=6)
    ),
    "description-interval-year-month": one(IntervalType(YEAR_MONTH)),
    "description-interval-day-second": one(IntervalType(DAY_SECOND)),
    "description-boolean": one(BooleanType()),
    "description-decfloat": one(DecFloatType(34)),
    "description-clob": one(LobType(binary=False, length=1048576, octets=False)),
    "description-blob": one(LobType(binary=True, length=65536, octets=True)),
    "description-json": one(JsonType()),
    "description-uuid": one(UuidType()),
    "description-array": one(ArrayType(3, BooleanType())),
    "description-row": one(
        RowType(
            (
                RowField("X", CharacterType(varying=True, length=3, octets=False)),
                RowField("Y", BooleanType()),
            )
        )
    ),
    "description-multiset": one(
        MultisetType(CharacterType(varying=False, length=2, octets=False))
    ),
    "description-structured": one(SHAPE),
    "description-reference": one(ReferenceType(SHAPE, None)),
    "description-reference-scoped": one(
        ReferenceType(SHAPE, QualifiedName("S", "SHAPES"))
    ),
    "description-xml-document": one(
        XmlType(XmlPrimary.DOCUMENT, XmlSecondary.UNTYPED, None)
    ),
    "description-xml-content": one(XmlType(XmlPrimary.CONTENT, XmlSecondary.ANY, None)),
    "description-xml-sequence": one(
        XmlType(XmlPrimary.SEQUENCE, XmlSecondary.UNTYPED, None)
    ),
    "description-xml-schema": one(
        XmlType(
            XmlPrimary.DOCUMENT,
            XmlSecondary.XMLSCHEMA,
            XmlSchemaName("S", "PO", "urn:po", None),
        )
    ),
    "description-distinct": one(CharacterType(varying=True, length=4, octets=False)),
    "description-declared-array": Description(
        (
            Column(
                "C",
                ArrayType(3, INTEGER),
                not_null=False,
                declared=declared("ARRAY", "INTEGER ARRAY[3]"),
            ),
        )
    ),
}
"""Each data type's sample, a Description of one column."""

UTC: Final = dt.UTC

VALUES: Final[dict[str, Reply]] = {
    "value-null": value(None),
    "value-character": value("abc"),
    "value-character-empty": value(""),
    "value-character-utf8": value("é€"),
    "value-exact": value(Decimal("123.45")),
    "value-exact-negative": value(-1),
    "value-exact-largest": value(2**127 - 1),
    "value-approximate": value(1.5),
    "value-approximate-negative-zero": value(-0.0),
    "value-plugin": value(PluginValue("ST_GEOMETRY", "POINT (1 2)", POINT)),
    "value-binary": value(bytes.fromhex("DEADBEEF")),
    "value-binary-empty": value(b""),
    "value-date": value(dt.date(2024, 2, 29)),
    "value-time": value(dt.time(12, 34, 56, 500000)),
    "value-time-zoned": value(
        dt.time(12, 34, 56, tzinfo=dt.timezone(dt.timedelta(minutes=330)))
    ),
    "value-timestamp": value(dt.datetime(2024, 2, 29, 12, 34, 56, 123456)),  # noqa: DTZ001
    "value-timestamp-zoned": value(
        dt.datetime(
            2024, 2, 29, 12, 34, 56, tzinfo=dt.timezone(dt.timedelta(minutes=-480))
        )
    ),
    "value-timestamp-earliest": value(dt.datetime(1, 1, 1)),  # noqa: DTZ001
    "value-interval-year-month": value(
        Interval(Qualifier(IntervalField.YEAR, IntervalField.MONTH, 2, 0), -14)
    ),
    "value-interval-day-second": value(Interval(DAY_SECOND, 93784500000)),
    "value-true": value(True),  # noqa: FBT003  # The value itself.
    "value-false": value(False),  # noqa: FBT003
    "value-decfloat": value(Decimal("-1.5")),
    "value-array": value([1, None]),
    "value-array-empty": value([]),
    "value-row": value(("x", True)),
    "value-lob-character": value("aé"),
    "value-lob-binary": value(b"\x00\xff"),
    "value-lob-locator": value(
        LobLocator(binary=False, locator=7, octets=300000, characters=200000)
    ),
    "value-multiset": value(Multiset(("a", "a"))),
    "value-structured": value(Structured("S", "SHAPE", (3, None))),
    "value-reference": value(Reference(bytes.fromhex("0102030405060708"))),
    "value-json": value({"a": [1, "x"]}),
    "value-json-scalars": value([None, True, False, -2, Decimal("1.50"), "", {}]),
    "value-xml": value(Xml("<a>&lt;</a>")),
    "value-uuid": value(uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")),
}
"""Each value tag's sample, Rows of one row of one value."""

REPLIES: Final[dict[str, Reply]] = {**MESSAGES, **TYPES, **VALUES}
"""Every server sample's reply."""
