"""Live tests of a CALL's parameter modes, and of the standard API's `callproc`."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import quote

import turborel
from turborel import ParameterMode, aio
from turborel.client import Offer, Rowset, Tcp, Trust, connect, connect_to

if TYPE_CHECKING:
    from live import Live

    from turborel.client import Connection

IN, INOUT, OUT = ParameterMode.IN, ParameterMode.INOUT, ParameterMode.OUT

PROCEDURES = (
    "CREATE TABLE PKS (K INTEGER)",
    "INSERT INTO PKS VALUES (1), (2)",
    (
        "CREATE PROCEDURE PFIND (IN WANTED INTEGER, OUT GOT INTEGER)"
        " READS SQL DATA SELECT K * 10 INTO GOT FROM PKS WHERE K = WANTED"
    ),
    (
        "CREATE PROCEDURE PBUMP (INOUT N INTEGER, OUT SEEN VARCHAR(5))"
        " READS SQL DATA SELECT N + MAX(K), 'X' INTO N, SEEN FROM PKS"
    ),
    "COMMIT",
)


def made(conn: Connection) -> None:
    """The table and procedures the tests call, made and committed once."""
    found = conn.query(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.ROUTINES WHERE ROUTINE_NAME = 'PBUMP'"
    )
    assert isinstance(found, Rowset)
    if found.rows == [(0,)]:
        for sql in PROCEDURES:
            conn.query(sql)
    conn.query("ROLLBACK")


def test_a_prepared_call_tells_each_mark_s_mode(live: Live) -> None:
    """Verifies: [PROTOCOL Parameter modes] tail 20 of a CALL, the capability granted.

    [PROTOCOL Capabilities] asked for by connecting; [CLIENT Prepared
    statements] each `?` in the order written, OUT ones too, its mode and
    its parameter's position; two of one IN argument each its position;
    an OUT one given no value, read back from the CALL's row. Another
    statement, or one not granted it, has none, each `?` IN.
    """
    conn = connect((live.host, live.port), "ANN", Trust())
    try:
        assert "parameter-modes" in conn.granted
        made(conn)
        bump = conn.prepare("CALL PBUMP(?, ?)")
        assert bump.procedure is not None
        assert bump.procedure[0] == "ANN"
        assert [(m.mode, m.position) for m in bump.marks] == [(INOUT, 1), (OUT, 2)]
        assert rows_of(conn.execute(bump, (5,))) == [(7, "X")]
        find = conn.prepare("CALL PFIND(CAST(? AS INTEGER) + CAST(? AS INTEGER), ?)")
        assert [(m.mode, m.position) for m in find.marks] == [
            (IN, 1),
            (IN, 1),
            (OUT, 2),
        ]
        assert rows_of(conn.execute(find, (1, 1))) == [(20,)]
        query = conn.prepare("SELECT K FROM PKS WHERE K = ?")
        assert query.procedure is None
        assert [(m.mode, m.position) for m in query.marks] == [(IN, None)]
    finally:
        conn.terminate()
    plain = connect_to(
        Tcp(live.host, live.port), "ANN", Trust(), offer=Offer(capabilities=())
    )
    try:
        assert "parameter-modes" not in plain.granted
        bump = plain.prepare("CALL PBUMP(?, ?)")
        assert bump.called is None
        assert [m.mode for m in bump.marks] == [IN]
    finally:
        plain.terminate()


def rows_of(outcome: object) -> list[tuple[object, ...]]:
    """A query's rows."""
    assert isinstance(outcome, Rowset)
    return outcome.rows


def uri(live: Live) -> str:
    """A URI of ANN at the live server over TCP, its password given."""
    secret = quote(live.password, safe="")
    return f"turborel://ANN:{secret}@{live.host}:{live.port}/"


def test_callproc_reads_back_the_output_values(live: Live) -> None:
    """Verifies: [DESIGN] D2 `callproc`, each parameter's mode and position.

    [CLIENT Prepared statements] the values given back, each of an OUT or
    INOUT parameter replaced by what the procedure returned, which the
    cursor fetches too; `parameters` each `?`'s mode, position and type;
    the asyncio cursor's alike.
    """
    with turborel.connect(uri(live)) as conn:
        made(conn.client)
        cursor = conn.cursor()
        assert cursor.callproc("PBUMP", (5, None)) == (7, "X")
        assert cursor.fetchone() == (7, "X")
        assert cursor.parameters is not None
        assert [(p.mode, p.position) for p in cursor.parameters] == [
            (INOUT, 1),
            (OUT, 2),
        ]
        assert cursor.parameters[0].type_code == turborel.NUMBER
        assert cursor.callproc("ann.pfind", [2, None]) == (2, 20)
        other = conn.cursor()
        other.execute("VALUES 1")
        assert other.parameters is None
        conn.rollback()

    async def called() -> tuple[object, ...]:
        async with await aio.connect(uri(live)) as conn:
            cursor = conn.cursor()
            got = await cursor.callproc("PFIND", (1, None))
            await conn.rollback()
            return got

    assert asyncio.run(called()) == (1, 10)
