"""Tests of a frame's header: written byte by byte, read back, refused."""

from __future__ import annotations

import pytest

from turborel import DatabaseError, Error, OperationalError
from turborel._codec.frames import (
    HEADER_BYTES,
    MAX_BODY,
    FrameHeader,
    decode_header,
    encode_header,
)

# The spec's worked example: each frame's kind, its body's length, and
# the header's bytes as the page prints them.
WORKED_EXAMPLE = [
    (0x48, 36, "48 24 00 00 00"),  # Hello
    (0x47, 0, "47 00 00 00 00"),  # Ping, and Pong
    (0x51, 13, "51 0D 00 00 00"),  # Query
    (0x42, 29, "42 1D 00 00 00"),  # Rows
    (0x4B, 14, "4B 0E 00 00 00"),  # Complete
]


def assert_connection_failure(failure: pytest.ExceptionInfo[OperationalError]) -> None:
    """Check that `failure` is a connection failure, -919 and 08006."""
    assert failure.value.sqlcode == -919
    assert failure.value.sqlstate == "08006"
    assert isinstance(failure.value, DatabaseError)
    assert isinstance(failure.value, Error)


def test_a_header_is_five_bytes() -> None:
    """Verifies: [PROTOCOL Frames] the header is five bytes."""
    assert HEADER_BYTES == 5
    assert len(encode_header(0x51, 13)) == HEADER_BYTES


@pytest.mark.parametrize(("kind", "length", "printed"), WORKED_EXAMPLE)
def test_headers_of_the_worked_example(kind: int, length: int, printed: str) -> None:
    """Verifies: [PROTOCOL A worked example] each frame's header, kind then length.

    [PROTOCOL Frames] kind `u8`, then the body's length `u32`, least
    significant byte first, the header not counted.
    """
    assert encode_header(kind, length) == bytes.fromhex(printed)
    assert decode_header(bytes.fromhex(printed)) == FrameHeader(kind, length)


@pytest.mark.parametrize("kind", [0, 1, 0x7F, 0xFF])
@pytest.mark.parametrize("length", [0, 1, 0x0102_0304, 0xFFFF_FFFF])
def test_a_header_reads_back_as_written(kind: int, length: int) -> None:
    """Verifies: [PROTOCOL Frames] every kind and length at their bounds.

    [PROTOCOL Values and fields] a `u32` is four bytes, least significant
    first.
    """
    header = encode_header(kind, length)
    assert header == bytes([kind]) + length.to_bytes(4, "little")
    assert decode_header(header, max_body=0xFFFF_FFFF) == FrameHeader(kind, length)


def test_the_client_takes_bodies_of_16_mib_by_default() -> None:
    """Verifies: [PROTOCOL Frames] the client takes replies of up to 16 MiB.

    One exactly as long is taken; one a byte longer fails the connection
    from its header alone.
    """
    assert MAX_BODY == 16 * 1024 * 1024
    assert decode_header(encode_header(0x42, MAX_BODY)).length == MAX_BODY
    with pytest.raises(OperationalError) as failure:
        decode_header(encode_header(0x42, MAX_BODY + 1))
    assert_connection_failure(failure)


@pytest.mark.parametrize("max_body", [0, 6, 16 * 1024])
def test_a_body_past_the_limit_given_fails_the_connection(max_body: int) -> None:
    """Verifies: [PROTOCOL Frames] a longer frame fails the connection.

    The limit is the reader's: a body of the limit is taken, one past it
    refused with SQLCODE -919 and SQLSTATE 08006.
    """
    assert decode_header(encode_header(0x4B, max_body), max_body).length == max_body
    with pytest.raises(OperationalError) as failure:
        decode_header(encode_header(0x4B, max_body + 1), max_body)
    assert_connection_failure(failure)
    assert str(max_body + 1) in failure.value.message


@pytest.mark.parametrize("header", [b"", b"\x47", b"\x47\x00\x00\x00", bytes(6)])
def test_a_header_not_of_five_bytes_fails_the_connection(header: bytes) -> None:
    """Verifies: [PROTOCOL Frames] a body cut short fails the connection.

    A header is the first five bytes of every frame, so fewer or more is
    a frame that cannot be read.
    """
    with pytest.raises(OperationalError) as failure:
        decode_header(header)
    assert_connection_failure(failure)


@pytest.mark.parametrize(
    ("kind", "length"), [(-1, 0), (0x100, 0), (0, -1), (0, 1 << 32)]
)
def test_no_header_is_written_that_a_frame_cannot_carry(kind: int, length: int) -> None:
    """Verifies: [PROTOCOL Frames] a kind is a `u8` and a length a `u32`.

    A kind or a length past its field is refused as a connection failure
    before a byte is written, never written cut to fit.
    """
    with pytest.raises(OperationalError) as failure:
        encode_header(kind, length)
    assert_connection_failure(failure)
