"""Compressed frames, once `compression` is granted [PROTOCOL Compressed frames].

    Compressed 'z'
      kind       u8, the kind of the frame it holds
      length     u32, the length of that frame's body
      stream     the rest, a zlib stream of the body

Either side may send any frame compressed. The client compresses each
frame whose whole length, header included, is at least its threshold,
and only where the compressed frame comes out shorter. A reader inflates
at most `length` bytes, itself at most the longest body it takes, so a
stream cannot make it hold more. A `z` frame holding another, one that
inflates to another length, or one received when compression was not
granted fails the connection. zlib (RFC 1950) is the standard library's.
"""

from __future__ import annotations

import zlib
from typing import Final

from turborel._codec.fields import Reader, Writer
from turborel._codec.frames import HEADER_BYTES, MAX_BODY, decode_header, encode_header

COMPRESSED: Final = ord("z")
"""The kind of a compressed frame, the same both ways."""

DEFAULT_THRESHOLD: Final = 1024
"""The client's threshold unless it chooses another: the server's default.

A frame shorter than this is never compressed, as the stream's header,
its trailer and the time taken outweigh what it saves.
"""

_PREFIX: Final = 5
"""A compressed frame's body before its stream: the kind and the length."""


def compress_frames(frames: bytes, threshold: int = DEFAULT_THRESHOLD) -> bytes:
    """`frames`, each of at least `threshold` bytes compressed where shorter.

    Args:
        frames: Whole frames, one after another, as requests encode them.
        threshold: The least whole length, header included, compressed.

    Returns:
        The frames, those compressed as `z` frames, the others as they were.
    """
    out = bytearray()
    at = 0
    while at < len(frames):
        kind, length = decode_header(frames[at : at + HEADER_BYTES], len(frames))
        whole = HEADER_BYTES + length
        body = frames[at + HEADER_BYTES : at + whole]
        stream = zlib.compress(body) if whole >= threshold else None
        if stream is not None and len(stream) + _PREFIX < length:
            held = Writer()
            held.u8(kind)
            held.u32(length)
            held.raw(stream)
            out += encode_header(COMPRESSED, len(held.data())) + held.data()
        else:
            out += frames[at : at + whole]
        at += whole
    return bytes(out)


def decompress(body: bytes, max_body: int = MAX_BODY) -> tuple[int, bytes]:
    """The kind and body of the frame the `z` frame's body `body` holds.

    Args:
        body: The compressed frame's body.
        max_body: The longest body taken.

    Returns:
        The held frame's kind, and its body inflated.

    Raises:
        OperationalError: SQLSTATE 08006, if it holds another `z` frame,
            declares more than `max_body`, is no zlib stream of its body,
            or inflates to another length than it declares.
    """
    r = Reader(body, "compressed frame")
    kind, length = r.u8(), r.u32()
    if kind == COMPRESSED:
        msg = "a compressed frame holds another"
        raise r.malformed(msg)
    if length > max_body:
        msg = f"a compressed message of {length} bytes is longer than {max_body}"
        raise r.malformed(msg)
    inflating = zlib.decompressobj()
    try:
        inflated = inflating.decompress(body[_PREFIX:], length + 1)
    except zlib.error as e:
        msg = "a compressed frame's stream is not zlib's"
        raise r.malformed(msg) from e
    whole = inflating.eof and not inflating.unused_data
    if not whole or len(inflated) != length:
        msg = "a compressed frame inflates to another length than it declares"
        raise r.malformed(msg)
    return kind, inflated


def unwrap(
    kind: int, body: bytes, *, compression: bool, max_body: int = MAX_BODY
) -> tuple[int, bytes]:
    """A frame read, inflated if it came compressed.

    Args:
        kind: The frame's kind.
        body: Its body.
        compression: Whether `compression` was granted.
        max_body: The longest body taken.

    Returns:
        The kind and body of the frame it is, or holds.

    Raises:
        OperationalError: SQLSTATE 08006, of a `z` frame when compression
            was not granted, or one `decompress` refuses.
    """
    if kind != COMPRESSED:
        return kind, body
    if not compression:
        msg = "a compressed frame came, and compression was not granted"
        raise Reader(body, "compressed frame").malformed(msg)
    return decompress(body, max_body)
