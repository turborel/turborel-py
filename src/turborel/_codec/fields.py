"""The fields messages are made of [PROTOCOL Values and fields].

Every integer is little-endian: `u8`, `u32`, `u64`, and `i128` in two's
complement. A flag is a `u8` of 0 or 1; a string is its length in bytes,
a `u32`, then its UTF-8; bytes are their length, then the bytes; a list
is its count, a `u32`, then each item; a key is 16 bytes with no length.

A `Reader` holds what it reads as it goes, never reserving for a count
before the items arrive, so a count larger than what follows fails as
the body runs out. Whatever it cannot read fails the connection, SQLCODE
-919 and SQLSTATE 08006, as turborel-client's reader does.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Final, TypeVar

from turborel._errors import OperationalError, connection_failure, misuse

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

KEY_BYTES: Final = 16
"""A cancel key's bytes: 128 bits, with no length before them."""

MAX_NESTING: Final = 16
"""The deepest arrays, rows, multisets and structured values nest.

turborel's `MAX_TYPE_NESTING`: a reader refuses parts nested deeper, so
a reply cannot exhaust the client's stack.
"""

_U8: Final = struct.Struct("<B")
_U16: Final = struct.Struct("<H")
_U32: Final = struct.Struct("<I")
_U64: Final = struct.Struct("<Q")
_I128_BYTES: Final = 16
_FALSE: Final = 0
_TRUE: Final = 1
_U8_MAX: Final = 0xFF
_U16_MAX: Final = 0xFFFF
_U32_MAX: Final = 0xFFFF_FFFF
_U64_MAX: Final = 0xFFFF_FFFF_FFFF_FFFF
_I32_MIN: Final = -(1 << 31)
_I32_MAX: Final = (1 << 31) - 1
_I64_MIN: Final = -(1 << 63)
_I64_MAX: Final = (1 << 63) - 1
I128_MIN: Final = -(1 << 127)
"""The least `i128`: the least units of an exact number."""
I128_MAX: Final = (1 << 127) - 1
"""The greatest `i128`: the greatest units of an exact number."""

_T = TypeVar("_T")


class Reader:
    """Reads the fields of one message's body, in order."""

    def __init__(self, body: bytes, what: str) -> None:
        """Read `body`, the body of a `what`, such as "reply".

        Args:
            body: The bytes to read.
            what: What they are, as an error names it.
        """
        self._body = body
        self._at = 0
        self._what = what
        self._depth = 0

    def malformed(self, why: str) -> OperationalError:
        """The connection failure of a body that cannot be read.

        Args:
            why: What is wrong, in plain words.

        Returns:
            The error, naming the byte reached.
        """
        msg = f"a {self._what} received is malformed at byte {self._at}: {why}"
        return connection_failure(msg)

    def take(self, count: int) -> bytes:
        """The next `count` bytes.

        Raises:
            OperationalError: If fewer remain.
        """
        end = self._at + count
        if end > len(self._body):
            msg = "it is cut short"
            raise self.malformed(msg)
        taken = self._body[self._at : end]
        self._at = end
        return taken

    def u8(self) -> int:
        """A `u8`."""
        return int(_U8.unpack(self.take(_U8.size))[0])

    def u16(self) -> int:
        """A `u16`, as a JSON datetime's zone is written."""
        return int(_U16.unpack(self.take(_U16.size))[0])

    def u32(self) -> int:
        """A `u32`."""
        return int(_U32.unpack(self.take(_U32.size))[0])

    def i32(self) -> int:
        """An `i32 as u32`: the signed number's bits in a `u32`."""
        return int.from_bytes(self.take(_U32.size), "little", signed=True)

    def u64(self) -> int:
        """A `u64`."""
        return int(_U64.unpack(self.take(_U64.size))[0])

    def i64(self) -> int:
        """An `i64 as u64`: the signed number's bits in a `u64`."""
        return int.from_bytes(self.take(_U64.size), "little", signed=True)

    def i128(self) -> int:
        """An `i128`, in two's complement."""
        return int.from_bytes(self.take(_I128_BYTES), "little", signed=True)

    def flag(self) -> bool:
        """A flag: 0 or 1.

        Raises:
            OperationalError: Of any other byte.
        """
        byte = self.u8()
        if byte not in (_FALSE, _TRUE):
            msg = f"a flag is {byte}, neither 0 nor 1"
            raise self.malformed(msg)
        return byte == _TRUE

    def octets(self) -> bytes:
        """Bytes: their length, then them."""
        return self.take(self.u32())

    def string(self) -> str:
        """A string: its length in bytes, then its UTF-8.

        Raises:
            OperationalError: If it is not UTF-8.
        """
        raw = self.octets()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as e:
            msg = "a string is not UTF-8"
            raise self.malformed(msg) from e

    def strings(self) -> list[str]:
        """A list of strings."""
        return self.items(Reader.string)

    def key(self) -> bytes:
        """A key: 16 bytes, with no length before them."""
        return self.take(KEY_BYTES)

    def items(self, read: Callable[[Reader], _T]) -> list[_T]:
        """A list: its count, then each item `read` reads.

        Nothing is reserved for the count, so a count larger than what
        follows fails as the body runs out.
        """
        count = self.u32()
        return [read(self) for _ in range(count)]

    def nested(self, read: Callable[[Reader], _T]) -> _T:
        """What `read` reads, one level deeper than this.

        Raises:
            OperationalError: Past `MAX_NESTING` levels.
        """
        if self._depth >= MAX_NESTING:
            msg = "its arrays and rows are nested too deep"
            raise self.malformed(msg)
        self._depth += 1
        try:
            return read(self)
        finally:
            self._depth -= 1

    def at_end(self) -> bool:
        """Whether every byte was read."""
        return self._at >= len(self._body)

    def finish(self) -> None:
        """Check that every byte was read.

        Raises:
            OperationalError: If bytes are left after the last field.
        """
        if not self.at_end():
            msg = "bytes are left after its last field"
            raise self.malformed(msg)


