"""A session's state: what the server told, and whether the connection is lost.

As turborel-client's `Connection` and `told.rs`: the capabilities granted;
each session setting as the last Status told it [CLIENT What the server
tells]; the notices, handed to a handler or the last 64 kept; the last
completion; whether a transaction is active; and the failure that lost
the connection, given again to every call after it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from turborel._codec.compress import compress_frames
from turborel._codec.frames import MAX_BODY
from turborel._codec.replies import (
    Complete,
    Description,
    Error,
    LobCreated,
    LobData,
    Rows,
    Suspended,
)
from turborel._errors import connection_failure
from turborel._session.capabilities import COMPRESSION, QUERY_ATTRIBUTES
from turborel._session.raising import ends_connection, raised

if TYPE_CHECKING:
    from collections.abc import Callable

    from turborel._codec.debug import Event
    from turborel._codec.failures import Failure, Notice
    from turborel._codec.replies import Reply
    from turborel._errors import Error as DriverError

KEPT_NOTICES: Final = 64
"""The notices kept when no handler takes them, the oldest dropped first."""

_WARNING_CLASS: Final = "01"


@dataclass(slots=True)
class Told:
    """What the server told the session, and what the session asked of it."""

    granted: tuple[str, ...] = ()
    """The capabilities granted, in Ready's order."""
    settings: dict[str, str] = field(default_factory=dict)
    """Each setting as the last Status told it."""
    handler: Callable[[Notice], None] | None = None
    notices: deque[Notice] = field(default_factory=lambda: deque(maxlen=KEPT_NOTICES))
    position: int | None = None
    """The log position of the last commit, with `commit-position`."""
    completed: Complete | None = None
    """The last statement's completion."""
    compress: int | None = None
    """The threshold the client compresses from, once compression is granted."""
    attributes: tuple[tuple[str, str], ...] = ()
    """The attributes each statement carries, with `query-attributes`."""
    events: deque[Event] = field(default_factory=deque)
    """With `debugger`, the Events of the target not yet read, in order."""

    def notice(self, notice: Notice) -> None:
        """A Notice: handed to the handler if there is one, else kept."""
        if self.handler is not None:
            self.handler(notice)
        else:
            self.notices.append(notice)

    def query_attributes(self) -> tuple[tuple[str, str], ...]:
        """The attributes a statement carries: none unless granted."""
        return self.attributes if QUERY_ATTRIBUTES in self.granted else ()


@dataclass(slots=True)
class Session:
    """A connection's session, and whether the connection is lost."""

    authorization: str = ""
    server: str = ""
    key: bytes | None = field(default=None, repr=False)
    """The cancel key Ready gave: the client's secret (R-SAFE-4)."""
    max_body: int = MAX_BODY
    lost: DriverError | None = None
    active: bool = False
    warning: str | None = None
    autocommit: bool = False
    next_statement: int = 0
    told: Told = field(default_factory=Told)
    copying: bool = False
    """Whether a copy is under way, so only its own requests and Ping go."""
    tap: Callable[[int, bytes], None] | None = None
    """What is given each Description and Rows as read, its kind and body:
    an export of the protocol's own frames."""

    def ready(self, authorization: str, key: bytes, server: str) -> None:
        """Ready read: who the session is, its key and the server's product."""
        self.authorization, self.key, self.server = authorization, key, server

    def grant(self, granted: tuple[str, ...], compress_from: int) -> None:
        """The capabilities granted, compression beginning after Ready if granted."""
        self.told.granted = granted
        self.told.compress = compress_from if COMPRESSION in granted else None

    def needs(self, capability: str, *, ok: bool = False) -> None:
        """Refuse, before anything is sent, a call needing `capability` not granted.

        Raises:
            OperationalError: SQLSTATE 08006, unless granted or `ok`.
        """
        if not ok and capability not in self.told.granted:
            msg = f"the server did not grant {capability}"
            raise connection_failure(msg)

    def outgoing(self, frames: bytes) -> bytes:
        """`frames` as sent: each compressed where it should be, once granted."""
        if self.told.compress is None:
            return frames
        return compress_frames(frames, self.told.compress)

    def is_lost(self) -> bool:
        """Whether the connection is lost."""
        return self.lost is not None

    def lose(self, error: DriverError) -> DriverError:
        """Lose the connection for `error`, given again to every later call."""
        self.lost = error
        return error

    def lose_by(self, why: str) -> DriverError:
        """Lose the connection, saying `why`."""
        return self.lose(connection_failure(why))

    def failed(self, failure: Failure) -> DriverError:
        """A failure the server sent, raised; the connection lost if it ends it."""
        error = raised(failure)
        if ends_connection(failure):
            self.lost = error
        return error

    def noted(self, reply: Reply) -> Reply:
        """`reply`, its end of a statement noted: whether a transaction goes on."""
        if isinstance(reply, Complete):
            self.active = reply.active
            warned = reply.sqlstate.startswith(_WARNING_CLASS)
            self.warning = reply.sqlstate if warned else None
            if reply.position is not None:
                self.told.position = reply.position
            self.told.completed = reply
        elif isinstance(reply, Error):
            self.active, self.warning = reply.failure.active, None
        elif isinstance(reply, Description):
            self.active, self.warning = True, None
        elif isinstance(reply, Rows | Suspended | LobData | LobCreated):
            # A locator is valid within its transaction alone.
            self.active = True
        return reply
