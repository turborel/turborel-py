"""Live tests of statements: queries, prepared statements, cursors, completions."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from turborel import (
    DataError,
    IntegrityError,
    InternalError,
    Interval,
    IntervalField,
    LargeObject,
    LobLocator,
    OperationalError,
    ProgrammingError,
    Qualifier,
    Xml,
)
from turborel.client import (
    Complete,
    Connection,
    Offer,
    Rowset,
    Scram,
    Tcp,
    Trust,
    connect,
    connect_local,
    connect_to,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from live import Live

    from turborel._codec.composites import Column


@pytest.fixture
def conn(live: Live) -> Iterator[Connection]:
    """A connection by trust, granted every capability but compression."""
    connection = connect((live.host, live.port), "ANN", Trust())
    yield connection
    if not connection.is_lost:
        connection.terminate()


def rows_of(outcome: object) -> list[tuple[object, ...]]:
    """A query's rows."""
    assert isinstance(outcome, Rowset)
    return outcome.rows


def test_a_statement_s_outcome(conn: Connection) -> None:
    """Verifies: [CLIENT Running statements] a query's columns and rows, or completion.

    [PROTOCOL Query 'Q'] a query answered by Description, Rows and
    Complete; another statement by Complete; a query of no row completes
    with SQLCODE 100 and SQLSTATE 02000.
    """
    conn.query("CREATE TABLE OUTCOME (ID INTEGER, NAME VARCHAR(10))")
    done = conn.query("INSERT INTO OUTCOME VALUES (1, 'Ada'), (2, 'Grace')")
    assert isinstance(done, Complete)
    assert (done.sqlcode, done.sqlstate) == (0, "00000")
    rowset = conn.query("SELECT ID, NAME FROM OUTCOME ORDER BY ID")
    assert isinstance(rowset, Rowset)
    assert [c.name for c in rowset.columns] == ["ID", "NAME"]
    assert rowset.rows == [(1, "Ada"), (2, "Grace")]
    nothing = conn.query("UPDATE OUTCOME SET NAME = 'x' WHERE ID = 99")
    assert isinstance(nothing, Complete)
    assert (nothing.sqlcode, nothing.sqlstate) == (100, "02000")
    assert rows_of(conn.query("SELECT ID FROM OUTCOME WHERE ID = 99")) == []
    conn.query("ROLLBACK")


def test_a_failure_carries_all_its_error_says(conn: Connection) -> None:
    """Verifies: [CLIENT Running statements] SQLCODE, SQLSTATE, message, rule, position.

    [CLIENT What the server tells] with `diagnostics`, its severity and
    what it is about; a duplicate key names its constraint and table, its
    detail the key.
    """
    with pytest.raises(ProgrammingError) as failure:
        conn.query("SELECT * FROM NOPE")
    error = failure.value
    assert (error.sqlcode, error.sqlstate) == (-103, "42000")
    assert error.message == "table ANN.NOPE is not defined"
    assert error.rule == "X3.135-1986 §5.4 SR5"
    assert error.position == 14
    assert error.diagnostics is not None
    assert (error.diagnostics.severity, error.diagnostics.table) == ("ERROR", "NOPE")
    conn.query("CREATE TABLE KEYED (ID INTEGER PRIMARY KEY)")
    conn.query("INSERT INTO KEYED VALUES (1)")
    with pytest.raises(IntegrityError) as duplicate:
        conn.query("INSERT INTO KEYED VALUES (1)")
    told = duplicate.value.diagnostics
    assert told is not None
    assert (told.table, told.detail) == ("KEYED", "the key (1) is held by another row")
    assert told.constraint is not None
    conn.query("ROLLBACK")


def test_every_value_reaches_python(conn: Connection) -> None:
    """Verifies: [CLIENT Running statements] exact, approximate, character, binary.

    Datetimes, intervals and null too, each as Appendix A maps it.
    """
    sql = (
        "VALUES (CAST(1.50 AS DECIMAL(5,2)), CAST(0.5 AS DOUBLE PRECISION), 'é',"
        " X'00FF', DATE '2024-02-29', TIME '23:59:59.5',"
        " TIMESTAMP '2026-11-19 01:02:03.000004', INTERVAL '1-2' YEAR TO MONTH,"
        " CAST(NULL AS INTEGER))"
    )
    [row] = rows_of(conn.query(sql))
    qualifier = Qualifier(IntervalField.YEAR, IntervalField.MONTH, 2, 0)
    assert row == (
        Decimal("1.50"),
        0.5,
        "é",
        b"\x00\xff",
        dt.date(2024, 2, 29),
        dt.time(23, 59, 59, 500_000),
        dt.datetime(2026, 11, 19, 1, 2, 3, 4),  # noqa: DTZ001  # Without a zone.
        Interval(qualifier, 14),
        None,
    )


