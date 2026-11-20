"""What the driver's tests share: a server's frames, and a peer to send them.

A `Peer` is the server's end of a socket pair: a test queues the frames
the server sends before the client reads them, and reads back what the
client sent, all on one thread, with no network (R-TEST-5, R-TEST-7).
"""

from __future__ import annotations

import socket
import struct
from typing import Self

from turborel._codec.fields import Writer
from turborel._codec.frames import decode_header, encode_header


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return struct.pack("<I", n)


def u64(n: int) -> bytes:
    """A `u64`, little-endian."""
    return struct.pack("<Q", n)


def text(s: str) -> bytes:
    """A string: its length, then its UTF-8."""
    return u32(len(s.encode())) + s.encode()


def frame(kind: str, body: bytes = b"") -> bytes:
    """A frame of the kind `kind`, one letter, whose body is `body`."""
    return encode_header(ord(kind), len(body)) + body


def ready(
    user: str = "ANN",
    capabilities: tuple[str, ...] = (),
    server: str = "turborel 0.0.0 (alpha)",
    key: bytes = bytes(range(16)),
) -> bytes:
    """A Ready of `user`, granting `capabilities`."""
    w = Writer()
    w.string(user)
    w.raw(key)
    w.strings(capabilities)
    w.string(server)
    return frame("R", w.data())


def status(name: str, value: str) -> bytes:
    """A Status of `name`."""
    return frame("T", text(name) + text(value))


def notice(sqlstate: str, message: str) -> bytes:
    """A Notice, with no diagnostics."""
    return frame("N", text(sqlstate) + text(message))


def failure(
    sqlcode: int, sqlstate: str, message: str, *, active: bool = False
) -> bytes:
    """A failure's body, uncited and unplaced."""
    signed = struct.pack("<i", sqlcode)
    return signed + text(sqlstate) + text(message) + bytes([0, 0, 1 if active else 0])


def error(sqlcode: int, sqlstate: str, message: str, *, active: bool = False) -> bytes:
    """An Error of `sqlcode` and `sqlstate`."""
    return frame("E", failure(sqlcode, sqlstate, message, active=active))


def complete(
    sqlstate: str = "00000", *, active: bool = False, tail: bytes = b""
) -> bytes:
    """A Complete of `sqlstate`, its tail as given."""
    sqlcode = 100 if sqlstate == "02000" else 0
    return frame(
        "K", u32(sqlcode) + text(sqlstate) + bytes([1 if active else 0]) + tail
    )


def description(*names: str) -> bytes:
    """A Description of nullable BOOLEAN columns of `names`."""
    body = u32(len(names))
    for name in names:
        body += b"\x01" + text(name) + bytes([14]) + b"\x00"
    return frame("D", body)


def rows(*values: tuple[bool, ...]) -> bytes:
    """A Rows reply of rows of truth values."""
    body = u32(len(values))
    for row in values:
        body += u32(len(row)) + b"".join(bytes([14, 1 if v else 0]) for v in row)
    return frame("B", body)


class Peer:
    """The server's end of a socket pair, the client's end given to the driver."""

    def __init__(self) -> None:
        """A connected pair; the client's end in `client`.

        Each end waits at most 10 seconds, so a test whose peer sends too
        little fails rather than hangs.
        """
        self.client, self._server = socket.socketpair()
        self._server.settimeout(5)
        self.client.settimeout(10)

    def reply(self, *frames: bytes) -> None:
        """Queue `frames`, as the server sends them."""
        self._server.sendall(b"".join(frames))

    def close(self) -> None:
        """End what the server sends, as a server closes after its last reply.

        The client may still write, as it writes Terminate before it reads
        to the close.
        """
        self._server.shutdown(socket.SHUT_WR)

    def received(self) -> tuple[int, bytes]:
        """The next frame the client sent: its kind and body."""
        kind, length = decode_header(self._read(5), 1 << 24)
        return kind, self._read(length)

    def _read(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            part = self._server.recv(count - len(data))
            if not part:
                break
            data += part
        return data

    def __enter__(self) -> Self:
        """It."""
        return self

    def __exit__(self, *_: object) -> None:
        """Both ends closed."""
        self.client.close()
        self._server.close()
