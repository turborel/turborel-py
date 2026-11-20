"""Datetimes, between their fields and Python's [PROTOCOL Values].

A date, a time and a timestamp are written alike: zoned, precision, the
zone's displacement in minutes, and the instant, microseconds in UTC.
turborel counts a timestamp's instant from 0001-01-01 00:00 UTC, a
time's from midnight UTC within a day, and a date's as its midnight's.
A value WITH TIME ZONE carries its own displacement; another carries the
one it is shown in, so its local fields are the instant moved by it.

A date reaches Python as a `datetime.date`; a time as a `datetime.time`,
with a fixed `timezone` if zoned; a timestamp as a `datetime.datetime`,
aware if zoned and naive otherwise. Python keeps microseconds, as
turborel does, so nothing is lost but the precision a value is shown
with.
"""

from __future__ import annotations

import datetime as dt
from typing import Final, NamedTuple

from turborel._codec.datatypes import Moment
from turborel._errors import DATETIME_FIELD_OVERFLOW, data_error, unsendable

SECONDS_PER_DAY: Final = 86_400
MICROS_PER_SECOND: Final = 1_000_000
MICROS_PER_MINUTE: Final = 60 * MICROS_PER_SECOND
MICROS_PER_DAY: Final = 24 * 60 * MICROS_PER_MINUTE

MAX_TIME_PRECISION: Final = 6
"""The digits of a second's fraction turborel keeps: microseconds.

The precision the driver sends of a time or a timestamp, all Python's
values hold.
"""

EPOCH: Final = dt.datetime(1, 1, 1)  # noqa: DTZ001  # turborel's epoch, local fields.
"""0001-01-01 00:00, from which an instant counts."""

_ONE_MINUTE: Final = dt.timedelta(minutes=1)


class Fields(NamedTuple):
    """A datetime's fields, as the protocol writes them."""

    moment: Moment
    zoned: bool
    precision: int
    zone: int
    """The displacement in minutes: its own if zoned, else as shown."""
    utc: int
    """The instant: microseconds in UTC."""


Datetime = dt.date | dt.time | dt.datetime
"""A datetime value as Python holds it."""


def to_python(fields: Fields) -> Datetime:
    """The Python value of `fields`.

    Raises:
        OverflowError: If its fields lie beyond Python's years 1 to 9999.
        ValueError: The same, or of a displacement of a day or more.
    """
    local = fields.utc + fields.zone * MICROS_PER_MINUTE
    if fields.moment == Moment.DATE:
        return dt.date.fromordinal(local // MICROS_PER_DAY + 1)
    zone = dt.timezone(dt.timedelta(minutes=fields.zone)) if fields.zoned else None
    if fields.moment == Moment.TIME:
        held = (EPOCH + dt.timedelta(microseconds=local % MICROS_PER_DAY)).time()
        return held.replace(tzinfo=zone)
    return (EPOCH + dt.timedelta(microseconds=local)).replace(tzinfo=zone)


def from_python(value: Datetime) -> Fields:
    """The fields of `value`, a date, a time or a datetime.

    Raises:
        DataError: SQLSTATE 22008, of a displacement that is not whole
            minutes.
        ProgrammingError: SQLSTATE 07006, of a time whose zone gives no
            fixed displacement without a date.
    """
    if isinstance(value, dt.datetime):
        return _timestamp(value)
    if isinstance(value, dt.time):
        return _time(value)
    utc = (value.toordinal() - 1) * MICROS_PER_DAY
    return Fields(Moment.DATE, zoned=False, precision=0, zone=0, utc=utc)


def _minutes(offset: dt.timedelta) -> int:
    """The whole minutes of a zone's displacement."""
    if offset % _ONE_MINUTE:
        msg = f"a displacement of {offset} is not whole minutes"
        raise data_error(msg, DATETIME_FIELD_OVERFLOW)
    return offset // _ONE_MINUTE


def _micros(span: dt.timedelta) -> int:
    """The microseconds of `span`, exactly."""
    return (
        span.days * SECONDS_PER_DAY + span.seconds
    ) * MICROS_PER_SECOND + span.microseconds


def _timestamp(value: dt.datetime) -> Fields:
    offset = value.utcoffset()
    local = _micros(value.replace(tzinfo=None) - EPOCH)
    if offset is None:
        return Fields(
            Moment.TIMESTAMP,
            zoned=False,
            precision=MAX_TIME_PRECISION,
            zone=0,
            utc=local,
        )
    zone = _minutes(offset)
    utc = local - zone * MICROS_PER_MINUTE
    return Fields(
        Moment.TIMESTAMP, zoned=True, precision=MAX_TIME_PRECISION, zone=zone, utc=utc
    )


def _time(value: dt.time) -> Fields:
    local = _micros(dt.datetime.combine(EPOCH, value.replace(tzinfo=None)) - EPOCH)
    if value.tzinfo is None:
        return Fields(
            Moment.TIME, zoned=False, precision=MAX_TIME_PRECISION, zone=0, utc=local
        )
    offset = value.utcoffset()
    if offset is None:
        msg = f"a time's zone, {value.tzinfo}, gives no displacement without a date"
        raise unsendable(msg)
    zone = _minutes(offset)
    utc = (local - zone * MICROS_PER_MINUTE) % MICROS_PER_DAY
    return Fields(
        Moment.TIME, zoned=True, precision=MAX_TIME_PRECISION, zone=zone, utc=utc
    )
