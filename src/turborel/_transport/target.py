"""Where a server is, and the stream to it.

[CLIENT Connecting] [PROTOCOL The Native Protocol]

A target is TCP, on port 7422 unless told another; a local socket, a
Unix socket's path or on Windows a named pipe's; or TCP secured by TLS,
begun on the same port. As turborel-client's `target.rs`: TCP tries each
address a name resolves to, within the connect timeout, with Nagle's
algorithm off, as requests are written whole.
"""

from __future__ import annotations

import socket
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from turborel._errors import connection_failure
from turborel._tls.contexts import secure
from turborel._transport.pipe import open_pipe
from turborel._transport.stream import Stream
from turborel._transport.timeouts import io_failed

if TYPE_CHECKING:
    import ssl

    from turborel._auth.mechanisms import TlsChannel

DEFAULT_PORT: Final = 7422
"""The TCP port a server listens on unless told another."""

DEFAULT_PIPE: Final = r"\\.\pipe\turborel"
"""The named pipe a server on Windows takes connections at, where asked."""


@dataclass(frozen=True, slots=True)
class Tcp:
    """A server over TCP."""

    host: str
    port: int = DEFAULT_PORT


@dataclass(frozen=True, slots=True)
class Local:
    """A server over a Unix socket, or on Windows a named pipe, by its path."""

    path: str


@dataclass(frozen=True, slots=True)
class Tls:
    """A server over TCP, secured by TLS, its certificate checked for `server_name`."""

    host: str
    context: ssl.SSLContext = field(repr=False)
    port: int = DEFAULT_PORT
    server_name: str | None = None
    """The name the server's certificate is checked against; `host` by default."""


Target = Tcp | Local | Tls
"""Where a server is."""


def tcp_to(host: str, port: int, within: float | None) -> socket.socket:
    """A TCP connection to `host`, each of its addresses tried within `within`.

    Raises:
        OperationalError: SQLSTATE 08006, if none can be reached.
    """
    try:
        tcp = socket.create_connection((host, port), timeout=within)
    except OSError as e:
        raise io_failed("connect", e) from e
    tcp.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return tcp


def _local(path: str, within: float | None) -> Stream:
    if sys.platform == "win32":
        try:
            local = Stream(open_pipe(path, within))
        except OSError as e:
            raise io_failed("connect", e) from e
    else:
        local = _unix(path, within)
    return local


def _unix(path: str, within: float | None) -> Stream:
    if not hasattr(socket, "AF_UNIX"):
        msg = f"{path} names a local socket, and this platform has none"
        raise connection_failure(msg)
    unix = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        unix.settimeout(within)
        unix.connect(path)
    except OSError as e:
        unix.close()
        raise io_failed("connect", e) from e
    return Stream(unix)


def open_target(
    target: Target, within: float | None
) -> tuple[Stream, TlsChannel | None]:
    """The stream to `target`, and what its TLS offers to bind, if TLS.

    Raises:
        OperationalError: SQLSTATE 08006, if it cannot be reached or its
            TLS handshake fails.
    """
    if isinstance(target, Local):
        return _local(target.path, within), None
    tcp = tcp_to(target.host, target.port, within)
    if isinstance(target, Tcp):
        return Stream(tcp), None
    secured = secure(tcp, target.server_name or target.host, target.context)
    return Stream(secured.socket), secured.channel
