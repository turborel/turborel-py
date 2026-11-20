"""Connecting to a server: by TCP, a local socket, TLS, or any target.

[CLIENT Connecting] [CLIENT Timeouts]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turborel._client.connection import Connection
from turborel._errors import CONNECTION_FAILURE_SQLCODE, OperationalError
from turborel._session.capabilities import Offer
from turborel._transport.target import DEFAULT_PORT, Local, Tcp, Tls, open_target
from turborel._transport.timeouts import Timeouts

if TYPE_CHECKING:
    import ssl

    from turborel._auth.mechanisms import Mechanism, TlsChannel
    from turborel._transport.stream import Stream
    from turborel._transport.target import Target

INVALID_AUTHORIZATION: Final = "28000"
"""SQLSTATE 28000: a secret refused over plain TCP before connecting."""

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
    opened = open_target(target, within.connect)
    return logged_in(target, opened, (user, mechanism), within, offer or Offer())


def logged_in(
    target: Target,
    opened: tuple[Stream, TlsChannel | None],
    who: tuple[str, Mechanism],
    within: Timeouts,
    offer: Offer,
) -> Connection:
    """A connection over the stream `opened` to `target`, `who` logged in.

    Raises:
        Error: As the server refuses the login, or the connection fails.
    """
    stream, channel = opened
    user, mechanism = who
    if channel is not None:
        mechanism.bind(channel)
    stream.set_timeout(within.connect)
    connection = Connection(stream, target, bounded=True)
    connection._log_in(user, mechanism, offer)  # noqa: SLF001  # Its maker.
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
