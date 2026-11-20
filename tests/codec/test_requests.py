"""Tests of every request, encoded byte for byte as its section lays it out."""

from __future__ import annotations

import pytest

from turborel import InterfaceError, OperationalError
from turborel._codec.requests import (
    Answer,
    Cancel,
    ChangeUser,
    Close,
    CopyData,
    CopyEnd,
    CopyIn,
    Deallocate,
    Describe,
    Execute,
    Fetch,
    Hello,
    LobAppend,
    LobCreate,
    LobFree,
    LobHold,
    LobRead,
    Ping,
    Prepare,
    Query,
    Reset,
    Terminate,
)


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def u64(n: int) -> bytes:
    """A `u64`, little-endian."""
    return n.to_bytes(8, "little")


def text(s: str) -> bytes:
    """A string: its length, then its UTF-8."""
    return u32(len(s.encode())) + s.encode()


def framed(kind: str, body: bytes) -> bytes:
    """A frame of `kind` whose body is `body`."""
    return kind.encode() + u32(len(body)) + body


def test_the_worked_example_s_hello_is_41_bytes() -> None:
    """Verifies: [PROTOCOL A worked example] the Hello of trust as ANN, asking ping.

    [PROTOCOL Hello 'H'] version 1, user, mechanism, initial bytes,
    capabilities; no attributes, so no tail.
    """
    printed = bytes.fromhex(
        "48 24000000 01000000 03000000414E4E 050000007472757374"
        " 00000000 01000000 0400000070696E67"
    )
    hello = Hello("ANN", "trust", capabilities=("ping",)).encode()
    assert hello == printed
    assert len(hello) == 41


def test_the_worked_example_s_ping_and_query() -> None:
    """Verifies: [PROTOCOL A worked example] Ping, a header alone; `VALUES 1`, ends 1.

    [PROTOCOL Ping 'G'] [PROTOCOL Query 'Q'] sql, ends flag.
    """
    assert Ping().encode() == bytes.fromhex("4700000000")
    query = bytes.fromhex("51 0D000000 08000000 56414C5545532031 01")
    assert Query("VALUES 1", ends=True).encode() == query


@pytest.mark.parametrize(
    ("request_", "expected"),
    [
        (Answer(b"\x09\x09"), framed("A", u32(2) + b"\x09\x09")),
        (Query("AB", ends=True), framed("Q", text("AB") + b"\x01")),
        (Query("", multi=True), framed("Q", u32(0) + b"\x00\x02")),
        (
            Prepare(0xFFFF_FFFF, "SELECT ?"),
            framed("P", u32(0xFFFF_FFFF) + text("SELECT ?")),
        ),
        (Execute(1), framed("E", u32(1) + u32(0) + u32(0) + b"\x00")),
        (
            Execute(
                1, (None, "é"), rows=10, ends=True, attributes=(("A", "b"),), cursor=5
            ),
            framed(
                "E",
                u32(1)
                + u32(2)
                + b"\x00\x01"
                + text("é")
                + u32(10)
                + b"\x01"
                + b"\x01"
                + u32(1)
                + text("A")
                + text("b")
                + b"\x03"
                + u32(5),
            ),
        ),
        (Fetch(2, rows=0xFFFF_FFFF), framed("F", u32(2) + u32(0xFFFF_FFFF))),
        (Fetch(2, rows=1, cursor=3), framed("F", u32(2) + u32(1) + b"\x03" + u32(3))),
        (Close(2), framed("C", u32(2))),
        (Close(2, cursor=5), framed("C", u32(2) + b"\x03" + u32(5))),
        (Deallocate(4), framed("D", u32(4))),
        (Terminate(), framed("X", b"")),
        (Reset(), framed("W", b"")),
        (Describe(2), framed("Y", b"\x00" + u32(2) + u32(0))),
        (Describe(2, cursor=7), framed("Y", b"\x01" + u32(2) + u32(7))),
        (
            ChangeUser("BOB", "password", b"pw"),
            framed("U", text("BOB") + text("password") + u32(2) + b"pw"),
        ),
        (
            CopyIn("T", ("ID", "NAME"), ends=True),
            framed("I", text("T") + u32(2) + text("ID") + text("NAME") + b"\x01"),
        ),
        (CopyIn("T"), framed("I", text("T") + u32(0) + b"\x00")),
        (
            CopyData(((1,), (None,))),
            framed(
                "J",
                u32(2)
                + u32(1)
                + b"\x02"
                + (1).to_bytes(16, "little")
                + u32(0)
                + u32(1)
                + b"\x00",
            ),
        ),
        (CopyEnd(abandon=True), framed("N", b"\x01")),
        (
            LobRead(7, 300, 262_144, characters=True),
            framed("L", b"\x00" + u32(7) + u64(300) + u64(262_144) + b"\x01"),
        ),
        (LobCreate(binary=True), framed("L", b"\x01\x01")),
        (LobAppend(7, b"ab"), framed("L", b"\x02" + u32(7) + u32(2) + b"ab")),
        (LobFree(7), framed("L", b"\x03" + u32(7))),
        (LobHold(7), framed("L", b"\x04" + u32(7))),
    ],
)
def test_requests_are_their_fields_in_order(request_: object, expected: bytes) -> None:
    """Verifies: [PROTOCOL Requests] each request's fields, then its tail.

    [PROTOCOL The tail] each field only where it says something, in
    increasing order: 1 attributes, then 3 cursor; 2 multi alone; a
    request of none is its first form exactly. [PROTOCOL Lob 'L'], the
    request, its five ops.
    """
    encode = getattr(request_, "encode")  # noqa: B009  # Every request has one.
    assert encode() == expected


def test_a_cancel_carries_its_key_and_never_shows_it() -> None:
    """Verifies: [PROTOCOL Cancel 'Z'] the key, 16 bytes, the client's secret.

    Its display form leaves the key out (R-SAFE-4); a key not 16 bytes is
    refused before it is sent.
    """
    key = bytes([7]) * 16
    assert Cancel(key).encode() == framed("Z", key)
    assert "7" not in repr(Cancel(key))
    with pytest.raises(InterfaceError):
        Cancel(bytes(15)).encode()


def test_hello_carries_the_connection_s_attributes() -> None:
    """Verifies: [PROTOCOL Hello 'H'] tail 1, the connection's attributes."""
    hello = Hello("ANN", "trust", attributes=(("application", "psql"),)).encode()
    assert hello.endswith(b"\x01" + u32(1) + text("application") + text("psql"))


@pytest.mark.parametrize(
    "attributes",
    [
        [("N", "v")] * 33,
        [("", "v")],
        [("N" * 65, "v")],
        [("N", "v" * 1025)],
    ],
)
def test_attributes_past_their_bounds_are_refused(
    attributes: list[tuple[str, str]],
) -> None:
    """Verifies: [PROTOCOL The tail] at most 32 attributes, names 1 to 64 bytes.

    A value of at most 1024; the server fails the connection for more,
    with SQLCODE -919 and SQLSTATE 08006, so the driver refuses it with
    them before sending.
    """
    assert Query("X", attributes=[("N" * 64, "v" * 1024)] * 32).encode()
    with pytest.raises(OperationalError) as failure:
        Query("X", attributes=attributes).encode()
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")
