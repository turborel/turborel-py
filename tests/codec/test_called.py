"""Tests of parameter modes: tail 20 of a Prepared of a CALL."""

from __future__ import annotations

import pytest
from tests.kit import text, u32

from turborel import OperationalError
from turborel._codec.called import Called, CalledParameter, ParameterMode
from turborel._codec.composites import Parameter
from turborel._codec.datatypes import ExactType
from turborel._codec.replies import Prepared, decode
from turborel._statements.prepared import Statement

INTEGER = ExactType(10, 0)
INTEGER_PARAMETER = b"\x00\x02" + u32(10) + u32(0)
HEAD = u32(3) + u32(1) + INTEGER_PARAMETER + u32(0)


def called(*marks: bytes) -> bytes:
    """Tag 20 of the procedure S.P and each of `marks`."""
    return b"\x14" + text("S") + text("P") + u32(len(marks)) + b"".join(marks)


def mark(mode: int, position: int) -> bytes:
    """A `?` of `mode` and `position`, of type INTEGER."""
    return bytes([mode]) + u32(position) + INTEGER_PARAMETER


def test_tail_20_gives_each_mark_its_mode_and_position() -> None:
    """Verifies: [PROTOCOL Parameter modes] a Prepared of a CALL, tail 20.

    The procedure's schema and name, then every `?` in the order written,
    OUT ones too, each with its mode, 1 IN, 2 INOUT or 4 OUT, its
    parameter's ordinal position and its type; several of one IN
    argument each with its position.
    """
    reply = decode(
        ord("P"), HEAD + called(mark(1, 1), mark(1, 1), mark(2, 2), mark(4, 3))
    )
    assert isinstance(reply, Prepared)
    integer = Parameter(varying=False, data_type=INTEGER)
    assert reply.called == Called(
        "S",
        "P",
        (
            CalledParameter(ParameterMode.IN, 1, integer),
            CalledParameter(ParameterMode.IN, 1, integer),
            CalledParameter(ParameterMode.INOUT, 2, integer),
            CalledParameter(ParameterMode.OUT, 3, integer),
        ),
    )
    statement = Statement(3, reply.parameters, reply.columns, reply.called)
    assert statement.procedure == ("S", "P")
    assert [m.mode for m in statement.marks] == [1, 1, 2, 4]


def test_without_tail_20_every_mark_is_an_input() -> None:
    """Verifies: [PROTOCOL Parameter modes] no tail 20: each parameter IN.

    Of another statement, or not granted: each `?` an input, of no
    position, its type the head's.
    """
    reply = decode(ord("P"), HEAD)
    assert isinstance(reply, Prepared)
    assert reply.called is None
    statement = Statement(3, reply.parameters, reply.columns)
    assert statement.procedure is None
    assert statement.marks == (
        CalledParameter(
            ParameterMode.IN, None, Parameter(varying=False, data_type=INTEGER)
        ),
    )


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        (ord("P"), HEAD + called(mark(3, 1))),
        (ord("P"), HEAD + called(mark(8, 1))),
        (ord("P"), HEAD + called(mark(1, 0))),
        (ord("D"), u32(0) + called()),
    ],
    ids=["mode 3", "mode 8", "position 0", "on a Description"],
)
def test_a_bad_mode_or_position_fails_the_connection(kind: int, body: bytes) -> None:
    """Verifies: [PROTOCOL Parameter modes] a mode of another code, or a position of 0.

    A malformed frame: SQLCODE -919, SQLSTATE 08006; tag 20 on a
    Description, a tag the message does not take, too.
    """
    with pytest.raises(OperationalError) as failure:
        decode(kind, body)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")
