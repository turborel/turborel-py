"""Columns and parameters, as Prepared and Description give them.

[PROTOCOL Composite fields]

    column       named flag; its name, string, if named; data type; not null flag
    parameter    varying flag; data type

A parameter's varying flag is 1 where the server gives the parameter
CHARACTER VARYING of the longest length, as it does of one whose type
the statement does not decide; its type is written all the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from turborel._codec.datatypes import DataType, read_data_type

if TYPE_CHECKING:
    from turborel._codec.fields import Reader


@dataclass(frozen=True, slots=True)
class Column:
    """A column of a result: its name if it has one, its type, NOT NULL."""

    name: str | None
    data_type: DataType
    not_null: bool


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
