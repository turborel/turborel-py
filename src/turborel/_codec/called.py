"""Parameter modes: what a Prepared of a CALL tells of each `?`.

[PROTOCOL Parameter modes] With `parameter-modes` granted, a Prepared of
a CALL of an SQL-invoked procedure ends with tag 20: the procedure's
specific name, then every `?` of the statement in the order written, its
OUT ones too, each with the mode and ordinal position of the parameter
whose argument holds it, and its type. A Prepared of another statement
has no tag 20, and each of its parameters is IN.

    called
      schema         string
      name           string
      parameters     a count u32, then of each ?
        mode         u8, 1 IN, 2 INOUT, 4 OUT
        ordinal      u32, from 1
        type         a parameter
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Final

from turborel._codec import tail
from turborel._codec.composites import Column, Parameter, read_declared, read_parameter

if TYPE_CHECKING:
    from turborel._codec.fields import Reader


class ParameterMode(IntEnum):
    """A procedure's parameter's mode, as the protocol codes it."""

    IN = 1
    INOUT = 2
    OUT = 4


@dataclass(frozen=True, slots=True)
class CalledParameter:
    """A `?` of a CALL: its parameter's mode and ordinal position, and its type."""

    mode: ParameterMode
    position: int | None
    """The ordinal position of the parameter whose argument holds it, from 1;
    None of a `?` of another statement than a CALL, which has none."""
    parameter: Parameter


@dataclass(frozen=True, slots=True)
class Called:
    """The procedure a prepared CALL invokes, and each of its `?` marks."""

    schema: str
    name: str
    """The procedure's specific name, in `schema`."""
    parameters: tuple[CalledParameter, ...]
    """Each `?` of the statement, in the order written, OUT ones too."""


def _called_parameter(r: Reader) -> CalledParameter:
    """One `?` of tag 20; a mode of no code, or a position of 0, malformed."""
    code = r.u8()
    if code not in _MODES:
        msg = f"{code} is no parameter mode's code"
        raise r.malformed(msg)
    position = r.u32()
    if position == 0:
        msg = "a parameter's ordinal position is from 1"
        raise r.malformed(msg)
    return CalledParameter(ParameterMode(code), position, read_parameter(r))


def read_prepared_tail(
    r: Reader, columns: tuple[Column, ...]
) -> tuple[tuple[Column, ...], Called | None]:
    """A Prepared's tail: its columns' declared types, 19, and its CALL's, 20."""
    called = None
    reading = tail.Tail(_PREPARED_TAIL)
    while (tag := reading.next(r)) is not None:
        if tag == tail.DECLARED:
            columns = read_declared(r, columns)
        else:
            schema, name = r.string(), r.string()
            called = Called(schema, name, tuple(r.items(_called_parameter)))
    return columns, called


_MODES: Final = frozenset(int(m) for m in ParameterMode)
_PREPARED_TAIL: Final = frozenset({tail.DECLARED, tail.CALLED})
