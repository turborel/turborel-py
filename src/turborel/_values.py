"""Values of the protocol that Python has no type of its own for.

Most values reach Python as its own types, `str`, `int`, `Decimal`,
`float`, `bytes`, `bool`, `datetime`, `uuid.UUID`, `list` and `tuple`
(doc/appendix/a-types.md). These classes hold the rest, and mark a
parameter whose Python type alone would be sent as another: a DECFLOAT,
rather than an exact number, a JSON or XML value, rather than a string.
Each is frozen, so it compares and hashes by its value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DecFloat:
    """A DECFLOAT value: a Decimal sent as decimal floating point, not exact.

    A DECFLOAT read from the server reaches Python as a plain Decimal.
    """

    value: Decimal
