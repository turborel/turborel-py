"""Tests of every reply, decoded from the bytes its section lays out."""

from __future__ import annotations

import dataclasses

import pytest

from turborel import OperationalError
from turborel._codec.composites import Column, Parameter
from turborel._codec.datatypes import BooleanType, CharacterType, ExactType
from turborel._codec.failures import Diagnostics, Failure, Notice
from turborel._codec.frames import decode_header
from turborel._codec.replies import (
    Challenge,
    Complete,
    Description,
    Error,
    LobCreated,
    LobData,
    Pong,
    Prepared,
    Ready,
    Rows,
    Status,
    Suspended,
    Timing,
    decode,
)
from turborel._codec.requests import Close, Ping


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def u64(n: int) -> bytes:
    """A `u64`, little-endian."""
    return n.to_bytes(8, "little")


def text(s: str) -> bytes:
    """A string: its length, then its UTF-8."""
    return u32(len(s.encode())) + s.encode()


def frame(printed: str) -> object:
    """The reply of the frame the spec prints as `printed`, header and all."""
    data = bytes.fromhex(printed)
    kind, length = decode_header(data[:5])
    assert length == len(data) - 5
    return decode(kind, data[5:])


def test_the_worked_example_s_replies() -> None:
    """Verifies: [PROTOCOL A worked example] Pong, Rows of the number 1, Complete.

    [PROTOCOL Rows 'B'] a batch of rows; [PROTOCOL Complete 'K'] with an
    empty tail, its first form; then with `row-counts`, tags 6 and 18.
    """
    assert frame("47 00000000") == Pong()
    rows = "42 1D000000 01000000 01000000 02 01000000000000000000000000000000 00000000"
    assert frame(rows) == Rows(((1,),))
    complete = "4B 0E000000 00000000 05000000 3030303030 00"
    assert frame(complete) == Complete(0, "00000", active=False)
    counted = bytes.fromhex(complete[3:].replace(" ", ""))[4:]
    counted += b"\x06" + u64(1) + b"\x12" + u64(180) + u64(4) + u64(0)
    expected = Complete(0, "00000", active=False, rows=1, time=Timing(180, 4, 0))
    assert decode(ord("K"), counted) == expected


FAILURE = (
    u32((-103) & 0xFFFF_FFFF)
    + text("2A000")
    + text("column K is ambiguous")
    + b"\x01"
    + text("X3.135-1986 §5.7 SR3b")
    + b"\x01"
    + u64(7)
    + b"\x00"
)
CITED = Failure(
    -103, "2A000", "column K is ambiguous", "X3.135-1986 §5.7 SR3b", 7, active=False
)


def test_an_error_carries_all_its_failure_says() -> None:
    """Verifies: [PROTOCOL Error 'E'] a failure: SQLCODE, SQLSTATE, message.

    [PROTOCOL Composite fields] its rule if cited, its position if placed,
    whether a transaction is active; its tail 7 to 15, severity to
    constraint [PROTOCOL Errors and notices].
    """
    assert decode(ord("E"), FAILURE) == Error(CITED)
    plain = u32((-911) & 0xFFFF_FFFF) + text("TB911") + text("") + b"\x00\x00\x01"
    assert decode(ord("E"), plain) == Error(
        Failure(-911, "TB911", "", None, None, active=True)
    )
    diagnosed = (
        FAILURE
        + b"\x07"
        + text("ERROR")
        + b"\x0c"
        + text("STAFF")
        + b"\x0f"
        + text("PK")
    )
    expected = Diagnostics(severity="ERROR", table="STAFF", constraint="PK")
    assert decode(ord("E"), diagnosed) == Error(
        dataclasses.replace(CITED, diagnostics=expected)
    )


def test_a_notice_and_a_status() -> None:
    """Verifies: [PROTOCOL Notice 'N'] SQLSTATE, message, tail 7 to 15.

    [PROTOCOL Status 'T'] a name and its value, empty for a null.
    """
    notice = text("01T01") + text("rolled back") + b"\x07" + text("NOTICE")
    assert decode(ord("N"), notice) == Notice(
        "01T01", "rolled back", Diagnostics(severity="NOTICE")
    )
    assert decode(ord("N"), text("01000") + text("w")) == Notice(
        "01000", "w", Diagnostics()
    )
    assert decode(ord("T"), text("SERVER_READ_ONLY") + text("NO")) == Status(
        "SERVER_READ_ONLY", "NO"
    )
    assert decode(ord("T"), text("SCHEMA") + text("")) == Status("SCHEMA", "")


def test_a_complete_carries_its_whole_tail() -> None:
    """Verifies: [PROTOCOL Complete 'K'] tags 4, 5, 6, 16, 17 and 18, in order.

    Tag 17's conditions each a failure as bytes, its own tail ending where
    its length does.
    """
    condition = FAILURE + b"\x07" + text("WARNING")
    body = u32(0) + text("01000") + b"\x01"
    body += b"\x04" + u64(4711) + b"\x05" + b"\x06" + u64(3)
    body += b"\x10" + u32(2) + text("3") + text("4")
    body += b"\x11" + u32(1) + u32(len(condition)) + condition
    body += b"\x12" + u64(1) + u64(2) + u64(3)
    warned = dataclasses.replace(CITED, diagnostics=Diagnostics(severity="WARNING"))
    assert decode(ord("K"), body) == Complete(
        0,
        "01000",
        active=True,
        position=4711,
        more=True,
        rows=3,
        generated=("3", "4"),
        conditions=(warned,),
        time=Timing(1, 2, 3),
    )


