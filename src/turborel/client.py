"""The low-level client: a blocking connection to a turborel server.

It does all that Turborel's own client library, turborel-client, does,
beneath the DB-API (RULES.md D2), and is the driver's public interface to
what the DB-API has no place for. `connect` connects over TCP,
`connect_local` over a Unix socket or, on Windows, a named pipe,
`connect_tls` over TLS, and `connect_to` to any `Target`; each takes the
user to connect as and a mechanism that proves it [CLIENT Connecting].

    >>> conn = connect("127.0.0.1", "ANN", Trust())  # doctest: +SKIP
    >>> conn.server, conn.authorization  # doctest: +SKIP
    ('turborel 0.0.0 (alpha)', 'ANN')
"""

from __future__ import annotations

from typing import IO, TYPE_CHECKING, Final

from turborel._auth.cache import KEY_CACHE_ENTRIES, KeyCache
from turborel._auth.mechanisms import (
    Certificate,
    ChannelBinding,
    Mechanism,
    Password,
    Scram,
    TlsChannel,
    Trust,
)
from turborel._codec import requests
from turborel._codec.failures import Notice
from turborel._codec.frames import HEADER_BYTES, decode_header
from turborel._codec.replies import Error as ErrorReply
from turborel._codec.replies import Pong, Status, decode
from turborel._errors import (
    CONNECTION_FAILURE_SQLCODE,
    OperationalError,
    connection_failure,
)
from turborel._session import ops
from turborel._session.capabilities import Offer
from turborel._session.raising import raised
from turborel._session.runner import run
from turborel._session.state import KEPT_NOTICES, Session
from turborel._tls.contexts import channel as tls_channel
from turborel._tls.contexts import presenting, roots, trusting
from turborel._transport.stream import Stream
from turborel._transport.target import (
    DEFAULT_PIPE,
    DEFAULT_PORT,
    Local,
    Target,
    Tcp,
    Tls,
    open_target,
)
from turborel._transport.timeouts import (
    CANCEL_WITHIN,
    CONNECT_WITHIN,
    TERMINATE_WITHIN,
    Timeouts,
)

if TYPE_CHECKING:
    import socket
    import ssl
    from collections.abc import Callable

INVALID_AUTHORIZATION: Final = "28000"
"""SQLSTATE 28000: a secret refused over plain TCP before connecting."""

__all__ = [
    "CANCEL_WITHIN",
    "CONNECT_WITHIN",
    "DEFAULT_PIPE",
    "DEFAULT_PORT",
    "KEPT_NOTICES",
    "KEY_CACHE_ENTRIES",
    "TERMINATE_WITHIN",
    "Canceller",
    "Certificate",
    "ChannelBinding",
    "Connection",
    "KeyCache",
    "Local",
    "Mechanism",
    "Notice",
    "Offer",
    "Password",
    "Scram",
    "Target",
    "Tcp",
    "Timeouts",
    "Tls",
    "TlsChannel",
    "Trust",
    "connect",
    "connect_local",
    "connect_tls",
    "connect_to",
    "presenting",
    "roots",
    "tls_channel",
    "trusting",
]

Address = str | tuple[str, int]
"""A server's host, on port 7422, or its host and port."""


def _split(address: Address) -> tuple[str, int]:
    return (address, DEFAULT_PORT) if isinstance(address, str) else address


def in_the_clear(mechanism: Mechanism) -> None:
    """Refuse a secret mechanism over plain TCP, before connecting.

    Raises:
        OperationalError: SQLSTATE 28000, of `password`, or of SCRAM unless
            the program asked for it in the clear.
    """
    if mechanism.secret:
        msg = (
            f"{mechanism.name} is sent only over TLS, a Unix socket or a named pipe,"
            " never over plain TCP"
        )
        raise OperationalError(
            msg, sqlcode=CONNECTION_FAILURE_SQLCODE, sqlstate=INVALID_AUTHORIZATION
        )


class Canceller:
    """What cancels the statement a connection runs, from another thread.

    The key is the session's secret, never shown (R-SAFE-4).
    """

    def __init__(self, target: Target, key: bytes) -> None:
        """Cancel by `key` at `target`."""
        self._target = target
        self._key = key

    def __repr__(self) -> str:
        """Never the key."""
        return "Canceller(..)"

    def cancel(self, within: float = CANCEL_WITHIN) -> None:
        """Cancel, on a connection of its own, giving up after `within` seconds.

        The statement cancelled fails with SQLCODE -920, SQLSTATE TB920
        [PROTOCOL Cancel 'Z'] [CLIENT Running statements].

        Raises:
            OperationalError: SQLSTATE 08006, if the server cannot be reached
                or does not close in time.
        """
        stream, _ = open_target(self._target, within)
        try:
            stream.set_timeout(within)
            stream.write(requests.Cancel(self._key).encode())
            stream.read_to_end(HEADER_BYTES)
        finally:
            stream.close()


