"""Tests of statements over a peer of the test's own: their requests and replies."""

from __future__ import annotations

import pytest
from tests.kit import (
    Peer,
    complete,
    description,
    error,
    frame,
    ready,
    rows,
    text,
    u32,
    u64,
)

from turborel import InternalError, OperationalError, ProgrammingError
from turborel._codec.requests import (
    CLOSE,
    DEALLOCATE,
    DESCRIBE,
    EXECUTE,
    FETCH,
    PREPARE,
    QUERY,
)
from turborel.client import Complete, Connection, Rowset, Trust

ALL = ("cursors", "describe", "multi-statement", "query-attributes", "fetch-ends")


def opened(peer: Peer, *capabilities: str) -> Connection:
    """A connection over `peer`, granted `capabilities`."""
    peer.reply(ready(capabilities=capabilities))
    conn = Connection.open(peer.client, "ANN", Trust())
    peer.received()
    return conn


def prepared(number: int, columns: int) -> bytes:
    """A Prepared of `number`, one BOOLEAN parameter, `columns` BOOLEAN columns."""
    body = u32(number) + u32(1) + b"\x00\x0e" + u32(columns)
    body += (b"\x01" + text("A") + b"\x0e\x00") * columns
    return frame("P", body)


def test_prepare_execute_and_deallocate() -> None:
    """Verifies: [PROTOCOL Prepare 'P'] the client's number, then Prepared.

    [PROTOCOL Execute 'E'] values, all rows, ends as autocommit says; a
    statement not a query answered by Complete; [PROTOCOL Deallocate 'D'].
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(prepared(0, 0))
        insert = conn.prepare("INSERT INTO T VALUES (?)")
        assert peer.received()[0] == PREPARE
        assert (insert.number, len(insert.parameters), insert.columns) == (0, 1, ())
        peer.reply(complete(tail=b"\x06" + u64(1)))
        done = conn.execute(insert, (True,))
        assert isinstance(done, Complete)
        assert conn.rows_affected == 1
        kind, body = peer.received()
        assert (kind, body[:4]) == (EXECUTE, u32(0))
        peer.reply(complete())
        conn.deallocate(insert)
        assert peer.received() == (DEALLOCATE, u32(0))
        peer.reply(prepared(1, 1))
        query = conn.prepare("SELECT A FROM T WHERE A = ?")
        peer.reply(rows((True,)), complete())
        outcome = conn.execute(query, (True,))
        assert isinstance(outcome, Rowset)
        assert outcome.rows == [(True,)]


def test_a_cursor_read_in_batches() -> None:
    """Verifies: [PROTOCOL Execute 'E'] rows sent now, then Suspended, the cursor open.

    [PROTOCOL Fetch 'F'] more rows, then Complete; [PROTOCOL Close 'C'];
    with `cursors`, a numbered cursor by tag 3; with `fetch-ends` under
    autocommit, the cursor's Execute ends the transaction with it.
    """
    with Peer() as peer:
        conn = opened(peer, *ALL)
        peer.reply(prepared(0, 1))
        statement = conn.prepare("SELECT A FROM T")
        peer.received()
        conn.autocommit = True
        peer.reply(rows((True,)), frame("S"))
        first = conn.open_cursor(statement, rows=1, cursor=2)
        assert (first.rows, first.more) == ([(True,)], True)
        kind, body = peer.received()
        assert kind == EXECUTE
        assert body.endswith(u32(1) + b"\x01" + b"\x03" + u32(2))
        peer.reply(rows((False,)), complete())
        rest = conn.fetch(statement, rows=5, cursor=2)
        assert (rest.rows, rest.more) == ([(False,)], False)
        assert peer.received() == (FETCH, u32(0) + u32(5) + b"\x03" + u32(2))
        peer.reply(complete())
        conn.close_cursor(statement, cursor=2)
        assert peer.received() == (CLOSE, u32(0) + b"\x03" + u32(2))
        peer.reply(error(-501, "24000", "the cursor is not open"))
        with pytest.raises(InternalError):
            conn.fetch(statement, cursor=2)


def test_numbered_cursors_and_describe_need_their_capabilities() -> None:
    """Verifies: [PROTOCOL Capabilities] `cursors` and `describe`, not granted.

    A method needing one fails before it sends anything, the connection
    kept [CLIENT What a connection asks for].
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(prepared(0, 1))
        statement = conn.prepare("SELECT A FROM T")
        for call in (
            lambda: conn.open_cursor(statement, cursor=1),
            lambda: conn.fetch(statement, cursor=1),
            lambda: conn.close_cursor(statement, cursor=1),
            lambda: conn.describe(statement),
            lambda: conn.describe_cursor(statement),
            lambda: conn.query_many("VALUES 1; VALUES 2"),
            lambda: conn.set_query_attributes([("k", "v")]),
        ):
            with pytest.raises(OperationalError):
                call()
        assert not conn.is_lost


