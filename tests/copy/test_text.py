"""Tests of each value as an export writes it, against turborel-client's own text.

Each expected text is what turborel-client's export wrote for the same
value, read from turboreld at 1c4187e4.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest

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
from turborel._codec.datatypes import (
    ArrayType,
    DatetimeType,
    DecFloatType,
    IntervalType,
    JsonType,
    Moment,
    RowField,
    RowType,
)
from turborel._copy.exporting import csv_field, csv_record
from turborel._copy.text import approximate, approximate_literal, literal, numeral, text

Y2M = Qualifier(IntervalField.YEAR, IntervalField.MONTH, 2, 0)
D2S = Qualifier(IntervalField.DAY, IntervalField.SECOND, 2, 6)
D2H = Qualifier(IntervalField.DAY, IntervalField.HOUR, 2, 0)
SECOND = Qualifier(IntervalField.SECOND, IntervalField.SECOND, 2, 6)
SECOND_3 = Qualifier(IntervalField.SECOND, IntervalField.SECOND, 2, 3)
MINUTE = Qualifier(IntervalField.MINUTE, IntervalField.MINUTE, 2, 0)
DAY = Qualifier(IntervalField.DAY, IntervalField.DAY, 2, 0)
PLUS_2 = dt.timezone(dt.timedelta(hours=2))
MINUS_5_30 = dt.timezone(-dt.timedelta(hours=5, minutes=30))
DECFLOAT = DecFloatType(34)


def stamp(precision: int, *, zoned: bool = False) -> DatetimeType:
    """A TIMESTAMP's type."""
    return DatetimeType(Moment.TIMESTAMP, zoned, precision)


def clock(precision: int, *, zoned: bool = False) -> DatetimeType:
    """A TIME's type."""
    return DatetimeType(Moment.TIME, zoned, precision)