def test_a_query_s_rows_a_batch_at_a_time(conn: Connection) -> None:
    """Verifies: [CLIENT Running statements] a query's rows given a batch at a time."""

    class Taken:
        def __init__(self) -> None:
            self.names: list[str | None] = []
            self.batches: list[int] = []

        def columns(self, columns: tuple[Column, ...]) -> None:
            self.names = [c.name for c in columns]

        def rows(self, rows: tuple[tuple[object, ...], ...]) -> None:
            self.batches.append(len(rows))

    taken = Taken()
    count = conn.query_into("VALUES 1, 2, 3", taken)
    assert (count, taken.names, sum(taken.batches)) == (3, [None], 3)
    done = conn.query_into("SET TIME ZONE LOCAL", taken)
    assert isinstance(done, Complete)


def test_a_transaction_lasts_until_commit_unless_autocommit(conn: Connection) -> None:
    """Verifies: [CLIENT Running statements] a transaction begun by the first statement.

    Lasting until COMMIT or ROLLBACK; whether one is active, as the server
    said; autocommit, each statement its own transaction by `ends`
    [PROTOCOL Query 'Q'], committed as it succeeds and rolled back as it
    fails [PROTOCOL Conversations].
    """
    conn.query("CREATE TABLE ENDS (N INTEGER PRIMARY KEY)")
    began = conn.in_transaction
    conn.query("COMMIT")
    committed = conn.in_transaction
    conn.autocommit = True
    conn.query("INSERT INTO ENDS VALUES (1)")
    assert (began, committed, conn.in_transaction) == (True, False, False)
    with pytest.raises(IntegrityError) as failure:
        conn.query("INSERT INTO ENDS VALUES (1)")
    assert failure.value.transaction_active is False
    assert rows_of(conn.query("SELECT N FROM ENDS")) == [(1,)]
    assert conn.autocommit


def test_several_statements_as_one_request(conn: Connection) -> None:
    """Verifies: [CLIENT Controlling the session] several statements, one request.

    [PROTOCOL Query 'Q'] with tag 2, each run in turn, the first failure
    ending the replies; each outcome, and the failure that stopped the
    rest.
    """
    ran = conn.query_many("VALUES 1; VALUES 2")
    assert [rows_of(o) for o in ran.outcomes] == [[(1,)], [(2,)]]
    assert ran.failure is None
    stopped = conn.query_many("VALUES 1; SELECT * FROM NOPE; VALUES 3")
    assert len(stopped.outcomes) == 1
    assert isinstance(stopped.failure, ProgrammingError)
    assert not conn.is_lost


def test_prepared_statements_and_their_cursors(conn: Connection) -> None:
    """Verifies: [CLIENT Prepared statements] prepare, execute, cursors, deallocate.

    [PROTOCOL Prepare 'P'] parameters in the order of their `?` marks, a
    query's columns; [PROTOCOL Execute 'E'] values, rows sent now, then
    Suspended, the cursor open; [PROTOCOL Fetch 'F'] the next batch;
    [PROTOCOL Close 'C']; [PROTOCOL Deallocate 'D']; a statement valid
    across transactions.
    """
    conn.query("CREATE TABLE PREPARED (ID INTEGER, NAME VARCHAR(10))")
    insert = conn.prepare("INSERT INTO PREPARED VALUES (?, ?)")
    assert len(insert.parameters) == 2
    assert insert.columns == ()
    for n, name in enumerate(["a", "b", "c"], 1):
        done = conn.execute(insert, (n, name))
        assert isinstance(done, Complete)
    conn.query("COMMIT")
    by_id = conn.prepare("SELECT NAME FROM PREPARED WHERE ID > ? ORDER BY ID")
    assert [c.name for c in by_id.columns] == ["NAME"]
    assert rows_of(conn.execute(by_id, (1,))) == [("b",), ("c",)]
    first = conn.open_cursor(by_id, (0,), rows=2)
    assert (first.rows, first.more) == ([("a",), ("b",)], True)
    rest = conn.fetch(by_id, rows=2)
    assert (rest.rows, rest.more) == ([("c",)], False)
    again = conn.open_cursor(by_id, (0,), rows=1)
    assert again.more
    conn.close_cursor(by_id)
    with pytest.raises(InternalError) as closed:
        conn.fetch(by_id)
    assert closed.value.sqlstate.startswith("24")
    conn.deallocate(by_id)
    with pytest.raises(ProgrammingError) as gone:
        conn.deallocate(by_id)
    assert gone.value.sqlstate == "26000"
    conn.query("ROLLBACK")