def test_describe_a_statement_and_a_cursor() -> None:
    """Verifies: [PROTOCOL Describe 'Y'] a statement, then an open cursor."""
    with Peer() as peer:
        conn = opened(peer, *ALL)
        peer.reply(prepared(0, 1))
        statement = conn.prepare("SELECT A FROM T")
        peer.received()
        peer.reply(prepared(0, 1))
        assert conn.describe(statement) == statement
        assert peer.received() == (DESCRIBE, b"\x00" + u32(0) + u32(0))
        peer.reply(description("A"))
        assert len(conn.describe_cursor(statement, cursor=3)) == 1
        assert peer.received() == (DESCRIBE, b"\x01" + u32(0) + u32(3))
        peer.reply(error(-501, "24000", "not open"))
        with pytest.raises(InternalError):
            conn.describe_cursor(statement, cursor=4)
        peer.reply(rows())
        with pytest.raises(OperationalError):
            conn.describe_cursor(statement, cursor=4)
        assert conn.is_lost


def test_several_statements_and_their_outcomes() -> None:
    """Verifies: [PROTOCOL Query 'Q'] tag 2, several statements; tag 5 but on the last.

    [CLIENT Controlling the session] each outcome, and the failure that
    stopped the rest.
    """
    with Peer() as peer:
        conn = opened(peer, *ALL)
        peer.reply(complete(tail=b"\x05"), description("A"), rows((True,)), complete())
        ran = conn.query_many("UPDATE T SET A = TRUE; SELECT A FROM T")
        assert len(ran.outcomes) == 2
        assert ran.failure is None
        assert peer.received()[1].endswith(b"\x02")
        peer.reply(complete(tail=b"\x05"), error(-103, "42000", "no"))
        stopped = conn.query_many("VALUES 1; NOPE")
        assert (len(stopped.outcomes), type(stopped.failure)) == (1, ProgrammingError)
        peer.reply(frame("G"))
        with pytest.raises(OperationalError):
            conn.query_many("VALUES 1")


def test_query_attributes_go_with_each_statement() -> None:
    """Verifies: [CLIENT Controlling the session] query attributes, until set again.

    [PROTOCOL The tail] tag 1 on Query and Execute, with `query-attributes`.
    """
    with Peer() as peer:
        conn = opened(peer, *ALL)
        conn.set_query_attributes([("k", "v")])
        peer.reply(complete())
        conn.query("VALUES 1")
        kind, body = peer.received()
        assert kind == QUERY
        assert body.endswith(b"\x01" + u32(1) + text("k") + text("v"))


def test_a_query_s_rows_given_to_a_sink() -> None:
    """Verifies: [CLIENT Running statements] a query's rows a batch at a time.

    A Complete alone is given back; rows broken off lose the connection.
    """

    class Counted:
        def __init__(self) -> None:
            self.batches = 0

        def columns(self, _: object) -> None:
            return

        def rows(self, _: object) -> None:
            self.batches += 1

    with Peer() as peer:
        conn = opened(peer)
        sink = Counted()
        peer.reply(description("A"), rows((True,)), rows((False,), (True,)), complete())
        assert conn.query_into("SELECT A FROM T", sink) == 3
        assert sink.batches == 2
        peer.reply(complete())
        assert isinstance(conn.query_into("UPDATE T SET A = TRUE", sink), Complete)
        peer.reply(error(-103, "42000", "no"))
        with pytest.raises(ProgrammingError):
            conn.query_into("NOPE", sink)
        peer.reply(description("A"), error(-301, "22003", "out of range"))
        with pytest.raises(Exception, match="out of range"):
            conn.query_into("SELECT A FROM T", sink)
        peer.reply(description("A"), frame("G"))
        with pytest.raises(OperationalError):
            conn.query_into("SELECT A FROM T", sink)


def test_what_the_completion_told() -> None:
    """Verifies: [CLIENT What the server tells] rows, generated values, time, position.

    [PROTOCOL Complete 'K'] tags 4, 6, 16 and 18; tag 17's conditions,
    and a warning's SQLSTATE.
    """
    condition = struct_failure()
    tail = (
        b"\x04" + u64(9) + b"\x06" + u64(2) + b"\x10" + u32(2) + text("1") + text("2")
    )
    tail += b"\x11" + u32(1) + u32(len(condition)) + condition
    tail += b"\x12" + u64(30) + u64(4) + u64(1)
    with Peer() as peer:
        conn = opened(peer)
        before = (conn.rows_affected, conn.last_generated, conn.server_time)
        assert (*before, len(conn.conditions)) == (None, (), None, 0)
        peer.reply(complete("01004", tail=tail))
        conn.query("INSERT INTO T VALUES (1), (2)")
        assert (conn.commit_position, conn.rows_affected) == (9, 2)
        assert conn.last_generated == ("1", "2")
        assert conn.warning == "01004"
        assert [c.sqlstate for c in conn.conditions] == ["01004"]
        time = conn.server_time
        assert time is not None
        assert (time.total, time.queued, time.locks) == (30, 4, 1)


def struct_failure() -> bytes:
    """A condition's body: a warning of 01004."""
    return u32(0) + text("01004") + text("truncated") + b"\x00\x00\x00"
