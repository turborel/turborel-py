"""A connection's core: its stream, its session, and the requests of no statement.

[CLIENT Connecting] [CLIENT What the server tells] [CLIENT Controlling the
session]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from turborel._client.cancel import Canceller
from turborel._codec import requests
from turborel._codec.failures import Notice
from turborel._codec.frames import HEADER_BYTES, decode_header
from turborel._codec.replies import Error as ErrorReply
from turborel._codec.replies import Pong, Status, decode
from turborel._errors import connection_failure
from turborel._session import ops
from turborel._session.raising import raised
from turborel._session.runner import run
from turborel._session.state import Session
from turborel._transport.timeouts import TERMINATE_WITHIN

if TYPE_CHECKING:
    from collections.abc import Callable

    from turborel._auth.mechanisms import Mechanism
    from turborel._session.capabilities import Offer
    from turborel._session.ops import Steps
    from turborel._transport.stream import Stream
    from turborel._transport.target import Target

_T = TypeVar("_T")


class Core:
    """A connection's stream and session, and what needs no statement."""

    def __init__(self, stream: Stream, target: Target | None, *, bounded: bool) -> None:
        """Hold `stream`, reached at `target`; use the connect functions instead."""
        self._stream = stream
        self._target = target
        self._bounded = bounded
        self._read_timeout: float | None = None
        self._session = Session()

    def __repr__(self) -> str:
        """Its target and user, never its key."""
        return f"Connection({self._target!r}, {self._session.authorization!r})"

    def _run(self, steps: Steps[_T]) -> _T:
        """What the request `steps` gives, run over the stream."""
        return run(self._stream, self._session, steps)

    def _log_in(self, user: str, mechanism: Mechanism, offer: Offer) -> None:
        try:
            run(
                self._stream,
                self._session,
                ops.login(self._session, user, mechanism, offer),
            )
        except BaseException:
            self._stream.close()
            raise

    @property
    def authorization(self) -> str:
        """The session's authorization identifier, as Ready told it."""
        return self._session.authorization

    @property
    def server(self) -> str:
        """The server's product, as `turborel 0.0.0 (alpha)`."""
        return self._session.server

    @property
    def target(self) -> Target | None:
        """Where the connection reached its server, if a connect function made it."""
        return self._target

    @property
    def granted(self) -> tuple[str, ...]:
        """The capabilities the server granted, in Ready's order."""
        return self._session.told.granted

    @property
    def in_transaction(self) -> bool:
        """Whether the session's transaction is active, as the server last said."""
        return self._session.active

    @property
    def is_lost(self) -> bool:
        """Whether the connection is lost: every call then gives its failure."""
        return self._session.lost is not None

    @property
    def read_timeout(self) -> float | None:
        """The read timeout, in seconds; None for no limit."""
        return self._read_timeout

    def set_read_timeout(self, within: float | None) -> None:
        """Bound each read and write from now on to `within` seconds.

        Raises:
            OperationalError: SQLSTATE 08006, of a stream given to `open`,
                which its maker bounds.
        """
        if not self._bounded:
            msg = "a stream given to open is bounded by its maker"
            raise connection_failure(msg)
        self._stream.set_timeout(within)
        self._read_timeout = within

    def set_max_body(self, most: int) -> None:
        """Take replies of at most `most` bytes of body; a longer one loses it."""
        self._session.max_body = most

    def setting(self, name: str) -> str | None:
        """A session setting as the server last told it, with no round trip."""
        return self._session.told.settings.get(name)

    def settings(self) -> dict[str, str]:
        """Every session setting the server told, as it last told them."""
        return dict(self._session.told.settings)

    def set_notice_handler(self, handler: Callable[[Notice], None] | None) -> None:
        """Hand each notice to `handler` as it comes; None to keep the last 64."""
        self._session.told.handler = handler

    def take_notices(self) -> list[Notice]:
        """The notices kept, taken."""
        taken = list(self._session.told.notices)
        self._session.told.notices.clear()
        return taken

    def canceller(self) -> Canceller | None:
        """What cancels this connection's statements, if it knows its target."""
        if self._target is None or self._session.key is None:
            return None
        return Canceller(self._target, self._session.key)

    def ping(self) -> None:
        """Whether the server and the connection are alive, with no statement run.

        Raises:
            Error: If `ping` was not granted, or the connection is lost.
        """
        self._run(ops.ping(self._session))

    def reset(self) -> None:
        """Put the session back as it was at login, its user kept.

        Its transaction is rolled back, its prepared statements, cursors,
        temporary tables and settings gone.

        Raises:
            Error: If `reset` was not granted, or the connection is lost.
        """
        self._run(ops.reset(self._session))

    def change_user(self, user: str, mechanism: Mechanism) -> None:
        """Authenticate the connection again as `user`, whose new session it is.

        Raises:
            Error: If `change-user` was not granted, or the login fails,
                which fails the connection.
        """
        steps = ops.change_user(self._session, user, mechanism)
        self._run(steps)

    @property
    def autocommit(self) -> bool:
        """Whether each statement is its own transaction."""
        return self._session.autocommit

    @autocommit.setter
    def autocommit(self, on: bool) -> None:
        self._session.autocommit = on

    def terminate(self) -> None:
        """End the session, its transaction as SESSION.COMMIT_AT_END says.

        It waits for the server to close at most the read timeout, else 60
        seconds [PROTOCOL Terminate 'X'] [CLIENT Connecting].

        Raises:
            Error: The failure of the commit the end made, or the connection's.
        """
        session = self._session
        if session.lost is not None:
            raise session.lost
        try:
            self._stream.write(requests.Terminate().encode())
            if self._bounded:
                self._stream.set_timeout(self._read_timeout or TERMINATE_WITHIN)
            rest = self._stream.read_to_end(session.max_body + HEADER_BYTES)
        finally:
            self._stream.close()
            session.lose_by("the session was terminated")
        if len(rest) < HEADER_BYTES:
            return
        kind, _ = decode_header(rest[:HEADER_BYTES], session.max_body)
        reply = decode(kind, rest[HEADER_BYTES:])
        if isinstance(reply, ErrorReply):
            raise raised(reply.failure)
        if not isinstance(reply, Notice | Status | Pong):
            msg = "the server answered Terminate"
            raise connection_failure(msg)

    def close(self) -> None:
        """Close the connection without ending the session first."""
        self._stream.close()
        if self._session.lost is None:
            self._session.lose_by("the connection was closed")
