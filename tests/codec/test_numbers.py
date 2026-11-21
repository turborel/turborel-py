"""Tests of exact numbers and DECFLOAT values, between their fields and Python."""

from __future__ import annotations

from decimal import Context, Decimal

import pytest

from turborel import DataError
from turborel._codec.fields import I128_MAX, I128_MIN
from turborel._codec.numbers import (
    decfloat_canonical,
    decfloat_to_python,
    exact_to_python,
    python_to_decfloat,
    python_to_exact,
)

U32_MAX = 0xFFFF_FFFF


@pytest.mark.parametrize(
    ("units", "scale", "expected"),
    [
        (1, 0, 1),
        (-150, 2, Decimal("-1.50")),
        (0, 3, Decimal("0.000")),
        (I128_MAX, 0, I128_MAX),
        (I128_MIN, 0, I128_MIN),
        (I128_MIN, 38, Decimal(I128_MIN).scaleb(-38, Context(prec=40))),
        (7, U32_MAX, Decimal((0, (7,), -U32_MAX))),
    ],
)
def test_exact_numbers_keep_units_and_scale(
    units: int, scale: int, expected: int | Decimal
) -> None:
    """Verifies: [PROTOCOL Values] units `i128` divided by ten to the scale `u32`.

    The full `i128` range and the greatest scale reach Python with no
    loss, an `int` of scale 0, else a Decimal of that exponent, and go
    back to the same units and scale.
    """
    value = exact_to_python(units, scale)
    assert type(value) is type(expected)
    assert value == expected
    if isinstance(value, Decimal):
        assert value.as_tuple().exponent == -scale
    assert python_to_exact(value) == (units, scale)


def test_38_digits_pass_through_exactly_past_the_default_context() -> None:
    """Verifies: [PROTOCOL Values] an exact number of 38 digits, no digit lost.

    Past the 28 digits of Python's default decimal context, read and sent
    with no rounding, as Turborel's exact numbers hold 38; one of 39 whose
    units fit an `i128` sent too, for the server to refuse.
    """
    widest = 10**38 - 1
    fraction = exact_to_python(widest, 10)
    assert str(fraction) == "9999999999999999999999999999.9999999999"
    assert python_to_exact(fraction) == (widest, 10)
    assert python_to_exact(Decimal("-1234567890123456789012345678.9012345678")) == (
        -12345678901234567890123456789012345678,
        10,
    )
    assert python_to_exact(10**38) == (10**38, 0)


def test_a_decimal_of_positive_exponent_is_scale_0() -> None:
    """Verifies: [PROTOCOL Values] an exact number's scale is a `u32`, at least 0."""
    assert python_to_exact(Decimal("12E+3")) == (12_000, 0)
    assert python_to_exact(Decimal("-0.00")) == (0, 2)


@pytest.mark.parametrize(
    "value",
    [
        I128_MAX + 1,
        I128_MIN - 1,
        Decimal("NaN"),
        Decimal("-Infinity"),
        Decimal((0, (1,), -(U32_MAX + 1))),
        Decimal(I128_MAX) * 10,
    ],
)
def test_an_exact_number_past_its_fields_is_refused(value: int | Decimal) -> None:
    """Verifies: [DESIGN] D13 a number its field cannot hold, SQLSTATE 22003."""
    with pytest.raises(DataError) as failure:
        python_to_exact(value)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-301, "22003")


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ((15, -1), (15, -1)),
        ((150, -2), (15, -1)),
        ((0, 5), (0, 0)),
        ((-(10**34) - 5, 0), (-1, 34)),  # half to even: down
        ((10**34 + 15, 0), (10**33 + 2, 1)),  # half to even: up
        ((10**34 + 16, 0), (10**33 + 2, 1)),
        ((1, 6144), (1, 6144)),
        ((12, 6143), (12, 6143)),
        ((1, -6143), (1, -6143)),
        ((1, 6145), None),
        ((12, 6144), None),
        ((1, -6144), None),
    ],
)
def test_decfloat_rounds_to_34_digits_within_decimal128(
    given: tuple[int, int], expected: tuple[int, int] | None
) -> None:
    """Verifies: [PROTOCOL Values] DECFLOAT's coefficient `i128` and exponent.

    turborel keeps a DECFLOAT canonical: 34 digits rounded half to even,
    no trailing zero, its adjusted exponent from -6143 to 6144.
    """
    assert decfloat_canonical(*given) == expected


def test_decfloat_reaches_python_as_its_digits() -> None:
    """Verifies: [PROTOCOL Values] a DECFLOAT read and written with no loss."""
    assert decfloat_to_python(15, -1) == Decimal("1.5")
    assert decfloat_to_python(-1, 6144) == Decimal("-1E+6144")
    assert python_to_decfloat(Decimal("1.50")) == (15, -1)
    assert python_to_decfloat(Decimal("0E+5")) == (0, 0)
    assert python_to_decfloat(Decimal("-" + "9" * 34)) == (-int("9" * 34), 0)


@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("1" * 35), Decimal("1E+6145")],
)
def test_a_decfloat_past_34_digits_is_refused(value: Decimal) -> None:
    """Verifies: [DESIGN] D13 a DECFLOAT past its digits or exponents, 22003."""
    with pytest.raises(DataError) as failure:
        python_to_decfloat(value)
    assert failure.value.sqlstate == "22003"
