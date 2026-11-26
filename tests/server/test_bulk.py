"""Live tests of large objects, copy, export and import."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from turborel import DataError, IntegrityError, InterfaceError, LargeObject, LobLocator
from turborel.client import (
    CHUNK_OCTETS,
    Connection,
    Delimited,
    Dialect,
    ExportFormat,
    Import,
    ImportFailure,
    Position,
    Rejected,
    Rowset,
    Trust,
    connect,
    import_rows,
    read_native,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from live import Live

BIG = 70_000
"""Octets past SERVER.LOB_INLINE_BYTES, 64 KiB by default."""


@pytest.fixture
def conn(live: Live) -> Iterator[Connection]:
    """A connection by trust, granted every capability but compression."""
    connection = connect((live.host, live.port), "ANN", Trust())
    yield connection
    if not connection.is_lost:
        connection.terminate()


def locator_of(outcome: object) -> LobLocator:
    """The one value of a query's one row, a large object by its locator."""
    [(value,)] = rows_of(outcome)
    assert isinstance(value, LobLocator)
    return value


def rows_of(outcome: object) -> list[tuple[object, ...]]:
    """A query's rows."""
    assert isinstance(outcome, Rowset)
    return outcome.rows


def test_a_large_object_whole_or_by_its_locator(conn: Connection) -> None:
    """Verifies: [PROTOCOL Values] a large object read whole, or by its locator.

    At most SERVER.LOB_INLINE_BYTES whole in its row, a longer one by its
    locator and lengths [CLIENT Large objects]; sent whole, or as a
    locator the client made [PROTOCOL Lob 'L'] create, then append,
    answered by Complete; a CLOB's octets UTF-8, a character split
    between writes.
    """
    conn.query("CREATE TABLE DOCS (ID INTEGER, BODY CLOB(1M), DATA BLOB(1M))")
    writer = conn.create_lob(binary=False)
    text = "é" * (BIG // 2)
    octets = text.encode("utf-8")
    writer.write(octets[:3])
    writer.write(octets[3:])
    body = writer.finish()
    assert (body.octets, body.characters) == (len(octets), len(text))
    insert = conn.prepare("INSERT INTO DOCS VALUES (?, ?, ?)")
    conn.execute(insert, (1, body, LargeObject(b"\x01\x02")))
    conn.execute(insert, (2, LargeObject("short"), LargeObject(bytes(BIG))))
    conn.query("COMMIT")
    [(_, long_body, small), (_, short, long_data)] = rows_of(
        conn.query("SELECT ID, BODY, DATA FROM DOCS ORDER BY ID")
    )
    assert (short, small) == ("short", b"\x01\x02")
    assert isinstance(long_body, LobLocator)
    assert (long_body.binary, long_body.octets, long_body.characters) == (
        False,
        len(octets),
        len(text),
    )
    assert isinstance(long_data, LobLocator)
    assert (long_data.binary, long_data.octets) == (True, BIG)
    conn.query("ROLLBACK")


def test_large_objects_in_an_insert_of_several_rows(conn: Connection) -> None:
    """Verifies: [CLIENT Large objects] a `?` of an INSERT's rows, its column's type.

    A long BLOB and CLOB bound in a row beside a row of short literals,
    and as several rows of marks, each stored whole.
    """
    conn.query("CREATE TABLE MANY (ID INTEGER, BODY CLOB(1M), DATA BLOB(1M))")
    text, data = "x" * BIG, bytes(range(256)) * (BIG // 256)
    conn.execute(
        conn.prepare("INSERT INTO MANY VALUES (?, ?, ?), (2, 'short', X'0102')"),
        (1, LargeObject(text), LargeObject(data)),
    )
    conn.execute(
        conn.prepare("INSERT INTO MANY VALUES (?, ?, ?), (?, ?, ?)"),
        (
            3,
            LargeObject("s"),
            LargeObject(b"\x03"),
            4,
            LargeObject(text),
            LargeObject(data),
        ),
    )
    lengths = rows_of(
        conn.query(
            "SELECT ID, CHARACTER_LENGTH(BODY), OCTET_LENGTH(DATA)"
            " FROM MANY ORDER BY ID"
        )
    )
    assert lengths == [(1, BIG, len(data)), (2, 5, 2), (3, 1, 1), (4, BIG, len(data))]
    conn.query("ROLLBACK")


def test_a_clob_written_is_checked_as_utf8_as_each_append_comes(
    conn: Connection,
) -> None:
    """Verifies: [PROTOCOL Lob 'L'] a CLOB's octets checked as UTF-8 at each Append.

    An octet that is not UTF-8 refused with 22021 by its Append, each
    Append after it and the CLOB's use refused too; one ending within a
    character refused, 22021, where it is used [CLIENT Large objects].
    """
    conn.query("CREATE TABLE NOTES (BODY CLOB(1M))")
    conn.query("COMMIT")
    insert = conn.prepare("INSERT INTO NOTES VALUES (?)")
    bad = conn.create_lob(binary=False)
    bad.write(b"a\xff")
    with pytest.raises(DataError) as refused:
        bad.flush()
    assert refused.value.sqlstate == "22021"
    bad.write(b"b")
    with pytest.raises(DataError) as again:
        bad.flush()
    assert again.value.sqlstate == "22021"
    conn.query("ROLLBACK")
    cut = conn.create_lob(binary=False)
    cut.write("aé".encode()[:2])
    held = cut.finish()
    with pytest.raises(DataError) as used:
        conn.execute(insert, (held,))
    assert used.value.sqlstate == "22021"
    conn.query("ROLLBACK")


def test_a_locator_read_by_ranges_and_as_a_stream(conn: Connection) -> None:
    """Verifies: [CLIENT Large objects] a range by octets or characters, 256 KiB most.

    [PROTOCOL Lob 'L'] read: locator, from, count, characters flag,
    answered by data; a reader of the whole value, a chunk at a time; one
    held whole read from the value itself.
    """
    conn.query("CREATE TABLE PAGES (BODY CLOB(2M))")
    insert = conn.prepare("INSERT INTO PAGES VALUES (?)")
    conn.execute(insert, (LargeObject("aé" * 200_000),))
    conn.query("COMMIT")
    [(body,)] = rows_of(conn.query("SELECT BODY FROM PAGES"))
    assert isinstance(body, LobLocator)
    assert conn.read_lob(body, 0, 4, characters=True) == "aéaé".encode()
    assert conn.read_lob(body, 1, 2) == "é".encode()
    assert len(conn.read_lob(body, 0, 10**7)) == CHUNK_OCTETS
    whole = conn.lob_reader(body).read()
    assert whole == ("aé" * 200_000).encode()
    assert conn.read_lob("aé", 1, 1, characters=True) == "é".encode()
    assert conn.read_lob(b"\x01\x02\x03", 1, 5) == b"\x02\x03"
    assert io.BufferedReader(conn.lob_reader("held")).read() == b"held"
    conn.query("ROLLBACK")


def test_a_locator_lasts_as_its_transaction(conn: Connection) -> None:
    """Verifies: [CLIENT Large objects] a locator valid until its transaction ends.

    The transaction kept open under autocommit too [PROTOCOL Query 'Q'];
    [PROTOCOL Lob 'L'] free, answered by Complete, the locator no longer
    valid (0F001); hold, kept past the commit until freed or a rollback.
    """
    conn.query("CREATE TABLE KEPT (BODY BLOB(1M))")
    conn.execute(
        conn.prepare("INSERT INTO KEPT VALUES (?)"), (LargeObject(bytes(BIG)),)
    )
    conn.query("COMMIT")
    conn.autocommit = True
    body = locator_of(conn.query("SELECT BODY FROM KEPT"))
    assert conn.in_transaction
    conn.query("COMMIT")
    with pytest.raises(Exception, match="locator") as ended:
        conn.read_lob(body, 0, 1)
    assert getattr(ended.value, "sqlstate", None) == "0F001"
    held = locator_of(conn.query("SELECT BODY FROM KEPT"))
    conn.hold_lob(held)
    conn.query("COMMIT")
    assert conn.read_lob(held, 0, 2) == b"\x00\x00"
    conn.free_lob(held)
    with pytest.raises(Exception, match="locator"):
        conn.read_lob(held, 0, 1)
    rolled = locator_of(conn.query("SELECT BODY FROM KEPT"))
    conn.hold_lob(rolled)
    conn.query("ROLLBACK")
    with pytest.raises(Exception, match="locator"):
        conn.read_lob(rolled, 0, 1)
    with pytest.raises(DataError) as whole:
        conn.free_lob("whole")
    assert whole.value.sqlstate == "22000"
    conn.query("ROLLBACK")


def test_a_copy_and_its_end(conn: Connection) -> None:
    """Verifies: [CLIENT Copying and exporting] copy into a table, many rows a message.

    [PROTOCOL CopyEnd 'N'] answered by a Complete counting the rows
    inserted; [PROTOCOL CopyIn 'I'] until CopyEnd only CopyData,
    CopyColumns, CopyEnd and Ping sent, any other request refused before
    it is sent; [PROTOCOL
    Ping 'G'] answered during a copy too; [PROTOCOL Conversations] a
    copy; the rows an iterator gives.
    """
    conn.query("CREATE TABLE NUMS (N INTEGER PRIMARY KEY, S VARCHAR(5))")
    conn.query("COMMIT")
    with conn.copy_in("NUMS") as copy:
        for n in range(5):
            copy.send((n, f"s{n}"))
        copy.ping()
        with pytest.raises(InterfaceError) as refused:
            conn.query("VALUES 1")
        assert refused.value.sqlstate == "TB910"
        assert copy.finish() == 5
    assert conn.copy_rows("NUMS", ("S", "N"), iter([("t", 10), ("u", 11)])) == 2
    assert rows_of(conn.query("SELECT COUNT(*) FROM NUMS")) == [(7,)]
    conn.query("COMMIT")


def test_a_copy_is_all_or_nothing(conn: Connection) -> None:
    """Verifies: [PROTOCOL CopyEnd 'N'] all or nothing, the failure kept until CopyEnd.

    Its detail naming the row, as `row 2 of the copy`; abandon undoes
    every row; [CLIENT Copying and exporting] a copy dropped before it
    finishes abandoned; [PROTOCOL Conversations] a copy whose row breaks a
    constraint.
    """
    conn.query("CREATE TABLE ONCE (N INTEGER PRIMARY KEY)")
    conn.query("INSERT INTO ONCE VALUES (1)")
    conn.query("COMMIT")
    with pytest.raises(IntegrityError) as broken:
        conn.copy_rows("ONCE", (), [(5,), (1,), (6,)])
    assert broken.value.diagnostics is not None
    assert broken.value.diagnostics.detail == "row 2 of the copy"
    with conn.copy_in("ONCE") as copy:
        copy.send((7,))
        copy.abandon()
    with conn.copy_in("ONCE") as dropped:
        dropped.send((8,))
    assert rows_of(conn.query("SELECT N FROM ONCE")) == [(1,)]
    conn.query("COMMIT")


def test_a_copy_s_transaction(conn: Connection) -> None:
    """Verifies: [PROTOCOL CopyEnd 'N'] `ends` 1 committed; another under a savepoint.

    A copy within a transaction that fails undoes its own rows alone,
    the transaction going on.
    """
    conn.query("CREATE TABLE SAVED (N INTEGER PRIMARY KEY)")
    conn.query("COMMIT")
    conn.query("INSERT INTO SAVED VALUES (1)")
    with pytest.raises(IntegrityError):
        conn.copy_rows("SAVED", (), [(2,), (1,)])
    assert conn.in_transaction
    assert rows_of(conn.query("SELECT N FROM SAVED")) == [(1,)]
    conn.query("ROLLBACK")
    conn.autocommit = True
    assert conn.copy_rows("SAVED", (), [(3,)]) == 1
    assert not conn.in_transaction


def test_an_export_as_csv_and_as_native_rows(conn: Connection) -> None:
    """Verifies: [CLIENT Copying and exporting] export as CSV: a header, a record a row.

    Export as the protocol's own frames, read back with every value as it
    was; a statement that is no query refused (08006).
    """
    conn.query("CREATE TABLE OUT (N INTEGER, S VARCHAR(10), D DATE)")
    conn.query("INSERT INTO OUT VALUES (1, 'a,b', DATE '2024-02-29'), (2, '', NULL)")
    out = io.BytesIO()
    assert conn.export("SELECT N, S, D FROM OUT ORDER BY N", out) == 2
    assert out.getvalue() == b'N,S,D\r\n1,"a,b",2024-02-29\r\n2,"",\r\n'
    native = io.BytesIO()
    assert conn.export("SELECT * FROM OUT ORDER BY N", native, ExportFormat.NATIVE) == 2
    native.seek(0)
    columns, rows = read_native(native)
    assert [c.name for c in columns] == ["N", "S", "D"]
    assert rows == rows_of(conn.query("SELECT * FROM OUT ORDER BY N"))
    with pytest.raises(Exception, match="an export runs a query") as no_query:
        conn.export("UPDATE OUT SET N = 3", io.BytesIO())
    assert getattr(no_query.value, "sqlstate", None) == "08006"
    assert not conn.is_lost
    conn.query("ROLLBACK")


def test_an_import_by_copy_and_by_insert(conn: Connection) -> None:
    """Verifies: [CLIENT Importing] import a source's rows into a table.

    Delimited text with a header; rows committed a batch at a time; by
    copy where the server grants it and no column is a large object's
    [CLIENT Copying and exporting]; a field longer than 64 KiB for a
    CLOB sent by creating a large object [CLIENT Large objects].
    """
    conn.query("CREATE TABLE PEOPLE (ID INTEGER, NAME CHAR(5), NOTE VARCHAR(4))")
    conn.query("CREATE TABLE BOOKS (ID INTEGER, TEXT CLOB(1M))")
    conn.query("COMMIT")
    source = Delimited(
        io.BytesIO(b'id,name,note\n1,Ada,x\n2,Grace,"  "\n3,,""\n'),
        Dialect.csv().with_header(),
    )
    imported = import_rows(conn, source, Import("PEOPLE", batch=2))
    assert (imported.rows, imported.rejected) == (3, 0)
    assert rows_of(conn.query("SELECT * FROM PEOPLE ORDER BY ID")) == [
        (1, "Ada  ", "x"),
        (2, "Grace", "  "),
        (3, None, ""),
    ]
    conn.query("COMMIT")
    book = b"1," + b"z" * BIG + b"\n2,small\n"
    assert (
        import_rows(conn, Delimited(io.BytesIO(book)), Import("BOOKS", batch=0)).rows
        == 2
    )
    found = rows_of(conn.query("SELECT ID, TEXT FROM BOOKS ORDER BY ID"))
    assert isinstance(found[0][1], LobLocator)
    assert found[0][1].characters == BIG
    assert found[1][1] == "small"
    conn.query("COMMIT")


def test_an_import_s_failures(conn: Connection) -> None:
    """Verifies: [CLIENT Importing] an import's failure: where, why, what was kept.

    A failing row skipped and given to the program, if asked; no
    transaction active on the session; the input's cause or SQL's.
    """
    conn.query("CREATE TABLE WHO (ID INTEGER, NAME CHAR(5))")
    conn.query("COMMIT")
    with pytest.raises(ImportFailure) as too_long:
        import_rows(conn, Delimited(io.BytesIO(b"1,Ada\n2,Barbara\n")), Import("WHO"))
    failure = too_long.value
    assert (failure.where, failure.committed, failure.rolled_back) == (
        Position(2, 2),
        0,
        1,
    )
    assert failure.sqlstate == "22001"
    assert str(failure).startswith(
        "record 2, line 2: SQLCODE -301 (SQLSTATE 22001): a value of 7"
    )
    skipped: list[Rejected] = []
    text = b"3,Bob\n4,Barbara\n5\n6,Al\n"
    imported = import_rows(
        conn, Delimited(io.BytesIO(text)), Import("WHO", skip=True), skipped.append
    )
    assert (imported.rows, imported.rejected) == (2, 2)
    assert [r.position.record for r in skipped] == [2, 3]
    assert str(skipped[1]) == "record 3, line 3: 1 fields, for 2 columns; skipped"
    with pytest.raises(ImportFailure) as unreadable:
        import_rows(
            conn, Delimited(io.BytesIO(b'7,Ok\n8,"bad\n')), Import("WHO", batch=1)
        )
    assert (unreadable.value.committed, unreadable.value.sqlstate) == (1, "22000")
    assert "a quoted field is not closed" in str(unreadable.value)
    conn.query("SELECT * FROM WHO")
    with pytest.raises(ImportFailure, match="no transaction active"):
        import_rows(conn, Delimited(io.BytesIO(b"9,x\n")), Import("WHO"))
    conn.query("ROLLBACK")
    with pytest.raises(ImportFailure, match="is not a <table name>"):
        import_rows(conn, Delimited(io.BytesIO(b"9,x\n")), Import("no such"))


def test_a_copy_by_column(conn: Connection) -> None:
    """Verifies: [PROTOCOL CopyColumns 'O'] rows by column, granted `columns`.

    [CLIENT Copying and exporting] rows of text sent by column: a null and
    the empty string kept apart; CopyData and CopyColumns mixed in one
    copy; a cell too long for its column failing the copy at CopyEnd, its
    row named in the detail, never cut; an abandoned copy taking nothing.
    """
    assert "columns" in conn.granted
    conn.query("CREATE TABLE CELLS (N INTEGER, S VARCHAR(3))")
    conn.query("COMMIT")
    with conn.copy_in("CELLS") as copy:
        copy.send(("1", None))
        copy.send(("2", ""))
        copy.send((3, "abc"))
        copy.send(("4", "d"))
        assert copy.finish() == 4
    stored = rows_of(conn.query("SELECT N, S FROM CELLS ORDER BY N"))
    assert stored == [(1, None), (2, ""), (3, "abc"), (4, "d")]
    conn.query("COMMIT")
    with conn.copy_in("CELLS") as copy:
        copy.send(("5", "e"))
        copy.send(("6", "toolong"))
        with pytest.raises(DataError) as long:
            copy.finish()
    assert long.value.sqlstate == "22001"
    assert long.value.failure is not None
    assert long.value.failure.diagnostics is not None
    assert "2" in (long.value.failure.diagnostics.detail or "")
    conn.query("ROLLBACK")
    with conn.copy_in("CELLS") as copy:
        copy.send(("7", "g"))
        copy.abandon()
    assert rows_of(conn.query("SELECT COUNT(*) FROM CELLS")) == [(4,)]
    conn.query("ROLLBACK")
