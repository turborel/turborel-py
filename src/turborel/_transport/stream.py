"""A connection's stream: frames written and read, blocking [PROTOCOL Frames].

A `Stream` holds a socket, TCP, Unix or TLS, or on Windows a named
pipe's file, and reads a frame as turborel-client's `frames.rs` does:
its header, its length checked against the longest body taken before
anything is held for it, then its body. Every I/O error is a connection
failure, SQLCODE -919 and SQLSTATE 08006 (`timeouts.io_failed`).
"""

from __future__ import annotations

import socket
from typing import IO, Final

from turborel._codec.frames import HEADER_BYTES, decode_header
from turborel._errors import connection_failure
from turborel._transport.timeouts import io_failed

_RESERVED: Final = 64 * 1024
"""The most of a body read at once: past it, the body grows as bytes arrive."""


class Stream:
    """A blocking stream to a server: a socket, or a named pipe's file."""

    def __init__(self, held: socket.socket | IO[bytes]) -> None:
        """Hold `held`, a connected socket or an open pipe."""
        self._held = held
        self._ahead = b""
        """A byte read ahead by `arrives_within`, the first the next read gives."""

    @property
    def held(self) -> socket.socket | IO[bytes]:
        """The socket or file the stream holds."""
        return self._held

    def set_timeout(self, within: float | None) -> None:
        """Bound each read and write to `within` seconds; None for no limit.

        A named pipe takes no timeout: its reads and writes wait as long as
        they must, as turborel-client's do [CLIENT Timeouts].
        """
        if isinstance(self._held, socket.socket):
            try:
                self._held.settimeout(within)
            except OSError as e:
                raise connection_failure(
                    f"cannot bound how long the connection waits: {e}"
                ) from e

    def write(self, data: bytes) -> None:
        """Write all of `data`.

        Raises:
            OperationalError: SQLSTATE 08006, if it cannot.
        """
        try:
            if isinstance(self._held, socket.socket):
                self._held.sendall(data)
            else:
                self._held.write(data)
                self._held.flush()
        except OSError as e:
            raise io_failed("send", e) from e

    def _read(self, count: int) -> bytes:
        if self._ahead:
            ahead, self._ahead = self._ahead, b""
            return ahead
        try:
            if isinstance(self._held, socket.socket):
                return self._held.recv(count)
            return self._held.read(count) or b""
        except OSError as e:
            raise io_failed("receive", e) from e

    def arrives_within(self, within: float | None, kept: float | None) -> bool:
        """Whether a frame begins to arrive within `within` seconds, None for no limit.

        Its first byte is read ahead and kept for the next read, so nothing
        of it is lost; the stream's own timeout, `kept`, put back. A named
        pipe waits without limit.

        Raises:
            OperationalError: SQLSTATE 08006, if the server closed the
                connection, or it fails.
        """
        if self._ahead:
            return True
        if not isinstance(self._held, socket.socket):
            self._ahead = self.read_exact(1)
            return True
        try:
            self._held.settimeout(within)
            first = self._held.recv(1)
        except TimeoutError:
            return False
        except OSError as e:
            raise io_failed("receive", e) from e
        finally:
            self.set_timeout(kept)
        if not first:
            msg = "the server closed the connection"
            raise connection_failure(msg)
        self._ahead = first
        return True

    def read_exact(self, count: int) -> bytes:
        """Exactly `count` bytes, read as they come, at most 64 KiB at a time.

        Raises:
            OperationalError: SQLSTATE 08006, if the connection closes first.
        """
        parts: list[bytes] = []
        left = count
        while left:
            part = self._read(min(left, _RESERVED))
            if not part:
                msg = "cannot receive: the connection closed within a reply"
                raise connection_failure(msg)
            parts.append(part)
            left -= len(part)
        return b"".join(parts)

    def read_frame(self, max_body: int) -> tuple[int, bytes]:
        """The next frame's kind and body, its body at most `max_body` bytes."""
        kind, length = decode_header(self.read_exact(HEADER_BYTES), max_body)
        return kind, self.read_exact(length)

    def read_frame_or_end(self, max_body: int) -> tuple[int, bytes] | None:
        """The next frame, as `read_frame` reads it; None if the server closed first."""
        first = self._read(1)
        if not first:
            return None
        kind, length = decode_header(
            first + self.read_exact(HEADER_BYTES - 1), max_body
        )
        return kind, self.read_exact(length)

    def read_to_end(self, most: int) -> bytes:
        """What the server sends until it closes, at most `most` bytes."""
        parts: list[bytes] = []
        taken = 0
        while taken < most:
            part = self._read(min(most - taken, _RESERVED))
            if not part:
                break
            parts.append(part)
            taken += len(part)
        return b"".join(parts)

    def close(self) -> None:
        """Close it; closing one already closed does nothing."""
        try:
            self._held.close()
        except OSError:
            # The connection is being given up: an error closing it leaves
            # nothing more to do, and its first failure is what the
            # program is told.
            return