def test_the_replies_of_a_login_and_a_statement() -> None:
    """Verifies: [PROTOCOL Ready 'R'] authorization, key, capabilities, server.

    [PROTOCOL Challenge 'C'] bytes; [PROTOCOL Prepared 'P'] statement,
    parameters, columns; [PROTOCOL Description 'D'] columns;
    [PROTOCOL Suspended 'S'] nothing; the key never shown (R-SAFE-4).
    """
    assert decode(ord("C"), u32(1) + b"\xff") == Challenge(b"\xff")
    key = bytes([0xAB]) * 16
    ready = text("ANN") + key + u32(1) + text("ping") + text("turborel 0.0.0 (alpha)")
    assert decode(ord("R"), ready) == Ready(
        "ANN", key, ("ping",), "turborel 0.0.0 (alpha)"
    )
    shown = repr(decode(ord("R"), ready))
    assert "key" not in shown
    assert repr(key) not in shown
    exact = bytes([2]) + u32(5) + u32(2)
    prepared = (
        u32(9) + u32(2) + b"\x01" + bytes([5]) + u32(9) + b"\x00" + b"\x00" + exact
    )
    prepared += u32(1) + b"\x01" + text("K") + bytes([14]) + b"\x01"
    assert decode(ord("P"), prepared) == Prepared(
        9,
        (
            Parameter(
                varying=True,
                data_type=CharacterType(varying=True, length=9, octets=False),
            ),
            Parameter(varying=False, data_type=ExactType(5, 2)),
        ),
        (Column("K", BooleanType(), not_null=True),),
    )
    assert decode(ord("P"), u32(0) + u32(0) + u32(0)) == Prepared(0, (), ())
    assert decode(ord("D"), u32(0)) == Description(())
    assert decode(ord("S"), b"") == Suspended()


def test_a_lob_reply_is_data_or_a_locator() -> None:
    """Verifies: [PROTOCOL Lob 'L'], the reply: 0 data, bytes; 1 locator, `u32`."""
    assert decode(ord("L"), b"\x00" + u32(2) + b"ab") == LobData(b"ab")
    assert decode(ord("L"), b"\x01" + u32(7)) == LobCreated(7)


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        (0, b""),  # no reply has kind 0
        (ord("Q"), b""),  # a request's kind
        (ord("z"), b""),  # a compressed frame, never decoded as a reply
        (ord("S"), b"\x00"),  # a byte after Suspended's end
        (ord("R"), b"\x00\x00\x00\x00\x01"),  # a key cut short
        (ord("B"), u32(1) + u32(1) + b"\x63"),  # a value of tag 99
        (ord("D"), u32(1) + b"\x02\x01" + u32(1) + b"\x00\x00"),  # a named flag of 2
        (ord("D"), u32(1) + b"\x00\x63\x00"),  # a type of tag 99
        (
            ord("K"),
            u32(0) + text("00000") + b"\x00" + b"\x06" + u64(1) + b"\x04" + u64(1),
        ),
        (ord("K"), u32(0) + text("00000") + b"\x00" + b"\x05\x05"),  # a tag twice
        (
            ord("K"),
            u32(0) + text("00000") + b"\x00" + b"\x03" + u32(1),
        ),  # a request's tag
        (
            ord("K"),
            u32(0)
            + text("00000")
            + b"\x00"
            + b"\x11"
            + u32(1)
            + u32(len(FAILURE) + 1)
            + FAILURE
            + b"\x00",
        ),
        (ord("E"), FAILURE + b"\x10" + u32(0)),  # Complete's tag on a failure
        (ord("L"), b"\x02"),
        (ord("N"), text("01000")),  # cut short
    ],
)
def test_a_reply_that_cannot_be_read_fails_the_connection(
    kind: int, body: bytes
) -> None:
    """Verifies: [PROTOCOL Errors and notices] a malformed message fails the connection.

    [PROTOCOL Frames] a kind the reader does not know, bytes left over;
    [PROTOCOL The tail] a tag out of order, twice, or not the message's:
    SQLCODE -919, SQLSTATE 08006.
    """
    with pytest.raises(OperationalError) as failure:
        decode(kind, body)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")


def test_a_kind_is_read_in_the_direction_it_travels() -> None:
    """Verifies: [PROTOCOL Frames] `C` from a client is Close, from a server Challenge.

    The same holds of `P`, `D`, `E`, `L`, `N` and `G`, each a request one
    way and a reply the other.
    """
    assert Close(2).encode()[0] == ord("C")
    assert decode(ord("C"), u32(0)) == Challenge(b"")
    assert Ping().encode()[0] == ord("G")
    assert decode(ord("G"), b"") == Pong()