@pytest.mark.parametrize(
    ("value", "data_type", "written"),
    [
        (Decimal("1.50"), None, "1.50"),
        (Decimal("-0.05"), None, "-0.05"),
        (7, None, "7"),
        (0.5, None, "5E-1"),
        (123.456, None, "1.23456E2"),
        (1.0, None, "1E0"),
        (1e300, None, "1E300"),
        (1e20, None, "1E20"),
        (1.5e-7, None, "1.5E-7"),
        (-1.230000052601099e-4, None, "-1.230000052601099E-4"),
        (0.0, None, "0E0"),
        (Decimal("2.5"), DECFLOAT, "2.5"),
        (
            Decimal("1.000000000000000036432197315497742E-10"),
            DECFLOAT,
            "1.000000000000000036432197315497742E-10",
        ),
        (Decimal(123456789012), DECFLOAT, "123456789012"),
        (Decimal("1E-7"), DECFLOAT, "1E-7"),
        (Decimal("0.000001"), DECFLOAT, "0.000001"),
        (
            Decimal(9999999999999999455752309870428160),
            DECFLOAT,
            "9999999999999999455752309870428160",
        ),
        (
            Decimal("-1.19999999999999999201984849403306E-9"),
            DECFLOAT,
            "-1.19999999999999999201984849403306E-9",
        ),
        (Decimal(0), DECFLOAT, "0"),
        (b"\x00\xff", None, "00FF"),
        (b"", None, ""),
        (True, None, "TRUE"),
        (dt.date(2024, 2, 29), None, "2024-02-29"),
        (dt.date(1, 1, 1), None, "0001-01-01"),
        (dt.time(23, 59, 59, 500_000), clock(1), "23:59:59.5"),
        (dt.time(1, 2, 3), clock(0), "01:02:03"),
        (dt.datetime(2026, 11, 19, 1, 2, 3, 4), stamp(6), "2026-11-19 01:02:03.000004"),  # noqa: DTZ001
        (
            dt.datetime(2026, 11, 19, 1, 2, 3, tzinfo=PLUS_2),
            stamp(0, zoned=True),
            "2026-11-19 01:02:03+02:00",
        ),
        (
            dt.datetime(2026, 11, 19, 1, 2, 3, 500_000, tzinfo=PLUS_2),
            stamp(1, zoned=True),
            "2026-11-19 01:02:03.5+02:00",
        ),
        (
            dt.time(1, 2, 3, 250_000, tzinfo=MINUS_5_30),
            clock(2, zoned=True),
            "01:02:03.25-05:30",
        ),
        (Interval(Y2M, 14), IntervalType(Y2M), "1-02"),
        (Interval(Y2M, -14), IntervalType(Y2M), "-1-02"),
        (
            Interval(D2S, -((3 * 86_400 + 4 * 3_600 + 5 * 60 + 6) * 10**6 + 500_000)),
            None,
            "-3 04:05:06.500000",
        ),
        (Interval(MINUTE, 90 * 60 * 10**6), None, "90"),
        (Interval(DAY, 5 * 86_400 * 10**6), None, "5"),
        (Interval(SECOND, 1_250_000), None, "1.250000"),
        (Interval(SECOND, -500_000), None, "-0.500000"),
        (Interval(D2H, (2 * 86_400 + 3 * 3_600) * 10**6), None, "2 03"),
        (Interval(SECOND_3, 1_123_000), None, "1.123"),
        ([1, 2, 3], None, "ARRAY[1, 2, 3]"),
        (["a  ", "b,c"], None, "ARRAY['a  ', 'b,c']"),
        ((1, "a"), None, "ROW(1, 'a')"),
        (
            uuid.UUID("919108f7-52d1-4320-9bac-f847db4148a8"),
            None,
            "919108f7-52d1-4320-9bac-f847db4148a8",
        ),
        ({"a": 1, "b": "x"}, JsonType(), '{"a":1,"b":"x"}'),
        ({"a": [1, Decimal("2.5"), 'x"y']}, JsonType(), '{"a":[1,2.5,"x\\"y"]}'),
        (
            {
                "k": "é\n\x01",
                "n": Decimal("1.0"),
                "big": 12345678901234567890,
                "e": 100.0,
            },
            JsonType(),
            '{"k":"é\\n\\u0001","n":1.0,"big":12345678901234567890,"e":1.0E2}',
        ),
        (Xml('<a x="1">b</a>'), None, '<a x="1">b</a>'),
        ("ab  ", None, "ab  "),
        ([1.5], None, "ARRAY[1.5E0]"),
        ([100.0], None, "ARRAY[1E2]"),
        ([None, 1], None, "ARRAY[NULL, 1]"),
        ([dt.date(2024, 1, 2)], None, "ARRAY[DATE '2024-01-02']"),
        (
            [dt.datetime(2024, 1, 2, 3, 4, 5, 500_000)],  # noqa: DTZ001
            ArrayType(0, stamp(1)),
            "ARRAY[TIMESTAMP '2024-01-02 03:04:05.5']",
        ),
        (
            [dt.time(3, 4, 5, tzinfo=dt.timezone(dt.timedelta(hours=1)))],
            ArrayType(0, clock(0, zoned=True)),
            "ARRAY[TIME '03:04:05+01:00']",
        ),
        ([True, False], None, "ARRAY[TRUE, FALSE]"),
        ([b"\x0a"], None, "ARRAY[X'0A']"),
        ([Interval(Y2M, 14)], None, "ARRAY[INTERVAL '1-02' YEAR(2) TO MONTH]"),
        ([Interval(DAY, 3 * 86_400 * 10**6)], None, "ARRAY[INTERVAL '3' DAY(2)]"),
        (
            [Interval(D2S, -((3 * 86_400 + 4 * 3_600 + 5 * 60 + 6) * 10**6 + 500_000))],
            None,
            "ARRAY[INTERVAL -'3 04:05:06.500000' DAY(2) TO SECOND(6)]",
        ),
        (
            [Interval(SECOND, 1_500_000)],
            None,
            "ARRAY[INTERVAL '1.500000' SECOND(2, 6)]",
        ),
        (
            [Interval(D2H, (2 * 86_400 + 3 * 3_600) * 10**6)],
            None,
            "ARRAY[INTERVAL '2 03' DAY(2) TO HOUR]",
        ),
        ([[1, 2], [3]], None, "ARRAY[ARRAY[1, 2], ARRAY[3]]"),
        ([Decimal("2.5")], ArrayType(0, DECFLOAT), "ARRAY[CAST('2.5' AS DECFLOAT)]"),
        (
            [uuid.UUID("919108f7-52d1-4320-9bac-f847db4148a8")],
            None,
            "ARRAY[UUID '919108f7-52d1-4320-9bac-f847db4148a8']",
        ),
        ([{"a": 1}], ArrayType(0, JsonType()), "ARRAY[JSON('{\"a\":1}')]"),
        (["it's"], None, "ARRAY['it''s']"),
        (((1, 2), ["x"]), None, "ROW(ROW(1, 2), ARRAY['x'])"),
        (Multiset((1, 2, 2)), None, "MULTISET[1, 2, 2]"),
        ([], None, "ARRAY[]"),
        ([Decimal("1.50")], None, "ARRAY[1.50]"),
        ([Xml("<a/>")], None, "ARRAY[XMLPARSE(CONTENT '<a/>' PRESERVE WHITESPACE)]"),
        (
            ("x  ", None),
            RowType((RowField("A", clock(0)), RowField("B", clock(0)))),
            "ROW('x  ', NULL)",
        ),
    ],
)
def test_each_value_as_an_export_writes_it(
    value: object, data_type: object, written: str
) -> None:
    """Verifies: [CLIENT Copying and exporting] export as CSV, each value as text.

    As turborel-client writes it: exact numbers with their scale,
    approximate ones `<mantissa>E<exponent>`, binary strings in hex,
    datetimes to their precision, intervals by their fields, composites
    as literals.
    """
    assert text(value, data_type) == written  # type: ignore[arg-type]  # A type or None.


