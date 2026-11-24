"""A procedure called by the standard API's `callproc`, and its parameters described.

PEP 249's `callproc` calls a procedure with a value for each of its
arguments and gives back the values, its OUT and INOUT ones replaced by
what the procedure returned. A prepared CALL tells, with
`parameter-modes`, each `?`'s mode and position [PROTOCOL Parameter
modes]: an execution gives values for its input ones alone, and the
output ones come back as the one row its columns describe, in the order
of the procedure's parameters [CLIENT Prepared statements].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from turborel._api.types import TypeCode
from turborel._codec.called import ParameterMode
from turborel._codec.written import written
from turborel._copy.names import table_name
from turborel._errors import misuse
from turborel._statements.queries import Rowset

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._statements.prepared import Statement
    from turborel._statements.queries import Outcome


@dataclass(frozen=True, slots=True)
class ParameterDescription:
    """A `?` of a statement run: its parameter's mode, position and type."""

    mode: ParameterMode
    """IN, INOUT or OUT; IN of any statement but a CALL."""
    position: int | None
    """Of a CALL, the ordinal position of the procedure's parameter whose
    argument holds the `?`, from 1; None of another statement."""
    type_code: TypeCode
    """Its type, which the module's type objects compare with."""


def call_text(procedure: str, count: int) -> str:
    """A CALL of `procedure`, a `?` for each of `count` arguments.

    Raises:
        InterfaceError: SQLSTATE TB910, if `procedure` is no procedure's
            name, so no other text is taken for one.
    """
    try:
        name = table_name(procedure)
    except ValueError as e:
        msg = f"{procedure} is not a procedure's name"
        raise misuse(msg) from e
    return f"CALL {name}({', '.join('?' * count)})"


def described(statement: Statement) -> tuple[ParameterDescription, ...]:
    """Each `?` of `statement`, in the order written, described."""
    return tuple(
        ParameterDescription(
            m.mode,
            m.position,
            TypeCode(m.parameter.data_type, None, written(m.parameter.data_type)),
        )
        for m in statement.marks
    )


def inputs_of(statement: Statement, values: Sequence[object]) -> tuple[object, ...]:
    """The values of `statement`'s input marks, a value given for every `?`.

    Raises:
        InterfaceError: SQLSTATE TB910, of a count of values not the marks'.
    """
    marks = statement.marks
    if len(values) != len(marks):
        msg = f"{len(values)} values for the {len(marks)} ? marks of the call"
        raise misuse(msg)
    return tuple(
        v for v, m in zip(values, marks, strict=True) if m.mode != ParameterMode.OUT
    )


def returned(
    statement: Statement, values: Sequence[object], outcome: Outcome
) -> tuple[object, ...]:
    """`values`, each of an OUT or INOUT `?` replaced by the value returned.

    The returned row holds them in the order of the procedure's parameters.
    """
    if not isinstance(outcome, Rowset) or not outcome.rows:
        return tuple(values)
    given = list(values)
    outputs = sorted(
        (m.position or 0, n)
        for n, m in enumerate(statement.marks)
        if m.mode != ParameterMode.IN
    )
    for (_, n), value in zip(outputs, outcome.rows[0], strict=False):
        given[n] = value
    return tuple(given)
