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

    from turborel._codec.datatypes import Qualifier


@dataclass(frozen=True, slots=True)
class DecFloat:
    """A DECFLOAT value: a Decimal sent as decimal floating point, not exact.

    A DECFLOAT read from the server reaches Python as a plain Decimal.
    """

    value: Decimal


@dataclass(frozen=True, slots=True)
class Interval:
    """An interval: its qualifier, then its units.

    The units are months of a year-month interval, microseconds of a
    day-time one, as the qualifier's start field says.
    """

    qualifier: Qualifier
    units: int


@dataclass(frozen=True, slots=True)
class Multiset:
    """A multiset: its elements, in no set order."""

    elements: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class Structured:
    """A value of a structured type: its most specific type, its attributes."""

    schema: str
    name: str
    attributes: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class Reference:
    """A reference to a row of a typed table: its octets."""

    octets: bytes


@dataclass(frozen=True, slots=True)
class Json:
    """A JSON value to send: a JSON value as Python holds it.

    A JSON value read from the server reaches Python as its JSON value
    itself (doc/appendix/a-types.md).
    """

    value: object


@dataclass(frozen=True, slots=True)
class Xml:
    """An XML value: its serialization as CONTENT."""

    text: str


@dataclass(frozen=True, slots=True)
class PluginValue:
    """A value of a plug-in's type: its type's name, its text and its bytes.

    It goes back to the server as it came, unchanged.
    """

    type_name: str
    text: str
    data: bytes


@dataclass(frozen=True, slots=True)
class LargeObject:
    """A large object sent whole: a str of a CLOB, bytes of a BLOB.

    One read whole from the server reaches Python as its str or bytes.
    """

    data: str | bytes


@dataclass(frozen=True, slots=True)
class LobLocator:
    """A large object by its locator: its kind, locator and lengths.

    It lasts until its transaction ends, and is read by Lob requests.
    """

    binary: bool
    locator: int
    octets: int
    characters: int
