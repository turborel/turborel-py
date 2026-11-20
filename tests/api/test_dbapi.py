"""Tests of the standard API, DB-API 2.0, over a peer of the test's own."""

from __future__ import annotations

import datetime as dt

import pytest
from tests.kit import Peer, complete, description, error, ready, rows, u32, u64

import turborel
from turborel import IntegrityError, InterfaceError
from turborel._api.dbapi import KEPT_STATEMENTS, Statements, options_of
from turborel._api.results import Results, parameters_of
from turborel._codec.datatypes import (
    ApproximateType,
    BinaryType,
    CharacterType,
    DatetimeType,
    ExactType,
    LobType,
    Moment,
    QualifiedName,
    ReferenceType,
    StructuredType,
)
from turborel._statements.prepared import Statement
from turborel.client import Connection as Client
from turborel.client import Trust


def opened(peer: Peer) -> turborel.Connection:
    """A connection of the standard API over `peer`."""
    peer.reply(ready(capabilities=("row-counts",)))
    client = Client.open(peer.client, "ANN", Trust())
    peer.received()
    return turborel.Connection(client)


def prepared(number: int, columns: int) -> bytes:
    """A Prepared of `number`, one BOOLEAN parameter, `columns` BOOLEAN columns."""
    body = u32(number) + u32(1) + b"\x00\x0e" + u32(columns)
    body += (b"\x01" + u32(1) + b"A" + b"\x0e\x00") * columns
    return b"P" + (len(body)).to_bytes(4, "little") + body


def test_the_module_s_globals_and_constructors() -> None:
    """Verifies: [DESIGN] D2 `connect` and the module's globals.

    The type objects, each equal to the type codes of its kind, and the
    constructors.
    """
    assert (turborel.apilevel, turborel.threadsafety, turborel.paramstyle) == (
        "2.0",
        1,
        "qmark",
    )
    assert callable(turborel.connect)
    assert CharacterType(varying=True, length=1, octets=False) == turborel.STRING
    assert LobType(binary=False, length=1, octets=False) == turborel.STRING
    assert LobType(binary=True, length=1, octets=False) == turborel.BINARY
    assert BinaryType(varying=False, length=1) == turborel.BINARY
    assert ExactType(10, 0) == turborel.NUMBER
    assert ApproximateType(53) == turborel.NUMBER
    assert CharacterType(varying=True, length=1, octets=False) != turborel.NUMBER
    assert DatetimeType(Moment.DATE, zoned=False, precision=0) == turborel.DATETIME
    referenced = StructuredType(QualifiedName("ANN", "T"), ())
    assert ReferenceType(referenced, None) == turborel.ROWID
    assert repr(turborel.ROWID) == "ROWID"
    assert len({turborel.STRING, turborel.BINARY}) == 2
    assert turborel.Date(2024, 2, 29) == dt.date(2024, 2, 29)
    assert turborel.Time(1, 2, 3) == dt.time(1, 2, 3)
    assert turborel.Timestamp(2024, 2, 29, 1, 2, 3) == dt.datetime(2024, 2, 29, 1, 2, 3)  # noqa: DTZ001
    assert turborel.Binary(bytearray(b"ab")) == b"ab"
    ticks = 86_400.0 * 365
    assert turborel.DateFromTicks(ticks) == dt.datetime.fromtimestamp(ticks).date()  # noqa: DTZ006
    assert turborel.TimeFromTicks(ticks) == dt.datetime.fromtimestamp(ticks).time()  # noqa: DTZ006
    assert turborel.TimestampFromTicks(ticks) == dt.datetime.fromtimestamp(ticks)  # noqa: DTZ006


def test_settings_by_name_over_a_uri() -> None:
    """Verifies: [DESIGN] D2 `connect` of a URI, settings by name laid over it."""
    options = options_of(
        "turborel://ann@db/?tls_mode=disable", {"port": 7000, "tls_system_roots": True}
    )
    assert (
        options.get("user"),
        options.get("port"),
        options.get("tls_system_roots"),
    ) == ("ann", "7000", "true")
    assert options_of(None, {"user": None}).is_empty()


