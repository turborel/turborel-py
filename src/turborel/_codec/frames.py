"""A frame's header: its kind and its body's length [PROTOCOL Frames].

Every message, either way, is a frame: a kind, `u8`; the length of its
body, `u32` little-endian, the header not counted; then the body. A
header is read before its body, so a length past the longest body taken
fails the connection before anything is held for it.
"""

from __future__ import annotations

import struct
from typing import Final, NamedTuple

from turborel._errors import connection_failure

# [PROTOCOL Frames] kind u8, length u32, least significant byte first.
_HEADER_LAYOUT: Final = struct.Struct("<BI")

HEADER_BYTES: Final = _HEADER_LAYOUT.size
"""The bytes of a frame's header: 5."""

MAX_BODY: Final = 16 * 1024 * 1024
"""The longest body read unless the program says otherwise, 16 MiB.

turborel-client takes replies of up to this many bytes by default, so a
server cannot make the client hold more without bound [PROTOCOL Frames].
"""

_MAX_KIND: Final = 0xFF
_MAX_LENGTH: Final = 0xFFFF_FFFF


class FrameHeader(NamedTuple):
    """A frame's header, read."""

    kind: int
    """The frame's kind, read in the direction it travels."""

    length: int
    """The bytes of its body, the header not counted."""


def encode_header(kind: int, length: int) -> bytes:
    """The header of a frame of kind `kind` whose body is `length` bytes.

    Args:
        kind: The frame's kind, 0 to 255.
        length: The bytes of its body, 0 to 2**32 - 1.

    Returns:
        The five bytes of the header.

    Raises:
        OperationalError: SQLSTATE 08006, if the kind is not a byte or the
            length does not fit its `u32`: no frame could carry it.
    """
    if not 0 <= kind <= _MAX_KIND:
        msg = f"a frame's kind is a byte, not {kind}"
        raise connection_failure(msg)
    if not 0 <= length <= _MAX_LENGTH:
        msg = f"a message of {length} bytes is longer than a frame can say"
        raise connection_failure(msg)
    return _HEADER_LAYOUT.pack(kind, length)


def decode_header(header: bytes, max_body: int = MAX_BODY) -> FrameHeader:
    """The kind and body length of the frame whose header is `header`.

    Args:
        header: The header's five bytes.
        max_body: The longest body taken; a longer one fails the
            connection, as turborel-client's does.

    Returns:
        The frame's kind and its body's length.

    Raises:
        OperationalError: SQLSTATE 08006, if `header` is not five bytes or
            the body would be longer than `max_body`.
    """
    if len(header) != HEADER_BYTES:
        msg = f"a frame's header is {HEADER_BYTES} bytes, not {len(header)}"
        raise connection_failure(msg)
    kind, length = _HEADER_LAYOUT.unpack(header)
    if length > max_body:
        msg = f"a message of {length} bytes is longer than the {max_body} taken"
        raise connection_failure(msg)
    return FrameHeader(kind=kind, length=length)
