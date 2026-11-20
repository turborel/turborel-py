"""A message's tail: the fields version 1 gained after its first form.

[PROTOCOL The tail]

    tail
      { tag u8, then the field of that tag }...  to the end of the body

Each field is written only where the capability that adds it was
granted and it has something to say, so a message with an empty tail is
its first form exactly. The tags come in increasing order; a tag the
message does not take, or one not past the last, fails the connection.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from turborel._errors import misuse

if TYPE_CHECKING:
    from turborel._codec.fields import Reader, Writer

# The tags [PROTOCOL The tail].
ATTRIBUTES: Final = 1
MULTI: Final = 2
CURSOR: Final = 3
POSITION: Final = 4
MORE: Final = 5
ROWS: Final = 6
SEVERITY: Final = 7
DETAIL: Final = 8
HINT: Final = 9
CONTEXT: Final = 10
SCHEMA: Final = 11
TABLE: Final = 12
COLUMN: Final = 13
DATA_TYPE: Final = 14
CONSTRAINT: Final = 15
GENERATED: Final = 16
CONDITIONS: Final = 17
TIME: Final = 18

DIAGNOSTICS: Final = frozenset(range(SEVERITY, CONSTRAINT + 1))
"""The tags of a failure's and a Notice's tail, 7 to 15."""

MAX_ATTRIBUTES: Final = 32
"""The most attributes a message takes."""
MAX_ATTRIBUTE_NAME: Final = 64
"""The longest name of an attribute, in bytes."""
MAX_ATTRIBUTE_VALUE: Final = 1024
"""The longest value of an attribute, in bytes."""

Attributes = Sequence[tuple[str, str]]
"""Attributes of a connection or a request: each a name and a value."""


class Tail:
    """The tags of a tail, read in order."""

    def __init__(self, taken: frozenset[int]) -> None:
        """Read a tail of a message that takes the tags `taken`."""
        self._taken = taken
        self._last = 0

    def next(self, r: Reader) -> int | None:
        """The next tag, or None at the end of the body.

        Raises:
            OperationalError: SQLSTATE 08006, of a tag the message does not
                take, or one not past the last.
        """
        if r.at_end():
            return None
        tag = r.u8()
        if tag <= self._last or tag not in self._taken:
            msg = f"its tail has tag {tag} out of place"
            raise r.malformed(msg)
        self._last = tag
        return tag


def write_attributes(w: Writer, attributes: Attributes) -> None:
    """Tag 1 and `attributes`, unless there are none.

    Raises:
        InterfaceError: SQLSTATE TB910, of more than 32, a name not 1 to
            64 bytes, or a value of more than 1024: the server would fail
            the connection for it.
    """
    if not attributes:
        return
    if len(attributes) > MAX_ATTRIBUTES:
        msg = f"{len(attributes)} attributes are more than the {MAX_ATTRIBUTES} taken"
        raise misuse(msg)
    w.u8(ATTRIBUTES)
    w.u32(len(attributes))
    for name, value in attributes:
        name_bytes, value_bytes = len(name.encode()), len(value.encode())
        if (
            not 1 <= name_bytes <= MAX_ATTRIBUTE_NAME
            or value_bytes > MAX_ATTRIBUTE_VALUE
        ):
            msg = (
                f"an attribute's name is 1 to {MAX_ATTRIBUTE_NAME} bytes"
                f" and its value at most {MAX_ATTRIBUTE_VALUE}"
            )
            raise misuse(msg)
        w.string(name)
        w.string(value)


def write_mark(w: Writer, tag: int, *, set_: bool) -> None:
    """`tag` alone, if `set_`."""
    if set_:
        w.u8(tag)


def write_number(w: Writer, tag: int, n: int) -> None:
    """`tag` and `n`, a `u32`, unless `n` is 0, its default."""
    if n:
        w.u8(tag)
        w.u32(n)
