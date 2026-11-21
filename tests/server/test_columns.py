"""Live tests of columns' declared types, and of a parameter cut to its type."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turborel.client import Connection, Offer, Rowset, Tcp, Trust, connect, connect_to

if TYPE_CHECKING:
    from collections.abc import Iterator

    from live import Live


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


DECLARED_TABLE = (
    ("SMALLINT", "SMALLINT", "SMALLINT"),
    ("INTEGER", "INTEGER", "INTEGER"),
    ("BIGINT", "BIGINT", "BIGINT"),
    ("DECIMAL(9,2)", "DECIMAL", "DECIMAL(9,2)"),
    ("NUMERIC(5)", "NUMERIC", "NUMERIC(5,0)"),
    ("REAL", "REAL", "REAL"),
    ("DOUBLE PRECISION", "DOUBLE PRECISION", "DOUBLE PRECISION"),
    ("FLOAT(20)", "FLOAT", "FLOAT(24)"),
    ("MONEY", "USER-DEFINED", "ANN.MONEY"),
    ("INTEGER ARRAY[3]", "ARRAY", "INTEGER ARRAY[3]"),
    ("DATE", "DATE", "DATE"),
    ("TIME(3)", "TIME", "TIME(3)"),
)
"""The page's table of declared types: each as declared, its name, as written."""


def test_each_column_s_declared_type_is_told(conn: Connection, live: Live) -> None:
    """Verifies: [PROTOCOL Declared types] the page's table of declared types.

    [PROTOCOL Capabilities] `declared-types` asked for by connecting and
    granted; [CLIENT Prepared statements] a column's declared type, its
    name as DATA_TYPE gives it and as SQL writes it, by a Prepared and a
    Description alike; a distinct type as USER-DEFINED and its name. Not
    granted, the columns alone, `type_written` as the tag says, the
    values the same.
    """
    assert "declared-types" in conn.granted
    conn.query("CREATE TYPE MONEY AS DECIMAL(9,2) FINAL")
    columns = ", ".join(f"C{n} {t}" for n, (t, _, _) in enumerate(DECLARED_TABLE))
    conn.query(f"CREATE TABLE DECLARED ({columns})")
    conn.query("INSERT INTO DECLARED (C1) VALUES (7)")
    conn.query("COMMIT")
    statement = conn.prepare("SELECT * FROM DECLARED")
    rowset = conn.execute(statement)
    assert isinstance(rowset, Rowset)
    for described in (statement.columns, rowset.columns):
        told = [(c.declared.name, c.declared.written) for c in described if c.declared]
        assert told == [(name, written) for _, name, written in DECLARED_TABLE]
        assert described[1].type_written == "INTEGER"
    plain = connect_to(
        Tcp(live.host, live.port), "ANN", Trust(), offer=Offer(capabilities=())
    )
    try:
        assert "declared-types" not in plain.granted
        rows = plain.query("SELECT C1, C9 FROM DECLARED")
        assert isinstance(rows, Rowset)
        assert [c.declared for c in rows.columns] == [None, None]
        assert [c.type_written for c in rows.columns] == [
            "NUMERIC(10,0)",
            "NUMERIC(10,0) ARRAY[3]",
        ]
        assert rows.rows == [(7, None)]
        assert rows.columns[0].data_type == rowset.columns[1].data_type
    finally:
        plain.terminate()


def test_a_parameter_cut_by_its_type_warns(conn: Connection) -> None:
    """Verifies: [CLIENT Running statements] a `?` cut to its column's type warns 01004.

    In an INSERT, an UPDATE and a comparison, with ORDER BY or without,
    each executed again from its kept plan; the value stored cut, the
    completion's SQLSTATE 01004.
    """
    conn.query("CREATE TABLE CUT (K INTEGER, V VARCHAR(5))")
    insert = conn.prepare("INSERT INTO CUT VALUES (?, ?)")
    for k in (1, 2):
        conn.execute(insert, (k, "abcdefgh"))
        assert conn.warning == "01004"
    update = conn.prepare("UPDATE CUT SET V = ? WHERE K = 2")
    conn.execute(update, ("uvwxyz",))
    assert conn.warning == "01004"
    for sql in (
        "SELECT K FROM CUT WHERE V = ?",
        "SELECT K FROM CUT WHERE V = ? ORDER BY K",
    ):
        select = conn.prepare(sql)
        for _ in range(2):
            assert rows_of(conn.execute(select, ("abcdefgh",))) == [(1,)]
            assert conn.warning == "01004"
    assert rows_of(conn.query("SELECT V FROM CUT ORDER BY K")) == [
        ("abcde",),
        ("uvwxy",),
    ]
    conn.query("ROLLBACK")


def test_values_of_one_number_type_keep_its_declared_type(conn: Connection) -> None:
    """Verifies: [PROTOCOL Declared types] values of one type keep its declared name.

    [CLIENT Prepared statements] a VALUES of CASTs, and a UNION of two
    INTEGER columns, declared INTEGER; INTEGER with SMALLINT NUMERIC.
    """
    cast = conn.prepare("VALUES (CAST(1 AS INTEGER), CAST(2.5 AS DECIMAL(9,2)))")
    assert [c.type_written for c in cast.columns] == ["INTEGER", "DECIMAL(9,2)"]
    conn.query("CREATE TABLE ONE_TYPE (I INTEGER, J INTEGER, S SMALLINT)")
    union = conn.prepare("SELECT I FROM ONE_TYPE UNION SELECT J FROM ONE_TYPE")
    assert [c.type_written for c in union.columns] == ["INTEGER"]
    mixed = conn.prepare("SELECT I FROM ONE_TYPE UNION SELECT S FROM ONE_TYPE")
    declared = mixed.columns[0].declared
    assert declared is not None
    assert declared.name == "NUMERIC"
    conn.query("ROLLBACK")
