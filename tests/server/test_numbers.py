"""Live tests of exact numbers to 38 digits, sent and read exactly."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from turborel import DataError
from turborel.client import Connection, Rowset, Trust, connect

if TYPE_CHECKING:
    from collections.abc import Iterator

    from live import Live

WIDEST = 10**38 - 1
"""The greatest exact number of scale 0: 38 nines."""


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


def test_an_exact_number_of_38_digits_goes_both_ways(conn: Connection) -> None:
    """Verifies: [PROTOCOL Values] tag 2, an exact number of 38 digits, exactly.

    Sent as a parameter and read back, as an `int` of scale 0 and a
    Decimal of scale 10, no digit lost; and read as a result of SQL that
    writes it, a column declared NUMERIC(38,0).
    """
    fraction = Decimal("1234567890123456789012345678.9012345678")
    conn.query("CREATE TABLE WIDE (N NUMERIC(38,0), D DECIMAL(38,10))")
    insert = conn.prepare("INSERT INTO WIDE VALUES (?, ?)")
    conn.execute(insert, (WIDEST, fraction))
    conn.execute(insert, (-WIDEST, -fraction))
    stored = rows_of(conn.query("SELECT N, D FROM WIDE ORDER BY N DESC"))
    assert stored == [(WIDEST, fraction), (-WIDEST, -fraction)]
    assert str(stored[0][1]) == str(fraction)
    select = conn.prepare("SELECT N FROM WIDE WHERE N = ?")
    assert rows_of(conn.execute(select, (WIDEST,))) == [(WIDEST,)]
    written = conn.prepare(f"VALUES CAST({WIDEST} AS NUMERIC(38,0))")
    assert written.columns[0].type_written == "NUMERIC(38,0)"
    assert rows_of(conn.execute(written, ())) == [(WIDEST,)]
    conn.query("ROLLBACK")


def test_an_exact_number_of_39_digits_is_refused(conn: Connection) -> None:
    """Verifies: [PROTOCOL Values] an exact number past 38 digits, refused with 22003.

    Its units fit tag 2's `i128`, so it is sent, and the server refuses
    it, as a parameter and as a result of SQL; the connection goes on.
    """
    conn.query("CREATE TABLE WIDER (N NUMERIC(38,0))")
    insert = conn.prepare("INSERT INTO WIDER VALUES (?)")
    with pytest.raises(DataError) as parameter:
        conn.execute(insert, (10**38,))
    assert (parameter.value.sqlcode, parameter.value.sqlstate) == (-301, "22003")
    conn.query("ROLLBACK")
    with pytest.raises(DataError) as product:
        conn.query(f"VALUES CAST({WIDEST} AS NUMERIC(38,0)) * 10")
    assert product.value.sqlstate == "22003"
    conn.query("ROLLBACK")
    assert rows_of(conn.query("VALUES 1 / 3")) == [(Decimal("0.333333"),)]
