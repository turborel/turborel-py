"""Tests of large objects, copy, export and names over a peer of the test's own."""

from __future__ import annotations

import io

import pytest
from tests.kit import Peer, complete, description, error, frame, ready, rows, u32, u64

from turborel import DataError, InternalError, OperationalError
from turborel._codec.requests import COPY_DATA, COPY_END, COPY_IN, LOB, PING
from turborel._copy.names import column_name, delimited, table_name
from turborel.client import Connection, ExportFormat, Trust, read_native

ALL = ("copy", "ping")


def opened(peer: Peer, *capabilities: str) -> Connection:
    """A connection over `peer`, granted `capabilities`."""
    peer.reply(ready(capabilities=capabilities))
    conn = Connection.open(peer.client, "ANN", Trust())
    peer.received()
    return conn


def lob_data(data: bytes) -> bytes:
    """A Lob reply of data."""
    return frame("L", b"\x00" + u32(len(data)) + data)


def lob_locator(locator: int) -> bytes:
    """A Lob reply of a locator."""
    return frame("L", b"\x01" + u32(locator))


def test_lob_requests_and_their_replies() -> None:
    """Verifies: [PROTOCOL Lob 'L'] read, create, append, free and hold, each answered.

    A read by data, a create by a locator, the rest by Complete; any
    other reply loses the connection; [CLIENT Large objects] a writer's
    pieces sent in Appends.
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(lob_locator(9))
        writer = conn.create_lob(binary=True)
        assert peer.received() == (LOB, b"\x01\x01")
        writer.write(b"abc")
        peer.reply(complete())
        located = writer.finish()
        assert peer.received() == (LOB, b"\x02" + u32(9) + u32(3) + b"abc")
        assert (located.locator, located.octets, located.binary) == (9, 3, True)
        peer.reply(lob_data(b"ab"))
        assert conn.read_lob(located, 0, 2) == b"ab"
        assert peer.received() == (LOB, b"\x00" + u32(9) + u64(0) + u64(2) + b"\x00")
        peer.reply(complete(), complete())
        conn.hold_lob(located)
        conn.free_lob(located)
        assert peer.received() == (LOB, b"\x04" + u32(9))
        assert peer.received() == (LOB, b"\x03" + u32(9))
        peer.reply(error(-301, "0F001", "not valid"))
        with pytest.raises(Exception, match="not valid"):
            conn.read_lob(located, 0, 1)
        peer.reply(lob_locator(1))
        with pytest.raises(OperationalError):
            conn.read_lob(located, 0, 1)
        assert conn.is_lost
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(lob_data(b""))
        with pytest.raises(OperationalError):
            conn.create_lob(binary=False)
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(complete())
        with pytest.raises(OperationalError):
            conn.create_lob(binary=False)
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(rows())
        with pytest.raises(OperationalError):
            conn.hold_lob(located)


def test_a_reader_stops_at_the_length() -> None:
    """Verifies: [CLIENT Large objects] a reader of the whole value, a chunk at a time.

    One the server sends less of than its length fails; a held one has
    no locator to free or hold (22000).
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(lob_locator(4), complete())
        writer = conn.create_lob(binary=False)
        writer.write("é".encode())
        located = writer.finish()
        peer.reply(lob_data(b""))
        with pytest.raises(OperationalError, match="less of the large object"):
            conn.lob_reader(located).read()
        assert located.characters == 1
        for call in (conn.free_lob, conn.hold_lob):
            with pytest.raises(DataError):
                call(b"whole")
        assert conn.lob_reader(b"").readinto(bytearray(4)) == 0


def test_a_copy_s_requests() -> None:
    """Verifies: [PROTOCOL CopyIn 'I'] table, columns and ends; CopyData then CopyEnd.

    [PROTOCOL CopyData 'J'] rows with no reply; [PROTOCOL CopyEnd 'N']
    answered by a Complete counting the rows; [PROTOCOL Capabilities]
    `copy`, not granted, refused before anything is sent; a reply out of
    turn loses the connection, and a lost copy is not abandoned.
    """
    with Peer() as peer:
        conn = opened(peer)
        with pytest.raises(OperationalError):
            conn.copy_in("T")
    with Peer() as peer:
        conn = opened(peer, *ALL)
        copy = conn.copy_in("T", ("A",))
        assert peer.received()[0] == COPY_IN
        copy.send((True,))
        peer.reply(frame("G"))
        copy.ping()
        assert [peer.received()[0] for _ in range(2)] == [COPY_DATA, PING]
        peer.reply(complete(tail=b"\x06" + u64(1)))
        assert copy.finish() == 1
        assert peer.received() == (COPY_END, b"\x00")
        peer.reply(error(-201, "23000", "broken"))
        with pytest.raises(Exception, match="broken"):
            conn.copy_rows("T", (), [(True,)])
        peer.reply(rows())
        with conn.copy_in("T") as dropped, pytest.raises(OperationalError):
            dropped.finish()
        assert conn.is_lost


def test_an_export_that_cannot_write() -> None:
    """Verifies: [CLIENT Copying and exporting] export a query's rows as they come.

    A write that fails ends the export (08006), not the connection;
    native rows read back refuse input that is not theirs.
    """

    class Broken(io.BytesIO):
        def write(self, _: object) -> int:
            msg = "the disk is full"
            raise OSError(msg)

    with Peer() as peer:
        conn = opened(peer)
        peer.reply(description("A"), rows((True,)), complete())
        with pytest.raises(OperationalError, match="the disk is full"):
            conn.export("SELECT A FROM T", Broken())
        assert not conn.is_lost

    class Unflushed(io.BytesIO):
        def flush(self) -> None:
            msg = "cannot flush"
            raise OSError(msg)

    with Peer() as peer:
        conn = opened(peer)
        peer.reply(description("A"), rows((True,)), complete())
        with pytest.raises(OperationalError, match="cannot flush"):
            conn.export("SELECT A FROM T", Unflushed(), ExportFormat.NATIVE)
    for wrong in (
        b"",
        frame("B", u32(0)),
        description("A") + frame("G"),
        description("A") + b"K\x09",
    ):
        with pytest.raises(OperationalError, match="not native rows"):
            read_native(io.BytesIO(wrong))


def test_names_as_an_import_writes_them() -> None:
    """Verifies: [CLIENT Importing] a table named as SQL does, columns as headings do.

    A regular identifier in upper case, a delimited one as written, a
    key word refused as a table's name but a column's as it is.
    """
    assert table_name('ann . "My Table"') == '"ANN"."My Table"'
    assert table_name("c.s.t") == '"C"."S"."T"'
    for wrong in (
        "names",
        "a.b.c.d",
        "a..b",
        '""',
        '"open',
        "a b",
        "1a",
        "a" * 129,
        '"a\nb"',
        "a.",
    ):
        with pytest.raises(ValueError, match="is not a <table name>"):
            table_name(wrong)
    assert column_name("full_name") == "FULL_NAME"
    assert column_name("names") == "NAMES"
    assert column_name('"Mixed"') == "Mixed"
    assert column_name("FULL NAME") == "FULL NAME"
    assert column_name("1st") == "1st"
    assert delimited('a"b') == '"a""b"'


def test_an_abandon_answered_by_an_error() -> None:
    """Verifies: [PROTOCOL CopyEnd 'N'] answered by the copy's Error, or lost.

    Any other reply loses the connection.
    """
    with Peer() as peer:
        conn = opened(peer, *ALL)
        copy = conn.copy_in("T")
        peer.reply(error(-501, "24000", "open"))
        with pytest.raises(InternalError):
            copy.abandon()
        assert not conn.is_lost
