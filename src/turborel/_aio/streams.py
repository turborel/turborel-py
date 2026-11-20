"""A connection's stream for asyncio: frames written and read [PROTOCOL Frames].

An `AsyncStream` holds asyncio's reader and writer of a TCP, Unix or TLS
connection, and reads a frame as the blocking `Stream` does: its header,
its length checked against the longest body taken, then its body. A
named pipe, on Windows, is the blocking stream's, each read and write
run in a thread of asyncio's. Every wait is bounded by the timeout set,
and every I/O error, or a wait that runs out, is a connection failure,
SQLCODE -919 and SQLSTATE 08006.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Final

from turborel._codec.frames import HEADER_BYTES, decode_header
from turborel._errors import connection_failure
from turborel._transport.timeouts import io_failed

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from turborel._transport.stream import Stream

_RESERVED: Final = 64 * 1024


class AsyncStream:
    """A stream to a server, its reads and writes awaited."""

    def __init__(
        self,
        reader: asyncio.StreamReader | None,
        writer: asyncio.StreamWriter | None,
        blocking: Stream | None = None,
    ) -> None:
        """Hold asyncio's `reader` and `writer`, or a `blocking` stream, in threads."""
        self._reader, self._writer, self._blocking = reader, writer, blocking
        self._within: float | None = None

    @property
    def writer(self) -> asyncio.StreamWriter | None:
        """Asyncio's writer, of its transport's details; None of a named pipe."""
        return self._writer

    def set_timeout(self, within: float | None) -> None:
        """Bound each read and write to `within` seconds; None for no limit."""
        self._within = within

    async def _bounded(self, waiting: Awaitable[bytes], what: str) -> bytes:
        try:
            return await asyncio.wait_for(waiting, self._within)
        except TimeoutError as e:
            raise io_failed(what, e) from e
        except OSError as e:
            raise io_failed(what, e) from e

    async def write(self, data: bytes) -> None:
        """Write all of `data`.

        Raises:
            OperationalError: SQLSTATE 08006, if it cannot.
        """
        if self._blocking is not None:
            await asyncio.to_thread(self._blocking.write, data)
            return
        assert self._writer is not None  # noqa: S101  # One or the other.
        self._writer.write(data)

        async def drained() -> bytes:
            assert self._writer is not None  # noqa: S101
            await self._writer.drain()
            return b""

        await self._bounded(drained(), "send")

    async def _read(self, count: int) -> bytes:
        if self._blocking is not None:
            return await asyncio.to_thread(self._blocking.read_exact, count)
        assert self._reader is not None  # noqa: S101
        try:
            return await self._bounded(self._reader.readexactly(count), "receive")
        except asyncio.IncompleteReadError:
            msg = "cannot receive: the connection closed within a reply"
            raise connection_failure(msg) from None

    async def read_frame(self, max_body: int) -> tuple[int, bytes]:
        """The next frame's kind and body, its body at most `max_body` bytes."""
        kind, length = decode_header(await self._read(HEADER_BYTES), max_body)
        return kind, (await self._read(length)) if length else b""

    async def read_frame_or_end(self, max_body: int) -> tuple[int, bytes] | None:
        """The next frame, as `read_frame` reads it; None if the server closed first."""
        if self._blocking is not None:
            return await asyncio.to_thread(self._blocking.read_frame_or_end, max_body)
        assert self._reader is not None  # noqa: S101
        first = await self._bounded(self._reader.read(1), "receive")
        if not first:
            return None
        kind, length = decode_header(
            first + await self._read(HEADER_BYTES - 1), max_body
        )
        return kind, (await self._read(length)) if length else b""

    def close(self) -> None:
        """Close it; closing one already closed does nothing."""
        if self._blocking is not None:
            self._blocking.close()
        elif self._writer is not None:
            self._writer.close()
