"""Tests of datetimes, between their fields and Python's."""

from __future__ import annotations

import datetime as dt

import pytest

from turborel import DataError
from turborel._codec.datatypes import Moment
from turborel._codec.datetimes import (
    MICROS_PER_DAY,
    MICROS_PER_MINUTE,
    Fields,
    from_python,
    to_python,
)

# turborel's least and greatest displacements: -12:59 and +14:00.
WEST = dt.timezone(-dt.timedelta(hours=12, minutes=59))
EAST = dt.timezone(dt.timedelta(hours=14))
LAST_DAY = 3_652_058  # 9999-12-31, in days from 0001-01-01


def _no_displacement(_: dt.tzinfo, __: dt.datetime | None) -> None:
    """No displacement, with no date to say it."""


# A zone that gives no displacement without a date, as a zone of rules
# does to a time alone.
NoDisplacement = type("NoDisplacement", (dt.tzinfo,), {"utcoffset": _no_displacement})


@pytest.mark.parametrize(
    ("value", "fields"),
    [
        (
            dt.date(1, 1, 1),
            Fields(Moment.DATE, zoned=False, precision=0, zone=0, utc=0),
        ),
        (
            dt.date(9999, 12, 31),
            Fields(
                Moment.DATE,
                zoned=False,
                precision=0,
                zone=0,
                utc=LAST_DAY * MICROS_PER_DAY,
            ),
        ),
        (
            dt.datetime(1, 1, 1),  # noqa: DTZ001  # A timestamp without a zone.
            Fields(Moment.TIMESTAMP, zoned=False, precision=6, zone=0, utc=0),
        ),
        (
            dt.datetime(1, 1, 1, 0, 0, 1, 5),  # noqa: DTZ001
            Fields(Moment.TIMESTAMP, zoned=False, precision=6, zone=0, utc=1_000_005),
        ),
        (
            dt.datetime(2000, 1, 1, tzinfo=WEST),
            Fields(
                Moment.TIMESTAMP,
                zoned=True,
                precision=6,
                zone=-779,
                utc=(730_119 * MICROS_PER_DAY) + 779 * MICROS_PER_MINUTE,
            ),
        ),
        (
            dt.datetime(2000, 1, 1, tzinfo=EAST),
            Fields(
                Moment.TIMESTAMP,
                zoned=True,
                precision=6,
                zone=840,
                utc=(730_119 * MICROS_PER_DAY) - 840 * MICROS_PER_MINUTE,
            ),
        ),
        (
            dt.time(23, 59, 59, 500_000),
            Fields(
                Moment.TIME,
                zoned=False,
                precision=6,
                zone=0,
                utc=MICROS_PER_DAY - 500_000,
            ),
        ),
        (
            dt.time(0, 0, tzinfo=EAST),
            Fields(
                Moment.TIME,
                zoned=True,
                precision=6,
                zone=840,
                utc=10 * 60 * MICROS_PER_MINUTE,
            ),
        ),
    ],
)
def test_datetimes_are_their_instant_in_utc(value: object, fields: Fields) -> None:
    """Verifies: [PROTOCOL Values] zoned, precision, displacement, instant in UTC.

    A date's instant is its midnight's from 0001-01-01; a time's counts
    from midnight UTC within a day; a timestamp's from 0001-01-01 UTC.
    Displacements -12:59 and +14:00, turborel's bounds, both ways.
    """
    assert isinstance(value, dt.date | dt.time)
    assert from_python(value) == fields
    back = to_python(fields)
    assert back == value
    assert type(back) is type(value)
    if isinstance(value, dt.datetime | dt.time):
        assert back.utcoffset() == value.utcoffset()  # type: ignore[union-attr]  # Both have one.


def test_a_value_without_a_zone_is_shown_in_its_displacement() -> None:
    """Verifies: [PROTOCOL Values] without a zone, the displacement it is shown in.

    The local fields are the instant moved by the displacement, and the
    value is naive.
    """
    shown = Fields(Moment.TIMESTAMP, zoned=False, precision=0, zone=60, utc=0)
    assert to_python(shown) == dt.datetime(1, 1, 1, 1, 0)  # noqa: DTZ001
    late = Fields(Moment.TIME, zoned=False, precision=0, zone=-60, utc=0)
    assert to_python(late) == dt.time(23, 0)


def test_python_s_years_bound_what_is_read() -> None:
    """Verifies: [PROTOCOL Values] an instant past year 9999 is not a Python value."""
    beyond = Fields(
        Moment.DATE,
        zoned=False,
        precision=0,
        zone=0,
        utc=(LAST_DAY + 1) * MICROS_PER_DAY,
    )
    with pytest.raises((OverflowError, ValueError)):
        to_python(beyond)


def test_a_displacement_of_part_of_a_minute_is_refused() -> None:
    """Verifies: [PROTOCOL Values] the displacement is whole minutes.

    [DESIGN] D13 refused before it is sent, SQLSTATE 22008.
    """
    odd = dt.timezone(dt.timedelta(seconds=30))
    with pytest.raises(DataError) as failure:
        from_python(dt.datetime(2000, 1, 1, tzinfo=odd))
    assert failure.value.sqlstate == "22008"


def test_a_time_whose_zone_needs_a_date_is_refused() -> None:
    """Verifies: [DESIGN] D13 a time's zone of no fixed displacement, 22000."""
    with pytest.raises(DataError) as failure:
        from_python(dt.time(12, 0, tzinfo=NoDisplacement()))
    assert failure.value.sqlstate == "22000"