def test_numbered_cursors_and_describe(conn: Connection) -> None:
    """Verifies: [CLIENT Controlling the session] several cursors of one statement.

    [PROTOCOL Execute 'E'] cursor 0 unless tag 3 names another, with
    `cursors`, one already open failing (24000); [PROTOCOL Describe 'Y'] a
    statement, answered by Prepared, and an open cursor, by Description.
    """
    statement = conn.prepare("VALUES 1, 2, 3")
    a = conn.open_cursor(statement, rows=1, cursor=1)
    b = conn.open_cursor(statement, rows=2, cursor=2)
    assert (a.rows, b.rows) == ([(1,)], [(1,), (2,)])
    with pytest.raises(InternalError) as open_already:
        conn.open_cursor(statement, rows=1, cursor=1)
    assert open_already.value.sqlstate.startswith("24")
    assert conn.describe(statement).columns == statement.columns
    assert len(conn.describe_cursor(statement, cursor=2)) == 1
    assert conn.fetch(statement, cursor=1).rows == [(2,), (3,)]
    conn.close_cursor(statement, cursor=2)
    conn.query("ROLLBACK")


def test_a_cursor_under_autocommit_ends_its_transaction(conn: Connection) -> None:
    """Verifies: [CLIENT What the server tells] under autocommit, with `fetch-ends`.

    The fetch that reads the last row commits [PROTOCOL Conversations],
    the cursor read in parts, its transaction ended by the Fetch.
    """
    conn.autocommit = True
    statement = conn.prepare("VALUES 1, 2, 3")
    conn.open_cursor(statement, rows=2)
    reading = conn.in_transaction
    assert conn.fetch(statement, rows=2).rows == [(3,)]
    assert (reading, conn.in_transaction) == (True, False)


def test_what_a_completion_tells(live: Live, conn: Connection) -> None:
    """Verifies: [CLIENT What the server tells] rows, generated values, time, position.

    [PROTOCOL Complete 'K'] tag 4 the commit's position, tag 6 the rows
    changed, tag 16 the identity values in their rows' order, tag 18 the
    server's time; tag 17 the conditions, with `conditions`.
    """
    conn.query("CREATE TABLE TOLD (ID INTEGER GENERATED ALWAYS AS IDENTITY, N INTEGER)")
    conn.query("COMMIT")
    position = conn.commit_position
    assert position is not None
    conn.query("INSERT INTO TOLD (N) VALUES (5), (6)")
    assert (conn.rows_affected, conn.last_generated) == (2, ("1", "2"))
    time = conn.server_time
    assert time is not None
    assert time.total >= time.locks >= 0
    conn.query("COMMIT")
    assert (conn.commit_position or 0) > position
    rowset = conn.query("SELECT CAST('abc' AS CHAR(2)) FROM TOLD")
    assert conn.rows_affected == len(rows_of(rowset)) == 2
    assert conn.warning == "01004"
    assert [c.sqlstate for c in conn.conditions] == ["01004"]
    assert conn.take_notices() == []
    noticed = connect_to(
        Tcp(live.host, live.port),
        "ANN",
        Trust(),
        offer=Offer(capabilities=("notices",)),
    )
    noticed.query("SELECT CAST('abc' AS CHAR(2)) FROM TOLD")
    assert [n.sqlstate for n in noticed.take_notices()] == ["01004"]
    noticed.terminate()


def test_query_attributes_reach_the_statement(conn: Connection) -> None:
    """Verifies: [CLIENT Controlling the session] query attributes on later statements.

    Read in SQL by QUERY_ATTRIBUTE, until set again [PROTOCOL Query 'Q'].
    """
    conn.set_query_attributes([("k", "v")])
    assert rows_of(conn.query("VALUES QUERY_ATTRIBUTE('k')")) == [("v",)]
    statement = conn.prepare("VALUES QUERY_ATTRIBUTE('k')")
    assert rows_of(conn.execute(statement)) == [("v",)]
    conn.set_query_attributes([])
    assert rows_of(conn.query("VALUES QUERY_ATTRIBUTE('k')")) == [(None,)]


