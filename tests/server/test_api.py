"""Live tests of the standard API: DB-API 2.0 and turborel.aio."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import quote

import pytest

import turborel
from turborel import IntegrityError, OperationalError, aio
from turborel.client import Local, Tls

if TYPE_CHECKING:
    from live import Live


def uri(live: Live, query: str = "") -> str:
    """A URI of ANN at the live server over TCP, its password given."""
    secret = quote(live.password, safe="")
    return f"turborel://ANN:{secret}@{live.host}:{live.port}/?{query}"


def test_the_standard_api(live: Live) -> None:
    """Verifies: [DESIGN] D2 `connect`, the Connection and the Cursor, against a server.

    A transaction begun by the first statement, ended by commit or
    rollback; one active rolled back as the connection closes; a
    statement of parameters prepared once and executed again after a
    reset of the session took it; type objects of the columns.
    """
    conn = turborel.connect(uri(live))
    assert isinstance(conn.client.target, Tls)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE API (ID INTEGER PRIMARY KEY, NAME VARCHAR(10))")
    conn.commit()
    cursor.executemany("INSERT INTO API VALUES (?, ?)", [(1, "a"), (2, "b"), (3, "c")])
    assert cursor.rowcount == 3
    conn.commit()
    cursor.execute("SELECT ID, NAME FROM API WHERE ID > ? ORDER BY ID", (1,))
    assert cursor.description is not None
    assert [d[0] for d in cursor.description] == ["ID", "NAME"]
    assert cursor.description[0][1] == turborel.NUMBER
    assert cursor.description[1][1] == turborel.STRING
    assert cursor.fetchall() == [(2, "b"), (3, "c")]
    cursor.execute("UPDATE API SET NAME = 'x' WHERE ID < ?", (3,))
    assert cursor.rowcount == 2
    conn.rollback()
    with pytest.raises(IntegrityError):
        cursor.executemany("INSERT INTO API VALUES (?, ?)", [(4, "d"), (1, "again")])
    conn.rollback()
    conn.client.reset()
    cursor.execute("SELECT NAME FROM API WHERE ID = ?", (1,))
    assert cursor.fetchone() == ("a",)
    cursor.execute("INSERT INTO API VALUES (9, 'left')")
    conn.close()
    with turborel.connect(uri(live)) as again:
        check = again.cursor()
        check.execute("SELECT COUNT(*) FROM API WHERE ID = 9")
        assert check.fetchone() == (0,)


def test_settings_by_name(live: Live) -> None:
    """Verifies: [DESIGN] D2 `connect` of settings by their names, a local socket."""
    with turborel.connect(host=live.socket, user="ANN") as conn:
        assert isinstance(conn.client.target, Local)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("VALUES CURRENT_USER")
        assert cursor.fetchone() == ("ANN",)
        assert not conn.in_transaction
    with pytest.raises(OperationalError) as refused:
        turborel.connect(host=live.host, port=live.port, user="ANN", password="wrong")  # noqa: S106
    assert refused.value.sqlstate == "28000"


def test_the_asyncio_interface(live: Live) -> None:
    """Verifies: [DESIGN] D2 `turborel.aio`, the asyncio interface, the same objects.

    Over TLS with a password, bound by SCRAM-PLUS, over a local socket by
    trust, and to the first of several servers kept.
    """

    async def main() -> None:
        async with await aio.connect(uri(live, "channel_binding=require")) as conn:
            assert isinstance(conn.client.target, Tls)
            cursor = conn.cursor()
            await cursor.execute("CREATE TABLE AIO (N INTEGER PRIMARY KEY)")
            await conn.commit()
            await cursor.executemany("INSERT INTO AIO VALUES (?)", [(1,), (2,)])
            await cursor.execute("SELECT N FROM AIO WHERE N > ? ORDER BY N", (0,))
            assert [row async for row in cursor] == [(1,), (2,)]
        async with await aio.connect(host=live.socket, user="ANN") as local:
            assert isinstance(local.client.target, Local)
            cursor = local.cursor()
            await cursor.execute("SELECT COUNT(*) FROM AIO")
            assert await cursor.fetchone() == (2,)
        secret = quote(live.password, safe="")
        several = f"turborel://ANN:{secret}@127.0.0.1:1,{live.host}:{live.port}/?target=read-write"
        kept = await aio.connect(several)
        await kept.close()
        with pytest.raises(OperationalError) as none:
            await aio.connect("turborel://ANN@127.0.0.1:1/?connect_timeout=5")
        assert none.value.sqlstate == "08006"
        with pytest.raises(OperationalError) as replica:
            await aio.connect(uri(live, "target=read-only"))
        assert replica.value.sqlstate == "08001"

    asyncio.run(main())
