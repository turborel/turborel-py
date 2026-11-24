"""Tests of `callproc`'s parts: the CALL's text, its inputs, the values returned."""

from __future__ import annotations

import pytest

from turborel import NUMBER, InterfaceError, ParameterMode
from turborel._api.calls import call_text, described, inputs_of, returned
from turborel._codec.called import Called, CalledParameter
from turborel._codec.composites import Column, Parameter
from turborel._codec.datatypes import CharacterType, ExactType
from turborel._codec.replies import Complete
from turborel._statements.prepared import Statement
from turborel._statements.queries import Rowset

INTEGER = Parameter(varying=False, data_type=ExactType(10, 0))
TEXT = Parameter(
    varying=False, data_type=CharacterType(varying=True, length=5, octets=False)
)
CALLED = Called(
    "ANN",
    "BUMP",
    (
        CalledParameter(ParameterMode.OUT, 3, TEXT),
        CalledParameter(ParameterMode.IN, 1, INTEGER),
        CalledParameter(ParameterMode.INOUT, 2, INTEGER),
    ),
)
COLUMNS = (
    Column("N", INTEGER.data_type, not_null=False),
    Column("S", TEXT.data_type, not_null=False),
)
STATEMENT = Statement(1, (INTEGER, INTEGER), COLUMNS, CALLED)


def test_a_call_s_text_names_its_procedure_alone() -> None:
    """Verifies: [DESIGN] D2 `callproc`: a CALL of the procedure, a `?` an argument.

    A name not a procedure's refused, SQLSTATE TB910, so no other text is
    taken for one.
    """
    assert call_text("ann.bump", 3) == 'CALL "ANN"."BUMP"(?, ?, ?)'
    assert call_text("P", 0) == 'CALL "P"()'
    with pytest.raises(InterfaceError) as wrong:
        call_text("P(1); DROP TABLE T", 1)
    assert wrong.value.sqlstate == "TB910"


def test_the_inputs_are_the_values_of_in_and_inout_marks() -> None:
    """Verifies: [CLIENT Prepared statements] an OUT `?` given no value.

    A value given for every `?`, that of an OUT one not sent; a count not
    the marks' refused, SQLSTATE TB910.
    """
    assert inputs_of(STATEMENT, (None, 5, 6)) == (5, 6)
    with pytest.raises(InterfaceError):
        inputs_of(STATEMENT, (5, 6))


def test_the_values_returned_replace_the_output_ones() -> None:
    """Verifies: [CLIENT Prepared statements] OUT values read back from the result.

    Its row in the procedure's parameters' order, put back where each
    OUT or INOUT `?` was written; of no row, the values as given.
    """
    outcome = Rowset(COLUMNS, [(7, "X")])
    assert returned(STATEMENT, (None, 5, 6), outcome) == ("X", 5, 7)
    assert returned(STATEMENT, (None, 5, 6), Complete(0, "00000", active=False)) == (
        None,
        5,
        6,
    )


def test_each_mark_is_described_with_its_mode_and_position() -> None:
    """Verifies: [CLIENT Prepared statements] each `?`'s mode, position and type.

    In the order written; its type code equal to the type object of its
    kind.
    """
    marks = described(STATEMENT)
    assert [(m.mode, m.position) for m in marks] == [
        (ParameterMode.OUT, 3),
        (ParameterMode.IN, 1),
        (ParameterMode.INOUT, 2),
    ]
    assert marks[1].type_code == NUMBER
    assert str(marks[1].type_code) == "NUMERIC(10,0)"