class Writer:
    """Writes fields, in order, into a body."""

    def __init__(self) -> None:
        """Begin an empty body."""
        self._out = bytearray()

    def data(self) -> bytes:
        """What is written."""
        return bytes(self._out)

    def raw(self, data: bytes) -> None:
        """Bytes as they are, with no length."""
        self._out += data

    def u8(self, n: int) -> None:
        """A `u8`."""
        self._out += _bounded(n, 0, _U8_MAX).to_bytes(_U8.size, "little")

    def u16(self, n: int) -> None:
        """A `u16`."""
        self._out += _bounded(n, 0, _U16_MAX).to_bytes(_U16.size, "little")

    def u32(self, n: int) -> None:
        """A `u32`."""
        self._out += _bounded(n, 0, _U32_MAX).to_bytes(_U32.size, "little")

    def i32(self, n: int) -> None:
        """An `i32 as u32`."""
        self._out += _bounded(n, _I32_MIN, _I32_MAX).to_bytes(
            _U32.size, "little", signed=True
        )

    def u64(self, n: int) -> None:
        """A `u64`."""
        self._out += _bounded(n, 0, _U64_MAX).to_bytes(_U64.size, "little")

    def i64(self, n: int) -> None:
        """An `i64 as u64`."""
        self._out += _bounded(n, _I64_MIN, _I64_MAX).to_bytes(
            _U64.size, "little", signed=True
        )

    def i128(self, n: int) -> None:
        """An `i128`, in two's complement."""
        self._out += _bounded(n, I128_MIN, I128_MAX).to_bytes(
            _I128_BYTES, "little", signed=True
        )

    def flag(self, set_: bool) -> None:  # noqa: FBT001  # A flag is a bool.
        """A flag: 1 if `set_`, else 0."""
        self._out.append(_TRUE if set_ else _FALSE)

    def octets(self, data: bytes) -> None:
        """Bytes: their length, then them."""
        self.u32(len(data))
        self._out += data

    def string(self, text: str) -> None:
        """A string: its length in bytes, then its UTF-8."""
        self.octets(text.encode("utf-8"))

    def strings(self, texts: Iterable[str]) -> None:
        """A list of strings."""
        items = list(texts)
        self.u32(len(items))
        for text in items:
            self.string(text)


def _bounded(n: int, least: int, most: int) -> int:
    """`n`, if it lies from `least` to `most`.

    Raises:
        InterfaceError: SQLSTATE TB910, if it does not: no field could
            carry it.
    """
    if not least <= n <= most:
        msg = f"{n} does not fit its field, from {least} to {most}"
        raise misuse(msg)
    return n
