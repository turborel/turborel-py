"""Tests of the fields messages are made of, read and written."""

from __future__ import annotations

import pytest

from turborel import InterfaceError, OperationalError
from turborel._codec.fields import I128_MAX, I128_MIN, MAX_NESTING, Reader, Writer


def reader(data: bytes) -> Reader:
    """A reader of `data`, as a reply's body."""
    return Reader(data, "reply")


def refused(failure: pytest.ExceptionInfo[OperationalError]) -> None:
    """Check `failure` is a connection failure, -919 and 08006."""
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")


def test_integers_are_little_endian() -> None:
    """Verifies: [PROTOCOL Values and fields] integers least significant first.

    `u8`, `u32`, `u64` of 1, 4 and 8 bytes; an `i128` of 16 in two's
    complement; `i32 as u32` and `i64 as u64` the signed bits.
    """
    w = Writer()
    w.u8(0xAB)
    w.u32(0x0102_0304)
    w.u64(0x0102_0304_0506_0708)
    w.i128(-2)
    w.i32(-1)
    w.i64(-3)
    w.u16(0xFFFE)
    data = w.data()
    assert data[:5] == bytes([0xAB, 4, 3, 2, 1])
    assert data[5:13] == bytes([8, 7, 6, 5, 4, 3, 2, 1])
    assert data[13:29] == bytes([0xFE]) + bytes([0xFF] * 15)
    r = reader(data)
    assert (r.u8(), r.u32(), r.u64()) == (0xAB, 0x0102_0304, 0x0102_0304_0506_0708)
    assert (r.i128(), r.i32(), r.i64(), r.u16()) == (-2, -1, -3, 0xFFFE)
    r.finish()


@pytest.mark.parametrize("n", [I128_MIN, -1, 0, 1, I128_MAX])
def test_an_i128_reads_back_over_its_range(n: int) -> None:
    """Verifies: [PROTOCOL Values and fields] an `i128` at its limits."""
    w = Writer()
    w.i128(n)
    assert len(w.data()) == 16
    assert reader(w.data()).i128() == n


def test_strings_bytes_lists_and_keys() -> None:
    """Verifies: [PROTOCOL Values and fields] strings, bytes, lists and keys.

    A string is its length in bytes, then its UTF-8; bytes their length,
    then them; strings a list, its count first; a key 16 bytes alone.
    """
    w = Writer()
    w.string("é")
    w.octets(b"\x00\xff")
    w.strings(["a", ""])
    w.raw(bytes(range(16)))
    data = w.data()
    assert data[:6] == bytes([2, 0, 0, 0, 0xC3, 0xA9])
    assert data[6:12] == bytes([2, 0, 0, 0, 0, 0xFF])
    assert data[12:25] == bytes([2, 0, 0, 0, 1, 0, 0, 0, 0x61, 0, 0, 0, 0])
    r = reader(data)
    assert (r.string(), r.octets(), r.strings(), r.key()) == (
        "é",
        b"\x00\xff",
        ["a", ""],
        bytes(range(16)),
    )
    r.finish()


def test_a_flag_is_0_or_1() -> None:
    """Verifies: [PROTOCOL Values and fields] any other byte fails the connection."""
    w = Writer()
    w.flag(True)  # noqa: FBT003  # The flag's value.
    w.flag(False)  # noqa: FBT003  # The flag's value.
    r = reader(w.data() + b"\x02")
    assert (r.flag(), r.flag()) == (True, False)
    with pytest.raises(OperationalError) as failure:
        r.flag()
    refused(failure)


@pytest.mark.parametrize(
    "body",
    [
        b"",  # nothing where a u32 should be
        b"\x05\x00\x00\x00ab",  # a string cut short
        b"\x01\x00\x00\x00\xff",  # not UTF-8
    ],
)
def test_a_string_that_cannot_be_read_fails(body: bytes) -> None:
    """Verifies: [PROTOCOL Frames] a body cut short fails the connection.

    [PROTOCOL Values and fields] a string is UTF-8.
    """
    with pytest.raises(OperationalError) as failure:
        reader(body).string()
    refused(failure)
    assert "reply received is malformed" in failure.value.message


def test_a_count_past_what_follows_reserves_nothing() -> None:
    """Verifies: [PROTOCOL Values and fields] a count larger than what follows.

    It fails as the body runs out, after the items there are, holding
    nothing for the count.
    """
    body = bytes([0xFF, 0xFF, 0xFF, 0xFF, 1, 0, 0, 0, 0x61])
    with pytest.raises(OperationalError) as failure:
        reader(body).strings()
    refused(failure)


def test_bytes_left_after_the_last_field_fail() -> None:
    """Verifies: [PROTOCOL Frames] bytes left over fail the connection."""
    r = reader(b"\x01\x00")
    r.u8()
    with pytest.raises(OperationalError) as failure:
        r.finish()
    refused(failure)


def nest(r: Reader, levels: int) -> int:
    """Read `levels` levels deep, nothing at the bottom."""
    if levels == 0:
        return 0
    return r.nested(lambda inner: nest(inner, levels - 1))


def test_parts_nest_to_a_bound() -> None:
    """Verifies: [DESIGN] D14 values and types nest at most 16 deep."""
    assert nest(reader(b""), MAX_NESTING) == 0
    with pytest.raises(OperationalError) as failure:
        nest(reader(b""), MAX_NESTING + 1)
    refused(failure)


@pytest.mark.parametrize(
    ("write", "n"),
    [
        (Writer.u8, 256),
        (Writer.u16, -1),
        (Writer.u32, 1 << 32),
        (Writer.i32, 1 << 31),
        (Writer.u64, -1),
        (Writer.i64, 1 << 63),
        (Writer.i128, I128_MAX + 1),
    ],
)
def test_no_field_is_written_cut_to_fit(write: object, n: int) -> None:
    """Verifies: [PROTOCOL Values and fields] each field's width bounds it.

    A number its field cannot hold is refused, never written cut short.
    """
    assert callable(write)
    with pytest.raises(InterfaceError) as failure:
        write(Writer(), n)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-910, "TB910")
