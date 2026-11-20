"""PEP 249's type objects and constructors [DESIGN] D2.

A column's `type_code` in a cursor's `description` is the data type the
server gave it; each type object compares equal to the type codes of its
kind, as PEP 249 asks: STRING to the character string types, BINARY to
the binary string types, NUMBER to the numeric types, DATETIME to the
datetime and interval types, ROWID to a reference type.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from turborel._codec.datatypes import (
    ApproximateType,
    BinaryType,
    CharacterType,
    DatetimeType,
    DecFloatType,
    ExactType,
    IntervalType,
    LobType,
    ReferenceType,
)


class DBAPITypeObject:
    """A kind of column type, equal to each type code of its kind."""

    def __init__(self, name: str, *kinds: type) -> None:
        """The kind `name`, of the data types of `kinds`."""
        self.name = name
        self._kinds = kinds

    def __repr__(self) -> str:
        """Its name."""
        return self.name

    def __eq__(self, other: object) -> bool:
        """Whether `other` is a type code of this kind."""
        if isinstance(other, LobType):
            return self.name == ("BINARY" if other.binary else "STRING")
        return isinstance(other, self._kinds)

    def __hash__(self) -> int:
        """Of its name."""
        return hash(self.name)


STRING: Final = DBAPITypeObject("STRING", CharacterType)
BINARY: Final = DBAPITypeObject("BINARY", BinaryType)
NUMBER: Final = DBAPITypeObject("NUMBER", ExactType, ApproximateType, DecFloatType)
DATETIME: Final = DBAPITypeObject("DATETIME", DatetimeType, IntervalType)
ROWID: Final = DBAPITypeObject("ROWID", ReferenceType)


def Date(year: int, month: int, day: int) -> dt.date:  # noqa: N802  # PEP 249 names it.
    """A date."""
    return dt.date(year, month, day)


def Time(hour: int, minute: int, second: int) -> dt.time:  # noqa: N802
    """A time of day, without a time zone."""
    return dt.time(hour, minute, second)


def Timestamp(  # noqa: N802, PLR0913, PLR0917  # PEP 249 names it and its fields.
    year: int, month: int, day: int, hour: int, minute: int, second: int
) -> dt.datetime:
    """A timestamp, without a time zone."""
    return dt.datetime(year, month, day, hour, minute, second)  # noqa: DTZ001  # Without.


def DateFromTicks(ticks: float) -> dt.date:  # noqa: N802
    """The local date of `ticks`, seconds since the epoch."""
    return dt.datetime.fromtimestamp(ticks).date()  # noqa: DTZ006  # Local, as PEP 249 says.


def TimeFromTicks(ticks: float) -> dt.time:  # noqa: N802
    """The local time of `ticks`, seconds since the epoch."""
    return dt.datetime.fromtimestamp(ticks).time()  # noqa: DTZ006


def TimestampFromTicks(ticks: float) -> dt.datetime:  # noqa: N802
    """The local timestamp of `ticks`, seconds since the epoch."""
    return dt.datetime.fromtimestamp(ticks)  # noqa: DTZ006


def Binary(data: bytes | bytearray | memoryview) -> bytes:  # noqa: N802
    """A binary string."""
    return bytes(data)
