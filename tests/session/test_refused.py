"""Tests of replies holding a value the client cannot take, and of Terminate."""

from __future__ import annotations

import asyncio
import socket

import pytest
from tests.kit import (
    Peer,
    complete,
    description,
    frame,
    notice,
    ready,
    rows,
    text,
    u32,
)

from turborel import DatabaseError, OperationalError
from turborel._aio.client import AsyncClient
from turborel._aio.streams import AsyncStream
from turborel._auth.mechanisms import Trust
from turborel._session.capabilities import Offer
from turborel._transport.timeouts import Timeouts
from turborel.client import Complete, Connection

JSON: int = 25
TRUTH: int = 14


def row_of(value: bytes) -> bytes:
    """A Rows reply of one row of one value, written as `value`."""
    return frame("B", u32(1) + u32(1) + value)


def nested(depth: int) -> bytes:
    """A JSON document of arrays nested `depth` deep around a null."""
    node = bytes([0])
    for _ in range(depth):
        node = bytes([10]) + u32(1) + u32(len(node)) + u32(0) + node
    return bytes([1]) + node


def json_value(document: bytes) -> bytes:
    """A JSON value of the stored form `document`."""
    return bytes([JSON]) + u32(len(document)) + document


def character_column(units: int) -> bytes:
    """A Description of one CHARACTER column whose units byte is `units`."""
    return frame(
        "D", u32(1) + b"\x01" + text("C") + bytes([1]) + u32(1) + bytes([units, 0])
    )


def complete_with_bad_condition(*, more: bool = False, active: bool = False) -> bytes:
    """A Complete whose one condition is malformed, saying more follow if `more`."""
    body = u32(0) + text("00000") + bytes([1 if active else 0])
    body += (b"\x05" if more else b"") + b"\x11" + u32(1) + u32(1) + b"\xff"
    return frame("K", body)


NO_DATA = complete("02000")


def opened(peer: Peer, *capabilities: str) -> Connection:
    """A connection over `peer`, granted `capabilities`."""
    peer.reply(ready(capabilities=capabilities))
    conn = Connection.open(peer.client, "ANN", Trust())
    peer.received()
    return conn


def bad_then_own(bad: bytes) -> None:
    """A statement answered by `bad` fails alone; the next takes its own reply."""
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(bad, NO_DATA)
        with pytest.raises(DatabaseError) as failure:
            conn.query("SELECT V FROM T")
        assert failure.value.sqlstate in {"TB916", "0A000"}
        assert not conn.is_lost
        done = conn.query("DELETE FROM T")
        assert isinstance(done, Complete)
        assert (done.sqlcode, done.sqlstate) == (100, "02000")


@pytest.mark.parametrize(
    "bad",
    [
        description("A")
        + row_of(json_value(bytes([1, 0xEE])))
        + row_of(bytes([TRUTH, 1]))
        + complete(),
        description("A") + row_of(json_value(nested(130))) + complete(),
        description("A") + row_of(bytes([TRUTH, 2])) + complete(),
        description("A") + row_of(bytes([18])) + complete(),
        character_column(7) + row_of(bytes([TRUTH, 1])) + complete(),
        complete_with_bad_condition(),
        complete_with_bad_condition(more=True) + complete(),
        description("A")
        + row_of(bytes([TRUTH, 2]))
        + row_of(bytes([TRUTH, 5]))
        + notice("01000", "a warning")
        + complete(),
    ],
    ids=[
        "damaged JSON",
        "JSON too deep",
        "truth 2",
        "tag 18",
        "units 7",
        "condition",
        "condition, more",
        "two bad rows",
    ],
)
def test_a_bad_value_is_read_past_with_its_statement_s_replies(bad: bytes) -> None:
    """Verifies: [PROTOCOL Values and fields] a value the client cannot take.

    Its frame whole; [CLIENT Running statements] its statement fails with the value's
    error, not of class 08, the rest of its replies read past first, and
    the connection goes on: the next statement takes its own reply.
    """
    bad_then_own(bad)


