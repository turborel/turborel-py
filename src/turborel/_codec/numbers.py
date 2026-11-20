"""Exact numbers and DECFLOAT values, between their fields and Python [PROTOCOL Values].

An exact number is its units, an `i128`, divided by ten to its scale, a
`u32`; it reaches Python as an `int` of scale 0, else a `decimal.Decimal`
of exactly that exponent, so 1.50 stays 1.50, and never passes through a
binary float (R-NUM-3). A DECFLOAT is a coefficient, an `i128`, times
ten to an exponent, an `i32`: turborel keeps it canonical, at most 34
digits with no trailing zero, its adjusted exponent within decimal128's.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from turborel._codec.fields import I128_MAX, I128_MIN
from turborel._errors import NUMERIC_OUT_OF_RANGE, data_error

DECFLOAT_DIGITS: Final = 34
"""The digits of a DECFLOAT's coefficient: turborel's `MAX_DECFLOAT_PRECISION`."""

DECFLOAT_MAX_EXPONENT: Final = 6144
"""The greatest adjusted exponent of a DECFLOAT, decimal128's."""

DECFLOAT_MIN_EXPONENT: Final = -6143
"""The least adjusted exponent of a DECFLOAT, decimal128's."""

_RADIX: Final = 10
_HALF: Final = 5
_U32_MAX: Final = 0xFFFF_FFFF


def exact_to_python(units: int, scale: int) -> int | Decimal:
    """The exact number `units` / 10**`scale`: an `int` of scale 0, else a Decimal.

    The Decimal keeps the scale as its exponent, so trailing zeros stay.
    """
    if scale == 0:
        return units
    sign = 1 if units < 0 else 0
    digits = tuple(int(d) for d in str(abs(units)))
    return Decimal((sign, digits, -scale))


def python_to_exact(value: int | Decimal) -> tuple[int, int]:
    """The units and scale of `value`, an `int` or a finite Decimal.

    Raises:
        DataError: SQLSTATE 22003, if it is not finite, or its units do not
            fit an `i128` or its scale a `u32`.
    """
    if isinstance(value, int):
        units, scale = value, 0
    else:
        units, scale = _decimal_parts(value)
    if not I128_MIN <= units <= I128_MAX or scale > _U32_MAX:
        msg = f"{value} has more digits than an exact number's units hold"
        raise data_error(msg, NUMERIC_OUT_OF_RANGE)
    return units, scale


def _finite_parts(value: Decimal, what: str) -> tuple[int, int]:
    """The signed digits and exponent of `value`, a finite Decimal.

    Raises:
        DataError: SQLSTATE 22003, if it is not finite.
    """
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        msg = f"{value} is no {what}"
        raise data_error(msg, NUMERIC_OUT_OF_RANGE)
    magnitude = int("".join(str(d) for d in digits))
    return (-magnitude if sign else magnitude), exponent


def _decimal_parts(value: Decimal) -> tuple[int, int]:
    """The units and scale of a finite Decimal, its exponent made a scale."""
    units, exponent = _finite_parts(value, "exact number")
    if exponent > 0:
        return units * _RADIX**exponent, 0
    return units, -exponent


def decfloat_canonical(coefficient: int, exponent: int) -> tuple[int, int] | None:
    """`coefficient` * 10**`exponent` rounded to 34 digits, half to even, canonical.

    As turborel's `DecFloat::new`: the digits dropped round the rest, the
    trailing zeros go into the exponent, and zero is (0, 0).

    Returns:
        The coefficient and exponent, or None if its adjusted exponent is
        out of decimal128's range.
    """
    negative, magnitude = coefficient < 0, abs(coefficient)
    drop = len(str(magnitude)) - DECFLOAT_DIGITS
    if magnitude and drop > 0:
        kept, dropped = divmod(magnitude, _RADIX**drop)
        half = _HALF * _RADIX ** (drop - 1)
        if dropped > half or (dropped == half and kept % 2 == 1):
            kept += 1
        magnitude, exponent = kept, exponent + drop
    if magnitude == 0:
        return 0, 0
    while magnitude % _RADIX == 0:
        magnitude //= _RADIX
        exponent += 1
    adjusted = exponent + len(str(magnitude)) - 1
    if not DECFLOAT_MIN_EXPONENT <= adjusted <= DECFLOAT_MAX_EXPONENT:
        return None
    return (-magnitude if negative else magnitude), exponent


def decfloat_to_python(coefficient: int, exponent: int) -> Decimal:
    """The DECFLOAT `coefficient` * 10**`exponent`, as a Decimal of those digits."""
    sign = 1 if coefficient < 0 else 0
    digits = tuple(int(d) for d in str(abs(coefficient)))
    return Decimal((sign, digits, exponent))


def python_to_decfloat(value: Decimal) -> tuple[int, int]:
    """The canonical coefficient and exponent of `value`, a finite Decimal.

    Raises:
        DataError: SQLSTATE 22003, if it is not finite, has more than 34
            significant digits, or lies beyond decimal128's exponents.
    """
    coefficient, exponent = _finite_parts(value, "DECFLOAT value")
    canonical = decfloat_canonical(coefficient, exponent)
    if canonical is None or decfloat_to_python(*canonical) != value:
        msg = f"{value} does not fit a DECFLOAT's 34 digits and exponents"
        raise data_error(msg, NUMERIC_OUT_OF_RANGE)
    return canonical