def test_xml_and_uuid_values(conn: Connection) -> None:
    """Verifies: [CLIENT XML values] an XML value as its text, its nodes, a parameter.

    [CLIENT UUIDs] a UUID read as its octets and text, and sent of either.
    """
    conn.query("CREATE TABLE ORDERS (ID INTEGER, BODY XML)")
    insert = conn.prepare("INSERT INTO ORDERS VALUES (?, ?)")
    conn.execute(insert, (18, Xml('<order no="18"><item>jam</item></order>')))
    [(body,)] = rows_of(conn.query("SELECT BODY FROM ORDERS WHERE ID = 18"))
    assert body == Xml('<order no="18"><item>jam</item></order>')
    assert isinstance(body, Xml)
    [order] = body.nodes()
    assert getattr(order, "tag") == "order"  # noqa: B009  # An element.
    conn.query("CREATE TABLE TICKETS (ID UUID, SEAT VARCHAR(4))")
    ticket = conn.prepare("INSERT INTO TICKETS VALUES (?, ?)")
    known = uuid.UUID("919108f7-52d1-4320-9bac-f847db4148a8")
    conn.execute(ticket, (known, "12A"))
    conn.execute(ticket, (uuid.UUID(bytes=bytes(range(16))), "12B"))
    found = rows_of(conn.query("SELECT ID FROM TICKETS ORDER BY SEAT"))
    assert found == [(known,), (uuid.UUID(bytes=bytes(range(16))),)]
    assert str(found[0][0]) == "919108f7-52d1-4320-9bac-f847db4148a8"
    conn.query("ROLLBACK")


def test_a_value_the_server_cannot_serialize_fails_the_fetch(conn: Connection) -> None:
    """Verifies: [CLIENT XML values] an attribute alone fails the fetch (2200W)."""
    with pytest.raises(DataError) as failure:
        conn.query(
            "VALUES XMLQUERY('/a/@x' PASSING BY VALUE XMLPARSE(DOCUMENT '<a x=\"1\"/>'"
            " PRESERVE WHITESPACE) RETURNING SEQUENCE NULL ON EMPTY)"
        )
    assert failure.value.sqlstate == "2200W"


def test_reset_forgets_prepared_statements(live: Live) -> None:
    """Verifies: [PROTOCOL Reset 'W'] prepared statements and settings gone.

    [PROTOCOL ChangeUser 'U'] refused, the connection fails; the session
    otherwise renewed, under a new cancel key.
    """
    conn = connect_local(live.socket, "ANN", Trust())
    statement = conn.prepare("VALUES 1")
    conn.reset()
    with pytest.raises(ProgrammingError) as gone:
        conn.execute(statement)
    assert gone.value.sqlstate == "26000"
    with pytest.raises(OperationalError):
        conn.change_user("ANN", Scram("wrong"))
    assert conn.is_lost


def test_a_cursor_closed_under_autocommit_commits(conn: Connection) -> None:
    """Verifies: [CLIENT What the server tells] under autocommit, close commits.

    [PROTOCOL Execute 'E'] a cursor left open keeps the transaction, ended
    with it under `fetch-ends`.
    """
    conn.autocommit = True
    statement = conn.prepare("VALUES 1, 2, 3")
    conn.open_cursor(statement, rows=1)
    open_kept = conn.in_transaction
    conn.close_cursor(statement)
    assert (open_kept, conn.in_transaction) == (True, False)


def test_a_result_sent_by_locator_keeps_its_transaction(conn: Connection) -> None:
    """Verifies: [PROTOCOL Query 'Q'] a locator sent keeps the transaction.

    A large object longer than SERVER.LOB_INLINE_BYTES comes by its
    locator, which lasts only as long as the transaction, so under
    autocommit the transaction stays active [PROTOCOL Values].
    """
    conn.query("CREATE TABLE SCANS (ID INTEGER, BODY CLOB(1M))")
    insert = conn.prepare("INSERT INTO SCANS VALUES (1, ?)")
    conn.execute(insert, (LargeObject("x" * 70_000),))
    conn.query("COMMIT")
    conn.autocommit = True
    [(body,)] = rows_of(conn.query("SELECT BODY FROM SCANS"))
    assert isinstance(body, LobLocator)
    assert (body.binary, body.characters, conn.in_transaction) == (False, 70_000, True)
    conn.query("COMMIT")