def test_the_rest_of_the_kinds() -> None:
    """Verifies: [CLIENT Copying and exporting] a locator, a plug-in's value, the rest.

    A large object by its locator said as what it is; a reference
    `REF(...)`; JSON's datetime has no text; null NULL.
    """
    assert (
        text(LobLocator(binary=False, locator=1, octets=8, characters=4))
        == "<CHARACTER LARGE OBJECT of 4 characters>"
    )
    assert (
        text(LobLocator(binary=True, locator=1, octets=8, characters=0))
        == "<BINARY LARGE OBJECT of 8 octets>"
    )
    assert text(PluginValue("ANN.POINT", "(1,2)", b"")) == "(1,2)"
    assert (
        literal(PluginValue("ANN.POINT", "(1,2)", b"")) == "CAST('(1,2)' AS ANN.POINT)"
    )
    assert text(Structured("ANN", "ADDRESS", ("Main", 3))) == "ANN.ADDRESS('Main', 3)"
    assert text(Reference(b"\x01\xab")) == "REF(01AB)"
    assert text(None) == "NULL"
    assert (
        text([dt.datetime(2024, 1, 2, 3, 4, 5, 120_000)])  # noqa: DTZ001
        == "ARRAY[TIMESTAMP '2024-01-02 03:04:05.12']"
    )
    assert text(dt.time(1, 2, 3)) == "01:02:03"
    assert text(dt.datetime(2024, 1, 2, 3, 4, 5), JsonType()).startswith("<")  # noqa: DTZ001
    assert text({"t": dt.date(2024, 1, 2)}, JsonType()).startswith("<")
    assert (
        text([1, {"a": None, "b": [True, False]}], JsonType())
        == '[1,{"a":null,"b":[true,false]}]'
    )
    assert text(Decimal("Infinity"), DECFLOAT) == "Infinity"
    assert (
        approximate(float("nan")),
        approximate(float("inf")),
        approximate(-float("inf")),
    ) == ("NaN", "inf", "-inf")
    assert (approximate(-0.0), approximate_literal(0.0), approximate_literal(1.5)) == (
        "-0E0",
        "0E0",
        "1.5E0",
    )
    assert numeral("5", -3) == "0.005"


def test_csv_fields_are_quoted_where_they_must_be() -> None:
    """Verifies: [CLIENT Copying and exporting] a CSV field quoted where it must be.

    RFC 4180 §2: where it holds a comma, a quote, a line break or spaces
    at either end, its quotes doubled; an empty string quoted; each
    record ended by CR LF.
    """
    assert csv_field("plain") == "plain"
    assert csv_field("a,b") == '"a,b"'
    assert csv_field('say "hi"') == '"say ""hi"""'
    assert csv_field(" pad") == '" pad"'
    assert csv_field("two\nlines") == '"two\nlines"'
    assert csv_field("") == '""'
    assert csv_record(["1", ""]) == b"1,\r\n"