def test_a_cursor_or_a_describe_reads_only_its_own() -> None:
    """Verifies: [CLIENT Running statements] a batch read past to its Suspended.

    A Describe of a cursor, answered by a Description alone, reads
    nothing past it; a Complete with a bad condition still tells whether
    a transaction is active.
    """
    with Peer() as peer:
        conn = opened(peer, "describe")
        prepared = frame("P", u32(0) + u32(0) + u32(0))
        peer.reply(
            prepared,
            row_of(bytes([TRUTH, 3])) + frame("S"),
            character_column(9),
            NO_DATA,
        )
        statement = conn.prepare("SELECT V FROM T")
        with pytest.raises(OperationalError) as cursor:
            conn.open_cursor(statement, rows=1)
        with pytest.raises(OperationalError) as described:
            conn.describe_cursor(statement)
        assert (cursor.value.sqlstate, described.value.sqlstate) == ("TB916", "TB916")
        done = conn.query("DELETE FROM T")
        assert isinstance(done, Complete)
        assert done.sqlcode == 100
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(complete_with_bad_condition(active=True))
        with pytest.raises(OperationalError):
            conn.query("COMMIT")
        assert conn.in_transaction


@pytest.mark.parametrize(
    "bad",
    [
        frame("K", u32(0) + text("00000") + b"\x02"),
        frame("K", u32(0) + text("00000") + b"\x00\x00"),
        description("A") + row_of(bytes([TRUTH, 2])) + frame("K", b"\x00"),
        description("A") + frame("B", u32(1) + u32(1) + bytes([99])),
    ],
    ids=[
        "a flag of 2",
        "a byte past its end",
        "cut short, read past",
        "a value of no tag",
    ],
)
def test_a_malformed_frame_loses_the_connection(bad: bytes) -> None:
    """Verifies: [PROTOCOL Values and fields] a malformed frame loses the connection.

    SQLSTATE 08006, and the next statement is told so.
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(bad, NO_DATA)
        with pytest.raises(OperationalError) as lost:
            conn.query("DELETE FROM T")
        assert lost.value.sqlstate == "08006"
        assert conn.is_lost
        with pytest.raises(OperationalError) as told:
            conn.query("DELETE FROM T")
        assert told.value.sqlstate == "08006"


def test_terminate_reads_past_a_notice_to_its_error() -> None:
    """Verifies: [CLIENT Connecting] Terminate reads past Notices to its Error.

    A Status too; the server's Error then given; a reply of another kind
    out of turn.
    """
    error = frame(
        "E", u32(0) + text("40002") + text("the commit failed") + b"\x00\x00\x00"
    )
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(
            notice("01000", "a warning"), frame("T", text("A") + text("B")), error
        )
        peer.close()
        with pytest.raises(Exception, match="the commit failed") as failed:
            conn.terminate()
        assert getattr(failed.value, "sqlstate", None) == "40002"
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(rows())
        peer.close()
        with pytest.raises(OperationalError, match="answered Terminate"):
            conn.terminate()


def test_terminate_on_a_stream_bounded_within_timeouts() -> None:
    """Verifies: [CLIENT Timeouts] a program's own stream opened within timeouts.

    Bounded as they say: Terminate waits at most the read timeout, and is
    told the server did not answer in time; the read timeout settable as
    a connection's.
    """
    client, server = socket.socketpair()
    with client, server:
        server.sendall(ready())
        conn = Connection.open_within(
            client, "ANN", Trust(), Timeouts(connect=5.0, read=0.05)
        )
        assert conn.read_timeout == 0.05
        with pytest.raises(OperationalError) as late:
            conn.terminate()
        assert late.value.sqlstate == "08006"


def test_the_asyncio_client_reads_past_a_bad_value() -> None:
    """Verifies: [CLIENT Running statements] for asyncio, a bad value read past.

    The same request generators: the statement fails alone, and the next
    takes its own reply.
    """

    async def main() -> None:
        with Peer() as peer:
            peer.client.setblocking(False)  # noqa: FBT003  # asyncio's.
            reader, writer = await asyncio.open_connection(sock=peer.client)
            peer.reply(ready())
            client = AsyncClient(AsyncStream(reader, writer), None)
            await client.log_in("ANN", Trust(), Offer())
            client.set_read_timeout(5)
            peer.reply(description("A"), row_of(bytes([TRUTH, 2])), complete(), NO_DATA)
            with pytest.raises(OperationalError) as failure:
                await client.query("SELECT V FROM T")
            assert failure.value.sqlstate == "TB916"
            done = await client.query("DELETE FROM T")
            assert isinstance(done, Complete)
            assert done.sqlcode == 100
            peer.reply(notice("01000", "a warning"))
            peer.close()
            await client.terminate()

    asyncio.run(main())