def test_a_cursor_runs_and_fetches() -> None:
    """Verifies: [DESIGN] D2 the Cursor, its execute and fetches.

    A statement of no parameters sent direct; one of parameters prepared
    once, kept by its text, and executed; `arraysize`; iteration.
    """
    with Peer() as peer:
        conn = opened(peer)
        cursor = conn.cursor()
        peer.reply(
            description("A"),
            rows((True,), (False,), (True,)),
            complete(tail=b"\x06" + u64(3)),
        )
        cursor.execute("SELECT A FROM T")
        described = cursor.description
        assert described is not None
        assert described == (("A", described[0][1], None, None, None, None, True),)
        assert cursor.rowcount == 3
        assert cursor.fetchone() == (True,)
        assert cursor.fetchmany() == [(False,)]
        assert list(cursor) == [(True,)]
        assert cursor.fetchall() == []
        peer.received()
        peer.reply(
            prepared(0, 0),
            complete(tail=b"\x06" + u64(1)),
            complete(tail=b"\x06" + u64(2)),
        )
        cursor.execute("UPDATE T SET A = ?", (True,))
        after: list[object] = [cursor.description, cursor.rowcount]
        assert after == [None, 1]
        cursor.execute("UPDATE T SET A = ?", [False])
        assert cursor.rowcount == 2
        kinds = [peer.received()[0] for _ in range(3)]
        assert kinds == [ord("P"), ord("E"), ord("E")]
        with pytest.raises(InterfaceError, match="no query"):
            cursor.fetchone()
        with pytest.raises(InterfaceError):
            cursor.execute("UPDATE T SET A = ?", {"a": 1})  # type: ignore[arg-type]
        cursor.setinputsizes(None)
        cursor.setoutputsize(1)
        with cursor:
            pass
        with pytest.raises(InterfaceError, match="closed"):
            cursor.execute("VALUES 1")


def test_executemany_in_one_pipeline() -> None:
    """Verifies: [DESIGN] D2 `executemany`, one pipeline, to a failure."""
    with Peer() as peer:
        conn = opened(peer)
        cursor = conn.cursor()
        peer.reply(
            prepared(0, 0),
            complete(tail=b"\x06" + u64(1)),
            complete(),
            complete(tail=b"\x06" + u64(1)),
            complete(),
        )
        cursor.executemany("INSERT INTO T VALUES (?)", [(True,), (False,)])
        assert cursor.rowcount == 2
        cursor.executemany("INSERT INTO T VALUES (?)", [])
        assert cursor.rowcount == 0
        peer.reply(
            error(-201, "23000", "duplicate", active=True),
            complete(),
            complete(),
            complete(),
        )
        with pytest.raises(IntegrityError):
            cursor.executemany("INSERT INTO T VALUES (?)", [(True,), (False,)])


def test_commit_rollback_and_close() -> None:
    """Verifies: [DESIGN] D2 the Connection: `commit`, `rollback`, `close`, `cursor`.

    Each only where a transaction is active; closing one active rolls it
    back first, as PEP 249 says; the exceptions as its attributes.
    """
    with Peer() as peer:
        conn = opened(peer)
        conn.commit()
        conn.rollback()
        peer.reply(complete(active=True), complete(), complete(active=True), complete())
        conn.cursor().execute("INSERT")
        assert conn.in_transaction
        conn.commit()
        conn.cursor().execute("INSERT")
        conn.rollback()
        sent = [peer.received()[1] for _ in range(4)]
        assert [b[4 : 4 + b[0]] for b in sent] == [
            b"INSERT",
            b"COMMIT",
            b"INSERT",
            b"ROLLBACK",
        ]
        conn.autocommit = True
        assert conn.autocommit
        conn.autocommit = False
        peer.reply(complete(active=True), complete())
        conn.cursor().execute("INSERT")
        peer.close()
        conn.close()
        peer.received()
        assert peer.received()[1][4:12] == b"ROLLBACK"
        assert conn.closed
        conn.close()
        with pytest.raises(InterfaceError):
            conn.cursor()
        assert conn.Error is turborel.Error
        assert conn.IntegrityError is IntegrityError


def test_the_connection_as_a_context() -> None:
    """Verifies: [DESIGN] D2 a connection as a context, committed."""
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(complete(active=True), complete())
        peer.close()
        with conn:
            conn.cursor().execute("INSERT")
        assert conn.closed
        texts = [peer.received()[1] for _ in range(2)]
        assert texts[1][4:10] == b"COMMIT"
        assert peer.received()[0] == ord("X")


def test_statements_kept_by_their_text() -> None:
    """Verifies: [DESIGN] D2 a statement prepared once, kept, the least used let go."""
    kept = Statements()
    first = Statement(0, (), ())
    assert kept.put("a", first) is None
    for n in range(1, KEPT_STATEMENTS):
        kept.put(f"s{n}", Statement(n, (), ()))
    assert kept.get("a") is first
    assert kept.put("last", Statement(999, (), ())) == Statement(1, (), ())
    kept.forget("a")
    assert kept.get("a") is None


def test_results_and_parameters() -> None:
    """Verifies: [DESIGN] D2 results; parameters by place."""
    results = Results()
    with pytest.raises(InterfaceError):
        results.fetch(1)
    assert parameters_of(None) is None
    assert parameters_of([1, 2]) == (1, 2)
    for wrong in ("ab", b"ab", {"a": 1}):
        with pytest.raises(InterfaceError, match="qmark"):
            parameters_of(wrong)  # type: ignore[arg-type]
