"""Tests of columns and parameters, as Prepared and Description give them."""

from __future__ import annotations

import pytest

from turborel import OperationalError
from turborel._codec.composites import Column, Parameter, read_column, read_parameter
from turborel._codec.datatypes import BooleanType, CharacterType, ExactType
from turborel._codec.fields import Reader


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def test_a_column_is_its_name_type_and_not_null_flag() -> None:
    """Verifies: [PROTOCOL Composite fields] column: named flag, name, type, not null.

    The spec's own robustness case too: a Description of one unnamed
    CHARACTER column, then the same with a named flag of 2.
    """
    named = bytes([1]) + u32(1) + b"K" + bytes([2]) + u32(9) + u32(2) + bytes([1])
    assert read_column(Reader(named, "reply")) == Column(
        "K", ExactType(9, 2), not_null=True
    )
    unnamed = bytes([0, 1]) + u32(1) + bytes([0, 0])
    expected = Column(
        None, CharacterType(varying=False, length=1, octets=False), not_null=False
    )
    assert read_column(Reader(unnamed, "reply")) == expected
    with pytest.raises(OperationalError):
        read_column(Reader(bytes([2]) + unnamed[1:], "reply"))


def test_a_parameter_is_its_varying_flag_and_type() -> None:
    """Verifies: [PROTOCOL Composite fields] parameter: varying flag; data type."""
    varying = bytes([1, 5]) + u32(0xFFFF_FFFF) + bytes([0])
    assert read_parameter(Reader(varying, "reply")) == Parameter(
        varying=True,
        data_type=CharacterType(varying=True, length=0xFFFF_FFFF, octets=False),
    )
    assert read_parameter(Reader(bytes([0, 14]), "reply")) == Parameter(
        varying=False, data_type=BooleanType()
    )