def test_reset_in_a_transaction(conn: Connection) -> None:
    """Verifies: [PROTOCOL Reset 'W'] the transaction rolled back, the session renewed.

    Prepared statements, temporary tables and settings gone, the
    authentication kept; its replies a Notice of 01T01 of severity NOTICE
    [PROTOCOL Errors and notices], told as a Notice though `conditions`
    is granted; then each setting's Status; then no transaction active
    [PROTOCOL Conversations] [CLIENT Controlling the session].
    """
    conn.query("CREATE LOCAL TEMPORARY TABLE SCRATCH (N INTEGER)")
    conn.query("SET TIME ZONE INTERVAL '+02:00' HOUR TO MINUTE")
    statement = conn.prepare("VALUES 1")
    conn.reset()
    [rolled_back] = conn.take_notices()
    assert (rolled_back.sqlstate, rolled_back.diagnostics.severity) == (
        "01T01",
        "NOTICE",
    )
    assert (conn.in_transaction, conn.authorization) == (False, "ANN")
    assert conn.setting("SESSION.TIME_ZONE") == "+00:00"
    with pytest.raises(ProgrammingError):
        conn.query("SELECT N FROM SCRATCH")
    with pytest.raises(ProgrammingError) as gone:
        conn.execute(statement)
    assert gone.value.sqlstate == "26000"
    conn.query("ROLLBACK")
    conn.reset()
    assert conn.take_notices() == []


def test_change_user_renews_the_session(live: Live) -> None:
    """Verifies: [PROTOCOL ChangeUser 'U'] the user proved again, the session renewed.

    The same Challenge and Answer steps as Hello's; accepted, as by Reset
    under a new cancel key, the transaction rolled back told by 01T01,
    none active after [CLIENT Controlling the session].
    """
    conn = connect_local(live.socket, "ANN", Trust())
    before = conn.canceller()
    assert before is not None
    conn.query("CREATE TABLE CHANGED (N INTEGER)")
    conn.change_user("ANN", Scram(live.password))
    assert [n.sqlstate for n in conn.take_notices()] == ["01T01"]
    assert (conn.in_transaction, conn.authorization) == (False, "ANN")
    after = conn.canceller()
    assert after is not None
    assert after._key != before._key  # noqa: SLF001  # The key, never shown.
    conn.ping()
    conn.terminate()


def test_what_each_capability_gives(live: Live) -> None:
    """Verifies: [PROTOCOL Capabilities] each, granted or not.

    Not granted: no diagnostics, row count, identity values, time, commit
    position or conditions told; ping, reset, change user, describe,
    numbered cursors, several statements and query attributes refused
    before anything is sent, the connection kept; a statement's warning
    still its Complete's SQLSTATE; with `notices` alone, conditions as
    Notices [PROTOCOL Errors and notices].
    """
    bare = connect_to(
        Tcp(live.host, live.port), "ANN", Trust(), offer=Offer(capabilities=())
    )
    with pytest.raises(ProgrammingError) as undiagnosed:
        bare.query("SELECT * FROM NOPE")
    assert undiagnosed.value.diagnostics is None
    bare.query("CREATE TABLE BARE (ID INTEGER GENERATED ALWAYS AS IDENTITY, N INTEGER)")
    bare.query("INSERT INTO BARE (N) VALUES (1)")
    bare.query("COMMIT")
    told = (
        bare.rows_affected,
        bare.last_generated,
        bare.server_time,
        bare.commit_position,
    )
    assert told == (None, (), None, None)
    bare.query("VALUES CAST('abc' AS CHAR(2))")
    assert (bare.warning, bare.conditions, bare.take_notices()) == ("01004", (), [])
    statement = bare.prepare("VALUES 1")
    for refused in (
        bare.ping,
        bare.reset,
        lambda: bare.change_user("ANN", Scram(live.password)),
        lambda: bare.describe(statement),
        lambda: bare.open_cursor(statement, cursor=1),
        lambda: bare.query_many("VALUES 1; VALUES 2"),
        lambda: bare.set_query_attributes([("k", "v")]),
    ):
        with pytest.raises(OperationalError) as failure:
            refused()
        assert failure.value.sqlstate == "08006"
    assert rows_of(bare.query("VALUES 1")) == [(1,)]
    bare.terminate()
    noticed = connect_to(
        Tcp(live.host, live.port),
        "ANN",
        Trust(),
        offer=Offer(capabilities=("notices",)),
    )
    noticed.query("VALUES CAST('abc' AS CHAR(2))")
    assert ([n.sqlstate for n in noticed.take_notices()], noticed.conditions) == (
        ["01004"],
        (),
    )
    noticed.terminate()


