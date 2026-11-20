"""Tests of compressed frames: written where shorter, inflated within bounds."""

from __future__ import annotations

import hashlib
import zlib

import pytest

from turborel import OperationalError
from turborel._codec.compress import (
    COMPRESSED,
    DEFAULT_THRESHOLD,
    compress_frames,
    decompress,
    unwrap,
)
from turborel._codec.frames import decode_header
from turborel._codec.requests import Query, Terminate


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def held(kind: int, length: int, stream: bytes) -> bytes:
    """A compressed frame's body: kind, length, then the stream."""
    return bytes([kind]) + u32(length) + stream


def scattered(count: int) -> bytes:
    """`count` bytes that do not compress, made by SHA-256 from a fixed seed."""
    out = b""
    block = b"seed"
    while len(out) < count:
        block = hashlib.sha256(block).digest()
        out += block
    return out[:count]


def test_a_long_frame_goes_compressed_and_inflates_to_itself() -> None:
    """Verifies: [PROTOCOL Compressed frames] kind `z`: kind, length, zlib stream.

    A frame shorter than the threshold, as Terminate, goes as it is.
    """
    query = Query("SELECT 1 FROM T; " * 200).encode()
    terminate = Terminate().encode()
    sent = compress_frames(query + terminate)
    assert len(sent) * 4 < len(query)
    assert sent.endswith(terminate)
    kind, length = decode_header(sent[:5])
    assert kind == COMPRESSED
    body = sent[5 : 5 + length]
    assert body[0] == ord("Q")
    assert decompress(body) == (ord("Q"), query[5:])


def test_the_threshold_is_the_client_s_and_counts_the_header() -> None:
    """Verifies: [PROTOCOL Compressed frames] a threshold of the client's own.

    A frame of exactly the threshold, header included, is compressed; one
    a byte shorter is not; one that would not come out shorter goes as it
    is, whatever its length.
    """
    frame = Query("x" * (DEFAULT_THRESHOLD - 10)).encode()
    assert len(frame) == DEFAULT_THRESHOLD
    assert compress_frames(frame)[0] == COMPRESSED
    assert compress_frames(frame, threshold=DEFAULT_THRESHOLD + 1) == frame
    assert compress_frames(frame, threshold=0)[0] == COMPRESSED
    noise = b"B" + u32(4096) + scattered(4096)
    assert compress_frames(noise) == noise


@pytest.mark.parametrize(
    ("body", "max_body"),
    [
        (held(COMPRESSED, 3, zlib.compress(b"abc")), 1 << 24),  # a z within a z
        (held(ord("Q"), 3, zlib.compress(b"abc")), 2),  # longer than taken
        (held(ord("Q"), 2, zlib.compress(b"abc")), 1 << 24),  # inflates past it
        (held(ord("Q"), 4, zlib.compress(b"abc")), 1 << 24),  # inflates short
        (held(ord("Q"), 3, b"\x00\x01\x02"), 1 << 24),  # no zlib stream
        (held(ord("Q"), 3, zlib.compress(b"abc")[:-2]), 1 << 24),  # cut short
        (held(ord("Q"), 3, zlib.compress(b"abc") + b"\x00"), 1 << 24),  # bytes after
        (
            held(ord("Q"), 3, zlib.compress(b"abc")[:-1] + b"\x00"),
            1 << 24,
        ),  # its Adler-32
        (b"Q\x03\x00", 1 << 24),  # its header cut short
    ],
)
def test_a_compressed_frame_that_cannot_be_inflated_fails(
    body: bytes, max_body: int
) -> None:
    """Verifies: [PROTOCOL Compressed frames] inflated to at most its length.

    A `z` within a `z`, a length past the longest body taken, a stream
    that inflates to another length, or one that is not zlib's fails the
    connection, SQLCODE -919 and SQLSTATE 08006.
    """
    with pytest.raises(OperationalError) as failure:
        decompress(body, max_body)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")


def test_a_bomb_is_refused_before_it_is_held() -> None:
    """Verifies: [PROTOCOL Compressed frames] a stream cannot make it hold more.

    A stream of 16 MiB of zeros declaring 10 bytes inflates no further
    than 11.
    """
    bomb = zlib.compress(bytes(16 << 20))
    with pytest.raises(OperationalError):
        decompress(held(ord("B"), 10, bomb))


def test_a_compressed_frame_needs_compression_granted() -> None:
    """Verifies: [PROTOCOL Compressed frames] not granted, a `z` fails the connection.

    Granted, it is inflated; any other frame passes as it is.
    """
    body = held(ord("K"), 3, zlib.compress(b"abc"))
    assert unwrap(ord("K"), b"xyz", compression=False) == (ord("K"), b"xyz")
    assert unwrap(COMPRESSED, body, compression=True) == (ord("K"), b"abc")
    with pytest.raises(OperationalError):
        unwrap(COMPRESSED, body, compression=False)