class Connection:
    """A session of a turborel server, over one stream."""

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

    @classmethod
    def open(
        cls,
        held: socket.socket | IO[bytes],
        user: str,
        mechanism: Mechanism,
        offer: Offer | None = None,
    ) -> Connection:
        """A connection over a stream the program opened, which bounds its waits.

        Over a TLS socket the program opened, bind SCRAM first:
        `mechanism.bind(tls_channel(sock))` [CLIENT Connecting].

        Raises:
            Error: As logging in fails.
        """
        connection = cls(Stream(held), None, bounded=False)
        connection._log_in(user, mechanism, offer or Offer())
        return connection

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
        run(self._stream, self._session, ops.ping(self._session))

    def reset(self) -> None:
        """Put the session back as it was at login, its user kept.

        Its transaction is rolled back, its prepared statements, cursors,
        temporary tables and settings gone.

        Raises:
            Error: If `reset` was not granted, or the connection is lost.
        """
        run(self._stream, self._session, ops.reset(self._session))

    def change_user(self, user: str, mechanism: Mechanism) -> None:
        """Authenticate the connection again as `user`, whose new session it is.

        Raises:
            Error: If `change-user` was not granted, or the login fails,
                which fails the connection.
        """
        steps = ops.change_user(self._session, user, mechanism)
        run(self._stream, self._session, steps)

    def query(self, sql: str) -> ops.Outcome:
        """Run one statement: a query's columns and rows, or a completion.

        Raises:
            Error: The statement's failure, or the connection's.
        """
        return run(self._stream, self._session, ops.query(self._session, sql))

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


def connect_to(
    target: Target,
    user: str,
    mechanism: Mechanism,
    timeouts: Timeouts | None = None,
    offer: Offer | None = None,
) -> Connection:
    """A connection to `target`, as `user`, proved by `mechanism`.

    Args:
        target: Where the server is.
        user: Who to connect as: read as an identifier, so `ann` is ANN.
        mechanism: What proves it.
        timeouts: How long to wait: 30 seconds to connect, no read limit.
        offer: What to ask for: every capability but compression.

    Raises:
        OperationalError: SQLSTATE 28000, of a secret over plain TCP; 08006
            if the server cannot be reached.
        Error: As the server refuses the login.
    """
    within = timeouts or Timeouts()
    if isinstance(target, Tcp):
        in_the_clear(mechanism)
    stream, channel = open_target(target, within.connect)
    if channel is not None:
        mechanism.bind(channel)
    stream.set_timeout(within.connect)
    connection = Connection(stream, target, bounded=True)
    connection._log_in(user, mechanism, offer or Offer())  # noqa: SLF001  # Its maker.
    connection.set_read_timeout(within.read)
    return connection


def connect(address: Address, user: str, mechanism: Mechanism) -> Connection:
    """A connection over TCP to `address`, a host on port 7422 or a host and port.

    Raises:
        OperationalError: SQLSTATE 28000, of a secret over plain TCP; 08006
            if the server cannot be reached.
        Error: As the server refuses the login.
    """
    host, port = _split(address)
    return connect_to(Tcp(host, port), user, mechanism)


def connect_local(path: str, user: str, mechanism: Mechanism) -> Connection:
    """A connection over a Unix socket, or on Windows the named pipe, at `path`.

    Raises:
        OperationalError: SQLSTATE 08006, if nothing serves at `path`.
        Error: As the server refuses the login.
    """
    return connect_to(Local(path), user, mechanism)


def connect_tls(
    address: Address,
    context: ssl.SSLContext,
    user: str,
    mechanism: Mechanism,
    server_name: str | None = None,
) -> Connection:
    """A connection over TLS to `address`, its certificate checked by `context`.

    SCRAM over it is SCRAM-SHA-256-PLUS, bound to the connection.

    Raises:
        OperationalError: SQLSTATE 08006, if the server cannot be reached or
            its certificate is not trusted.
        Error: As the server refuses the login.
    """
    host, port = _split(address)
    return connect_to(Tls(host, context, port, server_name), user, mechanism)
