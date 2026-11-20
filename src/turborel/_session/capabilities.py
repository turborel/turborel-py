"""The capabilities a client asks for, and what it offers [PROTOCOL Capabilities].

A client names the capabilities it wants in Hello, and the server grants
those it has, in Ready, in this table's order. A client never sends a
request, or a tail field, of a capability it was not granted
[CLIENT What a connection asks for].
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from turborel._codec.compress import DEFAULT_THRESHOLD

if TYPE_CHECKING:
    from collections.abc import Sequence

NOTICES: Final = "notices"
STATUS: Final = "status"
DIAGNOSTICS: Final = "diagnostics"
DESCRIBE: Final = "describe"
CURSORS: Final = "cursors"
PING: Final = "ping"
RESET: Final = "reset"
CHANGE_USER: Final = "change-user"
QUERY_ATTRIBUTES: Final = "query-attributes"
CONNECTION_ATTRIBUTES: Final = "connection-attributes"
MULTI_STATEMENT: Final = "multi-statement"
COMPRESSION: Final = "compression"
COMMIT_POSITION: Final = "commit-position"
COPY: Final = "copy"
ROW_COUNTS: Final = "row-counts"
GENERATED_VALUES: Final = "generated-values"
FETCH_ENDS: Final = "fetch-ends"
CONDITIONS: Final = "conditions"

ALL: Final = (
    NOTICES,
    STATUS,
    DIAGNOSTICS,
    DESCRIBE,
    CURSORS,
    PING,
    RESET,
    CHANGE_USER,
    QUERY_ATTRIBUTES,
    CONNECTION_ATTRIBUTES,
    MULTI_STATEMENT,
    COMPRESSION,
    COMMIT_POSITION,
    COPY,
    ROW_COUNTS,
    GENERATED_VALUES,
    FETCH_ENDS,
    CONDITIONS,
)
"""Every capability of version 1, in the order Ready grants them."""

APPLICATION: Final = "application"
"""The connection attribute a program's name goes by."""


@dataclass(frozen=True, slots=True)
class Offer:
    """What a connection asks for: capabilities, attributes, a threshold.

    By default every capability but compression, no attribute, and the
    server's own threshold for compressing what the client sends.
    """

    capabilities: Sequence[str] = tuple(c for c in ALL if c != COMPRESSION)
    attributes: Sequence[tuple[str, str]] = ()
    compress_from: int = DEFAULT_THRESHOLD
    """The shortest frame, header included, sent compressed once granted."""

    @classmethod
    def none(cls) -> Offer:
        """An offer of no capability: the server answers in the first form."""
        return cls(capabilities=())

    def compressed(self) -> Offer:
        """This offer, asking for compression too."""
        if COMPRESSION in self.capabilities:
            return self
        return replace(self, capabilities=(*self.capabilities, COMPRESSION))

    def attribute(self, name: str, value: str) -> Offer:
        """This offer, with the connection attribute `name` of `value`."""
        return replace(self, attributes=(*self.attributes, (name, value)))
