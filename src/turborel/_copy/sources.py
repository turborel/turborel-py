"""Where rows to import come from: a source of records [CLIENT Importing].

A source is any object that gives its headings, if it knows them, then
its records one at a time, so memory is bounded by a record, whatever
the source's size. `Delimited` reads CSV and tab-separated text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from turborel._errors import DATA_SQLCODE, DataError

if TYPE_CHECKING:
    from turborel._codec.datatypes import DataType


DATA_EXCEPTION: Final = "22000"
"""SQLSTATE 22000: a data exception, here a source's input that cannot be read."""


@dataclass(frozen=True, slots=True)
class Position:
    """Where in a source a record began: its number and line, each from 1."""

    record: int
    """Its number among the source's records of data, a header not counted."""
    line: int | None = None
    """The line it began on, from 1, of a source made of lines."""

    def __str__(self) -> str:
        """As `record 7, line 9`."""
        return f"record {self.record}" + (
            "" if self.line is None else f", line {self.line}"
        )


@dataclass(frozen=True, slots=True)
class Heading:
    """What a source says of a field: the column it names, and its type if known."""

    name: str
    data_type: DataType | None = None


@dataclass(frozen=True, slots=True)
class Record:
    """A record of a source: a value for each field, and where it began.

    A value is cast to its column's type as it is inserted, so a source
    that knows no types gives strings, and None for null.
    """

    values: list[object]
    position: Position


class SourceError(DataError):
    """Why a source cannot give its next record: where, and what is wrong.

    A data exception, SQLCODE -301 and SQLSTATE 22000, as an import's
    input that cannot be read is.
    """

    def __init__(self, position: Position, message: str) -> None:
        """A record at `position` that cannot be read, for `message`."""
        super().__init__(
            f"{position}: {message}", sqlcode=DATA_SQLCODE, sqlstate=DATA_EXCEPTION
        )
        self.where = position
        self.reason = message


SourceError.__module__ = "turborel.client"


class Source(Protocol):
    """Where rows to import come from.

    `headings` is asked once, before the first record; then `record`
    until it gives None, and None again if asked after. A source holds no
    more than a record at a time, and refuses a record past a bound of
    its own rather than read the rest of its input looking for its end.
    """

    def headings(self) -> list[Heading] | None:
        """Its fields' names and types, as of a header row; None if it knows none.

        With none, its fields are the table's columns in order.

        Raises:
            SourceError: Why it cannot be read, and where.
        """

    def record(self) -> Record | None:
        """The next record; None at the end.

        Raises:
            SourceError: Why it cannot be read, and where; it cannot go on after.
        """