def test_cursors_closed_and_statements_deallocated(conn: Connection) -> None:
    """Verifies: [PROTOCOL Close 'C'] a cursor not open, an Error.

    [PROTOCOL Deallocate 'D'] a statement whose cursor is open fails
    (24000); [PROTOCOL Query 'Q'] a text of no statement, one Complete.
    """
    statement = conn.prepare("VALUES 1, 2")
    with pytest.raises(InternalError) as not_open:
        conn.close_cursor(statement)
    assert not_open.value.sqlstate == "24000"
    conn.open_cursor(statement, rows=1)
    with pytest.raises(InternalError) as still_open:
        conn.deallocate(statement)
    assert still_open.value.sqlstate == "24000"
    conn.close_cursor(statement)
    conn.deallocate(statement)
    ran = conn.query_many("")
    assert (len(ran.outcomes), ran.failure) == (1, None)


def test_a_call_s_output_parameters(conn: Connection) -> None:
    """Verifies: [PROTOCOL Prepared 'P'] a CALL: its inputs, then its outputs.

    One column for each `?` of an OUT or INOUT parameter, in the
    procedure's order, named as each, an INOUT `?` both; [PROTOCOL
    Execute 'E'] one Rows reply of one row of their values, before the
    Complete, the CALL's outcome.
    """
    conn.query("CREATE TABLE KS (K INTEGER)")
    conn.query("INSERT INTO KS VALUES (1), (2)")
    conn.query(
        "CREATE PROCEDURE FIND (IN WANTED INTEGER, OUT GOT INTEGER)"
        " READS SQL DATA SELECT K * 10 INTO GOT FROM KS WHERE K = WANTED"
    )
    conn.query(
        "CREATE PROCEDURE BUMP (INOUT N INTEGER, OUT SEEN VARCHAR(5))"
        " READS SQL DATA SELECT N + MAX(K), 'X' INTO N, SEEN FROM KS"
    )
    find = conn.prepare("CALL FIND(?, ?)")
    assert (len(find.parameters), [c.name for c in find.columns]) == (1, ["GOT"])
    assert rows_of(conn.execute(find, (2,))) == [(20,)]
    bump = conn.prepare("CALL BUMP(?, ?)")
    assert (len(bump.parameters), [c.name for c in bump.columns]) == (1, ["N", "SEEN"])
    assert rows_of(conn.execute(bump, (5,))) == [(7, "X")]
    conn.query("ROLLBACK")


def test_a_query_failing_at_its_first_batch_is_answered_by_its_error(
    conn: Connection,
) -> None:
    """Verifies: [PROTOCOL Query 'Q'] a statement failing before its first batch.

    No Description or Rows before it, so no columns are given, its
    transaction's state still told; an earlier pipelined request's
    replies still come before it.
    """
    conn.query("CREATE TABLE ZERO (N INTEGER)")
    conn.query("INSERT INTO ZERO VALUES (0)")
    stream = conn._stream  # noqa: SLF001  # Its frames, counted here alone.
    kinds: list[int] = []
    reading = stream.read_frame

    def counted(max_body: int) -> tuple[int, bytes]:
        frame = reading(max_body)
        kinds.append(frame[0])
        return frame

    stream.read_frame = counted  # type: ignore[method-assign]  # Counted for the test.
    with pytest.raises(DataError) as failure:
        conn.query("SELECT 1 / N FROM ZERO")
    stream.read_frame = reading  # type: ignore[method-assign]
    assert failure.value.sqlstate == "22012"
    assert kinds == [ord("E")]
    assert conn.in_transaction
    answers = conn.pipeline().query("VALUES 1").query("SELECT 1 / N FROM ZERO").run()
    assert rows_of(answers[0]) == [(1,)]
    assert isinstance(answers[1], DataError)
    conn.query("ROLLBACK")
