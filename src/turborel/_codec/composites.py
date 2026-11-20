"""Columns and parameters, as Prepared and Description give them.

[PROTOCOL Composite fields]

    column       named flag; its name, string, if named; data type; not null flag
    parameter    varying flag; data type

A parameter's varying flag is 1 where the server gives the parameter
CHARACTER VARYING of the longest length, as it does of one whose type
the statement does not decide; its type is written all the same.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from turborel._codec import tail
from turborel._codec.datatypes import DataType, read_data_type
from turborel._codec.written import written

if TYPE_CHECKING:
    from turborel._codec.fields import Reader


@dataclass(frozen=True, slots=True)
class Declared:
    """The type a column was declared with [PROTOCOL Declared types].

    A tag can stand for several declared types: INTEGER and NUMERIC(10,0)
    are both an exact numeric type of tag 2.
    """

    name: str
    """Its name, as the Information Schema's DATA_TYPE gives it: INTEGER,
    DECIMAL, DOUBLE PRECISION, USER-DEFINED of a distinct type, ARRAY."""
    written: str
    """The whole type as SQL writes it: DECIMAL(9,2), S.MONEY, INTEGER ARRAY[3]."""


@dataclass(frozen=True, slots=True)
class Column:
    """A column of a result: its name if it has one, its type, NOT NULL."""

    name: str | None
    data_type: DataType
    not_null: bool
    declared: Declared | None = None
    """With `declared-types` granted, the type it was declared with."""

    @property
    def type_written(self) -> str:
        """Its type as SQL writes it: as declared if told, else as its tag says.

        Told, INTEGER; else NUMERIC(10,0) [CLIENT Prepared statements].
        """
        return (
            self.declared.written
            if self.declared is not None
            else written(self.data_type)
        )


@dataclass(frozen=True, slots=True)
class Parameter:
    """A dynamic parameter: whether the server chose CHARACTER VARYING, its type."""

    varying: bool
    data_type: DataType


def read_column(r: Reader) -> Column:
    """A column."""
    name = r.string() if r.flag() else None
    data_type = read_data_type(r)
    return Column(name, data_type, not_null=r.flag())


def read_parameter(r: Reader) -> Parameter:
    """A parameter."""
    varying = r.flag()
    return Parameter(varying=varying, data_type=read_data_type(r))


def read_columns(r: Reader) -> tuple[Column, ...]:
    """A list of columns, then their tail: tag 19, each one's declared type.

    [PROTOCOL Declared types] the tail of a Prepared and a Description, a
    count, then of each column in order its type's name and its type as
    SQL writes it; a count not the columns' is malformed.
    """
    columns = tuple(r.items(read_column))
    reading = tail.Tail(_DECLARED)
    while reading.next(r) is not None:
        told = tuple(r.items(lambda r: Declared(r.string(), r.string())))
        if len(told) != len(columns):
            msg = "its declared types are not one for each column"
            raise r.malformed(msg)
        columns = tuple(
            replace(c, declared=d) for c, d in zip(columns, told, strict=True)
        )
    return columns


_DECLARED: Final = frozenset({tail.DECLARED})
