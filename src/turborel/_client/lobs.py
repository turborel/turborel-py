"""A connection's large objects: read by ranges or as a stream, and written.

[CLIENT Large objects] [PROTOCOL Lob 'L']
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from turborel._client.statements import Statements
from turborel._errors import connection_failure
from turborel._lobs import locators
from turborel._lobs.locators import CHUNK_OCTETS
from turborel._values import LobLocator

if TYPE_CHECKING:
    from _typeshed import ReadableBuffer, WriteableBuffer

    from turborel._codec.replies import Complete

Lob = LobLocator | str | bytes
"""A large object as a result gives it: by its locator, or held whole."""


class LargeObjects(Statements):
    """What a connection does with large objects."""

    def read_lob(
        self, lob: Lob, start: int, count: int, *, characters: bool = False
    ) -> bytes:
        """At most `count` octets of `lob` from octet `start`, from 0.

        Of a character large object, its characters if `characters`, whole
        ones, as UTF-8. Fewer than asked only at its end, or at a chunk's,
        256 KiB. One held whole is read from the value itself.

        Raises:
            Error: SQLSTATE 0F001 if its locator is no longer valid; the
                connection's.
        """
        if not isinstance(lob, LobLocator):
            return locators.held_range(lob, (start, count), characters=characters)
        steps = locators.read(
            self._session, lob.locator, (start, count), characters=characters
        )
        return self._run(steps)

    def lob_reader(self, lob: Lob) -> LobReader:
        """`lob`'s octets as a binary stream, read a chunk at a time."""
        return LobReader(self, lob)

    def create_lob(self, *, binary: bool) -> LobWriter:
        """A new large object, a BLOB if `binary` else a CLOB, written in pieces.

        Raises:
            Error: The server's, or the connection's.
        """
        locator = self._run(locators.create(self._session, binary=binary))
        return LobWriter(self, locator, binary=binary)

    def free_lob(self, lob: Lob) -> Complete:
        """`lob`'s locator no longer valid, nor the value it named.

        Raises:
            DataError: SQLSTATE 22000, of a large object held whole.
            Error: SQLSTATE 0F001 if it is not valid; the connection's.
        """
        if not isinstance(lob, LobLocator):
            raise locators.no_locator(lob)
        return self._run(locators.free(self._session, lob.locator))

    def hold_lob(self, lob: Lob) -> Complete:
        """`lob`'s locator valid past its commit, until freed or a rollback.

        Raises:
            DataError: SQLSTATE 22000, of a large object held whole.
            Error: SQLSTATE 0F001 if it is not valid; the connection's.
        """
        if not isinstance(lob, LobLocator):
            raise locators.no_locator(lob)
        return self._run(locators.hold(self._session, lob.locator))

    def _append(self, locator: int, data: bytes) -> None:
        self._run(locators.append(self._session, locator, data))


def _octets(lob: Lob) -> int:
    if isinstance(lob, LobLocator):
        return lob.octets
    return len(lob.encode("utf-8") if isinstance(lob, str) else lob)


class LobReader(io.RawIOBase):
    """A large object's octets as a stream, a chunk read at a time."""

    def __init__(self, connection: LargeObjects, lob: Lob) -> None:
        """A stream of `lob`'s octets, read over `connection`."""
        super().__init__()
        self._connection = connection
        self._lob = lob
        self._at = 0
        self._chunk = b""
        self._taken = 0

    def readable(self) -> bool:
        """It is read."""
        return True

    def readinto(self, buffer: WriteableBuffer) -> int:
        """Octets into `buffer`: as many as the chunk at hand holds, 0 at the end.

        Raises:
            OperationalError: SQLSTATE 08006, if the server sent less than
                its length; the connection goes on.
            Error: As `read_lob`'s.
        """
        out = memoryview(buffer).cast("B")
        if self._taken >= len(self._chunk):
            if self._at >= _octets(self._lob) or not len(out):
                return 0
            self._chunk = self._connection.read_lob(self._lob, self._at, CHUNK_OCTETS)
            if not self._chunk:
                msg = "the server sent less of the large object than its length"
                raise connection_failure(msg)
            self._at += len(self._chunk)
            self._taken = 0
        n = min(len(out), len(self._chunk) - self._taken)
        out[:n] = self._chunk[self._taken : self._taken + n]
        self._taken += n
        return n


class LobWriter(io.RawIOBase):
    """A new large object written a piece at a time, sent in Appends of a chunk.

    `finish` gives the value to send as a parameter, by its locator.
    """

    def __init__(self, connection: LargeObjects, locator: int, *, binary: bool) -> None:
        """A writer of the large object `locator`, created over `connection`."""
        super().__init__()
        self._connection = connection
        self._locator = locator
        self._binary = binary
        self._pending = bytearray()
        self._octets = 0
        self._characters = 0

    def writable(self) -> bool:
        """It is written."""
        return True

    def write(self, data: ReadableBuffer) -> int:
        """`data` added: a CLOB's octets UTF-8, a character split between writes.

        Raises:
            Error: As an Append's, once a chunk is waiting.
        """
        octets = bytes(data)
        self._pending += octets
        self._octets += len(octets)
        if not self._binary:
            self._characters += locators.lead_octets(octets)
        if len(self._pending) >= CHUNK_OCTETS:
            self.flush()
        return len(octets)

    def flush(self) -> None:
        """Send what is written and not yet sent."""
        if self._pending:
            data, self._pending = bytes(self._pending), bytearray()
            self._connection._append(self._locator, data)  # noqa: SLF001  # Its own.

    def finish(self) -> LobLocator:
        """The large object written, to send as a parameter, within its transaction.

        Raises:
            Error: The server's: SQLSTATE 22021 if a CLOB's octets are not
                UTF-8, 22001 if it is longer than the longest.
        """
        self.flush()
        self.close()
        return LobLocator(self._binary, self._locator, self._octets, self._characters)
