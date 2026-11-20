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
from typing import TYPE_CHECKING, Final
from xml.etree import ElementTree as ET
from xml.parsers import expat

from turborel._errors import data_error

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
    """An XML value: its serialization as CONTENT [CLIENT XML values]."""

    text: str

    def nodes(self) -> list[str | ET.Element]:
        """Its nodes, parsed from its text as CONTENT: text and elements, in order.

        A document type declaration, and so any entity it declares, is
        refused, so a value cannot make the parse take memory without
        bound; Python's expat parses the rest.

        Raises:
            DataError: SQLSTATE 2200M, if it is not well-formed CONTENT.
        """
        builder = ET.TreeBuilder()
        parser = expat.ParserCreate()
        parser.StartDoctypeDeclHandler = _no_doctype
        parser.StartElementHandler = builder.start
        parser.EndElementHandler = builder.end
        parser.CharacterDataHandler = builder.data
        try:
            parser.Parse(f"<{_WRAPPER}>{self.text}</{_WRAPPER}>", True)  # noqa: FBT003
        except (expat.ExpatError, ValueError) as e:
            msg = f"an XML value is not well-formed CONTENT: {e}"
            raise data_error(msg, NOT_WELL_FORMED_XML) from e
        wrapper = builder.close()
        found: list[str | ET.Element] = [wrapper.text] if wrapper.text else []
        for element in wrapper:
            found.append(element)
            if element.tail:
                found.append(element.tail)
        return found


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


_WRAPPER: Final = "turborel-content"
"""The element CONTENT is parsed within, as a fragment needs one root."""

NOT_WELL_FORMED_XML: Final = "2200M"
"""SQLSTATE 2200M: invalid XML document, here a value not well-formed."""


def _no_doctype(*_: object) -> None:
    msg = "an XML value holds a document type declaration"
    raise ValueError(msg)
